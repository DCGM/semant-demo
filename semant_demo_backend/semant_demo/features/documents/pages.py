"""Document pages: the page manifest, page assets and the chunks of a page (#541, #351).

Page images, page layout files (docs/PAGE_LAYOUT.md) and thumbnails follow the document's
access rule (#279, ``service.readable_document``), checked before any file is touched: a
public document's pages are readable by anyone; a restricted or unknown one's only through
a collection the user can read and that holds the document. The browser loads assets
without a bearer token, so the manifest read through a collection gives such a document
signed asset URLs (``asset_access``), checked again on every asset read. The assets live
in the ``PageAssetStore`` (``PAGE_ASSETS_DIR``); a document without stored pages is a
text-only document, not an error. Clients use only the URLs of the manifest, so the
storage can change behind these reads.
"""
import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

from semant_demo.adapters.filesystem.page_assets import AssetKind, InvalidManifest, PageAssetStore
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.core.errors import InvalidRequestError, NotFoundError
from semant_demo.features.documents.asset_access import AssetGrant, AssetSigner
from semant_demo.features.documents.schemas import DocumentPage, DocumentPages, PageChunks
from semant_demo.features.documents.service import readable_document
from semant_demo.features.user_collections import access
from semant_demo.features.user_collections.access import Principal

logger = logging.getLogger(__name__)

Id = str | UUID

MAX_PAGE_CHUNKS = 50
"""Most chunks returned for one page."""


@dataclass(frozen=True)
class _Reader:
    id: UUID


def asset_url(document_id: UUID, page_id: UUID, kind: AssetKind, token: str | None = None) -> str:
    url = f"/api/documents/{document_id}/pages/{page_id}/{kind}"
    return f"{url}?access={quote(token, safe='')}" if token else url


async def read_pages(documents: DocumentRepository, collections: UserCollectionRepository, assets: PageAssetStore,
                     user: Principal | None, document_id: Id, collection_id: Id | None = None,
                     signer: AssetSigner | None = None) -> DocumentPages:
    """The page manifest of a readable document (``readable_document``) with the URL of each
    available asset; read through a collection, a document that is not public gets signed
    asset URLs (``signer``; none: its assets are not readable), with their expiry. No stored manifest, or one that
    cannot be read (logged), gives ``available: false``."""
    doc_id = await readable_document(documents, collections, user, document_id, collection_id)
    signed = None
    if collection_id is not None and user is not None and signer is not None \
            and not await documents.is_public(doc_id):
        signed = signer.sign(AssetGrant(doc_id, access.parse_id(collection_id, "Collection"), user.id))
    token = signed.token if signed else None
    try:
        manifest = await asyncio.to_thread(assets.read_manifest, doc_id)
    except InvalidManifest as e:
        logger.error("Unreadable page manifest of document %s: %s", doc_id, e)
        manifest = None
    if manifest is None:
        return DocumentPages(document_id=doc_id, available=False, pages=[])
    pages = [DocumentPage(page_id=p.pageId, order=p.order, label=p.label, page_type=p.pageType,
                          width=p.width, height=p.height,
                          image_url=asset_url(doc_id, p.pageId, "image", token) if p.image else None,
                          layout_url=asset_url(doc_id, p.pageId, "layout", token) if p.layout else None,
                          thumbnail_url=asset_url(doc_id, p.pageId, "thumbnail", token) if p.thumbnail else None)
             for p in manifest.pages]
    return DocumentPages(document_id=doc_id, available=True, pages=pages,
                         access_expires_at=signed.expires_at if signed else None)


async def read_page_asset(documents: DocumentRepository, collections: UserCollectionRepository,
                          assets: PageAssetStore, document_id: Id, page_id: Id, kind: AssetKind,
                          token: str | None = None, signer: AssetSigner | None = None) -> tuple[Path, bool]:
    """The file of one page asset and whether the document is public. A document that is not
    public needs a valid ``token`` (``asset_access``) whose user can still read its collection,
    which still holds the document. "Not found" when the document is absent or not readable so,
    or the asset is absent."""
    doc_id = access.parse_id(document_id, "Document")
    public = await documents.is_public(doc_id)
    if not public:
        grant = signer.verify(token, doc_id) if signer is not None else None
        if grant is None:
            raise NotFoundError(f"Document with id {document_id} not found")
        await readable_document(documents, collections, _Reader(grant.user_id), doc_id, grant.collection_id)
    page = access.parse_id(page_id, "Page")
    path = await asyncio.to_thread(assets.asset_file, doc_id, page, kind)
    if path is None:
        raise NotFoundError(f"No {kind} for page {page_id} of document {document_id}")
    return path, public


async def read_page_chunks(documents: DocumentRepository, collections: UserCollectionRepository,
                           user: Principal | None, document_id: Id, page: int, limit: int,
                           collection_id: Id | None = None) -> PageChunks:
    """Up to ``limit`` (at most ``MAX_PAGE_CHUNKS``) chunks whose ``from_page``..``to_page``
    includes ``page``, in document order: the chunks to show when a page is opened directly.
    Page ranges are the stored, coarse ones; the chunk's ``layoutStart``, when present, is
    its exact start. The document must be readable (``readable_document``)."""
    if page < 0 or not 1 <= limit <= MAX_PAGE_CHUNKS:
        raise InvalidRequestError(f"page must be at least 0 and limit between 1 and {MAX_PAGE_CHUNKS}")
    doc_id = await readable_document(documents, collections, user, document_id, collection_id)
    chunks = await documents.read_chunks_covering_page(doc_id, page, limit + 1)
    return PageChunks(page=page, chunks=chunks[:limit], has_more=len(chunks) > limit)
