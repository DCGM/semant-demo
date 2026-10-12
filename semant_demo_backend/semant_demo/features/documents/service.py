"""Corpus document reads.

Documents and their chunks are public corpus data: reading a document, browsing the
whole corpus, counting a document's chunks and reading a bounded passage around a chunk
(the search result context, #244) need no login. Reads limited to a
collection, or marking chunk membership in one, need read access to that collection
(``features/user_collections/access.py``), checked here before any other read. ``user`` is the
authenticated user or ``None``; malformed ids are "not found".
"""
from uuid import UUID

from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.core.errors import InvalidRequestError, NotFoundError
from semant_demo.features.user_collections import access
from semant_demo.features.user_collections.access import Principal
from semant_demo.features.documents.schemas import DocumentChunk, AdjacentChunks, Document, DocumentBrowse, DocumentChunkWindow, DocumentDetail

Id = str | UUID


async def read_document(documents: DocumentRepository, document_id: Id) -> Document:
    """A corpus document (public)."""
    document = await documents.read(access.parse_id(document_id, "Document"))
    if document is None:
        raise NotFoundError(f"Document with id {document_id} not found")
    return document


async def count_chunks(documents: DocumentRepository, document_id: Id) -> int:
    """The number of chunks of a corpus document (public; 0 for an unknown document)."""
    return await documents.count_chunks(access.parse_id(document_id, "Document"))


MAX_WINDOW_SIDE = 50
"""Most chunks read on either side of the anchor chunk in one passage request."""


def _check_window_side(*sides: int) -> None:
    if not all(0 <= side <= MAX_WINDOW_SIDE for side in sides):
        raise InvalidRequestError(f"before, after and limit must be between 0 and {MAX_WINDOW_SIDE}")


async def _read_anchor(documents: DocumentRepository, document_id: Id, chunk_id: Id) -> DocumentChunk:
    """The chunk, which must belong to the document (otherwise "not found")."""
    doc_id = access.parse_id(document_id, "Document")
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


async def read_chunk_window(documents: DocumentRepository, document_id: Id, chunk_id: Id,
                            before: int, after: int) -> DocumentChunkWindow:
    """
    A passage of a corpus document (public): the chunk and up to ``before``/``after``
    (at most ``MAX_WINDOW_SIDE``) chunks around it, with the document metadata and chunk
    count. The chunk must belong to the document.
    """
    _check_window_side(before, after)
    anchor = await _read_anchor(documents, document_id, chunk_id)
    document = await read_document(documents, anchor.document)
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


async def read_adjacent_chunks(documents: DocumentRepository, document_id: Id, chunk_id: Id,
                               direction: str, limit: int) -> AdjacentChunks:
    """
    Up to ``limit`` (at most ``MAX_WINDOW_SIDE``) chunks before or after a chunk of a corpus
    document (public), to extend a passage. Reads only the chunk and its neighbours: no
    document metadata, no chunk count. The chunk must belong to the document.
    """
    if direction not in ("before", "after"):
        raise InvalidRequestError("direction must be 'before' or 'after'")
    _check_window_side(limit)
    anchor = await _read_anchor(documents, document_id, chunk_id)
    chunks, has_more = await _adjacent(documents, anchor, direction, limit)
    return AdjacentChunks(chunks=chunks, has_more=has_more)


async def browse(documents: DocumentRepository, collections: UserCollectionRepository, user: Principal | None,
                 collection_id: Id | None = None, **options) -> DocumentBrowse:
    """
    One page of corpus documents (public), or of one collection's documents, which needs
    read access to it. ``options`` are the repository's paging, sorting and filter options.
    """
    scope = None
    if collection_id is not None:
        scope = (await access.require_collection_read(collections, user, collection_id)).collection_id
    return await documents.browse(collection_id=scope, **options)


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
