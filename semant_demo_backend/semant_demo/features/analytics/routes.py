"""HTTP routes of the Analytics feature; the rules live in ``service.py``."""
from fastapi import APIRouter, Depends, HTTPException

from semant_demo.adapters.weaviate.analytics import CorpusAnalyticsRepository, UnavailableFilter
from semant_demo.features.analytics import service
from semant_demo.features.analytics.schemas import (
    CorpusDistributions, CorpusDistributionsRequest, CorpusOverview, LibraryYearDistribution)
from semant_demo.routes.dependencies import get_corpus_analytics, get_corpus_overview_cache

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
                               cache: service.OverviewCache = Depends(get_corpus_overview_cache)) -> CorpusDistributions:
    """
    Document counts of the searchable corpus (public) restricted by metadata filters: the
    matching total and the matching documents per publication year, source library and
    document language. Without filters, a recent result may be served again. A filter on a
    property this corpus database does not record is rejected (422), never answered with 0.
    """
    try:
        return await service.cached_corpus_distributions(analytics, cache, request.filters)
    except UnavailableFilter as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@exp_router.post("/api/analytics/corpus/library-years", response_model=LibraryYearDistribution)
async def corpus_library_years(request: CorpusDistributionsRequest,
                               analytics: CorpusAnalyticsRepository = Depends(get_corpus_analytics),
                               cache: service.OverviewCache = Depends(get_corpus_overview_cache)) -> LibraryYearDistribution:
    """
    Document counts of the searchable corpus (public) restricted by metadata filters, per
    source library and publication year: one row per library (most documents first) and one
    for the remaining documents. Computed on request; takes about as long again as the
    distributions.
    """
    try:
        return await service.library_years(analytics, cache, request.filters)
    except UnavailableFilter as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
