import time

from fastapi import APIRouter, Depends, HTTPException
from semant_demo import schemas
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction
from semant_demo.summarization.templated import TemplatedSearchResultsSummarizer

from semant_demo.routes.dependencies import get_search, get_summarizer
from semant_demo.users.auth import current_active_optional_user
from semant_demo.users.models import User

exp_router = APIRouter()


@exp_router.post("/api/search", response_model=schemas.SearchResponse)
async def search(req: schemas.SearchRequest, searcher: WeaviateAbstraction = Depends(get_search),
                 summarizer: TemplatedSearchResultsSummarizer = Depends(get_summarizer),
                 current_user: User | None = Depends(current_active_optional_user)) -> schemas.SearchResponse:
    start_time = time.time()

    # <authorization>
    if req.user_collection_id is not None:
        if current_user is None:
            raise HTTPException(status_code=401,
                                detail="Unauthorized: user collection specified but no user authenticated")
        collections = await searcher.userCollection.read_all(current_user)
        user_collection_ids = {str(col.id) for col in collections}
        if req.user_collection_id not in user_collection_ids:
            raise HTTPException(status_code=403,
                                detail="Forbidden: user does not have access to the specified collection")

    # </authorization>

    response = await searcher.textChunk.search(req)
    await summarizer(req, response)

    response.time_spent = time.time() - start_time
    return response
