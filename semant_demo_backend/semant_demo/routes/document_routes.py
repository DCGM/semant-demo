from fastapi import APIRouter, HTTPException, Query, Depends
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction

from semant_demo import schemas
from semant_demo.schema.documents import DocumentBrowse, Document
from semant_demo.routes.dependencies import get_search


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


@exp_router.get("/api/documents/{document_id}/{collection_id}/chunks", response_model=schemas.DocumentDetail, response_model_exclude_none=True)
async def fetch_document_chunks(document_id: str,
                                collection_id: str,
                                searcher: WeaviateAbstraction = Depends(get_search)) -> schemas.DocumentDetail:
    """
    Retrieves all chunks for one document and marks whether each chunk belongs to the selected collection.
    """
    response = await searcher.document.read_document_chunks(document_id=document_id, collection_id=collection_id)
    if response is None:
        raise HTTPException(status_code=404, detail=f"Document with id {document_id} not found")
    return response
