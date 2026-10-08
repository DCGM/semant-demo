"""Annotations service (features/annotations/service.py) called directly, with in-memory fakes.

The service enforces access, validates offsets and orders the span write before the chunk
tag re-derivation; denied or invalid calls must not reach any write. Storage behavior is
covered against real Weaviate in tests/integration/test_annotations.py.
"""
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from weaviate.exceptions import WeaviateTimeoutError

from semant_demo.adapters.weaviate.chunk_tags import ChunkTag
from semant_demo.core.errors import IncompleteWriteError, InvalidRequestError, NotFoundError
from semant_demo.features.annotations import service
from semant_demo.features.annotations.offsets import InvalidSpanRange
from semant_demo.features.annotations.schemas import PatchSpan, PatchTag, PostSpan, PostTag, SpanType, TagSpan
from semant_demo.features.annotations.service import AnnotationStore
from semant_demo.features.collections.access import AuthenticationRequired
from semant_demo.schema.chunks import ChunkText
from semant_demo.schema.outcomes import StepFailure

OWNER, SHARED, OTHER = (SimpleNamespace(id=uuid4(), is_superuser=False) for _ in range(3))
COLLECTION, DOCUMENT = uuid4(), uuid4()
CHUNK_1, CHUNK_2, OUTSIDE_CHUNK = uuid4(), uuid4(), uuid4()
TAG, OTHER_TAG = uuid4(), uuid4()
SPAN_A, SPAN_B = uuid4(), uuid4()
TEXTS = {CHUNK_1: (0, "Jan Novák"), CHUNK_2: (1, " a Brno 😀")}  # 9 and 10 UTF-16 units


class FakeCollections:
    async def read_access_record(self, cid):
        return (OWNER.id, {SHARED.id}) if cid == COLLECTION else None

    async def chunk_ids_in_collection(self, ids, cid, document=None):
        return {i for i in ids if i in TEXTS} if cid == COLLECTION else set()

    async def document_in_collection(self, document_id, cid):
        return (document_id, cid) == (DOCUMENT, COLLECTION)


class Recorder:
    def __init__(self, writes: list):
        self.writes = writes
        self.fail: dict[str, Exception] = {}

    async def _write(self, name, *args):
        self.writes.append((name, *args))
        for key in ([f"{name}:{args[0]}"] if args else []) + [name]:
            if key in self.fail:
                raise self.fail[key]


class FakeTags(Recorder):
    async def read_collection_ids(self, ids):
        return {t: [COLLECTION] for t in ids if t in (TAG, OTHER_TAG)}

    async def find_same(self, cid, tag):
        return None

    async def insert(self, tag):
        await self._write("insert_tag")
        return UUID(int=1)

    async def link_to_collection(self, tag_id, cid):
        await self._write("link_collection", tag_id)

    async def delete_unlinked(self, tag_id):
        await self._write("delete_unlinked", tag_id)

    async def read(self, tag_id):
        return None

    async def update(self, tag_id, patch):
        await self._write("update_tag", tag_id)

    async def delete(self, tag_id):
        await self._write("delete_tag", tag_id)


class FakeSpans(Recorder):
    def __init__(self, writes):
        super().__init__(writes)
        self.stored = {
            SPAN_A: TagSpan(id=str(SPAN_A), chunkId=str(CHUNK_1), tagId=str(TAG), start=0, end=3,
                            type=SpanType.auto),
            # Stored with offsets that are no longer valid (before validation existed).
            SPAN_B: TagSpan(id=str(SPAN_B), chunkId=str(CHUNK_2), tagId=str(TAG), start=5, end=99,
                            type=SpanType.auto),
        }

    async def read_refs(self, ids):
        return {i: ([UUID(self.stored[i].tagId)], [UUID(self.stored[i].chunkId)]) for i in ids if i in self.stored}

    async def read(self, span_id):
        return self.stored.get(span_id)

    async def insert(self, span):
        await self._write("insert_span", span.chunkId)
        return UUID(int=2)

    async def update(self, span_id, patch):
        await self._write("update_span", span_id)
        self.stored[span_id] = self.stored[span_id].model_copy(update=patch.model_dump(exclude_none=True))

    async def delete(self, span_id):
        await self._write("delete_span", span_id)

    async def list_in_document(self, cid, document, tags, span_type):
        return {i: {ChunkTag.of(s.chunkId, s.tagId)} for i, s in self.stored.items() if s.type == span_type}


