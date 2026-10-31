from fastapi import APIRouter, Depends, HTTPException

from semant_demo.adapters.weaviate.criteria import UnavailableFilter
from semant_demo.features.search.schemas import SearchFiltersResponse, SearchRequest, SearchResponse, SearchVectorsResponse

from semant_demo.features.quota.principal import get_allowance_budget
from semant_demo.features.quota.service import AllowanceBudget
from semant_demo.features.search import service
from semant_demo.features.search.service import SearchBackends
from semant_demo.features.search.vectors import SearchVectors
from semant_demo.routes.dependencies import get_search_backends, get_summarizer, get_search_filters, get_search_vectors
from semant_demo.users.auth import current_active_optional_user
from semant_demo.users.models import User

exp_router = APIRouter()


@exp_router.get("/api/search/filters", response_model=SearchFiltersResponse)
async def get_available_search_filters(
    filters_response: SearchFiltersResponse = Depends(get_search_filters),
) -> SearchFiltersResponse:
    return filters_response


@exp_router.get("/api/search/vectors", response_model=SearchVectorsResponse)
async def get_available_search_vectors(vectors: SearchVectors = Depends(get_search_vectors)) -> SearchVectorsResponse:
    """The search vectors a search request may select, and the default one."""
    return vectors.describe()


@exp_router.post("/api/search", response_model=SearchResponse)
async def search(req: SearchRequest, backends: SearchBackends = Depends(get_search_backends),
                 summarizer: service.Summarizer = Depends(get_summarizer),
                 current_user: User | None = Depends(current_active_optional_user),
                 available_filters: SearchFiltersResponse = Depends(get_search_filters),
                 budget: AllowanceBudget = Depends(get_allowance_budget)) -> SearchResponse:
    """Retrieval, plus the titles and summaries asked for. Those are skipped with a warning
    (``quota_exhausted``) when the daily AI allowance has no room; the results are not.
    A document or chunk filter on a property this corpus database does not record is rejected
    (422), never answered with no results."""
    try:
        return await service.search(backends, summarizer, current_user, req, available_filters, budget)
    except UnavailableFilter as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
