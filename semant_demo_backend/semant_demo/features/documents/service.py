"""Corpus document reads.

Documents and their chunks are public corpus data: reading a document, browsing the
whole corpus, counting a document's chunks and reading a bounded passage around a chunk
(the search result context, #244) need no login. Reads limited to a
collection, or marking chunk membership in one, need read access to that collection
(``features/collections/access.py``), checked here before any other read. ``user`` is the
authenticated user or ``None``; malformed ids are "not found".
"""
from uuid import UUID

from semant_demo.adapters.weaviate.collections import UserCollectionRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.core.errors import InvalidRequestError, NotFoundError
from semant_demo.features.collections import access
from semant_demo.features.collections.access import Principal
from semant_demo.schema.documents import Document, DocumentBrowse, DocumentChunkWindow, DocumentDetail

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


async def read_chunk_window(documents: DocumentRepository, document_id: Id, chunk_id: Id,
                            before: int, after: int) -> DocumentChunkWindow:
    """
    A passage of a corpus document (public): the chunk and up to ``before``/``after``
    (at most ``MAX_WINDOW_SIDE``) chunks around it. The chunk must belong to the document.
    """
    if not (0 <= before <= MAX_WINDOW_SIDE and 0 <= after <= MAX_WINDOW_SIDE):
        raise InvalidRequestError(f"before and after must be between 0 and {MAX_WINDOW_SIDE}")
    doc_id = access.parse_id(document_id, "Document")
    anchor = await documents.read_chunk(access.parse_id(chunk_id, "Chunk"))
    if anchor is None or anchor.document != doc_id:
        raise NotFoundError(f"Chunk with id {chunk_id} not found in document {document_id}")
    document = await read_document(documents, doc_id)

    preceding, following = [], []
    if anchor.order is not None:
        # One more than requested on each side tells whether the document continues.
        preceding = await documents.read_adjacent_chunks(doc_id, anchor.order, "before", before + 1)
        following = await documents.read_adjacent_chunks(doc_id, anchor.order, "after", after + 1)
    return DocumentChunkWindow(
        document=document,
        chunks=[*preceding[max(len(preceding) - before, 0):], anchor, *following[:after]],
        anchor_chunk_id=anchor.id,
        has_before=len(preceding) > before,
        has_after=len(following) > after,
        total_chunks=await documents.count_chunks(doc_id),
    )


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
