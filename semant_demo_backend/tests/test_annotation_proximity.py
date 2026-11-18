"""Proximity, overlap and containment filters of annotation queries (#333), with in-memory fakes.

``proximity.match`` compares stored document intervals: gaps between span boundaries in words or
characters, direction, overlap, containment, self exclusion, several neighbors, and positions that
are not current (never a false match, never proof of absence). The service applies the filter
before counting and paging, explains matches by their nearest neighbors and refuses what it cannot
compare completely. The Weaviate query: tests/integration/test_annotation_concordance.py.
"""
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from semant_demo.core.errors import InvalidRequestError
from semant_demo.features.annotations import proximity, service
from semant_demo.features.annotations import attribute_codec as codec
from semant_demo.features.annotations.derivation import DERIVATION_VERSION
from semant_demo.features.annotations.schemas import (
    AnnotationFilters, AnnotationIdsRequest, AnnotationRow, DistanceUnit, NearDirection, NearFilter, NearRelation,
    SpanType,
)
from semant_demo.features.documents.criteria import DocumentFilters
from semant_demo.features.user_collections.access import ResourceNotFound
from tests.test_annotation_concordance import (  # noqa: F401  (the ``store`` fixture)
    ATTRIBUTE, COLLECTION, DOC_A, DOC_B, DOC_NO_YEAR, OTHER, OWNER, RED, store,
)

STATEMENT, CRITICISM = uuid4(), uuid4()


def span(words: tuple[int, int], *, tag=STATEMENT, document=DOC_A, chars: tuple[int, int] | None = None,
         current=True, type=SpanType.pos, values=None, rid=None) -> AnnotationRow:
    """An annotation over the word interval ``words``; characters ten per word unless given."""
    start, end = chars or (10 * words[0], 10 * words[1])
    positions = dict(documentStartChar=start, documentEndChar=end, documentStartWord=words[0],
                     documentEndWord=words[1], enrichmentStatus="ready", enrichedRevision=1,
                     derivationVersion=DERIVATION_VERSION, text="x", leftContext="", rightContext="")
    return AnnotationRow(id=rid or uuid4(), tagId=tag, type=type, chunkId=uuid4(), documentId=document, start=0, end=1,
                         revision=1, attributeValues=values, **(positions if current else {}))


def near(**kwargs) -> NearFilter:
    return NearFilter(tag_ids=[CRITICISM], **kwargs)


def matched(primary, neighbors, **kwargs) -> list[UUID]:
    return proximity.match(primary, neighbors, near(**kwargs)).ids


# ── Matching ─────────────────────────────────────────────────────────────

def test_the_worked_example_measures_the_gap_between_span_boundaries():
    a, b = span((100, 110)), span((140, 145), tag=CRITICISM)
    assert matched([a], [b], distance=50) == [a.id]
    assert matched([a], [b], distance=30) == [a.id]  # 30 intervening words
    assert matched([a], [b], distance=29) == []
    assert matched([a], [b], distance=50, direction=NearDirection.after) == [a.id]
    assert matched([a], [b], distance=50, direction=NearDirection.before) == []
    b2 = span((105, 115), tag=CRITICISM)
    assert matched([a], [b2], distance=0) == [a.id]
    assert matched([a], [b2], relation=NearRelation.overlaps) == [a.id]
    assert matched([a], [b], relation=NearRelation.overlaps) == []


def test_adjacent_and_overlapping_spans_have_zero_gap_but_only_overlap_overlaps():
    a = span((10, 20))
    adjacent_after, adjacent_before = span((20, 25), tag=CRITICISM), span((5, 10), tag=CRITICISM)
    for b in (adjacent_after, adjacent_before):
        assert matched([a], [b], distance=0) == [a.id]
        assert matched([a], [b], relation=NearRelation.overlaps) == []
    assert matched([a], [adjacent_after], distance=0, direction=NearDirection.after) == [a.id]
    assert matched([a], [adjacent_before], distance=0, direction=NearDirection.after) == []
    assert matched([a], [adjacent_before], distance=0, direction=NearDirection.before) == [a.id]


