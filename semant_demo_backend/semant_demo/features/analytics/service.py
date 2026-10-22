"""Corpus overview (#254): how many documents the searchable corpus holds, by publication
decade, source library and document language; and the same counts per publication year for
the documents matching optional metadata filters (#361, ``corpus_distributions``).

Scope: the public corpus as Search covers it, i.e. every corpus document; anonymous users
may read it. ``Documents.public`` is not used: its values are not verified (#279). When a
public-read policy restricts documents, it must be applied by the counting query, before
anything is counted, so no restricted document is ever reflected in these numbers.

Counts are read from the store with native aggregates (no objects are downloaded). They
take about 2 s for 300,000 documents (docs/ARCHITECTURE.md), so the application keeps the
last unfiltered counts for ``CORPUS_OVERVIEW_MAX_AGE`` seconds (``OverviewCache``): within
that time they are served again with ``data_source="cached_aggregation"`` and their original
``computed_at``, and concurrent requests wait for one computation instead of starting their
own. The overview is derived from them. Filtered counts match fewer documents, take well under
a second and are always computed live (never answered from the unfiltered cache). A failed
read raises (an error response, never a zero or empty overview) and is not cached.

A year counts only when it is a whole number from 1 to the current year; later years (e.g. a
typo such as 2879) and fractional years are "unknown or invalid". A year range is filtered in
the store, so a document with year 1909.5 matches 1900–1920 but is counted as unknown.
"""
import asyncio
from collections import Counter
from datetime import UTC, datetime, timedelta

from semant_demo.adapters.weaviate.analytics import (
    AnyOf, Condition, ContainsWords, CorpusAnalyticsRepository, NumberRange, Unavailable, ValueCounts)
from semant_demo.features.analytics.schemas import (
    CategoryCount, CategoryDistribution, CorpusDistributions, CorpusOverview, DocumentFilters, LibraryYearDistribution,
    LibraryYears, PublicationYearCounts, PublicationYearDistribution, UnavailableReason, YearBin, YearCount)

YEAR_PROPERTY = "yearIssued"
LIBRARY_PROPERTY = "library"
LANGUAGE_PROPERTY = "language"
TITLE_PROPERTY = "title"

GROUP_LIMIT = 10_000
"""Most distinct values read per property. Valid years are whole numbers up to the current
year, so more distinct values mean malformed data; the counts then fail rather than guess."""
MAX_LISTED_VALUES = 50
"""Most library/language values listed; the documents of further values are ``other_count``."""
BIN_WIDTH_YEARS = 10
MIN_YEAR = 1
MAX_HEATMAP_LIBRARIES = 20
"""Most libraries with a row of their own in the library × year counts; the documents of the
others are counted in the row of the remaining documents."""


class IncompleteCounts(Exception):
    """The counts do not account for every document (e.g. the corpus changed between the
    aggregate queries, or a property has more distinct values than are read)."""


_REASONS: dict[str, UnavailableReason] = {"missing": "missing_property", "unsupported_type": "unsupported_type"}


class OverviewCache:
    """The last computed unfiltered counts of one application. There is one corpus scope today;
    once the public-read policy (#279) distinguishes readers, the cache must be kept per scope."""

    def __init__(self, max_age_seconds: float):
        self.max_age = timedelta(seconds=max_age_seconds)
        self.distributions: CorpusDistributions | None = None
        self.lock = asyncio.Lock()


async def cached_corpus_distributions(analytics: CorpusAnalyticsRepository, cache: OverviewCache,
                                      filters: DocumentFilters) -> CorpusDistributions:
    """Counts of the documents matching ``filters``; the unfiltered ones from the cache while
    they are younger than its maximum age."""
    if filters != DocumentFilters():
        return await corpus_distributions(analytics, filters)
    async with cache.lock:  # one computation at a time; waiting requests then get its result
        cached = cache.distributions
        if cached is not None and datetime.now(UTC) - cached.computed_at < cache.max_age:
            return cached.model_copy(update={"data_source": "cached_aggregation"})
        cache.distributions = await corpus_distributions(analytics, filters)
        return cache.distributions


async def cached_corpus_overview(analytics: CorpusAnalyticsRepository, cache: OverviewCache) -> CorpusOverview:
    """The overview of the cached unfiltered counts (see ``cached_corpus_distributions``)."""
    return _overview(await cached_corpus_distributions(analytics, cache, DocumentFilters()))


async def corpus_overview(analytics: CorpusAnalyticsRepository) -> CorpusOverview:
    """A new overview, computed from the store now."""
    return _overview(await corpus_distributions(analytics, DocumentFilters()))


async def corpus_distributions(analytics: CorpusAnalyticsRepository, filters: DocumentFilters) -> CorpusDistributions:
    """New counts of the documents matching ``filters``, computed from the store now. Raises
    ``UnavailableFilter`` (adapter) for a filter on a property the store cannot filter by."""
    computed_at = datetime.now(UTC)
    counts = await analytics.count_documents(
        {YEAR_PROPERTY: "number", LIBRARY_PROPERTY: "text", LANGUAGE_PROPERTY: "text"}, group_limit=GROUP_LIMIT,
        conditions=_conditions(filters))
    total = counts.total
    return CorpusDistributions(
        scope="searchable_corpus", unit="documents", filters=filters, total_documents=total,
        computed_at=computed_at, data_source="live_aggregation",
        publication_year=_years(counts.properties[YEAR_PROPERTY], total, max_year=computed_at.year),
        libraries=_categories(counts.properties[LIBRARY_PROPERTY], total, LIBRARY_PROPERTY),
        languages=_categories(counts.properties[LANGUAGE_PROPERTY], total, LANGUAGE_PROPERTY))


