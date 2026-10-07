"""Current Weaviate adapter behavior on the fixture corpus.

These pin storage semantics that mocks cannot prove (reference filters, membership,
counts, Unicode round trips) before the adapters are moved in R2/R3.
"""
from types import SimpleNamespace
from uuid import UUID

import pytest

from semant_demo import schemas
from semant_demo.schemas import SpanType

pytestmark = pytest.mark.integration


def as_user(corpus, key):
    user = corpus.users[key]
    return SimpleNamespace(id=UUID(user["id"]), name=user["name"])


def ids(items):
    return {str(item.id) for item in items}


@pytest.mark.parametrize("user, visible, shared_with_me", [
    ("owner", {"chronicles", "newspapers"}, set()),
    ("annotator", {"chronicles"}, {"chronicles"}),
    ("outsider", {"outsider_notes"}, set()),
    ("admin", set(), set()),
])
async def test_collection_listing_includes_owned_and_shared(searcher, corpus, user, visible, shared_with_me):
    collections = await searcher.userCollection.read_all(as_user(corpus, user))

    by_id = {str(c.id): c for c in collections}
    assert set(by_id) == {corpus.collections[k]["id"] for k in visible}
    assert {k for k in visible if by_id[corpus.collections[k]["id"]].is_shared_with_me} == shared_with_me


async def test_collection_stats_count_membership_and_approved_annotations(searcher, corpus):
    stats = await searcher.userCollection.read_collection_stats(corpus.collections["chronicles"]["id"])

    assert (stats.documents_count, stats.chunks_count, stats.tags_count) == (2, 4, 2)
    # Only `pos` spans whose chunk and tag both belong to the collection.
    assert stats.annotations_count == 2


async def test_document_shared_by_two_collections_lists_in_both(searcher, corpus):
    chronicle = corpus.documents["chronicle"]["id"]

    for key in ("chronicles", "newspapers"):
        documents = await searcher.userCollection.read_all_documents(corpus.collections[key]["id"])
        assert chronicle in ids(documents)

    outsider_docs = await searcher.userCollection.read_all_documents(corpus.collections["outsider_notes"]["id"])
    assert ids(outsider_docs) == {corpus.documents["gazette"]["id"]}


async def test_document_chunks_are_limited_to_collection_membership(searcher, corpus):
    chronicle = corpus.documents["chronicle"]["id"]

    in_chronicles = await searcher.userCollection.read_all_chunks_by_document(
        chronicle, corpus.collections["chronicles"]["id"])
    in_newspapers = await searcher.userCollection.read_all_chunks_by_document(
        chronicle, corpus.collections["newspapers"]["id"])

    assert [c.order for c in in_chronicles] == [0, 1]
    assert [c.order for c in in_newspapers] == [2]


async def test_chunk_range_marks_membership_of_requested_collection(searcher, corpus):
    chunks = await searcher.userCollection.get_chunks_in_range(
        document_id=corpus.documents["chronicle"]["id"],
        collection_id=corpus.collections["chronicles"]["id"],
        order_gt=None, order_lt=None,
    )

    assert [(c.order, c.in_collection) for c in chunks] == [(0, True), (1, True), (2, False)]


async def test_document_stats_within_collection(searcher, corpus):
    stats = await searcher.userCollection.read_document_stats(
        corpus.collections["chronicles"]["id"], corpus.documents["chronicle"]["id"])

    assert (stats.chunks_in_collection, stats.total_chunks) == (2, 3)
    assert (stats.annotations_count, stats.distinct_tags_count) == (2, 2)


async def test_chunk_spans_keep_type_offsets_and_ai_metadata(searcher, corpus):
    chunk = corpus.chunks["chronicle_1"]

    spans = await searcher.span.read_all(chunk_id=chunk["id"], collection_id=corpus.collections["chronicles"]["id"])

    by_id = {s.id: s for s in spans}
    manual, automatic = corpus.spans["novak_manual"], corpus.spans["lhota_automatic"]
    assert set(by_id) == {manual["id"], automatic["id"]}
    assert (by_id[manual["id"]].type, by_id[manual["id"]].start, by_id[manual["id"]].end) == (SpanType.pos, 34, 43)
    assert by_id[manual["id"]].reason is None
    assert by_id[automatic["id"]].type == SpanType.auto
    assert (by_id[automatic["id"]].reason, by_id[automatic["id"]].confidence) == ("Název obce.", 0.9)


async def test_text_with_combining_marks_and_non_bmp_round_trips(searcher, corpus):
    letters = corpus.documents["letters"]["id"]

    chunks = await searcher.userCollection.read_all_chunks_by_document(letters, corpus.collections["chronicles"]["id"])

    assert [c.text for c in chunks] == [corpus.chunks["letters_1"]["text"], corpus.chunks["letters_2"]["text"]]


async def test_text_search_is_scoped_to_collection_and_chunk_tags(searcher, corpus):
    request = schemas.SearchRequest(
        query="Novák",
        type=schemas.SearchType.text,
        user_collection_id=corpus.collections["chronicles"]["id"],
        tag_uuids=[corpus.tags["person"]["id"]],
        positive=True,
        automatic=False,
    )

    response = await searcher.textChunk.search(request)

    # "Novák" occurs in chronicle_1 and chronicle_2; only chronicle_1 has the approved tag.
    assert [str(r.id) for r in response.results] == [corpus.chunks["chronicle_1"]["id"]]
