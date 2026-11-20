"""Facet counts of the annotation query (#667), with in-memory fakes.

Every facet value's count is the total the query returns when that value is chosen (lexical queries),
each facet is counted with its own filter removed, ranked queries count exactly their top ``k``, and
unauthorized or invalid requests read nothing. The Weaviate aggregations themselves:
tests/integration/test_annotation_concordance.py.
"""
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from semant_demo.core.errors import InvalidRequestError, NotFoundError, ServiceUnavailableError
from semant_demo.features.annotations import attribute_codec as codec
from semant_demo.features.annotations import facets, service
from semant_demo.features.annotations.schemas import (
    AnnotationFacetsRequest, AnnotationFilters, AnnotationRanking, AnnotationResultSet, FacetPopulation,
    RetrievalMode, SpanType,
)
from semant_demo.features.documents.criteria import DocumentFilters
from semant_demo.features.user_collections.access import ResourceNotFound
from tests.test_annotation_concordance import (  # noqa: F401  (fixtures)
    COLLECTION, DOC_A, DOC_B, DOC_GONE, DOC_NO_YEAR, OTHER, OTHER_TAG, OWNER, TAG, row, store,
)

ATTRIBUTE = UUID("00000000-0000-4000-8000-0000000000a1")
RED, GREEN, OLD = (UUID(f"00000000-0000-4000-8000-0000000000c{i}") for i in range(3))


class Attributes:
    """``ATTRIBUTE`` (values red, green, retired old) applying to ``TAG`` only, or to all tags."""

    def __init__(self, all_tags=False):
        self.all_tags = all_tags

    async def read(self, collection_id, attribute_id):
        if attribute_id != ATTRIBUTE:
            return None
        values = [SimpleNamespace(id=RED, retired=False), SimpleNamespace(id=GREEN, retired=False),
                  SimpleNamespace(id=OLD, retired=True)]
        return SimpleNamespace(id=ATTRIBUTE, values=values, all_tags=self.all_tags, tag_ids=[] if self.all_tags else [TAG])


def request(*facets_, **filters) -> AnnotationFacetsRequest:
    return AnnotationFacetsRequest(facets=list(facets_), **filters)


async def facet_counts(store, *names, attributes=None, **filters):
    result = await facets.annotation_facets(store, OWNER, COLLECTION, request(*names, **filters), attributes)
    return {f.facet: f for f in result.facets}


def counts(facet) -> dict[str, int]:
    return {v.value: v.count for v in facet.values}


@pytest.fixture
def populated(store):
    store.spans.rows = [
        row(DOC_A, 0), row(DOC_A, 10, tag=OTHER_TAG), row(DOC_A, 20, type=SpanType.auto),
        row(DOC_B, 0), row(DOC_B, 10, type=SpanType.neg), row(DOC_NO_YEAR, 0), row(DOC_GONE, 0, tag=OTHER_TAG)]
    return store


async def test_every_choice_counts_what_choosing_it_returns(populated):
    found = await facet_counts(populated, "tag", "type", "document", "year", "library", "language")
    chosen = {
        "tag": lambda v: AnnotationFilters(tag_ids=[UUID(v)]),
        "type": lambda v: AnnotationFilters(types=[SpanType(v)]),
        "document": lambda v: AnnotationFilters(document_ids=[UUID(v)]),
        "year": lambda v: AnnotationFilters(document_filters=DocumentFilters(year_min=int(v), year_max=int(v))),
        "library": lambda v: AnnotationFilters(document_filters=DocumentFilters(libraries=[v])),
        "language": lambda v: AnnotationFilters(document_filters=DocumentFilters(languages=[v])),
    }
    for name, facet in found.items():
        assert facet.values, name
        for value in facet.values:
            page = await service.query_annotations(populated, OWNER, COLLECTION, chosen[name](value.value))
            assert page.total == value.count, (name, value.value)


