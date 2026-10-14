"""Corpus overview (#254): how many documents the searchable corpus holds, by publication
decade, source library and document language.

Scope: the public corpus as Search covers it, i.e. every corpus document; anonymous users
may read it. ``Documents.public`` is not used: its values are not verified (#279). When a
public-read policy restricts documents, it must be applied by the counting query, before
anything is counted, so no restricted document is ever reflected in these numbers.

Counts are read from the store with native aggregates (no objects are downloaded). They
take about 2 s for 300,000 documents (docs/ARCHITECTURE.md), so the application keeps the
last overview for ``CORPUS_OVERVIEW_MAX_AGE`` seconds (``OverviewCache``): within that time
it is served again with ``data_source="cached_aggregation"`` and its original ``computed_at``,
and concurrent requests wait for one computation instead of starting their own. A failed
read raises (an error response, never a zero or empty overview) and is not cached.
"""
import asyncio
from collections import Counter
from datetime import UTC, datetime, timedelta

from semant_demo.adapters.weaviate.analytics import CorpusAnalyticsRepository, Unavailable, ValueCounts
from semant_demo.features.analytics.schemas import (
    CategoryCount, CategoryDistribution, CorpusOverview, PublicationYearDistribution, UnavailableReason, YearBin)

YEAR_PROPERTY = "yearIssued"
LIBRARY_PROPERTY = "library"
LANGUAGE_PROPERTY = "language"

GROUP_LIMIT = 10_000
"""Most distinct values read per property. Years are whole numbers up to 9999, so more
distinct values mean malformed data; the overview then fails rather than guess."""
MAX_LISTED_VALUES = 50
"""Most library/language values listed; the documents of further values are ``other_count``."""
BIN_WIDTH_YEARS = 10
MIN_YEAR, MAX_YEAR = 1, 9999


class IncompleteCounts(Exception):
    """The counts do not account for every document (e.g. the corpus changed between the
    aggregate queries, or a property has more distinct values than are read)."""


_REASONS: dict[str, UnavailableReason] = {"missing": "missing_property", "unsupported_type": "unsupported_type"}


class OverviewCache:
    """The last computed overview of one application. There is one corpus scope today; once
    the public-read policy (#279) distinguishes readers, the cache must be kept per scope."""

    def __init__(self, max_age_seconds: float):
        self.max_age = timedelta(seconds=max_age_seconds)
        self.overview: CorpusOverview | None = None
        self.lock = asyncio.Lock()


async def cached_corpus_overview(analytics: CorpusAnalyticsRepository, cache: OverviewCache) -> CorpusOverview:
    """The cached overview while it is younger than the cache's maximum age, else a new one."""
    async with cache.lock:  # one computation at a time; waiting requests then get its result
        cached = cache.overview
        if cached is not None and datetime.now(UTC) - cached.computed_at < cache.max_age:
            return cached.model_copy(update={"data_source": "cached_aggregation"})
        cache.overview = await corpus_overview(analytics)
        return cache.overview


async def corpus_overview(analytics: CorpusAnalyticsRepository) -> CorpusOverview:
    """A new overview, computed from the store now."""
    computed_at = datetime.now(UTC)
    counts = await analytics.count_documents(
        {YEAR_PROPERTY: "number", LIBRARY_PROPERTY: "text", LANGUAGE_PROPERTY: "text"}, group_limit=GROUP_LIMIT)
    total = counts.total
    return CorpusOverview(
        scope="searchable_corpus", unit="documents", total_documents=total,
        computed_at=computed_at, data_source="live_aggregation",
        publication_year=_years(counts.properties[YEAR_PROPERTY], total),
        libraries=_categories(counts.properties[LIBRARY_PROPERTY], total, LIBRARY_PROPERTY),
        languages=_categories(counts.properties[LANGUAGE_PROPERTY], total, LANGUAGE_PROPERTY))


def _check(counts: ValueCounts, total: int, prop: str) -> None:
    if not 0 <= counts.known <= total or sum(n for _, n in counts.groups) > counts.known:
        raise IncompleteCounts(f"Document counts of {prop} do not add up (the corpus may have changed).")


def _years(counts: ValueCounts | Unavailable, total: int) -> PublicationYearDistribution:
    if isinstance(counts, Unavailable):
        return PublicationYearDistribution(available=False, unavailable_reason=_REASONS[counts.reason])
    _check(counts, total, YEAR_PROPERTY)
    if not counts.complete:
        raise IncompleteCounts(f"More than {GROUP_LIMIT} distinct values of {YEAR_PROPERTY}.")
    decades: Counter[int] = Counter()
    for value, n in counts.groups:
        year = float(value)
        if year.is_integer() and MIN_YEAR <= year <= MAX_YEAR:
            decades[int(year) // BIN_WIDTH_YEARS * BIN_WIDTH_YEARS] += n
    bins = [YearBin(start=start, end_exclusive=start + BIN_WIDTH_YEARS, count=decades[start])
            for start in range(min(decades), max(decades) + 1, BIN_WIDTH_YEARS)] if decades else []
    return PublicationYearDistribution(available=True, bin_width_years=BIN_WIDTH_YEARS, bins=bins,
                                       unknown_count=total - sum(decades.values()))


def _categories(counts: ValueCounts | Unavailable, total: int, prop: str) -> CategoryDistribution:
    if isinstance(counts, Unavailable):
        return CategoryDistribution(available=False, unavailable_reason=_REASONS[counts.reason])
    _check(counts, total, prop)
    values = sorted(((str(value), n) for value, n in counts.groups if str(value).strip()),
                    key=lambda item: (-item[1], item[0]))
    blank = sum(n for value, n in counts.groups if not str(value).strip())
    listed = values[:MAX_LISTED_VALUES]
    # Unlisted values, including any beyond the group limit (their blanks cannot be told apart).
    other = counts.known - blank - sum(n for _, n in listed)
    return CategoryDistribution(available=True, values=[CategoryCount(value=v, count=n) for v, n in listed],
                                other_count=other, unknown_count=total - counts.known + blank)
