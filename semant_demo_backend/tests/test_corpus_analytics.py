"""Corpus overview (features/analytics, #254) and filtered distributions (#361) with a
stand-in repository.

Counts are distinct documents; for each available dimension the bins/values, ``other_count``
and ``unknown_count`` add up to the total; an unavailable property has no counts (``null``).
Recent unfiltered counts are served again, marked as cached, with their original
``computed_at``; filtered counts never are. Filters are validated and normalized before the
store is asked; the Weaviate filter they become is checked here, its matching semantics in
``integration/test_corpus_analytics.py``.
"""
import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from semant_demo.adapters.weaviate.analytics import (
    PER_VALUE_CONCURRENCY, AnyOf, ContainsWords, CorpusAnalyticsRepository, DocumentCounts, NumberRange, Unavailable,
    UnavailableFilter, ValueCounts, where)
from semant_demo.features.analytics import service
from semant_demo.features.analytics.schemas import DocumentFilters
from semant_demo.main import create_app
from semant_demo.routes.dependencies import get_corpus_analytics
from tests.app_support import make_test_config, offline_weaviate

PATH = "/api/analytics/corpus/overview"
DISTRIBUTIONS = "/api/analytics/corpus/distributions"
NEXT_YEAR = datetime.now(UTC).year + 1


class FakeAnalytics:
    """Answers with fixed counts whatever the conditions; like the store, it refuses a
    condition on a property it cannot count."""

    def __init__(self, total: int, **properties: ValueCounts | Unavailable):
        self.total = total
        self.properties = properties
        self.calls: list[tuple[dict, int, list]] = []

    async def count_documents(self, properties, group_limit, conditions=()):
        self.calls.append((properties, group_limit, list(conditions)))
        for condition in conditions:
            declared = self.properties.get(condition.prop, Unavailable("missing"))
            if isinstance(declared, Unavailable):
                raise UnavailableFilter(condition.prop, declared.reason)
        await asyncio.sleep(0)
        return DocumentCounts(total=self.total, properties={
            prop: self.properties.get(prop, Unavailable("missing")) for prop in properties})

    async def count_documents_per_value(self, prop, values, properties, group_limit, conditions=()):
        """The counts of ``per_value[value]`` (a FakeAnalytics) for each value; the conditions are
        only recorded here."""
        self.calls.append((prop, list(values), properties, group_limit, list(conditions)))
        return {value: await self.per_value[value].count_documents(properties, group_limit) for value in values}


def counts(groups, known=None, complete=True) -> ValueCounts:
    return ValueCounts(known=sum(n for _, n in groups) if known is None else known, groups=groups,
                       complete=complete)


def accounted(distribution) -> int:
    items = distribution.bins if hasattr(distribution, "bins") else distribution.values
    return sum(item.count for item in items) + getattr(distribution, "other_count", 0) + distribution.unknown_count


async def test_counts_documents_by_decade_library_and_language():
    analytics = FakeAnalytics(
        10,
        yearIssued=counts([(1909.0, 2), (1910.0, 3), (1851.0, 1), (1919.0, 1)]),
        library=counts([("mzk", 5), ("nkp", 2)]),
        language=counts([("ces", 6), ("deu", 1), ("cs", 1)]))

    overview = await service.corpus_overview(analytics)

    assert analytics.calls == [({"yearIssued": "number", "library": "text", "language": "text"}, service.GROUP_LIMIT, [])]
    assert (overview.scope, overview.unit, overview.data_source) == ("searchable_corpus", "documents", "live_aggregation")
    assert overview.total_documents == 10
    years = overview.publication_year
    assert years.available and years.bin_width_years == 10
    # Inclusive start, exclusive end: 1909 is in the 1900s, 1910 in the 1910s; empty decades in between stay.
    assert [(b.start, b.end_exclusive, b.count) for b in years.bins] == \
        [(1850, 1860, 1)] + [(start, start + 10, 0) for start in range(1860, 1900, 10)] + \
        [(1900, 1910, 2), (1910, 1920, 4)]
    assert years.unknown_count == 3
    assert [(v.value, v.count) for v in overview.libraries.values] == [("mzk", 5), ("nkp", 2)]
    assert (overview.libraries.other_count, overview.libraries.unknown_count) == (0, 3)
    # Different codes stay separate, even with the same meaning.
    assert [(v.value, v.count) for v in overview.languages.values] == [("ces", 6), ("cs", 1), ("deu", 1)]
    assert overview.languages.unknown_count == 2
    assert all(accounted(d) == 10 for d in (years, overview.libraries, overview.languages))


