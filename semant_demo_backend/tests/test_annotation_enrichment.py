"""Annotation enrichment in the Annotations service (#328), with in-memory fakes.

Creates and boundary edits store the derived text, context and positions with the span
and then its contextual vector; type/tag edits never call the embedder; a failed or late
embedding never leaves a vector that counts as current for a newer revision; reads hide
derived data of another revision; the backfill writes only derived data. Storage behavior
against real Weaviate: tests/integration/test_annotation_enrichment.py.
"""
import asyncio
import weakref
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from tests.chunk_fakes import in_range, positioned

from semant_demo.core.errors import InvalidRequestError
from semant_demo.core.outcomes import WriteOutcome
from semant_demo.features.annotations import backfill, service
from semant_demo.features.annotations.derivation import DERIVATION_VERSION
from semant_demo.features.annotations.enrichment import (
    AnnotationVector, AnnotationVectorSettings, Enrichment, text_current, vector_current,
)
from semant_demo.features.annotations.schemas import (
    AnnotationChunk, AnnotationRow, PatchSpan, PostSpan, SpanType, TagSpan,
)
from semant_demo.features.annotations.service import AnnotationStore
from semant_demo.features.documents.schemas import Document
from semant_demo.features.user_collections.access import AuthenticationRequired, ResourceNotFound

OWNER, OTHER = (SimpleNamespace(id=uuid4(), is_superuser=False) for _ in range(2))
COLLECTION, DOCUMENT, TAG, OTHER_TAG = uuid4(), uuid4(), uuid4(), uuid4()
CHUNK_1, CHUNK_2 = uuid4(), uuid4()
TEXTS = [(CHUNK_1, 0, "Roku 1848 přijel hejtman Jan Novák"), (CHUNK_2, 1, " a ubytoval se v Brně.")]
CONFIG_ID = "fake-context-v1"


class FakeCollections:
    async def read_access_record(self, cid):
        return (OWNER.id, set()) if cid == COLLECTION else None

    async def chunk_ids_in_collection(self, ids, cid, document=None):
        return {i for i in ids if i in {c for c, _, _ in TEXTS}} if cid == COLLECTION else set()


class FakeTags:
    async def read_collection_ids(self, ids):
        return {t: [COLLECTION] for t in ids if t in (TAG, OTHER_TAG)}


class FakeChunkTags:
    async def sync(self, cid, pairs):
        return []


class FakeDocuments:
    """``reads`` counts the reads of chunks around a span (ranges of orders)."""

    def __init__(self):
        self.reads = 0
        self.fail = False
        self.chunks = positioned([AnnotationChunk(id=c, document_id=DOCUMENT, order=o, text=t) for c, o, t in TEXTS])

    async def read_chunk_text(self, chunk_id):
        return next((c for c in self.chunks if c.id == chunk_id), None)

    async def read_chunk_texts_in_range(self, document_id, first, last):
        self.reads += 1
        if self.fail:
            raise ConnectionError("chunk read failed")
        return in_range(self.chunks, document_id, first, last)

    async def read_many(self, ids):
        return {DOCUMENT: Document(id=DOCUMENT, title="Kronika", yearIssued=1850)} if DOCUMENT in ids else {}


