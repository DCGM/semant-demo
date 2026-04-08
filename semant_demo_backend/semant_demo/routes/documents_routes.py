from fastapi import APIRouter, Depends, Query
from uuid import UUID
from semant_demo.routes.dependencies import get_weaviate_client
from semant_demo.weaviate_client import WeaviateClient
from semant_demo.schema.documents import Document, DocumentBrowse

router = APIRouter()

@router.get("/api/v1/documents/browse", response_model=DocumentBrowse, response_model_exclude_none=True)
async def browse_documents(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort_by: str | None = None,
    sort_desc: bool = False,
    collection_id: UUID | None = None,
    title: str | None = None,
    author: str | None = None,
    publisher: str | None = None,
    document_type: str | None = None,
    wv_client: WeaviateClient = Depends(get_weaviate_client),
) -> DocumentBrowse:
    return await wv_client.browse_documents(
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_desc=sort_desc,
        collection_id=collection_id,
        title=title,
        author=author,
        publisher=publisher,
        document_type=document_type,
    )

@router.get("/api/v1/documents", response_model=list[Document], response_model_exclude_none=True)
async def get_documents(collection_id: UUID | None = None, wv_client: WeaviateClient = Depends(get_weaviate_client)) -> list[Document]:
    documents = await wv_client.get_all_documents(collection_id=collection_id)
    return [document.model_dump(by_alias=False) for document in documents]


@router.get("/api/v1/documents/{document_id}", response_model=Document, response_model_exclude_none=True)
async def get_document(document_id: str, wv_client: WeaviateClient = Depends(get_weaviate_client)) -> Document:
    document = await wv_client.get_document_by_id(document_id)
    return document.model_dump(by_alias=False)