async def test_invalid_years_and_blank_values_are_unknown():
    analytics = FakeAnalytics(
        8,
        yearIssued=counts([(0.0, 1), (1909.5, 1), (-5.0, 1), (float(NEXT_YEAR), 1), (1900.0, 2)]),
        language=counts([("", 2), ("  ", 1), ("ces", 3)], known=7))

    overview = await service.corpus_overview(analytics)

    assert [(b.start, b.count) for b in overview.publication_year.bins] == [(1900, 2)]
    assert overview.publication_year.unknown_count == 6
    assert [(v.value, v.count) for v in overview.languages.values] == [("ces", 3)]
    # 1 document without a value, 3 with an empty one.
    assert (overview.languages.other_count, overview.languages.unknown_count) == (1, 4)
    assert accounted(overview.languages) == 8


async def test_values_beyond_the_listed_ones_are_other():
    groups = [(f"lang{i:03}", 100 - i) for i in range(60)]
    analytics = FakeAnalytics(10_000, language=counts(groups, known=9_000, complete=False))

    languages = (await service.corpus_overview(analytics)).languages

    assert len(languages.values) == service.MAX_LISTED_VALUES
    assert languages.values[0].value == "lang000"
    assert languages.other_count == 9_000 - sum(n for _, n in groups[:service.MAX_LISTED_VALUES])
    assert languages.unknown_count == 1_000
    assert accounted(languages) == 10_000


async def test_missing_or_unsupported_properties_are_unavailable_not_zero():
    analytics = FakeAnalytics(5, library=Unavailable("missing"), language=Unavailable("unsupported_type"),
                              yearIssued=Unavailable("missing"))

    overview = await service.corpus_overview(analytics)

    assert overview.total_documents == 5
    assert (overview.libraries.available, overview.libraries.unavailable_reason) == (False, "missing_property")
    assert overview.languages.unavailable_reason == "unsupported_type"
    for distribution in (overview.libraries, overview.languages):
        assert (distribution.values, distribution.other_count, distribution.unknown_count) == (None, None, None)
    assert (overview.publication_year.bins, overview.publication_year.unknown_count) == (None, None)


async def test_an_empty_corpus_is_an_ordinary_zero_overview():
    analytics = FakeAnalytics(0, yearIssued=counts([]), library=counts([]), language=counts([]))

    overview = await service.corpus_overview(analytics)

    assert overview.total_documents == 0
    assert (overview.publication_year.bins, overview.publication_year.unknown_count) == ([], 0)
    assert (overview.languages.values, overview.languages.other_count, overview.languages.unknown_count) == ([], 0, 0)


@pytest.mark.parametrize("prop, value_counts", [
    ("language", counts([("ces", 3)], known=6)),          # more values than documents
    ("language", counts([("ces", 3), ("deu", 2)], known=4)),  # groups exceed the known count
    ("yearIssued", counts([(1900.0, 1)], complete=False)),  # years cut off by the group limit
])
async def test_counts_that_do_not_add_up_fail_instead_of_misreporting(prop, value_counts):
    with pytest.raises(service.IncompleteCounts):
        await service.corpus_overview(FakeAnalytics(5, **{prop: value_counts}))


async def test_computed_at_is_the_request_time():
    before = datetime.now(UTC)
    overview = await service.corpus_overview(FakeAnalytics(0))
    assert before <= overview.computed_at <= datetime.now(UTC)


async def test_a_recent_overview_is_served_again_as_cached():
    analytics, cache = FakeAnalytics(4), service.OverviewCache(600)

    first = await service.cached_corpus_overview(analytics, cache)
    analytics.total = 5
    second = await service.cached_corpus_overview(analytics, cache)

    assert len(analytics.calls) == 1
    assert (first.data_source, second.data_source) == ("live_aggregation", "cached_aggregation")
    assert (second.total_documents, second.computed_at) == (4, first.computed_at)


async def test_an_expired_overview_is_computed_again():
    analytics, cache = FakeAnalytics(4), service.OverviewCache(600)
    first = await service.cached_corpus_overview(analytics, cache)
    cache.distributions = cache.distributions.model_copy(
        update={"computed_at": first.computed_at - timedelta(seconds=601)})
    analytics.total = 5

    second = await service.cached_corpus_overview(analytics, cache)

    assert (len(analytics.calls), second.data_source, second.total_documents) == (2, "live_aggregation", 5)
    assert second.computed_at >= first.computed_at