class FakeSpans:
    """Spans of one tenant as stored property dicts, with the named vectors."""

    def __init__(self):
        self.objects: dict[UUID, dict] = {}
        self.vectors: dict[UUID, dict] = {}
        self.derived_writes: list[tuple[UUID, dict]] = []
        self._locks = weakref.WeakValueDictionary()
        self.provenance = False

    def lock(self, span_id):
        lock = self._locks.get(span_id)
        if lock is None:
            lock = self._locks[span_id] = asyncio.Lock()
        return lock

    def _span(self, sid):
        p = self.objects[sid]
        return TagSpan(id=str(sid), chunkId=str(p["chunkId"]), tagId=str(p["tagId"]), start=p["start"], end=p["end"],
                       type=SpanType(p["type"]))

    def _row(self, sid):
        return AnnotationRow(id=sid, **self.objects[sid])

    async def insert(self, cid, span, document_id, derived=None, provenance=None):
        sid = uuid4()
        self.objects[sid] = {"start": span.start, "end": span.end, "type": span.type.value, "tagId": UUID(span.tagId),
                             "chunkId": UUID(span.chunkId), "documentId": document_id, **(derived or {})}
        return sid

    async def update(self, cid, sid, patch, derived=None, provenance=None):
        fields = patch.model_dump(exclude_none=True)
        props = {k: fields[k] for k in ("start", "end") if k in fields} | (derived or {})
        if patch.type is not None:
            props["type"] = patch.type.value
        if patch.tagId is not None:
            props["tagId"] = UUID(patch.tagId)
        if patch.chunkId is not None:
            props["chunkId"] = UUID(patch.chunkId)
        self.objects[sid] |= props

    async def replace_anchor_reference(self, cid, sid, chunk_id):
        pass

    async def read(self, cid, sid):
        return self._span(sid) if sid in self.objects else None

    async def read_many(self, cid, ids):
        return {i: self._span(i) for i in ids if i in self.objects} if cid == COLLECTION else {}

    async def read_row(self, cid, sid):
        return self._row(sid) if sid in self.objects else None

    async def write_derived(self, cid, sid, derived, vector=None):
        self.derived_writes.append((sid, derived))
        self.objects[sid] |= derived
        if vector is not None:
            self.vectors.setdefault(sid, {})[vector[0]] = vector[1]

    async def read_rows(self, cid, *, tag_ids=None, document_id=None, limit=100, offset=0):
        return [self._row(s) for s in self.objects][offset:offset + limit]

    async def near_vector(self, cid, target_vector, vector, config_id, limit, tag_ids=None):
        return [self._row(s).model_copy(update={"distance": 0.1}) for s, p in self.objects.items()
                if p.get("vectorStatus") == "ready" and p.get("vectorConfig") == config_id][:limit]

    async def iterate_rows(self, cid):
        for sid in list(self.objects):
            yield self._row(sid)


class FakeEmbedder:
    def __init__(self):
        self.documents: list[str] = []
        self.queries: list[str] = []
        self.fail = False
        self.gate: asyncio.Event | None = None

    async def embed_document(self, text):
        self.documents.append(text)
        if self.gate is not None:
            await self.gate.wait()
        if self.fail:
            raise TimeoutError("embedding service timed out")
        return [float(len(text)), 1.0]

    async def embed_query(self, text):
        self.queries.append(text)
        return [1.0, 0.0]


@pytest.fixture
def embedder():
    return FakeEmbedder()


@pytest.fixture
def store(embedder):
    vector = AnnotationVector(AnnotationVectorSettings.model_validate(
        {"id": CONFIG_ID, "embedding": {"provider": "embedding_service"}}), embedder)
    return AnnotationStore(collections=FakeCollections(), tags=FakeTags(), spans=FakeSpans(),
                           chunk_tags=FakeChunkTags(), documents=FakeDocuments(),
                           enrichment=Enrichment(derived=True, vector=vector))


def post(start, end, chunk=CHUNK_1, tag=TAG):
    return PostSpan(chunkId=str(chunk), tagId=str(tag), start=start, end=end, type=SpanType.pos)


async def create(store, start=25, end=34):
    result = await service.create_span(store, OWNER, post(start, end))
    return UUID(result.id), result


# ── Create and edits ──────────────────────────────────────────────────────

async def test_create_stores_derived_fields_and_a_vector_of_revision_1(store, embedder):
    sid, result = await create(store)  # "Jan Novák"

    assert result.outcome == WriteOutcome.complete
    row = await store.spans.read_row(COLLECTION, sid)
    assert (row.revision, row.text, row.documentStartChar, row.documentStartWord) == (1, "Jan Novák", 25, 4)
    assert row.leftContext == "Roku 1848 přijel hejtman "
    assert row.rightContext == " a ubytoval se v Brně."  # continues into the next chunk
    assert text_current(row) and vector_current(row, CONFIG_ID)
    assert embedder.documents == ["Roku 1848 přijel hejtman <<<Jan Novák>>> a ubytoval se v Brně."]
    assert store.spans.vectors[sid]["contextual"]


