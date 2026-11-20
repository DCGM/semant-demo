"""Corpus document reads and the document access rule (#279, ADR 0007).

A document is readable in one of two ways, decided by ``readable_document`` before any
other read:

* **public**: ``Documents.public`` is true. Readable by anyone, also anonymously, without
  a collection (the public document view, Search, Explore, RAG, MCP).
* **through a collection**: the request names a collection the user can read (owner or
  shared user, ``features/user_collections/access.py``) and the document is linked to it.
  Then also a restricted (``public`` false) or unknown (no value) document is readable, with
  all its chunks. Signing in alone never is enough, and neither is a document or chunk id.

A document that is not readable is "not found", as one that does not exist, so restricted
ids are not confirmed. Corpus-wide reads (browse, counts) without a collection cover only
public documents (``DocumentRepository``). ``user`` is the authenticated user or ``None``;
malformed ids are "not found".
"""
from uuid import UUID

from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.core.errors import InvalidRequestError, NotFoundError
from semant_demo.features.user_collections import access
from semant_demo.features.user_collections.access import Principal
from semant_demo.features.documents.criteria import (
    ChunkFilters, ChunkVocabulary, Condition, DocumentFilters, document_level_conditions)
from semant_demo.features.documents.schemas import DocumentChunk, AdjacentChunks, Document, DocumentBrowse, DocumentChunkWindow, DocumentDetail, \
    DocumentViewChunk

Id = str | UUID


async def readable_document(documents: DocumentRepository, collections: UserCollectionRepository,
                            user: Principal | None, document_id: Id, collection_id: Id | None = None) -> UUID:
    """The id of a document the caller may read (the module's rule); "not found" otherwise.

    With ``collection_id``: read access to the collection (its errors propagate: login needed,
    "not found") and the document's link to it. Without: the document must be public."""
    doc = access.parse_id(document_id, "Document")
    if collection_id is not None:
        grant = await access.require_collection_read(collections, user, collection_id)
        return await access.require_document_in_collection(collections, doc, grant.collection_id)
    if not await documents.is_public(doc):
        raise NotFoundError(f"Document with id {document_id} not found")
    return doc


async def read_document(documents: DocumentRepository, collections: UserCollectionRepository,
                        user: Principal | None, document_id: Id, collection_id: Id | None = None) -> Document:
    """A readable corpus document (``readable_document``)."""
    doc = await readable_document(documents, collections, user, document_id, collection_id)
    document = await documents.read(doc)
    if document is None:
        raise NotFoundError(f"Document with id {document_id} not found")
    return document


async def count_chunks(documents: DocumentRepository, collections: UserCollectionRepository,
                       user: Principal | None, document_id: Id, collection_id: Id | None = None) -> int:
    """The number of chunks of a readable corpus document. 0 for an unknown document and, without
    a collection, also for one that is not public (neither is confirmed); a malformed id is "not
    found". With a collection, its access and membership errors propagate."""
    doc = access.parse_id(document_id, "Document")
    if collection_id is None:
        return await documents.count_chunks(doc) if await documents.is_public(doc) else 0
    doc = await readable_document(documents, collections, user, doc, collection_id)
    return await documents.count_chunks(doc)


MAX_WINDOW_SIDE = 50
"""Most chunks read on either side of the anchor chunk in one passage request."""


def _check_window_side(*sides: int) -> None:
    if not all(0 <= side <= MAX_WINDOW_SIDE for side in sides):
        raise InvalidRequestError(f"before, after and limit must be between 0 and {MAX_WINDOW_SIDE}")


async def _read_anchor(documents: DocumentRepository, doc_id: UUID, document_id: Id, chunk_id: Id) -> DocumentChunk:
    """The chunk, which must belong to the (readable) document ``doc_id`` (otherwise "not found")."""
    anchor = await documents.read_chunk(access.parse_id(chunk_id, "Chunk"))
    if anchor is None or anchor.document != doc_id:
        raise NotFoundError(f"Chunk with id {chunk_id} not found in document {document_id}")
    return anchor


async def _adjacent(documents: DocumentRepository, anchor: DocumentChunk, direction: str,
                    count: int) -> tuple[list[DocumentChunk], bool]:
    """Up to ``count`` chunks next to the anchor (document order) and whether more follow."""
    if anchor.order is None:
        return [], False
    # One more than requested tells whether the document continues.
    chunks = await documents.read_adjacent_chunks(anchor.document, anchor.order, direction, count + 1)
    if direction == "before":
        return chunks[max(len(chunks) - count, 0):], len(chunks) > count
    return chunks[:count], len(chunks) > count