async def test_concurrent_requests_share_one_computation():
    analytics, cache = FakeAnalytics(4), service.OverviewCache(600)

    overviews = await asyncio.gather(*(service.cached_corpus_overview(analytics, cache) for _ in range(5)))

    assert len(analytics.calls) == 1
    assert sorted(o.data_source for o in overviews) == ["cached_aggregation"] * 4 + ["live_aggregation"]


async def test_a_failure_is_not_cached():
    class FailingOnce(FakeAnalytics):
        async def count_documents(self, properties, group_limit, conditions=()):
            if not self.calls:
                self.calls.append("failed")
                raise RuntimeError("store unavailable")
            return await super().count_documents(properties, group_limit, conditions)

    analytics, cache = FailingOnce(4), service.OverviewCache(600)
    with pytest.raises(RuntimeError):
        await service.cached_corpus_overview(analytics, cache)

    overview = await service.cached_corpus_overview(analytics, cache)

    assert (overview.data_source, overview.total_documents) == ("live_aggregation", 4)


async def _get(tmp_path, analytics, requests=1, **client_options):
    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    app.dependency_overrides[get_corpus_analytics] = lambda: analytics
    transport = ASGITransport(app=app, **client_options)
    async with LifespanManager(app), AsyncClient(transport=transport, base_url="http://test") as client:
        responses = [await client.get(PATH) for _ in range(requests)]
    return responses if requests > 1 else responses[0]


async def test_overview_is_answered_anonymously_with_explicit_nulls(tmp_path):
    analytics = FakeAnalytics(3, yearIssued=counts([(1909.0, 1), (1910.0, 1)]), language=counts([("ces", 3)]))

    response = await _get(tmp_path, analytics)

    assert response.status_code == 200
    body = response.json()
    assert {k: body[k] for k in ("scope", "unit", "total_documents", "data_source")} == \
        {"scope": "searchable_corpus", "unit": "documents", "total_documents": 3, "data_source": "live_aggregation"}
    assert datetime.fromisoformat(body["computed_at"]).tzinfo is not None
    assert body["publication_year"] == {
        "available": True, "unavailable_reason": None, "bin_width_years": 10, "unknown_count": 1,
        "bins": [{"start": 1900, "end_exclusive": 1910, "count": 1}, {"start": 1910, "end_exclusive": 1920, "count": 1}]}
    # The fake store declares no library property: unavailable, with null (not zero) counts.
    assert body["libraries"] == {"available": False, "unavailable_reason": "missing_property",
                                 "values": None, "other_count": None, "unknown_count": None}
    assert body["languages"]["values"] == [{"value": "ces", "count": 3}]


async def test_the_app_serves_its_recent_overview_again(tmp_path):
    analytics = FakeAnalytics(3)

    first, second = await _get(tmp_path, analytics, requests=2)

    assert len(analytics.calls) == 1
    assert (first.json()["data_source"], second.json()["data_source"]) == ("live_aggregation", "cached_aggregation")
    assert second.json()["computed_at"] == first.json()["computed_at"]


async def test_a_failed_store_read_is_an_error_not_an_empty_overview(tmp_path):
    class Failing:
        async def count_documents(self, properties, group_limit, conditions=()):
            raise RuntimeError("store unavailable")

    response = await _get(tmp_path, Failing(), raise_app_exceptions=False)

    assert response.status_code == 500
    assert "total_documents" not in response.text


def test_overview_is_a_public_typed_operation(tmp_path):
    schema = create_app(make_test_config(tmp_path)).openapi()
    operation = schema["paths"][PATH]

    assert list(operation) == ["get"]
    assert operation["get"]["operationId"] == "corpus_overview_api_analytics_corpus_overview_get"
    assert "security" not in operation["get"]
    assert operation["get"].get("parameters", []) == []
    assert operation["get"]["responses"]["200"]["content"]["application/json"]["schema"] == \
        {"$ref": "#/components/schemas/CorpusOverview"}
    overview = schema["components"]["schemas"]["CorpusOverview"]
    assert set(overview["required"]) >= {"total_documents", "computed_at", "publication_year", "libraries", "languages"}


# Filtered distributions (#361)

