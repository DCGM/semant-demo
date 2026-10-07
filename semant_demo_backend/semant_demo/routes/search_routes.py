import time

from fastapi import APIRouter, Depends, HTTPException
from semant_demo import schemas
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction
from semant_demo.summarization.templated import TemplatedSearchResultsSummarizer

from semant_demo.features.collections import access
from semant_demo.routes.dependencies import get_search, get_summarizer, get_search_filters
from semant_demo.users.auth import current_active_optional_user
from semant_demo.users.models import User

exp_router = APIRouter()


@exp_router.get("/api/search/filters", response_model=schemas.SearchFiltersResponse)
async def get_available_search_filters(
    filters_response: schemas.SearchFiltersResponse = Depends(get_search_filters),
) -> schemas.SearchFiltersResponse:
    return filters_response


@exp_router.post("/api/search", response_model=schemas.SearchResponse)
async def search(req: schemas.SearchRequest, searcher: WeaviateAbstraction = Depends(get_search),
                 summarizer: TemplatedSearchResultsSummarizer = Depends(get_summarizer),
                 current_user: User | None = Depends(current_active_optional_user),
                 available_filters: schemas.SearchFiltersResponse = Depends(get_search_filters)) -> schemas.SearchResponse:
    start_time = time.time()

    # Searching within a collection needs read access to it (direct lookup, not listing).
    if req.user_collection_id is not None:
        await access.require_collection_read(searcher, current_user, req.user_collection_id)

    # Parse and validate search filters
    filters = None
    if isinstance(available_filters, schemas.SearchFiltersResponse):
        from semant_demo.search_filters import parse_and_validate_search_filters, InvalidSearchFilterError
        try:
            filters = parse_and_validate_search_filters(req.filters, available_filters)
        except (InvalidSearchFilterError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e))

    response = await searcher.textChunk.search(req, filters=filters)

    await summarizer(req, response)

    response.time_spent = time.time() - start_time
    return response