class FakeChunkTags:
    def __init__(self, writes):
        self.writes = writes
        self.failures: list[StepFailure] = []

    async def sync(self, pairs):
        self.writes.append(("sync", frozenset(pairs)))
        return list(self.failures)


class FakeDocuments:
    def __init__(self):
        self.reads = []

    async def read_chunk_text(self, chunk_id):
        self.reads.append(("anchor", chunk_id))
        order, text = TEXTS[chunk_id]
        return ChunkText(id=chunk_id, document_id=DOCUMENT, order=order, text=text)

    async def read_following_chunk_texts(self, document_id, after_order, limit):
        self.reads.append(("following", after_order))
        return [ChunkText(id=c, document_id=DOCUMENT, order=o, text=t)
                for c, (o, t) in TEXTS.items() if o > after_order][:limit]


@pytest.fixture
def writes():
    return []


@pytest.fixture
def store(writes):
    return AnnotationStore(collections=FakeCollections(), tags=FakeTags(writes), spans=FakeSpans(writes),
                           chunk_tags=FakeChunkTags(writes), documents=FakeDocuments())


def post_span(start=0, end=3, chunk=CHUNK_1, **kw):
    return PostSpan(start=start, end=end, type=SpanType.pos, chunkId=str(chunk), tagId=str(TAG), **kw)


NEW_TAG = PostTag(name="Osoba", shorthand="OS", color="#000", pictogram="p", definition="d")

WRITES = [
    lambda s, u: service.create_tag(s, u, COLLECTION, NEW_TAG),
    lambda s, u: service.update_tag(s, u, TAG, PatchTag(name="x")),
    lambda s, u: service.delete_tag(s, u, TAG),
    lambda s, u: service.create_span(s, u, post_span()),
    lambda s, u: service.update_span(s, u, SPAN_A, PatchSpan(type=SpanType.pos)),
    lambda s, u: service.bulk_update_spans(s, u, [SPAN_A, SPAN_B], PatchSpan(type=SpanType.neg)),
    lambda s, u: service.delete_span(s, u, SPAN_A),
    lambda s, u: service.delete_approved_spans_in_document(s, u, COLLECTION, DOCUMENT, [TAG]),
    lambda s, u: service.delete_suggestions_in_document(s, u, COLLECTION, DOCUMENT, [TAG]),
]
READS = [
    lambda s, u: service.get_tag(s, u, TAG),
    lambda s, u: service.list_spans(s, u, COLLECTION),
    lambda s, u: service.list_spans_by_chunks(s, u, COLLECTION, [CHUNK_1]),
]


@pytest.mark.parametrize("call", WRITES + READS)
@pytest.mark.parametrize("user, error", [(OTHER, NotFoundError), (None, AuthenticationRequired)],
                         ids=["unrelated", "anonymous"])
async def test_users_without_access_reach_no_write(call, user, error, store, writes):
    with pytest.raises(error):
        await call(store, user)
    assert writes == []


@pytest.mark.parametrize("call", WRITES)
async def test_shared_users_may_annotate_and_edit_tags(call, store, writes):
    await call(store, SHARED)
    assert writes


# ── Tag creation: insert, then link ───────────────────────────────────────

async def test_tag_whose_collection_link_fails_is_removed_and_reported(store, writes):
    store.tags.fail["link_collection"] = RuntimeError("link failed")

    with pytest.raises(IncompleteWriteError) as raised:
        await service.create_tag(store, OWNER, COLLECTION, NEW_TAG)

    assert writes == [("insert_tag",), ("link_collection", UUID(int=1)), ("delete_unlinked", UUID(int=1))]
    assert (raised.value.step, raised.value.completed, raised.value.uncertain) == ("link_collection", {}, False)
    assert "nothing was saved" in raised.value.detail