async def _request(tmp_path, analytics, *requests: tuple[str, dict | None], **client_options):
    """Sends (path, body) requests to one app: a body means POST, ``None`` GET."""
    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    app.dependency_overrides[get_corpus_analytics] = lambda: analytics
    transport = ASGITransport(app=app, **client_options)
    async with LifespanManager(app), AsyncClient(transport=transport, base_url="http://test") as client:
        return [await (client.get(path) if body is None else client.post(path, json=body)) for path, body in requests]


async def test_distributions_count_documents_per_year_and_treat_future_years_as_unknown(tmp_path):
    analytics = FakeAnalytics(
        9, yearIssued=counts([(1910.0, 3), (1909.0, 2), (311.0, 1), (float(NEXT_YEAR), 1), (1909.5, 1)]),
        language=counts([("ces", 9)]))

    response, = await _request(tmp_path, analytics, (DISTRIBUTIONS, {}))  # anonymous

    assert response.status_code == 200
    body = response.json()
    assert {k: body[k] for k in ("scope", "unit", "total_documents", "data_source")} == \
        {"scope": "searchable_corpus", "unit": "documents", "total_documents": 9, "data_source": "live_aggregation"}
    assert body["filters"] == {"year_min": None, "year_max": None, "title_contains": [],
                               "libraries": [], "languages": []}
    # Only years with documents, ascending; the next year and 1909.5 are unknown or invalid.
    assert body["publication_year"] == {
        "available": True, "unavailable_reason": None, "unknown_count": 3,
        "years": [{"year": 311, "count": 1}, {"year": 1909, "count": 2}, {"year": 1910, "count": 3}]}
    assert body["libraries"]["available"] is False
    assert body["languages"]["values"] == [{"value": "ces", "count": 9}]


async def test_the_overview_counts_a_future_year_as_unknown():
    analytics = FakeAnalytics(3, yearIssued=counts([(float(NEXT_YEAR - 1), 1), (float(NEXT_YEAR), 2)]))

    years = (await service.corpus_overview(analytics)).publication_year

    decade = (NEXT_YEAR - 1) // 10 * 10
    assert [(b.start, b.count) for b in years.bins] == [(decade, 1)]
    assert years.unknown_count == 2


async def test_filters_are_normalized_and_become_one_set_of_conditions(tmp_path):
    analytics = FakeAnalytics(4, yearIssued=counts([(1905.0, 4)]), library=counts([("mzk", 4)]),
                              language=counts([("ces", 4)]), title=counts([]))  # title: declared, not counted

    response, = await _request(tmp_path, analytics, (DISTRIBUTIONS, {"filters": {
        "year_min": 1900, "year_max": 1920, "title_contains": ["  Pražský: věstník a pražský-1919 ", "brno", "BRNO"],
        "libraries": [" nkp", "mzk", "nkp"], "languages": ["ces"]}}))

    assert response.status_code == 200
    # Each title split like the store's words, without one-letter words and words repeated in
    # another case; titles repeated in another case are dropped and the rest sorted.
    assert response.json()["filters"] == {"year_min": 1900, "year_max": 1920,
                                          "title_contains": ["brno", "Pražský věstník 1919"],
                                          "libraries": ["mzk", "nkp"], "languages": ["ces"]}
    assert analytics.calls[0][2] == [NumberRange("yearIssued", 1900, 1920),
                                     ContainsWords("title", (("brno",), ("Pražský", "věstník", "1919"))),
                                     AnyOf("library", ("mzk", "nkp")), AnyOf("language", ("ces",))]


@pytest.mark.parametrize("filters, message", [
    ({"year_min": 0}, "greater than or equal to 1"),
    ({"year_max": NEXT_YEAR}, "cannot be after the current year"),
    ({"year_min": 1921, "year_max": 1920}, "must not be after the last one"),
    ({"year_min": 1900.5}, "valid integer"),
    ({"title_contains": ["škol*"]}, "does not support wildcards"),
    ({"title_contains": ["brno", "praz?ky"]}, "does not support wildcards"),
    ({"title_contains": ["a v z"]}, "at least one title word of two or more"),
    ({"title_contains": [" "]}, "must not be empty"),
    ({"title_contains": ["x" * 101]}, "at most 100 characters"),
    ({"title_contains": ["one two three four five six"]}, "at most 5 words"),
    ({"title_contains": [f"t{i}" for i in range(11)]}, "at most 10 items"),
    ({"title_contains": "brno"}, "valid list"),
    ({"libraries": ["mzk", " "]}, "must be non-empty"),
    ({"languages": [f"l{i}" for i in range(51)]}, "at most 50 items"),
    ({"publisher": "x"}, "Extra inputs are not permitted"),
])
async def test_invalid_filters_are_rejected_before_the_store_is_asked(tmp_path, filters, message):
    analytics = FakeAnalytics(1)

    response, = await _request(tmp_path, analytics, (DISTRIBUTIONS, {"filters": filters}))

    assert response.status_code == 422
    assert message in str(response.json()["detail"])
    assert analytics.calls == []


