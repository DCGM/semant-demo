"""Corpus document reads.

Documents and their chunks are public corpus data: reading a document, browsing the
whole corpus and counting a document's chunks need no login. Reads limited to a
collection, or marking chunk membership in one, need read access to that collection
(``features/collections/access.py``), checked here before any other read. ``user`` is the
authenticated user or ``None``; malformed ids are "not found".
"""
from uuid import UUID

from semant_demo.adapters.weaviate.collections import UserCollectionRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.core.errors import NotFoundError
from semant_demo.features.collections import access
from semant_demo.features.collections.access import Principal
from semant_demo.schema.documents import Document, DocumentBrowse, DocumentDetail

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