async def test_timed_out_link_is_uncertain_and_still_cleaned_up(store, writes):
    # The link may have landed; deleting the tag removes it with the tag either way.
    store.tags.fail["link_collection"] = WeaviateTimeoutError("slow")

    with pytest.raises(IncompleteWriteError) as raised:
        await service.create_tag(store, OWNER, COLLECTION, NEW_TAG)

    assert raised.value.uncertain
    assert writes[-1] == ("delete_unlinked", UUID(int=1))


async def test_failed_cleanup_reports_the_possibly_remaining_tag(store):
    store.tags.fail["link_collection"] = RuntimeError("link failed")
    store.tags.fail["delete_unlinked"] = RuntimeError("delete failed")

    with pytest.raises(IncompleteWriteError) as raised:
        await service.create_tag(store, OWNER, COLLECTION, NEW_TAG)

    assert (raised.value.step, raised.value.completed, raised.value.uncertain) == (
        "delete_unlinked_tag", {"insert_tag": 1}, False)
    assert "link_collection failed" in raised.value.detail
    assert str(UUID(int=1)) in raised.value.detail and "may remain" in raised.value.detail


async def test_timed_out_cleanup_makes_the_failure_uncertain(store):
    # The link failed outright; the deletion timed out and may or may not have happened.
    store.tags.fail["link_collection"] = RuntimeError("link failed")
    store.tags.fail["delete_unlinked"] = WeaviateTimeoutError("slow")

    with pytest.raises(IncompleteWriteError) as raised:
        await service.create_tag(store, OWNER, COLLECTION, NEW_TAG)

    assert (raised.value.step, raised.value.uncertain) == ("delete_unlinked_tag", True)


# ── Span creation ─────────────────────────────────────────────────────────

async def test_span_write_precedes_its_chunk_tag_sync(store, writes):
    result = await service.create_span(store, OWNER, post_span())

    assert writes == [("insert_span", str(CHUNK_1)), ("sync", frozenset({ChunkTag(CHUNK_1, TAG)}))]
    assert (result.outcome, result.succeeded, result.id) == ("complete", [str(UUID(int=2))], str(UUID(int=2)))


async def test_failed_chunk_tag_sync_keeps_the_span_and_is_partial(store):
    store.chunk_tags.failures = [StepFailure(item_id="c:t", step="update_chunk_tags", message="x")]

    result = await service.create_span(store, OWNER, post_span())

    assert result.outcome == "partial" and result.failed[0].step == "update_chunk_tags"


async def test_chunk_tags_are_synced_also_when_the_span_write_raises(store, writes):
    store.spans.fail["insert_span"] = WeaviateTimeoutError("slow")  # may have been stored

    with pytest.raises(WeaviateTimeoutError):
        await service.create_span(store, OWNER, post_span())

    assert writes[-1] == ("sync", frozenset({ChunkTag(CHUNK_1, TAG)}))


async def test_cross_chunk_span_reads_the_following_chunks(store, writes):
    await service.create_span(store, OWNER, post_span(start=4, end=15))  # "Novák" + " a Brno"

    assert store.documents.reads == [("anchor", CHUNK_1), ("following", 0)]
    assert writes[0] == ("insert_span", str(CHUNK_1))


async def test_span_inside_its_chunk_reads_no_following_chunk(store):
    await service.create_span(store, OWNER, post_span(start=4, end=9))

    assert store.documents.reads == [("anchor", CHUNK_1)]


@pytest.mark.parametrize("start, end, code", [
    (-1, 3, "negative_start"), (3, 3, "empty"), (9, 12, "start_outside_anchor"),
    (0, 20, "past_end"),  # 9 + 10 units in the document
])
async def test_invalid_offsets_are_rejected_before_any_write(start, end, code, store, writes):
    with pytest.raises(InvalidSpanRange) as raised:
        await service.create_span(store, OWNER, post_span(start=start, end=end))

    assert raised.value.code == code
    assert writes == []