async def test_a_filter_on_a_property_the_store_lacks_is_rejected_not_zero(tmp_path):
    analytics = FakeAnalytics(5, language=counts([("ces", 5)]))  # no library property

    response, = await _request(tmp_path, analytics, (DISTRIBUTIONS, {"filters": {"libraries": ["mzk"]}}))

    assert response.status_code == 422
    assert response.json() == {"detail": "Documents cannot be filtered by library: this corpus database is not recorded."}


async def test_only_unfiltered_distributions_are_served_again(tmp_path):
    analytics = FakeAnalytics(4, language=counts([("ces", 4)]))
    filtered = {"filters": {"languages": ["ces"]}}

    responses = await _request(tmp_path, analytics, (DISTRIBUTIONS, {}), (DISTRIBUTIONS, filtered),
                               (DISTRIBUTIONS, filtered), (DISTRIBUTIONS, {"filters": {}}), (PATH, None))

    assert [r.json()["data_source"] for r in responses] == \
        ["live_aggregation", "live_aggregation", "live_aggregation", "cached_aggregation", "cached_aggregation"]
    # The overview is the cached unfiltered computation, grouped into decades.
    assert [conditions for _, _, conditions in analytics.calls] == [[], [AnyOf("language", ("ces",))],
                                                                     [AnyOf("language", ("ces",))]]
    assert responses[4].json()["computed_at"] == responses[0].json()["computed_at"]


def test_distributions_are_a_public_typed_operation(tmp_path):
    schema = create_app(make_test_config(tmp_path)).openapi()
    operation = schema["paths"][DISTRIBUTIONS]

    assert list(operation) == ["post"]
    assert operation["post"]["operationId"] == "corpus_distributions_api_analytics_corpus_distributions_post"
    assert "security" not in operation["post"]
    assert operation["post"]["requestBody"]["content"]["application/json"]["schema"] == \
        {"$ref": "#/components/schemas/CorpusDistributionsRequest"}
    assert operation["post"]["responses"]["200"]["content"]["application/json"]["schema"] == \
        {"$ref": "#/components/schemas/CorpusDistributions"}
    distributions = schema["components"]["schemas"]["CorpusDistributions"]
    assert set(distributions["required"]) >= {"filters", "total_documents", "publication_year", "libraries", "languages"}


# The Weaviate filter (adapters/weaviate/analytics.py): one filter for every count.

TYPES = {"yearIssued": "number", "title": "text", "library": "text", "language": "text", "author": "text[]"}


def _parts(f):
    return [(p.target, p.operator.value, p.value) for p in getattr(f, "filters", [f])]


@pytest.mark.parametrize("data_type, bound_type", [("int", int), ("number", float)])
def test_a_year_range_is_compared_as_the_declared_type(data_type, bound_type):
    # Production and the fixtures declare yearIssued as int (#496), older stores as number.
    f = where([NumberRange("yearIssued", 1900, 1920)], {"yearIssued": data_type})

    assert _parts(f) == [("yearIssued", "GreaterThanEqual", 1900), ("yearIssued", "LessThanEqual", 1920)]
    assert all(type(p.value) is bound_type for p in f.filters)
    assert _parts(where([NumberRange("yearIssued", maximum=1909)], {"yearIssued": data_type})) == \
        [("yearIssued", "LessThanEqual", 1909)]


def test_conditions_are_combined_with_and_and_values_with_or():
    f = where([ContainsWords("title", (("Pražský", "věstník"),)), AnyOf("library", ("mzk", "nkp")),
               AnyOf("language", ("ces",))], TYPES)

    title, libraries, language = f.filters
    # One title: all its words.
    assert type(title).__name__ == "_FilterAnd"
    assert _parts(title) == [("title", "Like", "*Pražský*"), ("title", "Like", "*věstník*")]
    assert _parts(libraries) == [("library", "Equal", "mzk"), ("library", "Equal", "nkp")]
    assert type(libraries).__name__ == "_FilterOr"
    assert _parts(language) == [("language", "Equal", "ces")]
    assert where([], TYPES) is None


