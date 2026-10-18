"""Annotation derived data against real Weaviate (#328).

Span writes through the API store the canonical text, context and positions; the
contextual vector is written for the span's revision and kept by later patches that do not
change offsets; semantic search leaves out vectors that are not current; rows are read
from the annotations alone. An annotation collection created before #328 gets the derived
properties and the named vector added (``add_enrichment_schema``) without changing its
spans, and the backfill derives them. Embeddings are deterministic (``fake_embedding``).
"""
from types import SimpleNamespace
from uuid import UUID

import pytest
from weaviate.classes.config import Configure, DataType, Property, ReferenceProperty, Tokenization

from semant_demo.adapters.weaviate.chunk_tags import ChunkTagRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.adapters.weaviate.spans import SpanRepository, add_enrichment_schema, enrichment_schema
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.bootstrap import detect_enrichment
from semant_demo.features.annotations import backfill, service
from semant_demo.features.annotations.enrichment import (
    AnnotationVector, AnnotationVectorSettings, Enrichment, text_current, vector_current,
)
from semant_demo.features.annotations.schemas import PatchSpan, PostSpan, SpanType
from semant_demo.features.annotations.service import AnnotationStore
from tests.fakes import fake_embedding

pytestmark = pytest.mark.integration

CONFIG_ID = "fake-context-v1"


class Embedder:
    def __init__(self):
        self.calls = 0
        self.fail = False

    async def embed_document(self, text):
        self.calls += 1
        if self.fail:
            raise TimeoutError("embedding service timed out")
        return fake_embedding(text)

    async def embed_query(self, text):
        return fake_embedding(text)


@pytest.fixture
def embedder():
    return Embedder()


def make_store(client, names, embedder, vector_name="contextual") -> AnnotationStore:
    spans = SpanRepository(client, names)
    vector = AnnotationVector(AnnotationVectorSettings.model_validate(
        {"id": CONFIG_ID, "target_vector": vector_name, "embedding": {"provider": "embedding_service"}}), embedder)
    return AnnotationStore(collections=UserCollectionRepository(client, names, spans),
                           tags=TagRepository(client, names, spans), spans=spans,
                           chunk_tags=ChunkTagRepository(client, names, spans),
                           documents=DocumentRepository(client, names), enrichment=Enrichment(True, vector))


@pytest.fixture
def store(seeded_store, collection_names, embedder):
    return make_store(seeded_store, collection_names, embedder)


@pytest.fixture
def owner(ids):
    return SimpleNamespace(id=UUID(ids.user["owner"]), is_superuser=False)


def post(ids, chunk, start, end, tag="person"):
    return PostSpan(chunkId=ids.chunk[chunk], tagId=ids.tag[tag], start=start, end=end, type=SpanType.pos)


# ── Through the API (no vector configured) ────────────────────────────────

async def test_api_writes_store_canonical_text_and_positions_per_revision(api_client, login, ids, corpus, spans):
    owner = await login("owner")
    first, second = corpus.chunks["chronicle_1"]["text"], corpus.chunks["chronicle_2"]["text"]
    collection = UUID(ids.col["chronicles"])

    created = await api_client.post("/api/tag_spans", headers=owner, json={
        "chunkId": ids.chunk["chronicle_1"], "tagId": ids.tag["person"], "start": 80, "end": len(first) + 8,
        "type": "pos"})
    assert created.status_code == 200 and created.json()["outcome"] == "complete"
    sid = UUID(created.json()["id"])

    row = await spans.read_row(collection, sid)
    assert (row.revision, row.text) == (1, first[80:] + second[:8])
    assert (row.positionSegment, row.documentStartChar, row.documentEndChar) == (0, 80, len(first) + 8)
    assert row.rightContext.startswith(second[8:20]) and first[60:80] in row.leftContext
    assert row.vectorStatus == "pending" and text_current(row)

    approved = await api_client.patch(f"/api/tag_spans/{sid}", headers=owner,
                                      params={"collection_id": str(collection)}, json={"type": "neg"})
    assert approved.status_code == 200
    assert (await spans.read_row(collection, sid)).revision == 1

    moved = await api_client.patch(f"/api/tag_spans/{sid}", headers=owner,
                                   params={"collection_id": str(collection)}, json={"start": 34, "end": 43})
    assert moved.status_code == 200 and moved.json()["outcome"] == "complete"
    row = await spans.read_row(collection, sid)
    assert (row.revision, row.text, row.documentStartWord, row.documentEndWord) == (2, "Jan Novák", 6, 8)


