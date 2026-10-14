"""Corpus overview (features/analytics, #254) with a stand-in repository.

Counts are distinct documents; for each available dimension the bins/values, ``other_count``
and ``unknown_count`` add up to the total; an unavailable property has no counts (``null``).
A recent overview is served again, marked as cached, with its original ``computed_at``.
Real aggregation semantics are tested in ``integration/test_corpus_analytics.py``.
"""
import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from semant_demo.adapters.weaviate.analytics import DocumentCounts, Unavailable, ValueCounts
from semant_demo.features.analytics import service
from semant_demo.main import create_app
from semant_demo.routes.dependencies import get_corpus_analytics
from tests.app_support import make_test_config, offline_weaviate

PATH = "/api/analytics/corpus/overview"


class FakeAnalytics:
    def __init__(self, total: int, **properties: ValueCounts | Unavailable):
        self.total = total
        self.properties = properties
        self.calls: list[tuple[dict, int]] = []

    async def count_documents(self, properties, group_limit):
        self.calls.append((properties, group_limit))
        await asyncio.sleep(0)
        return DocumentCounts(total=self.total, properties={
            prop: self.properties.get(prop, Unavailable("missing")) for prop in properties})


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

    assert analytics.calls == [({"yearIssued": "number", "library": "text", "language": "text"}, service.GROUP_LIMIT)]
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
        yearIssued=counts([(0.0, 1), (1909.5, 1), (-5.0, 1), (12000.0, 1), (1900.0, 2)]),
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
    cache.overview = first.model_copy(update={"computed_at": first.computed_at - timedelta(seconds=601)})
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
        async def count_documents(self, properties, group_limit):
            if not self.calls:
                self.calls.append("failed")
                raise RuntimeError("store unavailable")
            return await super().count_documents(properties, group_limit)

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
        async def count_documents(self, properties, group_limit):
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