def test_title_alternatives_match_any_of_them_with_all_of_their_words():
    f = where([ContainsWords("title", (("brno",), ("pražský", "věstník")))], TYPES)

    assert type(f).__name__ == "_FilterOr"
    brno, prague = f.filters
    assert _parts(brno) == [("title", "Like", "*brno*")]
    assert type(prague).__name__ == "_FilterAnd"
    assert _parts(prague) == [("title", "Like", "*pražský*"), ("title", "Like", "*věstník*")]


@pytest.mark.parametrize("condition, reason", [
    (AnyOf("nothing", ("x",)), "missing"),
    (ContainsWords("author", (("Hájek",),)), "unsupported_type"),  # text[]: several values per document
    (NumberRange("title", 1900), "unsupported_type"),
])
def test_a_condition_on_a_property_that_cannot_be_filtered_is_refused(condition, reason):
    with pytest.raises(UnavailableFilter) as refused:
        where([condition], TYPES)
    assert (refused.value.prop, refused.value.reason) == (condition.prop, reason)


# Documents per library and year (#361, optional heatmap)

LIBRARY_YEARS = "/api/analytics/corpus/library-years"


def heatmap_analytics() -> FakeAnalytics:
    """10 documents: mzk 6 (one stored as " mzk"), nkp 2, 2 without a library; 2 without a year."""
    analytics = FakeAnalytics(
        10, yearIssued=counts([(1909.0, 3), (1910.0, 4), (1700.0, 1)]),
        library=counts([("mzk", 5), ("nkp", 2), (" mzk", 1)]), language=counts([("ces", 10)]))
    analytics.per_value = {
        "mzk": FakeAnalytics(6, yearIssued=counts([(1909.0, 3), (1910.0, 2)])),
        "nkp": FakeAnalytics(2, yearIssued=counts([(1910.0, 2)]))}
    return analytics


def rows_of(distribution):
    return [(r.library, r.kind, r.total_documents, [(y.year, y.count) for y in r.years], r.unknown_year_count)
            for r in distribution.rows]


async def test_library_years_count_each_document_once_and_the_rest_as_unknown():
    analytics = heatmap_analytics()

    result = await service.library_years(analytics, DocumentFilters(languages=["ces"]))

    assert (result.available, result.total_documents) == (True, 10)
    # " mzk" matches the same documents as "mzk" (field tokenization): one row.
    assert analytics.calls[1][:2] == ("library", ["mzk", "nkp"])
    assert analytics.calls[1][4] == [AnyOf("language", ("ces",))]  # the page's filters apply to every row
    assert rows_of(result) == [
        ("mzk", "value", 6, [(1909, 3), (1910, 2)], 1),
        ("nkp", "value", 2, [(1910, 2)], 0),
        # The documents without a library: the difference to the distributions.
        (None, "unknown", 2, [(1700, 1)], 1)]
    assert sum(r.total_documents for r in result.rows) == 10


async def test_library_years_list_at_most_20_libraries_and_name_the_rest_other_or_unknown():
    libraries = [(f"lib{i:02}", 1) for i in range(25)]
    analytics = FakeAnalytics(25, yearIssued=counts([(1900.0, 25)]), library=counts(libraries))
    analytics.per_value = {name: FakeAnalytics(1, yearIssued=counts([(1900.0, 1)])) for name, _ in libraries}

    result = await service.library_years(analytics, DocumentFilters())

    assert len(result.rows) == service.MAX_HEATMAP_LIBRARIES + 1
    assert rows_of(result)[-1] == (None, "other_or_unknown", 5, [(1900, 5)], 0)


@pytest.mark.parametrize("missing, unavailable_property", [("library", "library"), ("yearIssued", "publication_year")])
async def test_library_years_without_libraries_or_years_are_unavailable(missing, unavailable_property):
    analytics = heatmap_analytics()
    analytics.properties[missing] = Unavailable("missing")

    result = await service.library_years(analytics, DocumentFilters())

    assert (result.available, result.unavailable_reason, result.unavailable_property, result.rows) == \
        (False, "missing_property", unavailable_property, None)
    assert len(analytics.calls) == 1  # no per-library counts


