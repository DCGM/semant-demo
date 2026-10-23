"""Annotation provenance and edit versions against real Weaviate (#460).

Through the API: a create records its origin, creator and time; approve, reject and
retag record the review or edit and increment ``editVersion``; a write or delete based on
an outdated version is refused (409 with the current span, per item ``edit_conflict`` in a
review) and changes nothing. Seeded annotations (saved without provenance) report
``origin: unknown`` and version 0. An annotation collection created before #460 gets the
properties from ``add_provenance_schema`` without changing its spans, and until then the
backend writes none of them (Weaviate's auto-schema must not add them).
"""
from types import SimpleNamespace
from uuid import UUID

import pytest
from weaviate.classes.config import Configure, ReferenceProperty

from semant_demo.adapters.weaviate.chunk_tags import ChunkTagRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.adapters.weaviate.spans import (
    ENRICHMENT_PROPERTIES, PROVENANCE_PROPERTIES, SpanRepository, add_provenance_schema, provenance_schema,
)
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.bootstrap import detect_provenance
from semant_demo.core.errors import EditConflictError
from semant_demo.features.annotations import service
from semant_demo.features.annotations.schemas import PatchSpan, PostSpan, SpanType
from semant_demo.features.annotations.service import AnnotationStore

pytestmark = pytest.mark.integration


def _span(ids, tag="person"):
    return {"chunkId": ids.chunk["chronicle_1"], "tagId": ids.tag[tag], "start": 0, "end": 3, "type": "auto"}


async def _row(api_client, headers, collection, span_id):
    response = await api_client.get(f"/api/user_collections/{collection}/annotations", headers=headers,
                                     params={"type": ["pos", "auto", "neg"], "limit": 200})
    assert response.status_code == 200
    return next(r for r in response.json()["rows"] if r["id"] == span_id)


async def test_writes_record_provenance_and_an_outdated_version_is_refused(api_client, login, ids):
    owner, annotator = await login("owner"), await login("annotator")
    collection = ids.col["chronicles"]
    c = {"collection_id": collection}
    created = (await api_client.post("/api/tag_spans", headers=owner, json=_span(ids))).json()
    span_id = created["id"]
    assert created["editVersion"] == 0

    # The annotator approves the version the owner created.
    approved = await api_client.patch(f"/api/tag_spans/{span_id}", headers=annotator,
                                      params=c | {"expected_version": 0}, json={"type": "pos"})
    assert (approved.status_code, approved.json()["editVersion"]) == (200, 1)

    # The owner still has version 0: the rejection and the deletion change nothing.
    stale = await api_client.patch(f"/api/tag_spans/{span_id}", headers=owner,
                                   params=c | {"expected_version": 0}, json={"type": "neg"})
    assert stale.status_code == 409
    assert (stale.json()["current"]["type"], stale.json()["current"]["editVersion"]) == ("pos", 1)
    deleted = await api_client.delete(f"/api/tag_spans/{span_id}", headers=owner, params=c | {"expected_version": 0})
    assert deleted.status_code == 409

    row = await _row(api_client, owner, collection, span_id)
    provenance = row["provenance"]
    assert (row["type"], row["editVersion"]) == ("pos", 1)
    assert (provenance["origin"], provenance["createdBy"]) == ("manual", ids.user["owner"])
    assert (provenance["reviewedBy"], provenance["lastEditedBy"]) == (ids.user["annotator"], ids.user["annotator"])
    assert provenance["createdAt"] <= provenance["reviewedAt"] == provenance["lastEditedAt"]
    assert provenance["aiRunId"] is None

    # With the current version, the delete goes through.
    current = await api_client.delete(f"/api/tag_spans/{span_id}", headers=owner, params=c | {"expected_version": 1})
    assert current.status_code == 200


async def test_a_review_refuses_annotations_changed_since_they_were_selected(api_client, login, ids):
    owner, annotator = await login("owner"), await login("annotator")
    collection = ids.col["chronicles"]
    lhota, novak = ids.span["lhota_automatic"], ids.span["novak_manual"]
    resolved = (await api_client.post(f"/api/user_collections/{collection}/annotations/ids", headers=owner,
                                      json={"within": [lhota, novak]})).json()
    assert resolved["versions"] == {lhota: 0, novak: 0}

    # Someone retags one of the selected annotations meanwhile.
    await api_client.patch(f"/api/tag_spans/{lhota}", headers=annotator,
                           params={"collection_id": collection, "expected_version": 0},
                           json={"tagId": ids.tag["person"]})

    result = (await api_client.post(f"/api/user_collections/{collection}/annotations/review", headers=owner,
                                    json={"action": "reject", "annotation_ids": [lhota, novak],
                                          "expected_versions": resolved["versions"]})).json()

    assert result["succeeded"] == [novak]
    assert [(f["item_id"], f["step"]) for f in result["failed"]] == [(lhota, "edit_conflict")]
    assert result["versions"] == {novak: 1, lhota: 1}
    row = await _row(api_client, owner, collection, lhota)
    assert (row["type"], row["tagId"]) == ("auto", ids.tag["person"])
    # Saved before provenance: its origin stays unknown, the AI reason is kept.
    assert (row["provenance"]["origin"], row["provenance"]["createdBy"]) == ("unknown", None)