def test_a_direction_excludes_overlapping_neighbors():
    a, b = span((10, 20)), span((15, 30), tag=CRITICISM)
    assert matched([a], [b], distance=5) == [a.id]
    assert matched([a], [b], distance=5, direction=NearDirection.after) == []
    assert matched([a], [b], distance=5, direction=NearDirection.before) == []


def test_containment_in_both_directions():
    outer, inner = span((10, 30)), span((12, 15), tag=CRITICISM)
    assert matched([outer], [inner], relation=NearRelation.contains) == [outer.id]
    assert matched([outer], [inner], relation=NearRelation.contained_by) == []
    small, big = span((12, 15)), span((10, 30), tag=CRITICISM)
    assert matched([small], [big], relation=NearRelation.contained_by) == [small.id]
    assert matched([small], [big], relation=NearRelation.contains) == []
    same = span((12, 15), tag=CRITICISM)
    assert matched([small], [same], relation=NearRelation.contains) == [small.id]
    assert matched([small], [same], relation=NearRelation.contained_by) == [small.id]


def test_character_distance_uses_the_character_intervals():
    a = span((0, 1), chars=(0, 10))
    b = span((1, 2), tag=CRITICISM, chars=(25, 30))  # adjacent words, 15 characters apart
    assert matched([a], [b], distance=0) == [a.id]
    assert matched([a], [b], distance=14, unit=DistanceUnit.chars) == []
    assert matched([a], [b], distance=15, unit=DistanceUnit.chars) == [a.id]


def test_spans_inside_one_word_have_zero_word_gap():
    a = span((3, 4), chars=(30, 32))
    b = span((3, 4), tag=CRITICISM, chars=(35, 38))
    assert matched([a], [b], distance=0, direction=NearDirection.after) == [a.id]
    assert matched([a], [b], distance=2, unit=DistanceUnit.chars) == []


def test_only_neighbors_of_the_same_document_match():
    a = span((10, 20))
    assert matched([a], [span((10, 20), tag=CRITICISM, document=DOC_B)], relation=NearRelation.same_document) == []
    assert matched([a], [span((900, 901), tag=CRITICISM)], relation=NearRelation.same_document) == [a.id]


def test_an_annotation_is_not_its_own_neighbor_but_one_of_the_same_tag_is():
    first, second = span((10, 12)), span((40, 42))
    found = proximity.match([first, second], [first, second], NearFilter(tag_ids=[STATEMENT], distance=5))
    assert found.ids == []
    found = proximity.match([first, second], [first, second], NearFilter(tag_ids=[STATEMENT], distance=30))
    assert sorted(found.ids) == sorted([first.id, second.id])
    assert {a: [b.id for b in bs] for a, bs in found.neighbors.items()} == {first.id: [second.id], second.id: [first.id]}


def test_several_neighbors_match_once_and_the_nearest_explain_it():
    a = span((100, 110))
    neighbors = [span((100 + d, 101 + d), tag=CRITICISM) for d in (40, 12, 30, 20, -5)]
    found = proximity.match([a], neighbors, near(distance=50))
    assert found.ids == [a.id]
    assert [b.id for b in found.neighbors[a.id]] == [neighbors[1].id, neighbors[4].id, neighbors[3].id]  # gaps 2, 4, 10


def test_missing_positions_never_make_a_close_match():
    a, unknown = span((10, 20)), span((10, 20), current=False)
    found = proximity.match([a, unknown], [span((10, 20), tag=CRITICISM, current=False)], near(distance=1000))
    assert found.ids == []
    assert (found.unknown, found.neighbors_unpositioned) == (1, 1)
    found = proximity.match([unknown], [span((15, 16), tag=CRITICISM)], near(distance=1000))
    assert (found.ids, found.unknown) == ([], 1)


def test_absence_needs_known_positions_of_the_annotation_and_every_neighbor_of_its_document():
    far, close, unknown = span((10, 20)), span((500, 510)), span((900, 910), current=False)
    other = span((10, 20), document=DOC_B)
    neighbors = [span((505, 506), tag=CRITICISM), span((10, 11), tag=CRITICISM, document=DOC_B, current=False)]
    found = proximity.match([far, close, unknown, other], neighbors, near(distance=10, absent=True))
    assert found.ids == [far.id]
    assert found.neighbors == {}
    assert found.unknown == 2  # its own position, a neighbor's position in its document


