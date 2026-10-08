from fastapi import APIRouter, Depends
from semant_demo import schemas
from semant_demo.summarization.templated import TemplatedSearchResultsSummarizer

from semant_demo.features.search import service
from semant_demo.features.search.service import SearchBackends
from semant_demo.routes.dependencies import get_search_backends, get_summarizer, get_search_filters
from semant_demo.users.auth import current_active_optional_user
from semant_demo.users.models import User

exp_router = APIRouter()


@exp_router.get("/api/search/filters", response_model=schemas.SearchFiltersResponse)
async def get_available_search_filters(
    filters_response: schemas.SearchFiltersResponse = Depends(get_search_filters),
) -> schemas.SearchFiltersResponse:
    return filters_response


@exp_router.post("/api/search", response_model=schemas.SearchResponse)
async def search(req: schemas.SearchRequest, backends: SearchBackends = Depends(get_search_backends),
                 summarizer: TemplatedSearchResultsSummarizer = Depends(get_summarizer),
                 current_user: User | None = Depends(current_active_optional_user),
                 available_filters: schemas.SearchFiltersResponse = Depends(get_search_filters)) -> schemas.SearchResponse:
    return await service.search(backends, summarizer, current_user, req, available_filters)