async def test_counts_and_missing_values(populated):
    found = await facet_counts(populated, "tag", "type", "year", "library", "language", "document")
    assert counts(found["tag"]) == {str(TAG): 4, str(OTHER_TAG): 2} and found["tag"].missing == 0
    assert found["tag"].total == 6  # the default types: not the rejected one
    assert counts(found["type"]) == {"pos": 5, "auto": 1, "neg": 1} and found["type"].total == 7  # type: own filter removed
    assert counts(found["year"]) == {"1912": 3, "1850": 1} and found["year"].missing == 2  # no year; deleted document
    assert counts(found["library"]) == {"mzk": 4, "nkp": 1} and found["library"].missing == 1
    assert counts(found["language"]) == {"ces": 3, "deu": 1} and found["language"].missing == 2
    assert counts(found["document"]) == {str(DOC_A): 3, str(DOC_B): 1, str(DOC_NO_YEAR): 1, str(DOC_GONE): 1}
    assert found["document"].distinct == 4 and not found["document"].truncated and found["document"].missing == 0
    assert all(f.total == (6 if n != "type" else 7) for n, f in found.items())


async def test_a_facet_ignores_its_own_filter_only(populated):
    found = await facet_counts(populated, "tag", "type", "year", "document", tag_ids=[TAG], document_ids=[DOC_A])
    assert counts(found["tag"]) == {str(TAG): 2, str(OTHER_TAG): 1}  # the tag filter removed, the document filter kept
    assert counts(found["type"]) == {"pos": 1, "auto": 1}  # tag and document filters kept, the type one removed
    assert counts(found["document"]) == {str(DOC_A): 2, str(DOC_B): 1, str(DOC_NO_YEAR): 1}
    assert counts(found["year"]) == {"1912": 2}


async def test_without_self_exclusion_every_facet_counts_the_query_itself(populated, monkeypatch):
    """The statistics of a query (#818): one population, which every facet's values add up to."""
    calls = []
    original = facets._lexical_scope

    async def scope(*args):
        calls.append(args)
        return await original(*args)

    monkeypatch.setattr(facets, "_lexical_scope", scope)
    result = await facets.annotation_facets(
        populated, OWNER, COLLECTION,
        request("tag", "type", "year", "document", tag_ids=[TAG], document_ids=[DOC_A, DOC_B], self_exclusion=False))
    assert (result.population, result.self_exclusion) == (FacetPopulation.filtered, False)
    found = {f.facet: f for f in result.facets}
    page = await service.query_annotations(populated, OWNER, COLLECTION,
                                           AnnotationFilters(tag_ids=[TAG], document_ids=[DOC_A, DOC_B]))
    assert all(f.total == page.total == 3 for f in found.values())
    assert counts(found["tag"]) == {str(TAG): 3}  # the tag filter is kept
    assert counts(found["type"]) == {"pos": 2, "auto": 1}  # the default types: not the rejected one
    assert counts(found["document"]) == {str(DOC_A): 2, str(DOC_B): 1} and found["document"].distinct == 2
    assert counts(found["year"]) == {"1912": 2, "1850": 1} and found["year"].missing == 0
    assert len(calls) == 1  # the population is read once for every facet


async def test_without_self_exclusion_missing_values_are_of_the_same_population(populated):
    found = await facet_counts(populated, "year", "library", "type", types=list(SpanType), self_exclusion=False)
    assert all(f.total == 7 for f in found.values())
    assert counts(found["type"]) == {"pos": 5, "auto": 1, "neg": 1}
    for facet in found.values():
        assert sum(counts(facet).values()) + facet.missing == facet.total


async def test_year_range_is_removed_from_the_year_facet_but_narrows_the_others(populated):
    found = await facet_counts(populated, "year", "library", document_filters=DocumentFilters(year_min=1900))
    assert counts(found["year"]) == {"1912": 3, "1850": 1}  # the whole range, so another year can be chosen
    assert counts(found["library"]) == {"mzk": 3}


async def test_an_active_choice_with_no_match_is_simply_absent(populated):
    found = await facet_counts(populated, "tag", tag_ids=[uuid4()], q="nikde")
    assert found["tag"].values == [] and found["tag"].total == 0


async def test_words_narrow_every_facet(populated):
    populated.spans.rows[0].text = "jiné"
    found = await facet_counts(populated, "tag", q="slovo")
    assert found["tag"].total == 5


async def test_a_facet_beyond_the_document_limit_is_truncated(populated, monkeypatch):
    monkeypatch.setattr(facets, "MAX_FACET_VALUES", 2)
    found = await facet_counts(populated, "document")
    assert [v.value for v in found["document"].values] == [str(DOC_A), str(DOC_B)]
    assert found["document"].distinct == 4 and found["document"].truncated


def held(rows, *values, type=SpanType.pos):
    for r, value in zip(rows, values):
        r.attributeValues = [codec.encode(ATTRIBUTE, v) for v in value]
        r.type = type