async def test_cross_chunk_span_text_is_the_canonical_text(store):
    sid, _ = await create(store, 29, 36)  # "Novák" + " a"

    row = await store.spans.read_row(COLLECTION, sid)
    assert (row.text, row.documentEndChar, row.documentEndWord) == ("Novák a", 36, 7)


@pytest.mark.parametrize("patch", [PatchSpan(type=SpanType.neg), PatchSpan(tagId=str(OTHER_TAG))],
                         ids=["status", "tag"])
async def test_type_and_tag_edits_keep_the_revision_and_call_no_embedder(store, embedder, patch):
    sid, _ = await create(store)
    embedder.documents.clear()
    reads = store.documents.reads

    result = await service.update_span(store, OWNER, COLLECTION, sid, patch)

    assert result.outcome == WriteOutcome.complete
    row = await store.spans.read_row(COLLECTION, sid)
    assert row.revision == 1 and text_current(row) and vector_current(row, CONFIG_ID)
    assert embedder.documents == [] and store.documents.reads == reads


async def test_boundary_edit_is_a_new_revision_with_new_text_and_vector(store, embedder):
    sid, _ = await create(store)

    result = await service.update_span(store, OWNER, COLLECTION, sid, PatchSpan(start=29))

    assert result.outcome == WriteOutcome.complete
    row = await store.spans.read_row(COLLECTION, sid)
    assert (row.revision, row.text, row.vectorRevision) == (2, "Novák", 2)
    assert vector_current(row, CONFIG_ID)
    assert len(embedder.documents) == 2


async def test_moving_a_span_to_the_next_chunk_is_a_new_revision_derived_there(store, embedder):
    sid, _ = await create(store)  # "Jan Novák", chunk 1

    # " a ubytoval": its start moved into chunk 2 (#436).
    result = await service.update_span(store, OWNER, COLLECTION, sid, PatchSpan(chunkId=str(CHUNK_2), start=0, end=11))

    assert (result.outcome, result.id, result.chunkId) == (WriteOutcome.complete, str(sid), str(CHUNK_2))
    row = await store.spans.read_row(COLLECTION, sid)
    assert (row.chunkId, row.revision, row.text, row.documentStartChar) == (CHUNK_2, 2, " a ubytoval", 34)
    assert vector_current(row, CONFIG_ID)
    assert len(embedder.documents) == 2


async def test_saving_the_same_offsets_again_changes_nothing_when_current(store, embedder):
    sid, _ = await create(store)

    await service.update_span(store, OWNER, COLLECTION, sid, PatchSpan(start=25, end=34))

    assert (await store.spans.read_row(COLLECTION, sid)).revision == 1
    assert len(embedder.documents) == 1


async def older_policy(store):
    """A span whose text, context and vector were derived under an older derivation policy."""
    sid, _ = await create(store)
    store.spans.objects[sid] |= {"derivationVersion": DERIVATION_VERSION - 1, "leftContext": "old policy "}
    return sid


async def test_derived_data_of_an_older_policy_is_not_current_and_not_returned(store, embedder):
    sid = await older_policy(store)

    row = await store.spans.read_row(COLLECTION, sid)
    assert not text_current(row) and not vector_current(row, CONFIG_ID)
    [listed] = await service.list_annotation_rows(store, OWNER, COLLECTION)
    assert listed.text is None and listed.leftContext is None
    assert await service.similar_annotations(store, OWNER, COLLECTION, "hejtman") == []


async def test_saving_again_rederives_an_older_policy_and_reembeds(store, embedder):
    sid = await older_policy(store)

    await service.update_span(store, OWNER, COLLECTION, sid, PatchSpan(start=25, end=34))

    row = await store.spans.read_row(COLLECTION, sid)
    assert (row.revision, row.derivationVersion, row.leftContext) == (1, DERIVATION_VERSION, "Roku 1848 přijel hejtman ")
    assert text_current(row) and vector_current(row, CONFIG_ID) and len(embedder.documents) == 2


