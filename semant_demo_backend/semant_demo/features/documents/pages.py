"""Document pages: the page manifest, page assets and the chunks of a page (#541, #351).

Page images, page layout files (docs/PAGE_LAYOUT.md) and thumbnails are public corpus
data, like the document text: every read first checks, through ``_require_document``,
that the document exists. That is the one place where a future corpus access rule (#279)
applies to them. The assets live in the ``PageAssetStore`` (``PAGE_ASSETS_DIR``); a
document without stored pages is a text-only document, not an error. Clients use only the
URLs of the manifest, so the storage can change behind these reads.
"""
import asyncio
import logging
from pathlib import Path
from uuid import UUID

from semant_demo.adapters.filesystem.page_assets import AssetKind, InvalidManifest, PageAssetStore
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.core.errors import InvalidRequestError, NotFoundError
from semant_demo.features.documents.schemas import DocumentPage, DocumentPages, PageChunks
from semant_demo.features.user_collections import access

logger = logging.getLogger(__name__)

Id = str | UUID

MAX_PAGE_CHUNKS = 50
"""Most chunks returned for one page."""


async def _require_document(documents: DocumentRepository, document_id: Id) -> UUID:
    """The id of an existing corpus document (public); otherwise "not found"."""
    doc_id = access.parse_id(document_id, "Document")
    if not await documents.exists(doc_id):
        raise NotFoundError(f"Document with id {document_id} not found")
    return doc_id


def asset_url(document_id: UUID, page_id: UUID, kind: AssetKind) -> str:
    return f"/api/documents/{document_id}/pages/{page_id}/{kind}"


async def read_pages(documents: DocumentRepository, assets: PageAssetStore, document_id: Id) -> DocumentPages:
    """The document's page manifest with the URL of each available asset. No stored manifest,
    or one that cannot be read (logged), gives ``available: false``."""
    doc_id = await _require_document(documents, document_id)
    try:
        manifest = await asyncio.to_thread(assets.read_manifest, doc_id)
    except InvalidManifest as e:
        logger.error("Unreadable page manifest of document %s: %s", doc_id, e)
        manifest = None
    if manifest is None:
        return DocumentPages(document_id=doc_id, available=False, pages=[])
    pages = [DocumentPage(page_id=p.pageId, order=p.order, label=p.label, page_type=p.pageType,
                          width=p.width, height=p.height,
                          image_url=asset_url(doc_id, p.pageId, "image") if p.image else None,
                          layout_url=asset_url(doc_id, p.pageId, "layout") if p.layout else None,
                          thumbnail_url=asset_url(doc_id, p.pageId, "thumbnail") if p.thumbnail else None)
             for p in manifest.pages]
    return DocumentPages(document_id=doc_id, available=True, pages=pages)


async def read_page_asset(documents: DocumentRepository, assets: PageAssetStore, document_id: Id,
                          page_id: Id, kind: AssetKind) -> Path:
    """The file of one page asset; "not found" when the document or the asset is absent."""
    doc_id = await _require_document(documents, document_id)
    page = access.parse_id(page_id, "Page")
    path = await asyncio.to_thread(assets.asset_file, doc_id, page, kind)
    if path is None:
        raise NotFoundError(f"No {kind} for page {page_id} of document {document_id}")
    return path


async def read_page_chunks(documents: DocumentRepository, document_id: Id, page: int, limit: int) -> PageChunks:
    """Up to ``limit`` (at most ``MAX_PAGE_CHUNKS``) chunks whose ``from_page``..``to_page``
    includes ``page``, in document order: the chunks to show when a page is opened directly.
    Page ranges are the stored, coarse ones; the chunk's ``layoutStart``, when present, is
    its exact start."""
    if page < 0 or not 1 <= limit <= MAX_PAGE_CHUNKS:
        raise InvalidRequestError(f"page must be at least 0 and limit between 1 and {MAX_PAGE_CHUNKS}")
    doc_id = await _require_document(documents, document_id)
    chunks = await documents.read_chunks_covering_page(doc_id, page, limit + 1)
    return PageChunks(page=page, chunks=chunks[:limit], has_more=len(chunks) > limit)
