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

Ranked results (#619, ``ranked_results_distributions``): the same counts over exactly the ids
a text-query search ranked (Documents or Passages Results), read by id under that search's
access and eligibility again; see the function.

A year counts only when it is a whole number from 1 to the current year; later years (e.g. a
typo such as 2879) and fractional years are "unknown or invalid". A year range is filtered in
the store, so a document with year 1909.5 matches 1900–1920 but is counted as unknown.
"""
import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from semant_demo.adapters.weaviate.analytics import CorpusAnalyticsRepository, Unavailable, ValueCounts
from semant_demo.core.errors import InvalidRequestError
from semant_demo.features.analytics.schemas import (
    CategoryCount, CategoryDistribution, CorpusDistributions, CorpusOverview, DocumentFilters, LibraryYearDistribution,
    LibraryYears, PublicationYearCounts, PublicationYearDistribution, RankedResultsDistributions,
    RankedResultsDistributionsRequest, RankingScope, ResultMember, UnavailableReason, YearBin, YearCount)
from semant_demo.features.documents import service as document_service
from semant_demo.features.documents.criteria import (
    LANGUAGE_PROPERTY, LIBRARY_PROPERTY, YEAR_PROPERTY, ChunkFilters, ChunkVocabulary, Condition,
    document_level_conditions)
from semant_demo.features.search import service as search_service
from semant_demo.features.search.schemas import SearchFiltersResponse, SearchType
from semant_demo.features.user_collections.access import Principal

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
                                      filters: DocumentFilters, chunk_filters: ChunkFilters | None = None,
                                      vocabulary: ChunkVocabulary | None = None) -> CorpusDistributions:
    """Counts of the documents matching ``filters`` and ``chunk_filters`` (per dimension, on the
    documents' chunk-value summaries, checked against ``vocabulary``); the unfiltered ones from
    the cache while they are younger than its maximum age."""
    if filters != DocumentFilters() or (chunk_filters is not None and not chunk_filters.is_empty()):
        return await corpus_distributions(analytics, filters, chunk_filters, vocabulary)
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


async def corpus_distributions(analytics: CorpusAnalyticsRepository, filters: DocumentFilters,
                               chunk_filters: ChunkFilters | None = None,
                               vocabulary: ChunkVocabulary | None = None) -> CorpusDistributions:
    """New counts of the documents matching ``filters`` and ``chunk_filters``, computed from the
    store now. Raises ``InvalidChunkFilterError`` for an unconfigured chunk filter and
    ``UnavailableFilter`` (adapter) for a filter on a property the store cannot filter by
    (e.g. chunk filters on a store without the chunk-value summaries)."""
    chunks, conditions = document_level_conditions(filters, chunk_filters, vocabulary)
    return await _distributions(analytics, filters, chunks, conditions)


async def _distributions(analytics: CorpusAnalyticsRepository, filters: DocumentFilters, chunk_filters: ChunkFilters,
                         conditions: list[Condition]) -> CorpusDistributions:
    computed_at = datetime.now(UTC)
    counts = await analytics.count_documents(
        {YEAR_PROPERTY: "number", LIBRARY_PROPERTY: "text", LANGUAGE_PROPERTY: "text"}, group_limit=GROUP_LIMIT,
        conditions=conditions)
    total = counts.total
    return CorpusDistributions(
        scope="searchable_corpus", unit="documents", filters=filters, chunk_filters=chunk_filters,
        total_documents=total,
        computed_at=computed_at, data_source="live_aggregation",
        publication_year=_years(counts.properties[YEAR_PROPERTY], total, max_year=computed_at.year),
        libraries=_categories(counts.properties[LIBRARY_PROPERTY], total, LIBRARY_PROPERTY),
        languages=_categories(counts.properties[LANGUAGE_PROPERTY], total, LANGUAGE_PROPERTY))


async def library_years(analytics: CorpusAnalyticsRepository, filters: DocumentFilters,
                        chunk_filters: ChunkFilters | None = None,
                        vocabulary: ChunkVocabulary | None = None) -> LibraryYearDistribution:
    """Documents per source library and publication year (#361, optional heatmap), restricted as
    ``corpus_distributions`` is.

    Weaviate groups by one property only, so the years are counted once per library (a filter
    on that library) and the remaining documents are the difference to the distributions, which
    also gives the documents without a library (they cannot be filtered directly). Libraries
    whose stored values differ only in surrounding whitespace match the same documents
    (``field`` tokenization), so they are one row. Counting takes about as long again as the
    distributions, so it is only done on request and not cached.

    The distributions are computed now, never taken from the ``OverviewCache``: older totals
    and live per-library counts would not add up. When the corpus changes between the
    readings, everything is counted once more before ``IncompleteCounts`` is raised."""
    chunks, conditions = document_level_conditions(filters, chunk_filters, vocabulary)
    try:
        return await _library_years(analytics, filters, chunks, conditions)
    except IncompleteCounts:
        return await _library_years(analytics, filters, chunks, conditions)


async def _library_years(analytics: CorpusAnalyticsRepository, filters: DocumentFilters, chunk_filters: ChunkFilters,
                         conditions: list[Condition]) -> LibraryYearDistribution:
    distributions = await _distributions(analytics, filters, chunk_filters, conditions)
    base = dict(scope="searchable_corpus", unit="documents", filters=filters, chunk_filters=chunk_filters,
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
        LIBRARY_PROPERTY, listed, {YEAR_PROPERTY: "number"}, group_limit=GROUP_LIMIT, conditions=conditions)

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


@dataclass(frozen=True)
class RankingLimits:
    """The configured size of a ranking per results mode (``config.py``)."""
    documents: int
    """``SEARCH_DOCUMENTS_METADATA_LIMIT + SEARCH_DOCUMENTS_CHUNK_LIMIT``."""
    passages: int
    """``SEARCH_PASSAGES_LIMIT``."""


_COUNTED = {YEAR_PROPERTY: "number", LIBRARY_PROPERTY: "text", LANGUAGE_PROPERTY: "text"}


async def ranked_results_distributions(analytics: CorpusAnalyticsRepository, search: search_service.SearchBackends,
                                       user: Principal | None, request: RankedResultsDistributionsRequest,
                                       vocabulary: ChunkVocabulary, filter_definitions: SearchFiltersResponse | None,
                                       limits: RankingLimits) -> RankedResultsDistributions:
    """Counts of the ranked results of one text-query search (#619): exactly the ids its Results
    hold, by their document's publication year, library and language.

    The ids, criteria and collection come from the client, so none is trusted: read access to the
    collection is checked again and each id is read under the eligibility of its mode, as the
    search's later pages are (``search.service.read_documents``/``read_passages``). Documents: in
    the collection, meeting the document filters and, per dimension, the chunk filters (#529);
    passages: in the collection, the document filters on their document and every chunk filter
    on the passage itself (same-chunk, #526). Ids that do not pass, also unknown or forged ones,
    are not counted (``missing_count``). Nothing is ranked, embedded or scanned: only the named
    records are read, without text or vectors, in bounded batches; a property the store cannot
    count is unavailable for every result. Documents are counted once each; passages each count
    once, also several of one document (``distinct_documents`` tells them apart).

    The ranking itself (``ranking``) is the client's description of its search and is echoed; the
    vector must be a configured one. Raises ``InvalidRequestError`` for more ids than the mode's
    configured limit.
    """
    computed_at = datetime.now(UTC)
    limit = limits.documents if request.mode == "documents" else limits.passages
    if len(request.ids) > limit:
        raise InvalidRequestError(f"A {request.mode} ranking holds at most {limit} results; {len(request.ids)} were named.")
    ranking = request.ranking
    vector = None if ranking.type == SearchType.text else search.vectors.resolve(ranking.vector).id

    availability = await analytics.availability(_COUNTED)
    readable = [prop for prop, unavailable in availability.items() if unavailable is None]
    criteria = request.criteria
    records: list[tuple[UUID, UUID, dict[str, Any]]]
    if request.mode == "documents":
        chunk_filters, _ = document_level_conditions(None, criteria.chunk_filters, vocabulary)
        scope, conditions = await document_service.browse_scope(
            search.collections, user, request.user_collection_id, criteria.document_filters, criteria.chunk_filters,
            vocabulary)
        criteria = criteria.model_copy(update={"chunk_filters": chunk_filters})
        found = await analytics.document_values(request.ids, readable, scope, conditions)
        records = [(i, i, found[i]) for i in request.ids if i in found]
    else:
        criteria, records = await search_service.passage_document_values(
            search, user, request.ids, criteria, request.user_collection_id, filter_definitions, readable)

    total = len(records)
    max_year = computed_at.year

    def counts(prop: str) -> ValueCounts | Unavailable:
        unavailable = availability[prop]
        if unavailable is not None:
            return unavailable
        values = [values[prop] for _, _, values in records if values.get(prop) is not None]
        groups = Counter(values).most_common()
        return ValueCounts(known=len(values), groups=groups, complete=True)

    members = None
    if request.members:
        members = [ResultMember(id=i, document_id=d, year=_valid_year(values.get(YEAR_PROPERTY), max_year),
                                library=_known(values.get(LIBRARY_PROPERTY)), language=_known(values.get(LANGUAGE_PROPERTY)))
                   for i, d, values in records]
    return RankedResultsDistributions(
        scope="ranked_results", mode=request.mode, unit=request.mode, criteria=criteria,
        ranking=RankingScope(type=ranking.type, vector=vector, bounded=ranking.bounded, retrieval_limit=limit),
        input_count=len(request.ids), total_count=total, missing_count=len(request.ids) - total,
        distinct_documents=len({d for _, d, _ in records}), computed_at=computed_at,
        publication_year=_years(counts(YEAR_PROPERTY), total, max_year=max_year),
        libraries=_categories(counts(LIBRARY_PROPERTY), total, LIBRARY_PROPERTY),
        languages=_categories(counts(LANGUAGE_PROPERTY), total, LANGUAGE_PROPERTY),
        members=members)


def _valid_year(value: Any, max_year: int) -> int | None:
    """The year as ``_years`` counts it, or None when it is counted as unknown."""
    if value is None:
        return None
    year = float(value)
    return int(year) if year.is_integer() and MIN_YEAR <= year <= max_year else None


def _known(value: Any) -> str | None:
    """The value as ``_categories`` lists it, or None when it is counted as unknown."""
    return str(value) if value is not None and str(value).strip() else None


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
