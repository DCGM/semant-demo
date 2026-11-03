"""HTTP routes of the Documents feature (public corpus reads); the rules live in ``service.py`` and ``pages.py``."""
import asyncio
import hashlib
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from pydantic import ValidationError

from semant_demo.adapters.filesystem.page_assets import MEDIA_TYPES, AssetKind, PageAssetStore
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.adapters.weaviate.criteria import UnavailableFilter
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.features.documents.criteria import ChunkFilters, ChunkVocabulary, DocumentFilters
from semant_demo.features.documents import pages, service
from semant_demo.routes.dependencies import get_chunk_vocabulary, get_page_assets, get_user_collections, get_documents
from semant_demo.features.documents.schemas import (
    AdjacentChunks, Document, DocumentBrowse, DocumentChunkWindow, DocumentDetail, DocumentPages, PageChunks)
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
                           year_min: int | None = None,
                           year_max: int | None = None,
                           title_contains: list[str] = Query(default=[]),
                           libraries: list[str] = Query(default=[]),
                           languages: list[str] = Query(default=[]),
                           chunk_languages: list[str] = Query(default=[]),
                           chunk_classifications: list[str] = Query(default=[]),
                           documents: DocumentRepository = Depends(get_documents),
                           collections: UserCollectionRepository = Depends(get_user_collections),
                           vocabulary: ChunkVocabulary = Depends(get_chunk_vocabulary),
                           current_user: User | None = Depends(current_active_optional_user)) -> DocumentBrowse:
    """
        Browses the corpus with pagination, filtering and sorting options. With ``collection_id``
        only that collection's documents are browsed, which needs read access to it.

        ``year_min``, ``year_max``, ``title_contains``, ``libraries`` and ``languages`` are the
        shared document filters (``DocumentFilters``; repeat a list parameter for alternatives):
        they select the same documents as the Analytics counts for them. ``title``, ``author``,
        ``publisher`` and ``document_type`` are older substring filters. A filter on a property
        this corpus database does not record is rejected (422).

        ``chunk_languages`` and ``chunk_classifications`` are the shared chunk filters
        (``ChunkFilters``): chunk languages, and ``<classification>:<value>`` pairs such as
        ``complexity:easy`` (repeat a parameter for alternatives). A document matches when, for
        each filter, some chunk of it has one of the values; different filters may be met by
        different chunks. They are answered from the documents' chunk-value summaries, as last
        recomputed: a document never recomputed matches no chunk filter, and a corpus database
        without the summaries rejects chunk filters (422). An unconfigured value is rejected (400).
    """
    try:
        filters = DocumentFilters(year_min=year_min, year_max=year_max, title_contains=title_contains,
                                  libraries=libraries, languages=languages)
    except ValidationError as e:
        raise _query_error(e.errors()) from e
    try:
        chunk_filters = ChunkFilters.from_query(chunk_languages, chunk_classifications)
    except ValidationError as e:
        errors = [{**error, "loc": ("chunk_languages" if error["loc"][:1] == ("languages",) else "chunk_classifications",
                                    *error["loc"][1:])} for error in e.errors()]
        raise _query_error(errors) from e
    except ValueError as e:
        raise _query_error([{"type": "invalid_filter", "loc": ("chunk_classifications",), "msg": str(e),
                             "input": chunk_classifications}]) from e
    try:
        return await service.browse(documents, collections, current_user, collection_id, filters=filters,
                                    chunk_filters=chunk_filters, vocabulary=vocabulary,
                                    limit=limit, offset=offset, sort_by=sort_by, sort_desc=sort_desc,
                                    title=title, author=author, publisher=publisher, document_type=document_type)
    except UnavailableFilter as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


def _query_error(errors: list[dict]) -> RequestValidationError:
    return RequestValidationError([{**error, "loc": ("query", *error["loc"])} for error in errors])


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


@exp_router.get("/api/documents/{document_id}/chunks/by_page", response_model=PageChunks,
                response_model_exclude_none=True)
async def read_document_page_chunks(
    document_id: str,
    page: int = Query(ge=0),
    limit: int = Query(default=20, ge=1, le=pages.MAX_PAGE_CHUNKS),
    documents: DocumentRepository = Depends(get_documents),
) -> PageChunks:
    """
    Returns, in document order, up to ``limit`` chunks whose page range (``from_page``..
    ``to_page``) includes page ``page`` (the page's ``order`` in the page manifest), and
    whether more do (public corpus data). Used to open a page directly.
    """
    return await pages.read_page_chunks(documents, document_id, page, limit)


@exp_router.get("/api/documents/{document_id}/pages", response_model=DocumentPages,
                response_model_exclude_none=True)
async def read_document_pages(document_id: str, response: Response,
                              documents: DocumentRepository = Depends(get_documents),
                              assets: PageAssetStore = Depends(get_page_assets)) -> DocumentPages:
    """
    Returns the document's pages in order, each with the URLs of its available image,
    layout file and thumbnail (public corpus data). ``available`` is false, with no pages,
    for a document without imported pages (a text-only document).
    """
    response.headers["Cache-Control"] = "no-cache"
    return await pages.read_pages(documents, assets, document_id)


ASSET_CACHE_CONTROL = {"image": "public, max-age=86400", "thumbnail": "public, max-age=86400", "layout": "no-cache"}
"""Scans and thumbnails do not change; a layout file is replaced when a document is
re-imported with other parameters, together with its chunks' anchors, so it is revalidated."""


@exp_router.get(
    "/api/documents/{document_id}/pages/{page_id}/{kind}",
    response_class=FileResponse,
    responses={200: {"content": {"image/jpeg": {}, "application/json": {}},
                     "description": "The page scan or thumbnail (JPEG) or the page layout file (JSON)."},
               304: {"description": "Not modified (``If-None-Match``)."},
               404: {"description": "Unknown document, or the asset is not available."}},
)
async def read_document_page_asset(document_id: str, page_id: str, kind: AssetKind, request: Request,
                                   documents: DocumentRepository = Depends(get_documents),
                                   assets: PageAssetStore = Depends(get_page_assets)) -> Response:
    """
    Returns one asset of a page (public corpus data): ``image`` (the scan) or ``thumbnail``
    (``image/jpeg``), or ``layout`` (the page layout file, ``application/json``,
    docs/PAGE_LAYOUT.md). 404 when it is not available. Answers ``If-None-Match`` with 304.
    """
    path = await pages.read_page_asset(documents, assets, document_id, page_id, kind)
    stat = await asyncio.to_thread(path.stat)
    etag = '"' + hashlib.sha256(f"{stat.st_mtime_ns}-{stat.st_size}".encode()).hexdigest()[:32] + '"'
    headers = {"Cache-Control": ASSET_CACHE_CONTROL[kind], "ETag": etag}
    if etag in [t.strip() for t in request.headers.get("if-none-match", "").split(",")]:
        return Response(status_code=304, headers=headers)
    return FileResponse(path, media_type=MEDIA_TYPES[kind], headers=headers, stat_result=stat)
