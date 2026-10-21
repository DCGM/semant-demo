"""Concordance (KWIC) queries against real Weaviate (#329).

Rows come from the annotations alone, paged in a total order: consecutive pages are exactly
one full read in document order (title, then position, then id) and in text order;
repeated identical annotations keep their own ids; cross-chunk and non-BMP text is returned
as derived; filters by type, tag, words (any case, inside a word), document and year are
applied by the store; spans saved without derived data are listed as pending. Through the
API, owner and shared users read and other users are refused. Selections (#459): all matches
resolve to ids by the store's filters (also among given ids), and review writes reach the
annotations and their chunk tags per item.
"""
from types import SimpleNamespace
from uuid import UUID

import pytest

from semant_demo.adapters.weaviate.chunk_tags import ChunkTagRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.adapters.weaviate.spans import SpanRepository
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.features.annotations import service
from semant_demo.features.annotations.enrichment import Enrichment
from semant_demo.core.errors import InvalidRequestError
from semant_demo.features.annotations.schemas import (
    AnnotationIdsRequest, AnnotationSort, PatchSpan, PostSpan, SpanType, TextStatus,
)
from semant_demo.features.annotations.service import AnnotationStore

pytestmark = pytest.mark.integration


@pytest.fixture
def store(seeded_store, collection_names) -> AnnotationStore:
    spans = SpanRepository(seeded_store, collection_names)
    return AnnotationStore(collections=UserCollectionRepository(seeded_store, collection_names, spans),
                           tags=TagRepository(seeded_store, collection_names, spans), spans=spans,
                           chunk_tags=ChunkTagRepository(seeded_store, collection_names, spans),
                           documents=DocumentRepository(seeded_store, collection_names),
                           enrichment=Enrichment(derived=True))


@pytest.fixture
def owner(ids):
    return SimpleNamespace(id=UUID(ids.user["owner"]), is_superuser=False)


async def create(store, owner, ids, chunk, start, end, tag="person", type=SpanType.pos) -> UUID:
    result = await service.create_span(store, owner, PostSpan(chunkId=ids.chunk[chunk], tagId=ids.tag[tag],
                                                              start=start, end=end, type=type))
    assert result.outcome == "complete"
    return UUID(result.id)


@pytest.fixture
async def created(store, owner, ids, corpus):
    """Derived annotations of the "chronicles" collection, besides the seeded ones (not derived)."""
    first, letter = corpus.chunks["chronicle_1"]["text"], corpus.chunks["letters_2"]["text"]
    karel = letter.index("Karel")
    novak = sorted([await create(store, owner, ids, "chronicle_1", 34, 43) for _ in range(2)], key=str)
    return SimpleNamespace(
        novak=novak,
        cross=await create(store, owner, ids, "chronicle_1", 80, len(first) + 8),
        zdenka=await create(store, owner, ids, "letters_2", 10, 16, tag="person"),
        karel=await create(store, owner, ids, "letters_2", karel, karel + 5, tag="person"),
        brno=await create(store, owner, ids, "chronicle_2", 29, 33, tag="place", type=SpanType.auto),
    )


async def query(store, owner, ids, **kwargs):
    return await service.query_annotations(store, owner, ids.col["chronicles"], **kwargs)


async def all_pages(store, owner, ids, size, **kwargs):
    rows, offset = [], 0
    while True:
        page = await query(store, owner, ids, limit=size, offset=offset, **kwargs)
        rows += page.rows
        offset += size
        if offset >= page.total:
            return [r.id for r in rows]


@pytest.mark.parametrize("sort", list(AnnotationSort))
async def test_pages_partition_one_total_order(store, owner, ids, created, sort):
    full = await query(store, owner, ids, sort=sort, limit=200)
    assert full.total == len(full.rows) == 10  # 6 created; seeded: pos Novák, Brně, auto Lhoty, Prahy
    for size in (1, 2, 3, 5):
        assert await all_pages(store, owner, ids, size, sort=sort) == [r.id for r in full.rows], size


async def test_document_order_and_row_fields(store, owner, ids, corpus, created):
    rows = (await query(store, owner, ids, limit=200)).rows
    # "Dopisy z Prahy" before "Kronika obce Lhota"; position order within each.
    assert [r.documentTitle for r in rows] == ["Dopisy z Prahy"] * 3 + ["Kronika obce Lhota"] * 7
    by_id = {r.id: r for r in rows}
    letters = [r.id for r in rows[:3]]
    assert letters[1:] == [created.zdenka, created.karel]  # the seeded "Prahy" comes first
    chronicle = [r.id for r in rows[3:]]
    assert chronicle.index(created.novak[0]) + 1 == chronicle.index(created.novak[1])

    first, second = corpus.chunks["chronicle_1"]["text"], corpus.chunks["chronicle_2"]["text"]
    cross = by_id[created.cross]
    assert (cross.textStatus, cross.text) == (TextStatus.ready, first[80:] + second[:8])
    assert cross.chunkId == UUID(ids.chunk["chronicle_1"]) and (cross.start, cross.end) == (80, len(first) + 8)
    karel = by_id[created.karel]
    assert karel.text == "Karel" and karel.rightContext.startswith(" ") and karel.documentYear == 1902
    seeded = by_id[UUID(corpus.spans["praha_automatic"]["id"])]
    assert (seeded.textStatus, seeded.text, seeded.type) == (TextStatus.pending, None, SpanType.auto)