def test_too_many_comparisons_are_refused(monkeypatch):
    monkeypatch.setattr(proximity, "MAX_NEAR_COMPARISONS", 3)
    primary = [span((i, i + 1)) for i in range(3)]
    neighbors = [span((i, i + 1), tag=CRITICISM) for i in range(3)]
    with pytest.raises(proximity.TooManyComparisons):
        proximity.match(primary, neighbors, near(distance=10))


def test_a_direction_only_with_within():
    with pytest.raises(ValidationError):
        NearFilter(relation=NearRelation.overlaps, direction=NearDirection.after)
    with pytest.raises(ValidationError):
        NearFilter(distance=-1)


# ── The service ──────────────────────────────────────────────────────────

def corpus(store) -> dict[str, AnnotationRow]:
    rows = {
        "a_close": span((100, 110)), "a_far": span((300, 310)), "a_b_doc": span((10, 20), document=DOC_B),
        "a_alone": span((10, 20), document=DOC_NO_YEAR), "a_unknown": span((120, 125), current=False),
        "c_near": span((140, 145), tag=CRITICISM), "c_red": span((312, 313), tag=CRITICISM, values=[codec.encode(ATTRIBUTE, RED)]),
        "c_b_doc": span((60, 61), tag=CRITICISM, document=DOC_B),
    }
    store.spans.rows = list(rows.values())
    return rows


def statements(**kwargs) -> AnnotationFilters:
    return AnnotationFilters(tag_ids=[STATEMENT], near=near(**kwargs))


async def test_pages_and_counts_enumerate_distinct_matching_annotations(store):
    rows = corpus(store)
    store.spans.rows += [span((150, 151), tag=CRITICISM), span((95, 96), tag=CRITICISM)]  # more neighbors of a_close
    filters = statements(distance=50)
    first = await service.query_annotations(store, OWNER, COLLECTION, filters, limit=1, offset=0)
    second = await service.query_annotations(store, OWNER, COLLECTION, filters, limit=1, offset=1)
    assert first.total == second.total == 3
    third = await service.query_annotations(store, OWNER, COLLECTION, filters, limit=1, offset=2)
    listed = [p.rows[0].id for p in (first, second, third)]
    assert sorted(listed) == sorted([rows["a_close"].id, rows["a_far"].id, rows["a_b_doc"].id])
    assert first.proximity.unknown == 1
    by_id = {p.rows[0].id: p.rows[0] for p in (first, second, third)}
    far = by_id[rows["a_far"].id].neighbors
    # a_far covers characters [3000, 3100), c_red [3120, 3130): 120 code units after its start.
    assert [(n.id, n.tagId, n.start, n.end) for n in far] == [(rows["c_red"].id, CRITICISM, 120, 130)]
    assert len(by_id[rows["a_close"].id].neighbors) == 3


async def test_neighbor_attributes_constrain_the_neighbor_side_only(store):
    rows = corpus(store)
    filters = AnnotationFilters(tag_ids=[STATEMENT], near=near(distance=50, attribute_values=[codec.encode(ATTRIBUTE, RED)]))
    page = await service.query_annotations(store, OWNER, COLLECTION, filters)
    assert [r.id for r in page.rows] == [rows["a_far"].id]


async def test_absence_lists_annotations_of_documents_without_neighbors_and_proven_ones(store):
    rows = corpus(store)
    page = await service.query_annotations(store, OWNER, COLLECTION, statements(distance=5, absent=True))
    assert {r.id for r in page.rows} == {rows["a_close"].id, rows["a_b_doc"].id, rows["a_alone"].id}
    assert page.total == 3
    assert all(r.neighbors == [] for r in page.rows)


async def test_the_same_filter_selects_the_same_annotations_in_ids_documents_and_export_query(store):
    rows = corpus(store)
    request = AnnotationIdsRequest(tag_ids=[STATEMENT], near=near(distance=10, direction=NearDirection.after))
    resolved = await service.resolve_annotation_ids(store, OWNER, COLLECTION, request)
    assert resolved.ids == [rows["a_far"].id]
    documents = await service.list_annotated_documents(store, OWNER, COLLECTION, request)
    assert [(d.id, d.count) for d in documents] == [(DOC_A, 1)]