async def test_offsets_count_utf16_units(store):
    # " a Brno 😀" is 9 code points but 10 UTF-16 units, as the browser measures it.
    await service.create_span(store, OWNER, post_span(start=8, end=10, chunk=CHUNK_2))


async def test_span_on_a_chunk_outside_the_collection_is_not_found(store, writes):
    with pytest.raises(NotFoundError):
        await service.create_span(store, OWNER, post_span(chunk=OUTSIDE_CHUNK))
    assert writes == []


# ── Span updates ──────────────────────────────────────────────────────────

async def test_empty_patch_is_rejected(store, writes):
    with pytest.raises(InvalidRequestError):
        await service.update_span(store, OWNER, SPAN_A, PatchSpan())
    assert writes == []


async def test_approving_a_span_with_old_invalid_offsets_works(store):
    # Offsets are validated only when they change.
    result = await service.update_span(store, OWNER, SPAN_B, PatchSpan(type=SpanType.pos))

    assert result.type == SpanType.pos and result.end == 99


async def test_invalid_offset_patch_writes_nothing(store, writes):
    with pytest.raises(InvalidSpanRange):
        await service.update_span(store, OWNER, SPAN_A, PatchSpan(end=50))
    assert writes == []


async def test_tag_change_syncs_the_old_and_the_new_pair(store, writes):
    await service.update_span(store, OWNER, SPAN_A, PatchSpan(tagId=str(OTHER_TAG)))

    assert writes[-1] == ("sync", frozenset({ChunkTag(CHUNK_1, TAG), ChunkTag(CHUNK_1, OTHER_TAG)}))


async def test_bulk_update_keeps_completed_updates_and_reports_failed_ones(store, writes):
    store.spans.fail[f"update_span:{SPAN_B}"] = RuntimeError("boom")

    result = await service.bulk_update_spans(store, OWNER, [SPAN_A, SPAN_B], PatchSpan(type=SpanType.pos))

    assert result.outcome == "partial"
    assert result.succeeded == [str(SPAN_A)] == [s.id for s in result.spans]
    assert [(f.item_id, f.step) for f in result.failed] == [(str(SPAN_B), "update_span")]
    # One sync for every touched pair, after all updates, also for the failed span's pair.
    assert writes[-1] == ("sync", frozenset({ChunkTag(CHUNK_1, TAG), ChunkTag(CHUNK_2, TAG)}))
    assert [w[0] for w in writes].count("sync") == 1


async def test_bulk_offset_patch_is_validated_for_every_span_before_writing(store, writes):
    # Valid for SPAN_A (chunk 1, 9 units + 10 following), past the end for SPAN_B (chunk 2).
    with pytest.raises(InvalidSpanRange):
        await service.bulk_update_spans(store, OWNER, [SPAN_A, SPAN_B], PatchSpan(end=12))
    assert writes == []


# ── Deletion ──────────────────────────────────────────────────────────────

async def test_scoped_delete_keeps_going_after_a_failed_span(store, writes):
    store.spans.fail[f"delete_span:{SPAN_A}"] = RuntimeError("boom")

    result = await service.delete_suggestions_in_document(store, OWNER, COLLECTION, DOCUMENT, [TAG])

    assert result.outcome == "partial"
    assert result.succeeded == [str(SPAN_B)]
    assert [(f.item_id, f.step) for f in result.failed] == [(str(SPAN_A), "delete_span")]
    assert writes[-1] == ("sync", frozenset({ChunkTag(CHUNK_1, TAG), ChunkTag(CHUNK_2, TAG)}))


async def test_scoped_delete_with_a_document_outside_the_collection_is_not_found(store, writes):
    with pytest.raises(NotFoundError):
        await service.delete_approved_spans_in_document(store, OWNER, COLLECTION, uuid4(), [TAG])
    assert writes == []