async def test_attribute_values_count_approved_annotations_once_per_value(populated):
    rows = populated.spans.rows
    held(rows[:3], [RED], [RED, GREEN], [GREEN])  # the third is a suggestion: its value is not accepted
    rows[2].type = SpanType.auto
    held(rows[3:4], [OLD])
    found = await facet_counts(populated, f"attribute:{ATTRIBUTE}", attributes=Attributes(all_tags=True))
    facet = found[f"attribute:{ATTRIBUTE}"]
    assert counts(facet) == {str(RED): 2, str(GREEN): 1, str(OLD): 1}
    assert sum(counts(facet).values()) > 3  # RED and GREEN on one annotation: more values than annotations
    assert facet.total == 6 and facet.missing == 6 - 3  # approved without a value, suggestions, ...
    for value in facet.values:
        page = await service.query_annotations(populated, OWNER, COLLECTION, AnnotationFilters(
            attribute_values=[codec.encode(ATTRIBUTE, UUID(value.value))], types=[SpanType.pos]))
        assert page.total == value.count


async def test_attribute_facet_lists_every_active_value_and_a_retired_one_only_with_annotations(populated):
    found = await facet_counts(populated, f"attribute:{ATTRIBUTE}", attributes=Attributes())
    assert {v.value: v.count for v in found[f"attribute:{ATTRIBUTE}"].values} == {str(RED): 0, str(GREEN): 0}
    assert found[f"attribute:{ATTRIBUTE}"].missing == 6


async def test_values_on_annotations_the_attribute_no_longer_applies_to_are_marked(populated):
    rows = populated.spans.rows
    held(rows[:2], [RED], [RED])  # rows[1] has OTHER_TAG, to which the attribute does not apply
    found = await facet_counts(populated, f"attribute:{ATTRIBUTE}", attributes=Attributes())
    red = {v.value: v for v in found[f"attribute:{ATTRIBUTE}"].values}[str(RED)]
    assert (red.count, red.inapplicable) == (2, 1)
    narrowed = await facet_counts(populated, f"attribute:{ATTRIBUTE}", attributes=Attributes(), tag_ids=[OTHER_TAG])
    red = {v.value: v for v in narrowed[f"attribute:{ATTRIBUTE}"].values}[str(RED)]
    assert (red.count, red.inapplicable) == (1, 1)


async def test_the_attribute_filter_of_the_facet_is_removed_but_other_attributes_stay(populated):
    rows = populated.spans.rows
    held(rows[:2], [RED], [GREEN])
    own = [codec.encode(ATTRIBUTE, RED)]
    found = await facet_counts(populated, f"attribute:{ATTRIBUTE}", attributes=Attributes(all_tags=True),
                               attribute_values=own)
    assert counts(found[f"attribute:{ATTRIBUTE}"]) == {str(RED): 1, str(GREEN): 1}
    other = UUID(int=7)
    found = await facet_counts(populated, "tag", attributes=Attributes(), attribute_values=[codec.encode(other, RED)])
    assert found["tag"].total == 0


async def test_ranked_queries_count_exactly_their_top_k(populated, monkeypatch):
    rows = populated.spans.rows
    top = [rows[0].id, rows[2].id, rows[3].id]
    seen = {}

    async def rank(store, cid, filters, ranking, query, text, conditions):
        seen["conditions"] = conditions
        return service._Ranked(ids=top, result=AnnotationResultSet(), documents=None)

    monkeypatch.setattr(service, "_rank", rank)
    populated.enrichment = SimpleNamespace(vector=SimpleNamespace(id="v"), sort_keys=False)
    result = await facets.annotation_facets(
        populated, OWNER, COLLECTION,
        request("tag", "type", "year", tag_ids=[OTHER_TAG], ranking_query="slovo",
                ranking=AnnotationRanking(mode=RetrievalMode.semantic, k=3)))
    assert (result.population, result.self_exclusion, result.k) == (FacetPopulation.top_k, False, 3)
    statistics = await facets.annotation_facets(
        populated, OWNER, COLLECTION,
        request("tag", tag_ids=[OTHER_TAG], ranking_query="slovo", self_exclusion=False,
                ranking=AnnotationRanking(mode=RetrievalMode.semantic, k=3)))
    assert statistics.facets[0].total == 3  # the same top k, whether or not facets exclude their own filter
    by_name = {f.facet: f for f in result.facets}
    assert all(f.total == 3 for f in result.facets)  # the filters do not widen or narrow the retrieved set
    assert counts(by_name["tag"]) == {str(TAG): 3} and counts(by_name["type"]) == {"pos": 2, "auto": 1}
    assert counts(by_name["year"]) == {"1912": 2, "1850": 1}