async def test_library_years_that_do_not_add_up_fail_instead_of_misreporting():
    analytics = heatmap_analytics()
    analytics.per_value["nkp"] = FakeAnalytics(5, yearIssued=counts([(1910.0, 5)]))  # more than in the corpus

    with pytest.raises(service.IncompleteCounts):
        await service.library_years(analytics, DocumentFilters())
    assert len(analytics.calls) == 4  # counted twice: distributions and libraries, then again


async def test_library_years_are_counted_again_when_the_corpus_changed_between_the_readings():
    analytics = heatmap_analytics()
    consistent = analytics.per_value["nkp"]
    analytics.per_value["nkp"] = FakeAnalytics(5, yearIssued=counts([(1910.0, 5)]))  # read after documents were added
    count_per_value = analytics.count_documents_per_value

    async def changed_once(*args, **kwargs):
        result = await count_per_value(*args, **kwargs)
        analytics.per_value["nkp"] = consistent
        return result

    analytics.count_documents_per_value = changed_once

    result = await service.library_years(analytics, DocumentFilters())

    assert len(analytics.calls) == 4
    assert [(r.library, r.total_documents) for r in result.rows] == [("mzk", 6), ("nkp", 2), (None, 2)]


async def test_library_years_count_fresh_totals_while_the_overview_is_cached(tmp_path):
    # Review of #481: the unfiltered totals came from the overview cache while the libraries
    # were counted live, so documents added within CORPUS_OVERVIEW_MAX_AGE made them not add up.
    analytics = heatmap_analytics()
    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    app.dependency_overrides[get_corpus_analytics] = lambda: analytics
    async with LifespanManager(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        cached = await client.post(DISTRIBUTIONS, json={})
        # Two documents of nkp from 1910 added.
        analytics.total = 12
        analytics.properties.update(yearIssued=counts([(1909.0, 3), (1910.0, 6), (1700.0, 1)]),
                                    library=counts([("mzk", 5), ("nkp", 4), (" mzk", 1)]))
        analytics.per_value["nkp"] = FakeAnalytics(4, yearIssued=counts([(1910.0, 4)]))
        heatmap = await client.post(LIBRARY_YEARS, json={})
        again = await client.post(DISTRIBUTIONS, json={})

    assert cached.json()["total_documents"] == 10
    assert heatmap.status_code == 200
    assert heatmap.json()["total_documents"] == 12
    assert [(r["library"], r["total_documents"]) for r in heatmap.json()["rows"]] == \
        [("mzk", 6), ("nkp", 4), (None, 2)]
    # The page's distributions are still served from the cache until it expires.
    assert (again.json()["data_source"], again.json()["total_documents"]) == ("cached_aggregation", 10)


async def test_per_value_counts_run_at_most_a_few_at_once_across_requests():
    repository = CorpusAnalyticsRepository(client=None, collection_names=None)
    running, most = 0, 0

    async def property_types():
        return {"library": "text", "yearIssued": "number"}

    async def count(filters, properties, types, group_limit):
        nonlocal running, most
        running += 1
        most = max(most, running)
        for _ in range(3):
            await asyncio.sleep(0)
        running -= 1
        return DocumentCounts(total=1, properties={})

    repository._property_types = property_types
    repository._count = count
    values = [f"lib{i:02}" for i in range(20)]

    first, second = await asyncio.gather(*(
        repository.count_documents_per_value("library", values, {"yearIssued": "number"}, group_limit=10)
        for _ in range(2)))

    assert most == PER_VALUE_CONCURRENCY == 4
    assert list(first) == list(second) == values


async def test_library_years_are_answered_anonymously_and_refuse_unavailable_filters(tmp_path):
    analytics = heatmap_analytics()

    ok, refused = await _request(tmp_path, analytics, (LIBRARY_YEARS, {}),
                                 (LIBRARY_YEARS, {"filters": {"title_contains": ["brno"]}}))  # no title property

    assert ok.status_code == 200
    assert [r["library"] for r in ok.json()["rows"]] == ["mzk", "nkp", None]
    assert refused.status_code == 422
    schema = create_app(make_test_config(tmp_path)).openapi()
    operation = schema["paths"][LIBRARY_YEARS]["post"]
    assert "security" not in operation
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == \
        {"$ref": "#/components/schemas/LibraryYearDistribution"}