async def test_positions_continue_through_a_chunk_outside_the_collection(store, owner, ids, corpus):
    # chronicle_3 (order 2) belongs to "newspapers"; its text still counts in the document.
    lengths = sum(len(corpus.chunks[c]["text"]) for c in ("chronicle_1", "chronicle_2"))
    created = await service.create_span(store, owner, post(ids, "chronicle_3", 0, 5, tag="event"))

    row = await store.spans.read_row(UUID(ids.col["newspapers"]), UUID(created.id))
    assert (row.text, row.positionSegment, row.documentStartChar) == ("Požár", 0, lengths)


# ── Contextual vector ─────────────────────────────────────────────────────

async def test_vector_is_current_after_create_and_kept_by_a_type_change(store, owner, ids, embedder):
    collection = UUID(ids.col["chronicles"])
    created = await service.create_span(store, owner, post(ids, "chronicle_1", 34, 43))
    sid = UUID(created.id)
    assert created.outcome == "complete" and embedder.calls == 1

    await service.update_span(store, owner, collection, sid, PatchSpan(type=SpanType.neg))

    assert embedder.calls == 1
    row = await store.spans.read_row(collection, sid)
    assert vector_current(row, CONFIG_ID)
    found = await service.similar_annotations(store, owner, collection, "Jan Novák")
    assert sid in [r.id for r in found] and all(r.distance is not None for r in found)
    # The patch did not drop the stored vector.
    obj = await store.spans._tenant(collection).query.fetch_object_by_id(sid, include_vector=True)
    assert obj.vector["contextual"] == pytest.approx(fake_embedding(store.enrichment.vector.input_of(
        SimpleNamespace(left_context=row.leftContext, text=row.text, right_context=row.rightContext))))


async def test_a_vector_of_an_older_revision_is_never_returned(store, owner, ids, embedder):
    collection = UUID(ids.col["chronicles"])
    sid = UUID((await service.create_span(store, owner, post(ids, "chronicle_1", 34, 43))).id)
    embedder.fail = True

    moved = await service.update_span(store, owner, collection, sid, PatchSpan(start=38))

    assert moved.outcome == "partial" and [f.step for f in moved.failed] == ["embed_annotation"]
    row = await store.spans.read_row(collection, sid)
    assert (row.start, row.revision, row.text, row.vectorStatus) == (38, 2, "Novák", "failed")
    assert sid not in [r.id for r in await service.similar_annotations(store, owner, collection, "Jan Novák")]

    embedder.fail = False
    retried = await service.update_span(store, owner, collection, sid, PatchSpan(start=38))
    assert retried.outcome == "complete"
    assert sid in [r.id for r in await service.similar_annotations(store, owner, collection, "Novák")]


async def test_rows_are_read_from_annotations_with_their_document(store, owner, ids, corpus):
    collection = UUID(ids.col["chronicles"])
    sid = UUID((await service.create_span(store, owner, post(ids, "chronicle_1", 34, 43))).id)

    rows = {r.id: r for r in await service.list_annotation_rows(
        store, owner, collection, tag_ids=[ids.tag["person"]], document_id=ids.doc["chronicle"])}

    assert rows[sid].text == "Jan Novák"
    assert rows[sid].documentTitle == corpus.documents["chronicle"]["properties"]["title"]
    # Seeded spans predate #328: listed, without derived data until the backfill.
    seeded = UUID(ids.span["novak_manual"])
    assert seeded in rows and rows[seeded].text is None


# ── Existing collections: schema and backfill ─────────────────────────────