async def test_undoing_an_approval_restores_the_proposal_unless_changed_since(api_client, login, ids):
    # #461: the review returns the previous values; restoring clears the stored review.
    owner, annotator = await login("owner"), await login("annotator")
    collection = ids.col["chronicles"]
    c = {"collection_id": collection}
    first, second = [(await api_client.post("/api/tag_spans", headers=owner, json=_span(ids))).json()["id"]
                     for _ in range(2)]
    approved = (await api_client.post(f"/api/user_collections/{collection}/annotations/review", headers=annotator,
                                      json={"action": "approve", "annotation_ids": [first, second],
                                            "expected_versions": {first: 0, second: 0}})).json()
    assert approved["previous"] == {i: {"type": "auto", "tag_id": None, "chunk_id": None, "start": None, "end": None}
                                    for i in (first, second)}
    # Someone rejects the second one meanwhile.
    await api_client.patch(f"/api/tag_spans/{second}", headers=owner, params=c | {"expected_version": 1},
                           json={"type": "neg"})

    undone = await api_client.post(f"/api/user_collections/{collection}/annotations/restore", headers=annotator,
                                   json={"items": [{"id": i, "expected_version": approved["versions"][i],
                                                    "values": approved["previous"][i]} for i in (first, second)]})

    assert undone.status_code == 200
    result = undone.json()
    assert result["succeeded"] == [first]
    assert [(f["item_id"], f["step"]) for f in result["failed"]] == [(second, "edit_conflict")]
    row = await _row(api_client, owner, collection, first)
    assert (row["type"], row["editVersion"]) == ("auto", 2)
    assert (row["provenance"]["reviewedBy"], row["provenance"]["reviewedAt"]) == (None, None)
    assert row["provenance"]["lastEditedBy"] == ids.user["annotator"]
    assert (await _row(api_client, owner, collection, second))["type"] == "neg"


async def test_undoing_a_boundary_edit_restores_the_range_and_its_text(api_client, login, ids):
    owner = await login("owner")
    collection = ids.col["chronicles"]
    c = {"collection_id": collection}
    span_id = (await api_client.post("/api/tag_spans", headers=owner, json=_span(ids))).json()["id"]
    before = await _row(api_client, owner, collection, span_id)
    edited = (await api_client.patch(f"/api/tag_spans/{span_id}", headers=owner, params=c | {"expected_version": 0},
                                     json={"start": 1, "end": 8})).json()
    assert (await _row(api_client, owner, collection, span_id))["text"] != before["text"]

    undone = (await api_client.post(f"/api/user_collections/{collection}/annotations/restore", headers=owner,
                                    json={"items": [{"id": span_id, "expected_version": edited["editVersion"],
                                                     "values": {"start": 0, "end": 3}}]})).json()

    assert undone["outcome"] == "complete"
    row = await _row(api_client, owner, collection, span_id)
    assert (row["start"], row["end"], row["text"], row["editVersion"]) == (0, 3, before["text"], 2)
    assert row["revision"] == before["revision"] + 2


# ── A collection created before #460 ─────────────────────────────────────


def _store(client, names, provenance: bool) -> AnnotationStore:
    spans = SpanRepository(client, names, provenance=provenance)
    return AnnotationStore(collections=UserCollectionRepository(client, names, spans),
                           tags=TagRepository(client, names, spans), spans=spans,
                           chunk_tags=ChunkTagRepository(client, names, spans),
                           documents=DocumentRepository(client, names))


async def _create_pre_460_collection(client, names, chunks_collection):
    from weaviate.classes.config import DataType, Property, Tokenization
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
            *ENRICHMENT_PROPERTIES,
        ],
        references=[ReferenceProperty(name="text_chunk", target_collection=chunks_collection)])


async def test_provenance_is_added_to_an_existing_collection_without_changing_its_spans(
        seeded_store, collection_names, ids):
    names = collection_names.model_copy(update={"annotation_collection_name": "AnnotationPre460"})
    await _create_pre_460_collection(seeded_store, names, collection_names.chunks_collection_name)
    owner = SimpleNamespace(id=UUID(ids.user["owner"]), is_superuser=False)
    collection = UUID(ids.col["chronicles"])
    post = PostSpan(chunkId=ids.chunk["chronicle_1"], tagId=ids.tag["person"], start=34, end=43, type=SpanType.auto)
    try:
        # Before the operator step: nothing is recorded, versions are not checked, and
        # Weaviate's auto-schema adds no provenance property.
        config = SimpleNamespace(collectionNames=names)
        assert await detect_provenance(seeded_store, config) is False
        before = _store(seeded_store, names, provenance=False)
        old = await service.create_span(before, owner, post)
        await service.update_span(before, owner, collection, old.id, PatchSpan(type=SpanType.pos), expected_version=5)
        properties = {p.name for p in (await seeded_store.collections.get(names.annotation_collection_name)
                                       .config.get()).properties}
        assert properties.isdisjoint(p.name for p in PROVENANCE_PROPERTIES)

        added = await add_provenance_schema(seeded_store, names)
        assert added == [p.name for p in PROVENANCE_PROPERTIES]
        assert await provenance_schema(seeded_store, names) == []
        assert await add_provenance_schema(seeded_store, names) == []  # idempotent
        assert await detect_provenance(seeded_store, config) is True

        after = _store(seeded_store, names, provenance=True)
        unchanged = await after.spans.read(collection, UUID(old.id))
        assert (unchanged.type, unchanged.start, unchanged.editVersion) == (SpanType.pos, 34, 0)
        [row] = await after.spans.read_rows(collection)
        assert row.provenance().origin == "unknown"

        # The old span is written with versions from now on.
        rejected = await service.update_span(after, owner, collection, old.id, PatchSpan(type=SpanType.neg),
                                             expected_version=0)
        assert rejected.editVersion == 1
        with pytest.raises(EditConflictError):
            await service.update_span(after, owner, collection, old.id, PatchSpan(type=SpanType.pos),
                                      expected_version=0)
        [row] = await after.spans.read_rows(collection)
        provenance = row.provenance()
        assert (provenance.origin, provenance.reviewedBy, provenance.lastEditedBy) == ("unknown", owner.id, owner.id)
    finally:
        await seeded_store.collections.delete(names.annotation_collection_name)