async def test_provider_failure_keeps_the_edit_and_marks_the_vector_failed(store, embedder):
    sid, _ = await create(store)
    embedder.fail = True

    result = await service.update_span(store, OWNER, COLLECTION, sid, PatchSpan(start=29))

    assert result.outcome == WriteOutcome.partial
    assert [f.step for f in result.failed] == ["embed_annotation"]
    row = await store.spans.read_row(COLLECTION, sid)
    assert (row.start, row.revision, row.text) == (29, 2, "Novák")  # the edit and its text are kept
    assert row.vectorStatus == "failed" and not vector_current(row, CONFIG_ID)
    # The old vector (revision 1) is still stored but does not count.
    assert row.vectorRevision == 2


async def test_saving_again_retries_a_failed_vector_without_a_new_revision(store, embedder):
    sid, _ = await create(store)
    embedder.fail = True
    await service.update_span(store, OWNER, COLLECTION, sid, PatchSpan(start=29))
    embedder.fail = False

    result = await service.update_span(store, OWNER, COLLECTION, sid, PatchSpan(start=29))

    assert result.outcome == WriteOutcome.complete
    row = await store.spans.read_row(COLLECTION, sid)
    assert row.revision == 2 and vector_current(row, CONFIG_ID)


async def test_source_read_failure_keeps_the_edit_with_failed_text(store, embedder):
    sid, _ = await create(store)
    store.documents.fail = True

    result = await service.update_span(store, OWNER, COLLECTION, sid, PatchSpan(start=29))

    assert [f.step for f in result.failed] == ["derive_annotation"]
    row = await store.spans.read_row(COLLECTION, sid)
    assert (row.start, row.revision, row.enrichmentStatus) == (29, 2, "failed")
    assert not text_current(row) and not vector_current(row, CONFIG_ID)
    # Revision 1's text is not left to be searched or sorted by (#329).
    assert (row.text, row.leftContext, row.rightContext) == ("", "", "")
    assert len(embedder.documents) == 1  # nothing to embed


async def test_a_late_embedding_cannot_overwrite_a_newer_boundary_edit(store, embedder):
    sid, _ = await create(store)
    gate = embedder.gate = asyncio.Event()
    first = asyncio.create_task(service.update_span(store, OWNER, COLLECTION, sid, PatchSpan(start=29)))
    for _ in range(100):  # until revision 2 is being embedded
        if len(embedder.documents) == 2 or first.done():
            break
        await asyncio.sleep(0)
    assert len(embedder.documents) == 2 and not first.done()
    embedder.gate = None
    await service.update_span(store, OWNER, COLLECTION, sid, PatchSpan(start=25, end=28))  # revision 3: "Jan"
    gate.set()
    await asyncio.wait_for(first, 5)  # the embedding of revision 2 arrives last

    row = await store.spans.read_row(COLLECTION, sid)
    assert (row.revision, row.text, row.vectorRevision) == (3, "Jan", 3)
    assert vector_current(row, CONFIG_ID)
    assert store.spans.vectors[sid]["contextual"][0] == len(embedder.documents[2])


async def test_denied_writes_derive_and_embed_nothing(store, embedder):
    with pytest.raises(ResourceNotFound):
        await service.create_span(store, OTHER, post(25, 34))
    with pytest.raises(AuthenticationRequired):
        await service.create_span(store, None, post(25, 34))

    assert store.documents.reads == 0 and embedder.documents == [] and store.spans.objects == {}


async def test_without_the_derived_schema_nothing_derived_is_written(store, embedder):
    store.enrichment = Enrichment.disabled()

    sid, result = await create(store)

    assert result.outcome == WriteOutcome.complete
    assert "revision" not in store.spans.objects[sid] and embedder.documents == []


# ── Reads ─────────────────────────────────────────────────────────────────