async def library_years(analytics: CorpusAnalyticsRepository, cache: OverviewCache,
                        filters: DocumentFilters) -> LibraryYearDistribution:
    """Documents per source library and publication year (#361, optional heatmap).

    Weaviate groups by one property only, so the years are counted once per library (a filter
    on that library) and the remaining documents are the difference to the distributions, which
    also gives the documents without a library (they cannot be filtered directly). Libraries
    whose stored values differ only in surrounding whitespace match the same documents
    (``field`` tokenization), so they are one row. Counting takes about as long again as the
    distributions, so it is only done on request and not cached."""
    distributions = await cached_corpus_distributions(analytics, cache, filters)
    base = dict(scope="searchable_corpus", unit="documents", filters=filters,
                total_documents=distributions.total_documents, computed_at=datetime.now(UTC))
    for prop, counted in (("library", distributions.libraries), ("publication_year", distributions.publication_year)):
        if not counted.available:
            return LibraryYearDistribution(**base, available=False, unavailable_reason=counted.unavailable_reason,
                                           unavailable_property=prop)

    merged: Counter[str] = Counter()
    for value in distributions.libraries.values or []:
        merged[value.value.strip()] += value.count
    every = sorted(merged, key=lambda library: (-merged[library], library))
    listed = every[:MAX_HEATMAP_LIBRARIES]
    counts = await analytics.count_documents_per_value(
        LIBRARY_PROPERTY, listed, {YEAR_PROPERTY: "number"}, group_limit=GROUP_LIMIT, conditions=_conditions(filters))

    rows: list[LibraryYears] = []
    rest = Counter({y.year: y.count for y in distributions.publication_year.years or []})
    rest_total = distributions.total_documents
    rest_unknown = distributions.publication_year.unknown_count or 0
    for library in listed:
        library_counts = counts[library]
        years = _years(library_counts.properties[YEAR_PROPERTY], library_counts.total, max_year=base["computed_at"].year)
        rows.append(LibraryYears(library=library, kind="value", total_documents=library_counts.total,
                                 years=years.years or [], unknown_year_count=years.unknown_count or 0))
        rest.subtract({y.year: y.count for y in years.years or []})
        rest_total -= library_counts.total
        rest_unknown -= years.unknown_count or 0
    if rest_total < 0 or rest_unknown < 0 or any(n < 0 for n in rest.values()):
        raise IncompleteCounts("Library and year counts do not add up (the corpus may have changed).")
    if rest_total:
        complete = len(listed) == len(every) and not distributions.libraries.other_count
        rows.append(LibraryYears(library=None, kind="unknown" if complete else "other_or_unknown",
                                 total_documents=rest_total, unknown_year_count=rest_unknown,
                                 years=[YearCount(year=y, count=n) for y, n in sorted(rest.items()) if n]))
    return LibraryYearDistribution(**base, available=True, rows=rows)


def _conditions(filters: DocumentFilters) -> list[Condition]:
    conditions: list[Condition] = []
    if filters.year_min is not None or filters.year_max is not None:
        conditions.append(NumberRange(YEAR_PROPERTY, filters.year_min, filters.year_max))
    if filters.title_contains:
        conditions.append(ContainsWords(TITLE_PROPERTY, filters.title_alternatives()))
    if filters.libraries:
        conditions.append(AnyOf(LIBRARY_PROPERTY, tuple(filters.libraries)))
    if filters.languages:
        conditions.append(AnyOf(LANGUAGE_PROPERTY, tuple(filters.languages)))
    return conditions


def _overview(distributions: CorpusDistributions) -> CorpusOverview:
    """The same counts with years grouped into decades; empty decades in between have count 0."""
    return CorpusOverview(
        scope=distributions.scope, unit=distributions.unit, total_documents=distributions.total_documents,
        computed_at=distributions.computed_at, data_source=distributions.data_source,
        publication_year=_decades(distributions.publication_year),
        libraries=distributions.libraries, languages=distributions.languages)


def _decades(years: PublicationYearCounts) -> PublicationYearDistribution:
    if not years.available:
        return PublicationYearDistribution(available=False, unavailable_reason=years.unavailable_reason)
    decades: Counter[int] = Counter()
    for year in years.years or []:
        decades[year.year // BIN_WIDTH_YEARS * BIN_WIDTH_YEARS] += year.count
    bins = [YearBin(start=start, end_exclusive=start + BIN_WIDTH_YEARS, count=decades[start])
            for start in range(min(decades), max(decades) + 1, BIN_WIDTH_YEARS)] if decades else []
    return PublicationYearDistribution(available=True, bin_width_years=BIN_WIDTH_YEARS, bins=bins,
                                       unknown_count=years.unknown_count)


def _check(counts: ValueCounts, total: int, prop: str) -> None:
    if not 0 <= counts.known <= total or sum(n for _, n in counts.groups) > counts.known:
        raise IncompleteCounts(f"Document counts of {prop} do not add up (the corpus may have changed).")


def _years(counts: ValueCounts | Unavailable, total: int, max_year: int) -> PublicationYearCounts:
    if isinstance(counts, Unavailable):
        return PublicationYearCounts(available=False, unavailable_reason=_REASONS[counts.reason])
    _check(counts, total, YEAR_PROPERTY)
    if not counts.complete:
        raise IncompleteCounts(f"More than {GROUP_LIMIT} distinct values of {YEAR_PROPERTY}.")
    years: Counter[int] = Counter()
    for value, n in counts.groups:
        year = float(value)
        if year.is_integer() and MIN_YEAR <= year <= max_year:
            years[int(year)] += n
    return PublicationYearCounts(available=True, years=[YearCount(year=y, count=years[y]) for y in sorted(years)],
                                 unknown_count=total - sum(years.values()))


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