async def test_filters_are_applied_by_the_store(store, owner, ids, corpus, created):
    novak = await query(store, owner, ids, text="NOVÁ")
    # The seeded "Novák" has no derived text, so no text matches it.
    assert [r.id for r in novak.rows] == created.novak

    rejected = await query(store, owner, ids, types=[SpanType.neg])
    assert [r.id for r in rejected.rows] == [UUID(corpus.spans["kronikar_rejected"]["id"])]

    places = await query(store, owner, ids, tag_ids=[ids.tag["place"]], types=[SpanType.auto])
    assert {r.id for r in places.rows} == {created.brno, UUID(corpus.spans["lhota_automatic"]["id"]),
                                           UUID(corpus.spans["praha_automatic"]["id"])}

    letters = await query(store, owner, ids, year_from=1900, sort=AnnotationSort.text)
    assert {r.documentTitle for r in letters.rows} == {"Dopisy z Prahy"} and letters.total == 3
    chronicle = await query(store, owner, ids, document_ids=[ids.doc["chronicle"]], sort=AnnotationSort.text)
    assert chronicle.total == 7

    documents = await service.list_annotated_documents(store, owner, ids.col["chronicles"])
    assert [(d.title, d.year, d.count) for d in documents] == [("Dopisy z Prahy", 1902, 3),
                                                               ("Kronika obce Lhota", 1851, 7)]


async def test_the_document_limit_counts_only_the_chosen_documents(store, owner, ids, created, monkeypatch):
    monkeypatch.setattr(service, "_MAX_DOCUMENTS", 1)  # both documents are annotated
    with pytest.raises(InvalidRequestError):
        await query(store, owner, ids)
    chronicle = await query(store, owner, ids, document_ids=[ids.doc["chronicle"]])
    assert chronicle.total == 7


async def test_a_failed_re_derivation_leaves_no_searchable_text(store, owner, ids, monkeypatch):
    moved = await create(store, owner, ids, "chronicle_1", 34, 43)

    async def unreadable(document_id):
        raise RuntimeError("source unavailable")
    monkeypatch.setattr(store.documents, "read_chunk_texts", unreadable)
    result = await service.update_span(store, owner, ids.col["chronicles"], str(moved), PatchSpan(start=35))
    assert [f.step for f in result.failed] == ["derive_annotation"]

    assert moved not in [r.id for r in (await query(store, owner, ids, text="Novák")).rows]
    by_text = (await query(store, owner, ids, sort=AnnotationSort.text, limit=200)).rows
    [row] = [r for r in by_text if r.id == moved]
    assert (row.textStatus, row.text) == (TextStatus.failed, None)
    # Sorted with the rows without text, not by its old "Novák".
    assert all(r.text is None for r in by_text[:by_text.index(row) + 1])


async def test_a_collection_without_annotations_is_empty(store, owner, ids):
    # "newspapers" has the seeded "Požár" only; a tag of another collection matches nothing.
    page = await service.query_annotations(store, owner, ids.col["newspapers"], tag_ids=[ids.tag["person"]])
    assert (page.total, page.rows) == (0, [])


async def test_api_reads_for_owner_and_shared_user_only(api_client, login, ids):
    path = f"/api/user_collections/{ids.col['chronicles']}/annotations"
    owner, annotator, outsider = [await login(name) for name in ("owner", "annotator", "outsider")]

    mine = await api_client.get(path, headers=owner, params={"sort": "text"})
    shared = await api_client.get(path, headers=annotator, params={"sort": "text"})
    refused = await api_client.get(path, headers=outsider)

    assert mine.status_code == 200 and mine.json() == shared.json()
    assert mine.json()["total"] == 4  # seeded pos Novák, Brně and auto Lhoty, Prahy
    assert refused.status_code == 404


# ── Selection and review (#459) ───────────────────────────────────────────

async def test_all_matches_resolve_to_the_ids_the_pages_show(store, owner, ids, created):
    col = ids.col["chronicles"]
    for request, kwargs in [(AnnotationIdsRequest(), {}),
                            (AnnotationIdsRequest(tag_ids=[ids.tag["person"]], q="nov"),
                             {"tag_ids": [ids.tag["person"]], "text": "nov"}),
                            (AnnotationIdsRequest(year_from=1900), {"year_from": 1900})]:
        resolved = await service.resolve_annotation_ids(store, owner, col, request)
        rows = await all_pages(store, owner, ids, 3, **kwargs)
        assert sorted(resolved.ids, key=str) == sorted(rows, key=str), request
        assert resolved.ids == sorted(resolved.ids, key=str)

    within = await service.resolve_annotation_ids(
        store, owner, col, AnnotationIdsRequest(types=[SpanType.auto], within=[created.brno, created.zdenka]))
    assert within.ids == [created.brno]


async def test_api_review_is_per_item_for_owner_and_shared_user_only(api_client, login, store, owner, ids, created):
    col = ids.col["chronicles"]
    path = f"/api/user_collections/{col}/annotations/review"
    annotator, outsider = await login("annotator"), await login("outsider")
    body = {"action": "reject", "annotation_ids": [str(created.brno), str(created.zdenka)]}

    refused = await api_client.post(path, headers=outsider, json=body)
    assert refused.status_code == 404

    rejected = await api_client.post(path, headers=annotator, json=body)
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["outcome"] == "complete"
    page = await query(store, owner, ids, types=[SpanType.neg])
    assert {r.id for r in page.rows} >= {created.brno, created.zdenka}

    deleted = await api_client.post(path, headers=annotator, json={
        "action": "delete", "annotation_ids": [str(created.karel), str(created.karel)]})
    again = await api_client.post(path, headers=annotator, json={"action": "delete", "annotation_ids": [str(created.karel)]})
    assert deleted.json()["succeeded"] == [str(created.karel)]
    assert [(f["item_id"], f["step"]) for f in again.json()["failed"]] == [(str(created.karel), "find_annotation")]
    assert again.json()["outcome"] == "failed"
