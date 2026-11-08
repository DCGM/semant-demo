"""HTTP routes of the Analytics feature; the rules live in ``service.py``."""
from fastapi import APIRouter, Depends, HTTPException

from semant_demo.adapters.weaviate.analytics import CorpusAnalyticsRepository, UnavailableFilter
from semant_demo.config import Config
from semant_demo.features.analytics import service
from semant_demo.features.analytics.schemas import (
    CorpusDistributions, CorpusDistributionsRequest, CorpusOverview, LibraryYearDistribution, RankedResultsDistributions,
    RankedResultsDistributionsRequest)
from semant_demo.features.documents.criteria import ChunkVocabulary
from semant_demo.features.search.schemas import SearchFiltersResponse
from semant_demo.features.search.service import SearchBackends
from semant_demo.routes.dependencies import (
    get_chunk_vocabulary, get_config, get_corpus_analytics, get_corpus_overview_cache, get_search_backends,
    get_search_filters)
from semant_demo.users.auth import current_active_optional_user
from semant_demo.users.models import User

exp_router = APIRouter()


@exp_router.get("/api/analytics/corpus/overview", response_model=CorpusOverview)
async def corpus_overview(analytics: CorpusAnalyticsRepository = Depends(get_corpus_analytics),
                          cache: service.OverviewCache = Depends(get_corpus_overview_cache)) -> CorpusOverview:
    """
    Document counts of the searchable corpus (public): the total and the documents by
    publication decade, source library and document language, with unknown values and
    unavailable properties stated explicitly. A recent result may be served again
    (``data_source``, ``computed_at``).
    """
    return await service.cached_corpus_overview(analytics, cache)


@exp_router.post("/api/analytics/corpus/distributions", response_model=CorpusDistributions)
async def corpus_distributions(request: CorpusDistributionsRequest,
                               analytics: CorpusAnalyticsRepository = Depends(get_corpus_analytics),
                               cache: service.OverviewCache = Depends(get_corpus_overview_cache),
                               vocabulary: ChunkVocabulary = Depends(get_chunk_vocabulary)) -> CorpusDistributions:
    """
    Document counts of the searchable corpus (public) restricted by metadata filters and chunk
    filters: the matching total and the matching documents per publication year, source library
    and document language. Chunk filters apply per dimension (some chunk of the document has
    one of the values), as in document browsing. Without filters, a recent result may be served
    again. A filter on a property this corpus database does not record (including chunk filters
    without the documents' chunk-value summaries) is rejected (422), never answered with 0.
    """
    try:
        return await service.cached_corpus_distributions(analytics, cache, request.filters, request.chunk_filters,
                                                         vocabulary)
    except UnavailableFilter as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@exp_router.post("/api/analytics/corpus/library-years", response_model=LibraryYearDistribution)
async def corpus_library_years(request: CorpusDistributionsRequest,
                               analytics: CorpusAnalyticsRepository = Depends(get_corpus_analytics),
                               vocabulary: ChunkVocabulary = Depends(get_chunk_vocabulary)) -> LibraryYearDistribution:
    """
    Document counts of the searchable corpus (public) restricted by metadata filters, per
    source library and publication year: one row per library (most documents first) and one
    for the remaining documents. Computed on request; takes about as long again as the
    distributions. Filters are applied and rejected as for the distributions.
    """
    try:
        return await service.library_years(analytics, request.filters, request.chunk_filters, vocabulary)
    except UnavailableFilter as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@exp_router.post("/api/analytics/results/distributions", response_model=RankedResultsDistributions)
async def ranked_results_distributions(request: RankedResultsDistributionsRequest,
                                       analytics: CorpusAnalyticsRepository = Depends(get_corpus_analytics),
                                       backends: SearchBackends = Depends(get_search_backends),
                                       vocabulary: ChunkVocabulary = Depends(get_chunk_vocabulary),
                                       available_filters: SearchFiltersResponse = Depends(get_search_filters),
                                       current_user: User | None = Depends(current_active_optional_user),
                                       config: Config = Depends(get_config)) -> RankedResultsDistributions:
    """
    Counts of the ranked results of one text-query search (#619): exactly the ids that
    ``POST /api/search/documents`` (``ranked``) or ``POST /api/search/passages`` (``ranked_ids``)
    returned, with that search's criteria and collection, per publication year, source library and
    document language of their documents. Documents count once each; passages count as passages.
    Access and eligibility are checked again: ids the search could not return now (gone, no longer
    matching, outside the collection) are left out and reported (``missing_count``). The ranking's
    description (``ranking``) is echoed with the configured limit; a bounded ranking describes the
    retrieved results only. Without a text query, or with an id named twice: 422; more ids than the
    mode's limit or an unconfigured chunk filter: 400; a filter on a property the store does not
    record: 422.
    """
    limits = service.RankingLimits(
        documents=config.SEARCH_DOCUMENTS_METADATA_LIMIT + config.SEARCH_DOCUMENTS_CHUNK_LIMIT,
        passages=config.SEARCH_PASSAGES_LIMIT)
    try:
        return await service.ranked_results_distributions(analytics, backends, current_user, request, vocabulary,
                                                          available_filters, limits)
    except UnavailableFilter as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
