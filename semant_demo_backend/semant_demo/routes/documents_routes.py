from fastapi import APIRouter, Query, Depends
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction

from semant_demo_backend.semant_demo.schema.documents import DocumentBrowse
from semant_demo.routes.dependencies import get_search


exp_router = APIRouter()


@exp_router.get("/api/documents/browse", response_model=DocumentBrowse, response_model_exclude_none=True)
async def browse_documents(collection_id: str,
                           limit: int = Query(default=50, ge=1, le=200),
                           offset: int = Query(default=0, ge=0),
                           sort_by: str | None = None,
                           sort_desc: bool = False,
                           title: str | None = None,
                           author: str | None = None,
                           publisher: str | None = None,
                           document_type: str | None = None,
                           searcher: WeaviateAbstraction = Depends(get_search)) -> DocumentBrowse:
    """
        Browses documents which belong to collection given by id with pagination, filtering and sorting options
    """
    return await searcher.document.browse_documents(
        collection_id=collection_id,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_desc=sort_desc,
        title=title,
        author=author,
        publisher=publisher,
        document_type=document_type
    )
