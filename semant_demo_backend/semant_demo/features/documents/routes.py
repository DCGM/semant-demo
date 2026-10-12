"""HTTP routes of the Documents feature (public corpus reads); the rules live in ``service.py``."""
from typing import Literal

from fastapi import APIRouter, Depends, Query

from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.features.documents import service
from semant_demo.routes.dependencies import get_user_collections, get_documents
from semant_demo.features.documents.schemas import AdjacentChunks, Document, DocumentBrowse, DocumentChunkWindow, DocumentDetail
from semant_demo.users.auth import current_active_optional_user, current_active_user
from semant_demo.users.models import User


exp_router = APIRouter()

@exp_router.get("/api/document/{document_id}", response_model=Document, response_model_exclude_none=True)
async def fetch_document(document_id: str, documents: DocumentRepository = Depends(get_documents)) -> Document:
    """
    Retrieves document by its id
    """
    return await service.read_document(documents, document_id)

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
                           documents: DocumentRepository = Depends(get_documents),
                           collections: UserCollectionRepository = Depends(get_user_collections),
                           current_user: User | None = Depends(current_active_optional_user)) -> DocumentBrowse:
    """
        Browses the corpus with pagination, filtering and sorting options. With ``collection_id``
        only that collection's documents are browsed, which needs read access to it.
    """
    return await service.browse(documents, collections, current_user, collection_id,
                                limit=limit, offset=offset, sort_by=sort_by, sort_desc=sort_desc,
                                title=title, author=author, publisher=publisher, document_type=document_type)


@exp_router.get("/api/user_collections/{collection_id}/documents/{document_id}", response_model=DocumentDetail, response_model_exclude_none=True)
async def fetch_collection_document(collection_id: str,
                                    document_id: str,
                                    documents: DocumentRepository = Depends(get_documents),
                                    collections: UserCollectionRepository = Depends(get_user_collections),
                                    current_user: User = Depends(current_active_user)) -> DocumentDetail:
    """
    Retrieves the document with all its chunks and marks whether each chunk belongs to the collection.
    Collection-scoped (needs read access); corpus-only document reads stay under ``/api/documents``.
    """
    return await service.read_chunks_in_collection(documents, collections, current_user, document_id, collection_id)


@exp_router.get(
    "/api/documents/{document_id}/chunks/count",
    response_model=int,
)
async def count_document_chunks(
    document_id: str,
    documents: DocumentRepository = Depends(get_documents),
) -> int:
    """Returns the total number of chunks in the given document (public corpus data)."""
    return await service.count_chunks(documents, document_id)


@exp_router.get(
    "/api/documents/{document_id}/chunks/{chunk_id}/window",
    response_model=DocumentChunkWindow,
    response_model_exclude_none=True,
)
async def read_document_chunk_window(
    document_id: str,
    chunk_id: str,
    before: int = Query(default=3, ge=0, le=service.MAX_WINDOW_SIDE),
    after: int = Query(default=3, ge=0, le=service.MAX_WINDOW_SIDE),
    documents: DocumentRepository = Depends(get_documents),
) -> DocumentChunkWindow:
    """
    Returns the chunk and up to ``before``/``after`` neighbouring chunks of its document,
    in document order (public corpus data). Used to show a search hit in its context.
    """
    return await service.read_chunk_window(documents, document_id, chunk_id, before, after)


@exp_router.get(
    "/api/documents/{document_id}/chunks/{chunk_id}/adjacent",
    response_model=AdjacentChunks,
    response_model_exclude_none=True,
)
async def read_document_adjacent_chunks(
    document_id: str,
    chunk_id: str,
    direction: Literal["before", "after"],
    limit: int = Query(default=5, ge=1, le=service.MAX_WINDOW_SIDE),
    documents: DocumentRepository = Depends(get_documents),
) -> AdjacentChunks:
    """
    Returns up to ``limit`` chunks directly before or after the chunk, in document order,
    without the chunk itself (public corpus data). Extends a passage read with ``/window``
    without reading the document metadata or chunk count again.
    """
    return await service.read_adjacent_chunks(documents, document_id, chunk_id, direction, limit)
