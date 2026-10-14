"""HTTP routes of the Analytics feature; the rules live in ``service.py``."""
from fastapi import APIRouter, Depends

from semant_demo.adapters.weaviate.analytics import CorpusAnalyticsRepository
from semant_demo.features.analytics import service
from semant_demo.features.analytics.schemas import CorpusOverview
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