async def _create_pre_328_collection(client, names, chunks_collection):
    await client.collections.create(
        names.annotation_collection_name,
        multi_tenancy_config=Configure.multi_tenancy(enabled=True, auto_tenant_creation=False,
                                                     auto_tenant_activation=True),
        vector_config=Configure.Vectors.self_provided(name="default", vector_index_config=Configure.VectorIndex.flat()),
        properties=[
            Property(name="tagId", data_type=DataType.UUID), Property(name="chunkId", data_type=DataType.UUID),
            Property(name="documentId", data_type=DataType.UUID), Property(name="start", data_type=DataType.INT),
            Property(name="end", data_type=DataType.INT),
            Property(name="type", data_type=DataType.TEXT, tokenization=Tokenization.FIELD, index_searchable=False),
            Property(name="reason", data_type=DataType.TEXT), Property(name="confidence", data_type=DataType.NUMBER),
        ],
        references=[ReferenceProperty(name="text_chunk", target_collection=chunks_collection)])


async def test_schema_is_added_to_an_existing_collection_and_the_backfill_derives_its_spans(
        seeded_store, collection_names, ids, corpus, owner, embedder):
    names = collection_names.model_copy(update={"annotation_collection_name": "AnnotationPre328"})
    await _create_pre_328_collection(seeded_store, names, collection_names.chunks_collection_name)
    try:
        legacy = SpanRepository(seeded_store, names)
        collection = UUID(ids.col["chronicles"])
        keys = ["novak_manual", "lhota_automatic", "brno_manual"]
        stored = {}
        for key in keys:
            s = corpus.spans[key]
            span = PostSpan(chunkId=ids.chunk[s["chunk"]], tagId=ids.tag[s["tag"]], start=s["start"], end=s["end"],
                            type=SpanType(s["type"]))
            stored[await legacy.insert(collection, span, UUID(ids.doc["chronicle"]))] = s

        assert (await enrichment_schema(seeded_store, names, "contextual"))[1] is False
        added = await add_enrichment_schema(seeded_store, names, "contextual")
        assert "text" in added and "vector:contextual" in added
        assert await enrichment_schema(seeded_store, names, "contextual") == ([], True)
        assert await add_enrichment_schema(seeded_store, names, "contextual") == []  # idempotent

        store = make_store(seeded_store, names, embedder)
        [report] = await backfill.status(store, [collection])
        assert (report.spans, report.incomplete, dict(report.text)) == (3, 3, {"missing": 3})

        result = await backfill.backfill(store, [collection], limit=2)
        assert (result.processed, result.remaining, result.failed) == (2, 1, [])
        result = await backfill.backfill(store, [collection], limit=10)
        assert (result.processed, result.text_written, result.vector_written) == (1, 1, 1)

        for sid, s in stored.items():
            row = await store.spans.read_row(collection, sid)
            assert (row.start, row.end, row.type.value, row.revision) == (s["start"], s["end"], s["type"], None)
            assert row.text == s["quote"] and vector_current(row, CONFIG_ID)
        [report] = await backfill.status(store, [collection])
        assert report.incomplete == 0 and report.vector == {"current": 3}
    finally:
        await seeded_store.collections.delete(names.annotation_collection_name)


async def test_without_the_derived_properties_spans_are_saved_without_them(seeded_store, collection_names, ids,
                                                                          owner, embedder):
    # A store not yet given add-schema: the backend must not let auto-schema add properties.
    names = collection_names.model_copy(update={"annotation_collection_name": "AnnotationPre328Writes"})
    await _create_pre_328_collection(seeded_store, names, collection_names.chunks_collection_name)
    try:
        store = make_store(seeded_store, names, embedder)
        store.enrichment = await detect_enrichment(seeded_store, SimpleNamespace(collectionNames=names),
                                                   store.enrichment.vector)
        assert store.enrichment == Enrichment.disabled()

        created = await service.create_span(store, owner, post(ids, "chronicle_1", 34, 43))
        await service.update_span(store, owner, UUID(ids.col["chronicles"]), UUID(created.id), PatchSpan(start=38))

        assert created.outcome == "complete" and embedder.calls == 0
        config = await seeded_store.collections.get(names.annotation_collection_name).config.get()
        assert {p.name for p in config.properties}.isdisjoint({"revision", "text", "vectorStatus"})
        assert set(config.vector_config) == {"default"}
    finally:
        await seeded_store.collections.delete(names.annotation_collection_name)