async def test_document_filters_restrict_the_compared_documents(store):
    rows = corpus(store)
    filters = statements(distance=50).model_copy(update={"document_filters": DocumentFilters(year_min=1900)})
    page = await service.query_annotations(store, OWNER, COLLECTION, filters)
    assert {r.id for r in page.rows} == {rows["a_close"].id, rows["a_far"].id}


async def test_more_annotations_than_can_be_compared_are_refused(store, monkeypatch):
    corpus(store)
    monkeypatch.setattr(proximity, "MAX_NEAR_ANNOTATIONS", 2)
    with pytest.raises(InvalidRequestError, match="neighbor annotations"):
        await service.query_annotations(store, OWNER, COLLECTION, statements())
    store.spans.rows = [r for r in store.spans.rows if r.tagId == STATEMENT or r.documentId == DOC_B]
    with pytest.raises(InvalidRequestError, match="narrow the filters"):
        store.spans.rows += [span((1, 2), document=DOC_B), span((3, 4), document=DOC_B)]
        await service.query_annotations(store, OWNER, COLLECTION, statements())


async def test_a_denied_request_compares_nothing(store):
    corpus(store)
    with pytest.raises(ResourceNotFound):
        await service.query_annotations(store, OTHER, COLLECTION, statements())
    assert store.spans.queries == 0


async def test_absence_is_never_proven_by_an_unknown_position_even_without_neighbors_in_the_document(store):
    rows = corpus(store)
    unknown = span((30, 31), document=DOC_NO_YEAR, current=False)  # its document holds no Criticism at all
    store.spans.rows.append(unknown)
    page = await service.query_annotations(store, OWNER, COLLECTION, statements(distance=5, absent=True))
    assert unknown.id not in {r.id for r in page.rows}
    assert rows["a_alone"].id in {r.id for r in page.rows}
    assert page.proximity.unknown == 2  # a_unknown (next to a neighbor) and the one without any neighbor
    resolved = await service.resolve_annotation_ids(store, OWNER, COLLECTION, AnnotationIdsRequest(
        tag_ids=[STATEMENT], near=near(distance=5, absent=True)))
    assert unknown.id not in resolved.ids and sorted(resolved.ids, key=str) == sorted((r.id for r in page.rows), key=str)


async def test_absence_compares_the_annotations_of_every_document_within_the_limit(store, monkeypatch):
    corpus(store)
    monkeypatch.setattr(proximity, "MAX_NEAR_ANNOTATIONS", 4)  # 5 Statements, 3 of them in documents with a neighbor
    await service.query_annotations(store, OWNER, COLLECTION, statements(distance=5))
    with pytest.raises(InvalidRequestError, match="More than 4 annotations would"):
        await service.query_annotations(store, OWNER, COLLECTION, statements(distance=5, absent=True))


async def test_absence_caps_only_the_candidates_of_the_documents_the_document_filters_select(store, monkeypatch):
    rows = corpus(store)
    # DOC_A (1912) holds 3 Statements, DOC_B (1850) one, DOC_NO_YEAR one: 5 in the tenant, 3 eligible.
    monkeypatch.setattr(proximity, "MAX_NEAR_ANNOTATIONS", 4)
    filters = statements(distance=5, absent=True)
    with pytest.raises(InvalidRequestError, match="More than 4 annotations would"):
        await service.query_annotations(store, OWNER, COLLECTION, filters)
    page = await service.query_annotations(store, OWNER, COLLECTION, filters.model_copy(
        update={"document_filters": DocumentFilters(year_min=1900)}))
    assert {r.id for r in page.rows} == {rows["a_close"].id}
    assert (page.proximity.primary, page.proximity.unknown) == (3, 1)  # DOC_A only: a_close, a_far, a_unknown
    none = await service.query_annotations(store, OWNER, COLLECTION, filters.model_copy(
        update={"document_filters": DocumentFilters(year_min=2000)}))
    assert (none.total, none.proximity.primary) == (0, 0)
