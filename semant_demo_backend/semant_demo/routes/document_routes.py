from fastapi import APIRouter, HTTPException, Query, Depends
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction

from semant_demo import schemas
from semant_demo.schema.documents import DocumentBrowse, Document
from semant_demo.features.collections import access
from semant_demo.routes.dependencies import get_search
from semant_demo.users.auth import current_active_optional_user, current_active_user
from semant_demo.users.models import User


exp_router = APIRouter()

@exp_router.get("/api/document/{document_id}", response_model=Document, response_model_exclude_none=True)
async def fetch_document(document_id: str, searcher: WeaviateAbstraction = Depends(get_search)) -> Document:
    """
    Retrieves document by its id
    """
    response = await searcher.document.read(document_id)
    if response is None:
        raise HTTPException(status_code=404, detail=f"Document with id {document_id} not found")
    return response

@exp_router.get("/api/documents/browse", response_model=DocumentBrowse, response_model_exclude_none=True)
async def browse_documents(collection_id: str | None = None,
                           limit: int = Query(default=50, ge=1, le=200),
                           offset: int = Query(default=0, ge=0),
                           sort_by: str | None = None,
                           sort_desc: bool = False,
                           title: str | None = None,
                           author: str | None = None,
                           publisher: str | None = None,
                           document_type: str | None = None,
                           searcher: WeaviateAbstraction = Depends(get_search),
                           current_user: User | None = Depends(current_active_optional_user)) -> DocumentBrowse:
    """
        Browses the corpus with pagination, filtering and sorting options. With ``collection_id``
        only that collection's documents are browsed, which needs read access to it.
    """
    if collection_id is not None:
        collection_id = str((await access.require_collection_read(searcher, current_user, collection_id)).collection_id)
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


@exp_router.get("/api/documents/{document_id}/{collection_id}/chunks", response_model=schemas.DocumentDetail, response_model_exclude_none=True)
async def fetch_document_chunks(document_id: str,
                                collection_id: str,
                                searcher: WeaviateAbstraction = Depends(get_search),
                                current_user: User = Depends(current_active_user)) -> schemas.DocumentDetail:
    """
    Retrieves all chunks for one document and marks whether each chunk belongs to the selected collection.
    """
    grant = await access.require_collection_read(searcher, current_user, collection_id)
    document = await access.require_document_in_collection(searcher, document_id, grant.collection_id)
    response = await searcher.document.read_document_chunks(document_id=str(document), collection_id=str(grant.collection_id))
    if response is None:
        raise HTTPException(status_code=404, detail=f"Document with id {document_id} not found")
    return response