async def test_an_empty_top_k_has_empty_facets(populated, monkeypatch):
    async def rank(*args):
        return service._Ranked(ids=[], result=AnnotationResultSet(), documents=None)

    monkeypatch.setattr(service, "_rank", rank)
    populated.enrichment = SimpleNamespace(vector=SimpleNamespace(id="v"), sort_keys=False)
    result = await facets.annotation_facets(
        populated, OWNER, COLLECTION,
        request("tag", "document", ranking_query="slovo", ranking=AnnotationRanking(mode=RetrievalMode.hybrid)))
    assert [(f.values, f.total, f.missing) for f in result.facets] == [([], 0, 0), ([], 0, 0)]


async def test_denied_and_invalid_requests_read_nothing(populated):
    with pytest.raises(ResourceNotFound):
        await facets.annotation_facets(populated, OTHER, COLLECTION, request("tag"))
    populated.spans.attributes = False
    with pytest.raises(ServiceUnavailableError):
        await facets.annotation_facets(populated, OWNER, COLLECTION, request(f"attribute:{ATTRIBUTE}"), Attributes())
    populated.spans.attributes = True
    with pytest.raises(NotFoundError):
        await facets.annotation_facets(populated, OWNER, COLLECTION, request(f"attribute:{uuid4()}"), Attributes())
    with pytest.raises(InvalidRequestError):
        await facets.annotation_facets(populated, OWNER, COLLECTION, request("tag", ranking_query="text"))
    with pytest.raises(InvalidRequestError):
        await facets.annotation_facets(populated, OWNER, COLLECTION, request("tag", attribute_values=["x"]))
    with pytest.raises(ResourceNotFound):
        await facets.annotation_facets(populated, OTHER, COLLECTION, request("tag", self_exclusion=False))
    with pytest.raises(InvalidRequestError):
        await facets.annotation_facets(populated, OWNER, COLLECTION,
                                       request("tag", attribute_values=["x"], self_exclusion=False))
    assert populated.spans.queries == 0 and populated.documents.reads == []


def test_the_facet_names_are_validated():
    assert request("tag", "tag", "year").facets == ["tag", "year"]
    for bad in ("tags", "attribute", "attribute:x", ""):
        with pytest.raises(ValidationError):
            request(bad)
    with pytest.raises(ValidationError):
        AnnotationFacetsRequest(facets=[])


async def test_a_count_that_needs_more_documents_than_allowed_is_left_out_not_the_whole_answer(populated, monkeypatch):
    monkeypatch.setattr(service, "_MAX_DOCUMENTS", 2)
    found = await facet_counts(populated, "tag", "type", "year")
    assert set(found) == {"tag", "type"}  # the annotations are in 4 documents: only the per-document facet fails
    assert found["tag"].total == 6
    found = await facet_counts(populated, "tag", "year", self_exclusion=False)
    assert set(found) == {"tag"}  # also over the query's own population: left out, never counted as 0


async def test_the_proximity_filter_restricts_every_facet_before_counting(populated, monkeypatch):
    kept = {populated.spans.rows[0].id, populated.spans.rows[3].id}
    seen = []

    async def near(store, cid, filters, query, conditions):
        seen.append(filters.near)
        return query.model_copy(update={"ids": list(kept)}), None

    monkeypatch.setattr(service, "_apply_near", near)
    found = await facet_counts(populated, "tag", "type", "year")
    assert len(seen) == 3 and all(n is None for n in seen)  # once per facet, with the request's own filter
    assert [f.total for f in found.values()] == [2, 2, 2]
    assert counts(found["type"]) == {"pos": 2}


def test_at_most_a_hundred_facets_are_accepted():
    from semant_demo.features.annotations.schemas import MAX_FACETS
    assert MAX_FACETS == 100
    attributes = [f"attribute:{uuid4()}" for _ in range(MAX_FACETS)]
    assert len(AnnotationFacetsRequest(facets=attributes).facets) == 100
    with pytest.raises(ValidationError):
        AnnotationFacetsRequest(facets=[*attributes, "tag"])