async def test_rows_hide_derived_fields_of_another_revision_and_join_the_document(store, embedder):
    current, _ = await create(store)
    stale, _ = await create(store, 0, 4)
    store.spans.objects[stale]["revision"] = 2  # edited elsewhere; derived data still of revision 1

    rows = {r.id: r for r in await service.list_annotation_rows(store, OWNER, COLLECTION)}

    assert rows[current].text == "Jan Novák" and rows[current].documentTitle == "Kronika"
    assert rows[current].documentYear == 1850
    assert rows[stale].text is None and rows[stale].documentStartWord is None
    assert store.documents.reads == 2  # the two creates; reading rows reads no chunks


async def test_semantic_search_leaves_out_stale_vectors(store, embedder):
    current, _ = await create(store)
    stale, _ = await create(store, 0, 4)
    store.spans.objects[stale]["revision"] = 2

    rows = await service.similar_annotations(store, OWNER, COLLECTION, "hejtman")

    assert [r.id for r in rows] == [current] and embedder.queries == ["hejtman"]


async def test_reads_are_authorized_before_embedding_the_query(store, embedder):
    with pytest.raises(ResourceNotFound):
        await service.similar_annotations(store, OTHER, COLLECTION, "hejtman")
    with pytest.raises(ResourceNotFound):
        await service.list_annotation_rows(store, OTHER, COLLECTION)
    assert embedder.queries == []


async def test_semantic_search_needs_a_configured_vector(store):
    store.enrichment = Enrichment(derived=True)
    with pytest.raises(InvalidRequestError):
        await service.similar_annotations(store, OWNER, COLLECTION, "hejtman")


# ── Backfill ──────────────────────────────────────────────────────────────

def legacy(store, start, end, chunk=CHUNK_1):
    """A span saved before #328: no revision, no derived fields."""
    sid = uuid4()
    store.spans.objects[sid] = {"start": start, "end": end, "type": "pos", "tagId": TAG, "chunkId": chunk,
                                "documentId": DOCUMENT}
    return sid


async def test_backfill_derives_legacy_spans_and_preserves_their_fields(store, embedder):
    a, b = legacy(store, 25, 34), legacy(store, 0, 4)
    invalid = legacy(store, 30, 999)
    before = {s: dict(store.spans.objects[s]) for s in (a, b, invalid)}

    [report] = await backfill.status(store, [COLLECTION])
    assert report.as_dict() == {"collection_id": str(COLLECTION), "spans": 3, "text": {"missing": 3},
                                "vector": {"pending": 3}, "incomplete": 3}

    result = await backfill.backfill(store, [COLLECTION], limit=10)

    assert (result.processed, result.text_written, result.vector_written, result.failed) == (3, 2, 2, [])
    assert store.documents.reads == 1  # one read for the document's spans
    for sid in (a, b, invalid):
        for key, value in before[sid].items():
            assert store.spans.objects[sid][key] == value
        assert "revision" not in store.spans.objects[sid]
    assert (await store.spans.read_row(COLLECTION, a)).text == "Jan Novák"
    [report] = await backfill.status(store, [COLLECTION])
    assert report.text == {"current": 2, "invalid": 1} and report.incomplete == 0


async def test_backfill_is_bounded_and_reports_the_remaining_spans(store):
    for start in (0, 5, 10):
        legacy(store, start, start + 4)

    result = await backfill.backfill(store, [COLLECTION], limit=2)

    assert (result.processed, result.not_processed, result.remaining_incomplete) == (2, 1, 1)
    [report] = await backfill.status(store, [COLLECTION])
    assert report.incomplete == 1


async def test_backfill_counts_failed_embeddings_as_remaining_incomplete(store, embedder):
    legacy(store, 25, 34)
    embedder.fail = True

    result = await backfill.backfill(store, [COLLECTION], limit=10)

    assert (result.text_written, result.not_processed, result.remaining_incomplete) == (1, 0, 1)
    assert [f.step for f in result.failed] == ["embed_annotation"]


