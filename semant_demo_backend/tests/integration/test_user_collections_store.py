"""Weaviate repository reads on the fixture corpus.

These pin storage semantics that mocks cannot prove (reference filters, membership,
counts, Unicode round trips). Repository writes, missing ids and paging are covered in
test_repositories.py.
"""
from uuid import UUID

import pytest

from semant_demo.features.annotations.schemas import SpanType

pytestmark = pytest.mark.integration


def ids(items):
    return {str(item.id) for item in items}


def col(corpus, key) -> UUID:
    return UUID(corpus.collections[key]["id"])


def doc(corpus, key) -> UUID:
    return UUID(corpus.documents[key]["id"])


@pytest.mark.parametrize("user, visible, shared_with_me", [
    ("owner", {"chronicles", "newspapers"}, set()),
    ("annotator", {"chronicles"}, {"chronicles"}),
    ("outsider", {"outsider_notes"}, set()),
    ("admin", set(), set()),
])
async def test_collection_listing_includes_owned_and_shared(collections, corpus, user, visible, shared_with_me):
    listed = await collections.read_all(UUID(corpus.users[user]["id"]))

    by_id = {str(c.id): c for c in listed}
    assert set(by_id) == {corpus.collections[k]["id"] for k in visible}
    assert {k for k in visible if by_id[corpus.collections[k]["id"]].is_shared_with_me} == shared_with_me


async def test_collection_stats_count_membership_and_approved_annotations(collections, corpus):
    stats = await collections.read_collection_stats(col(corpus, "chronicles"))

    assert (stats.documents_count, stats.chunks_count, stats.tags_count) == (2, 4, 2)
    # Only `pos` spans whose chunk and tag both belong to the collection.
    assert stats.annotations_count == 2


async def test_document_shared_by_two_collections_lists_in_both(collections, corpus):
    chronicle = corpus.documents["chronicle"]["id"]

    for key in ("chronicles", "newspapers"):
        documents = await collections.read_all_documents(col(corpus, key))
        assert chronicle in ids(documents)

    outsider_docs = await collections.read_all_documents(col(corpus, "outsider_notes"))
    assert ids(outsider_docs) == {corpus.documents["gazette"]["id"]}


async def test_document_chunks_are_limited_to_collection_membership(collections, corpus):
    chronicle = doc(corpus, "chronicle")

    in_chronicles = await collections.read_all_chunks_by_document(chronicle, col(corpus, "chronicles"))
    in_newspapers = await collections.read_all_chunks_by_document(chronicle, col(corpus, "newspapers"))

    assert [c.order for c in in_chronicles] == [0, 1]
    assert [c.order for c in in_newspapers] == [2]


async def test_chunk_range_marks_membership_of_requested_collection(collections, corpus):
    chunks = await collections.get_chunks_in_range(
        document_id=doc(corpus, "chronicle"),
        collection_id=col(corpus, "chronicles"),
        order_gt=None, order_lt=None,
    )

    assert [(c.order, c.in_collection) for c in chunks] == [(0, True), (1, True), (2, False)]


async def test_document_stats_within_collection(collections, corpus):
    stats = await collections.read_document_stats(col(corpus, "chronicles"), doc(corpus, "chronicle"))

    assert (stats.chunks_in_collection, stats.total_chunks) == (2, 3)
    assert (stats.annotations_count, stats.distinct_tags_count) == (2, 2)


async def test_chunk_spans_keep_type_offsets_and_ai_metadata(spans, corpus):
    chunk = corpus.chunks["chronicle_1"]

    found = await spans.read_by_collection(UUID(corpus.collections["chronicles"]["id"]), UUID(chunk["id"]))

    by_id = {s.id: s for s in found}
    manual, automatic = corpus.spans["novak_manual"], corpus.spans["lhota_automatic"]
    assert set(by_id) == {manual["id"], automatic["id"]}
    assert (by_id[manual["id"]].type, by_id[manual["id"]].start, by_id[manual["id"]].end) == (SpanType.pos, 34, 43)
    assert by_id[manual["id"]].reason is None
    assert by_id[automatic["id"]].type == SpanType.auto
    assert (by_id[automatic["id"]].reason, by_id[automatic["id"]].confidence) == ("Název obce.", 0.9)


async def test_text_with_combining_marks_and_non_bmp_round_trips(collections, corpus):
    chunks = await collections.read_all_chunks_by_document(doc(corpus, "letters"), col(corpus, "chronicles"))

    assert [c.text for c in chunks] == [corpus.chunks["letters_1"]["text"], corpus.chunks["letters_2"]["text"]]