async def read_chunk_window(documents: DocumentRepository, collections: UserCollectionRepository,
                            user: Principal | None, document_id: Id, chunk_id: Id, before: int, after: int,
                            collection_id: Id | None = None) -> DocumentChunkWindow:
    """
    A passage of a readable corpus document (``readable_document``): the chunk and up to
    ``before``/``after`` (at most ``MAX_WINDOW_SIDE``) chunks around it, with the document
    metadata and chunk count. The chunk must belong to the document.
    """
    _check_window_side(before, after)
    doc_id = await readable_document(documents, collections, user, document_id, collection_id)
    anchor = await _read_anchor(documents, doc_id, document_id, chunk_id)
    document = await documents.read(doc_id)
    if document is None:
        raise NotFoundError(f"Document with id {document_id} not found")
    preceding, has_before = await _adjacent(documents, anchor, "before", before)
    following, has_after = await _adjacent(documents, anchor, "after", after)
    return DocumentChunkWindow(
        document=document,
        chunks=[*preceding, anchor, *following],
        anchor_chunk_id=anchor.id,
        has_before=has_before,
        has_after=has_after,
        total_chunks=await documents.count_chunks(anchor.document),
    )


async def read_adjacent_chunks(documents: DocumentRepository, collections: UserCollectionRepository,
                               user: Principal | None, document_id: Id, chunk_id: Id, direction: str, limit: int,
                               collection_id: Id | None = None) -> AdjacentChunks:
    """
    Up to ``limit`` (at most ``MAX_WINDOW_SIDE``) chunks before or after a chunk of a readable
    corpus document (``readable_document``), to extend a passage. Reads only the rights, the
    chunk and its neighbours: no document metadata, no chunk count. The chunk must belong to
    the document.
    """
    if direction not in ("before", "after"):
        raise InvalidRequestError("direction must be 'before' or 'after'")
    _check_window_side(limit)
    doc_id = await readable_document(documents, collections, user, document_id, collection_id)
    anchor = await _read_anchor(documents, doc_id, document_id, chunk_id)
    chunks, has_more = await _adjacent(documents, anchor, direction, limit)
    return AdjacentChunks(chunks=chunks, has_more=has_more)


async def browse(documents: DocumentRepository, collections: UserCollectionRepository, user: Principal | None,
                 collection_id: Id | None = None, filters: DocumentFilters | None = None,
                 chunk_filters: ChunkFilters | None = None, vocabulary: ChunkVocabulary | None = None,
                 **options) -> DocumentBrowse:
    """
    One page of public corpus documents, or of one collection's documents (any rights), which
    needs read access to it. ``filters`` and ``chunk_filters`` are the shared search criteria (the
    same documents as Analytics counts for them); chunk filters apply per dimension to the
    documents' chunk-value summaries and are checked against ``vocabulary`` before anything is
    read (``InvalidChunkFilterError``). ``options`` are the repository's paging, sorting and
    substring filter options.
    """
    scope, conditions = await browse_scope(collections, user, collection_id, filters, chunk_filters, vocabulary)
    return await documents.browse(collection_id=scope, conditions=conditions, **options)


async def browse_by_year(documents: DocumentRepository, collections: UserCollectionRepository,
                         user: Principal | None, collection_id: Id | None = None,
                         filters: DocumentFilters | None = None, chunk_filters: ChunkFilters | None = None,
                         vocabulary: ChunkVocabulary | None = None, limit: int = 50, offset: int = 0,
                         ) -> DocumentBrowse:
    """``browse`` in a stable order for paging (Explore Documents, #606): publication year,
    oldest first, then id, the documents without a year last. The same access, criteria and
    chunk-filter rules; no substring filters."""
    scope, conditions = await browse_scope(collections, user, collection_id, filters, chunk_filters, vocabulary)
    return await documents.browse_by_year(collection_id=scope, conditions=conditions, limit=limit, offset=offset)


async def browse_scope(collections: UserCollectionRepository, user: Principal | None, collection_id: Id | None,
                        filters: DocumentFilters | None, chunk_filters: ChunkFilters | None,
                        vocabulary: ChunkVocabulary | None) -> tuple[UUID | None, list[Condition]]:
    """The collection a browse reads (read access checked) and its criteria predicates on
    ``Documents``; the chunk filters are checked first, before anything is read. Also the
    eligibility of documents for a text query (#607)."""
    _, conditions = document_level_conditions(filters, chunk_filters, vocabulary)
    scope = None
    if collection_id is not None:
        scope = (await access.require_collection_read(collections, user, collection_id)).collection_id
    return scope, conditions


async def read_chunks_in_collection(documents: DocumentRepository, collections: UserCollectionRepository,
                                    user: Principal | None, document_id: Id, collection_id: Id) -> DocumentDetail:
    """
    The document with all its chunks, each marked with membership in the collection. Needs
    read access to the collection, and the document must belong to it.
    """
    grant = await access.require_collection_read(collections, user, collection_id)
    document = await access.require_document_in_collection(collections, document_id, grant.collection_id)
    detail = await documents.read_chunks(document_id=document, collection_id=grant.collection_id)
    if detail is None:
        raise NotFoundError(f"Document with id {document_id} not found")
    return detail


def chunks_in_collection(detail: DocumentDetail) -> list[DocumentViewChunk]:
    """The document's chunks that are in the collection, in document order (chunks without
    an order last): the scope of the document summary and the document chat (ADR 0006).
    Raises ``NotFoundError`` when none is."""
    chunks = sorted((chunk for chunk in detail.chunks if chunk.in_user_collection),
                    key=lambda chunk: (chunk.order is None, chunk.order))
    if not chunks:
        raise NotFoundError("The document has no passages in this collection.")
    return chunks
