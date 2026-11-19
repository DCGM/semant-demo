"""Writes and readbacks of the text document upload (#785, ``features/user_collections/text_upload.py``).

Only new objects are written, with the single-object insert, which Weaviate refuses for an
existing id (``chunk_ingest.AlreadyExists``): a ``Documents`` object with the given
properties and no references, and ``Chunks`` objects with their ``document`` and user
collection references and their named vectors in the same write. The one change of an
existing object is the last step: adding the document's ``collection`` reference. Nothing is
ever deleted. The schema is only read. Readbacks return what the upload compares (order,
text, references, vector lengths), never other properties.
"""
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter, QueryReference

from semant_demo.adapters.weaviate import chunk_ingest
from semant_demo.adapters.weaviate.chunk_ingest import AlreadyExists
from semant_demo.adapters.weaviate.document_cleanup import resolve_collection
from semant_demo.adapters.weaviate.names import CollectionNames

__all__ = ["AlreadyExists", "StoredUploadChunk", "UploadSchema", "TextUploadRepository"]

DOCUMENT_COLLECTION_LINK = "collection"
"""The ``Documents`` reference to its user collections."""
READ_BATCH = 100


@dataclass(frozen=True)
class UploadSchema:
    """What the stores declare: property types (``"text"``, ``"int"``, ``"text[]"``...) and
    reference names of documents and chunks, and the chunks' named vectors."""
    document_properties: dict[str, str]
    document_references: frozenset[str]
    chunk_properties: dict[str, str]
    chunk_references: frozenset[str]
    chunk_vectors: frozenset[str]


@dataclass(frozen=True)
class StoredUploadChunk:
    id: UUID
    document: UUID | None
    collections: frozenset[UUID]
    order: int | None
    text: str | None
    vector_lengths: dict[str, int]
    """The length of each requested named vector that is stored."""


def _vector_lengths(vector: Any, names: list[str]) -> dict[str, int]:
    if not isinstance(vector, dict):
        return {}
    return {name: len(vector[name]) for name in names if vector.get(name)}


class TextUploadRepository:
    def __init__(self, client: WeaviateAsyncClient, names: CollectionNames):
        self.client = client
        self.names = names
        self.link = names.user_collection_link_name

    def _documents(self):
        return self.client.collections.get(self.names.document_collection_name)

    def _chunks(self):
        return self.client.collections.get(self.names.chunks_collection_name)

    async def schema(self) -> UploadSchema:
        """The declared schema of the document and chunk collections (through aliases)."""
        documents = await chunk_ingest.schema(
            self.client, await resolve_collection(self.client, self.names.document_collection_name))
        chunks_name = await resolve_collection(self.client, self.names.chunks_collection_name)
        chunks = await chunk_ingest.schema(self.client, chunks_name)
        config = await self.client.collections.get(chunks_name).config.get()
        vectors = frozenset((config.vector_config or {}).keys())
        return UploadSchema(documents.properties, frozenset(documents.references),
                            chunks.properties, frozenset(chunks.references), vectors)

    async def create_document(self, document_id: UUID, properties: dict[str, Any]) -> None:
        """Insert the document with these properties and no references; ``AlreadyExists`` if
        the id is taken."""
        try:
            await self._documents().data.insert(uuid=document_id, properties=properties)
        except Exception as e:
            if _already_exists(e):
                raise AlreadyExists(str(document_id)) from e
            raise

    async def insert_chunk(self, chunk_id: UUID, document_id: UUID, collection_id: UUID,
                           properties: dict[str, Any], vectors: dict[str, list[float]]) -> None:
        """Insert the chunk with its document and collection references and its named vectors
        in one write; ``AlreadyExists`` if the id is taken."""
        try:
            await self._chunks().data.insert(
                uuid=chunk_id, properties=properties, vector=vectors,
                references={"document": document_id, self.link: collection_id})
        except Exception as e:
            if _already_exists(e):
                raise AlreadyExists(str(chunk_id)) from e
            raise

    async def read_chunks(self, ids: list[UUID], vector_names: list[str]) -> dict[UUID, StoredUploadChunk]:
        """The chunks with these ids that exist, with the lengths of their named vectors."""
        found: dict[UUID, StoredUploadChunk] = {}
        for start in range(0, len(ids), READ_BATCH):
            batch = ids[start:start + READ_BATCH]
            response = await self._chunks().query.fetch_objects(
                filters=Filter.by_id().contains_any(batch), limit=len(batch),
                return_properties=["order", "text"], include_vector=vector_names,
                return_references=[QueryReference(link_on="document", return_properties=[]),
                                   QueryReference(link_on=self.link, return_properties=[])])
            for o in response.objects:
                refs = o.references or {}
                documents = [t.uuid for t in refs["document"].objects] if refs.get("document") else []
                collections = frozenset(t.uuid for t in refs[self.link].objects) if refs.get(self.link) else frozenset()
                found[o.uuid] = StoredUploadChunk(
                    o.uuid, documents[0] if len(documents) == 1 else None, collections,
                    o.properties.get("order"), o.properties.get("text"), _vector_lengths(o.vector, vector_names))
        return found

    async def count_chunks(self, document_id: UUID) -> int:
        """How many chunks reference the document."""
        response = await self._chunks().aggregate.over_all(
            total_count=True, filters=Filter.by_ref("document").by_id().equal(document_id))
        return response.total_count or 0

    async def link_document(self, document_id: UUID, collection_id: UUID) -> None:
        """Add the document's reference to the user collection: the last step of an upload."""
        await self._documents().data.reference_add(
            from_uuid=document_id, from_property=DOCUMENT_COLLECTION_LINK, to=collection_id)


def _already_exists(e: Exception) -> bool:
    status = getattr(e, "status_code", None)
    return status == 422 and "already exists" in str(e)