async def test_backfill_rederives_an_older_policy_and_replaces_its_vector(store, embedder):
    sid = await older_policy(store)
    [report] = await backfill.status(store, [COLLECTION])
    assert (report.text, report.vector, report.incomplete) == ({"outdated": 1}, {"stale": 1}, 1)

    result = await backfill.backfill(store, [COLLECTION], limit=10)

    assert (result.text_written, result.vector_written, result.remaining_incomplete) == (1, 1, 0)
    row = await store.spans.read_row(COLLECTION, sid)
    assert row.derivationVersion == DERIVATION_VERSION and vector_current(row, CONFIG_ID)
    assert embedder.documents[-1] == "Roku 1848 přijel hejtman <<<Jan Novák>>> a ubytoval se v Brně."


async def test_backfill_replaces_vectors_of_another_configuration_from_the_stored_text(store, embedder):
    sid, _ = await create(store)
    store.spans.objects[sid]["vectorConfig"] = "older-model-v0"
    reads = store.documents.reads

    result = await backfill.backfill(store, [COLLECTION], limit=10)

    assert (result.text_written, result.vector_written) == (0, 1)
    assert store.documents.reads == reads
    assert vector_current(await store.spans.read_row(COLLECTION, sid), CONFIG_ID)


async def test_backfill_keeps_the_newer_derivation_of_a_span_edited_meanwhile(store):
    sid = legacy(store, 25, 34)
    rows = [r async for r in store.spans.iterate_rows(COLLECTION)]

    async def edited_meanwhile(cid):
        for row in rows:
            yield row
        store.spans.objects[sid] |= {"start": 29, "revision": 1}

    store.spans.iterate_rows = edited_meanwhile

    result = await backfill.backfill(store, [COLLECTION], limit=10)

    assert (result.superseded, result.text_written) == (1, 0)
    assert "text" not in store.spans.objects[sid]


async def test_backfill_without_vectors_calls_no_embedder(store, embedder):
    legacy(store, 25, 34)

    result = await backfill.backfill(store, [COLLECTION], limit=10, vectors=False)

    assert (result.text_written, result.vector_written) == (1, 0) and embedder.documents == []
    assert (result.not_processed, result.remaining_incomplete) == (0, 1)  # the vector is still to embed


async def test_backfill_without_vectors_marks_the_vector_of_an_older_policy_pending(store, embedder):
    sid = await older_policy(store)

    result = await backfill.backfill(store, [COLLECTION], limit=10, vectors=False)

    row = await store.spans.read_row(COLLECTION, sid)
    assert text_current(row) and row.vectorStatus == "pending" and not vector_current(row, CONFIG_ID)
    assert result.remaining_incomplete == 1
    assert await service.similar_annotations(store, OWNER, COLLECTION, "hejtman") == []


# ── Configuration ─────────────────────────────────────────────────────────

def test_the_default_vector_configuration_loads_and_an_empty_one_configures_none(tmp_path):
    from pydantic import ValidationError

    from semant_demo.bootstrap import load_annotation_vector
    from semant_demo.config import SCRIPT_PATH, Config

    default = load_annotation_vector(Config(environ={}))
    assert (default.id, default.target_vector) == ("qwen3-embedding-0.6b-context-v1", "contextual")
    gemma = load_annotation_vector(Config(environ={
        "ANNOTATION_VECTOR_CONFIG": str(SCRIPT_PATH / "configs" / "annotation_vector_gemma.yaml")}))
    assert (gemma.id, gemma.target_vector) == ("bge-gemma2-context-v1", "contextual")
    assert load_annotation_vector(Config(environ={"ANNOTATION_VECTOR_CONFIG": ""})) is None

    invalid = tmp_path / "vector.yaml"
    invalid.write_text("id: x\ntarget_vector: has-dash\nembedding: {provider: embedding_service}\n")
    with pytest.raises(ValidationError):
        load_annotation_vector(Config(environ={"ANNOTATION_VECTOR_CONFIG": str(invalid)}))
