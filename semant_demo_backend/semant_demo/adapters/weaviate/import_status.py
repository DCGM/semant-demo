"""Reads of the imported documents and their chunks for the import status report (#884, #560).

Every read is read-only: the listed documents with their metadata and stored chunk-value
summaries, each document's chunks (through the ``document`` reference; ids and the properties
the stages write, never text or vectors), the named vector of a few chunks, and two vector
queries per sampled chunk (the index check of ``db_benchmark inventory``). Collection names are
resolved through aliases by the caller.
"""
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter

from semant_demo.adapters.weaviate.paging import fetch_all
from semant_demo.features.documents.criteria import SUMMARIES_COMPUTED_AT, summary_property

DOCUMENT_LINK = "document"
DOCUMENT_PROPERTIES = ("public", "library", "title", "yearIssued")
CHUNK_PAGE_SIZE = 1000


@dataclass(frozen=True)
class ImportedDocument:
    """A document's metadata (``DOCUMENT_PROPERTIES``, None when absent), its stored summaries
    per dimension (sorted, empty when absent) and when they were computed."""
    id: UUID
    properties: dict[str, Any]
    summaries: dict[str, tuple[str, ...]]
    computed_at: Any


@dataclass(frozen=True)
class ImportedChunk:
    """A chunk's id and the properties read (None when absent)."""
    id: UUID
    properties: dict[str, Any]


async def declared_properties(client: WeaviateAsyncClient, collection: str) -> set[str]:
    config = await client.collections.get(collection).config.get()
    return {p.name for p in config.properties}


async def vector_names(client: WeaviateAsyncClient, collection: str) -> set[str]:
    config = await client.collections.get(collection).config.get()
    return set((config.vector_config or {}).keys())


def text_values(value) -> tuple[str, ...]:
    if value is None:
        return ()
    items = [value] if isinstance(value, str) else value
    return tuple(sorted(item for item in items if isinstance(item, str) and item.strip()))


async def read_documents(client: WeaviateAsyncClient, collection: str, ids: Sequence[UUID],
                         dimensions: Sequence[str]) -> dict[UUID, ImportedDocument]:
    """The documents with these ids that exist, with their metadata and stored summaries."""
    if not ids:
        return {}
    summaries = [summary_property(d) for d in dimensions]
    response = await client.collections.get(collection).query.fetch_objects(
        filters=Filter.by_id().contains_any(list(ids)), limit=len(ids),
        return_properties=[*DOCUMENT_PROPERTIES, *summaries, SUMMARIES_COMPUTED_AT])
    return {obj.uuid: ImportedDocument(
        obj.uuid, {p: obj.properties.get(p) for p in DOCUMENT_PROPERTIES},
        {d: text_values(obj.properties.get(summary_property(d))) for d in dimensions},
        obj.properties.get(SUMMARIES_COMPUTED_AT)) for obj in response.objects}


async def read_document_chunks(client: WeaviateAsyncClient, collection: str, document_id: UUID,
                               properties: Sequence[str]) -> list[ImportedChunk]:
    """The chunks referencing the document, with ``properties``. More chunks than Weaviate's
    ``QUERY_MAXIMUM_RESULTS`` fail instead of being truncated (``paging.fetch_all``)."""
    objects = await fetch_all(client.collections.get(collection), page_size=CHUNK_PAGE_SIZE,
                              filters=Filter.by_ref(DOCUMENT_LINK).by_id().equal(document_id),
                              return_properties=list(properties))
    return [ImportedChunk(obj.uuid, {p: obj.properties.get(p) for p in properties}) for obj in objects]


async def read_vectors(client: WeaviateAsyncClient, collection: str, ids: Sequence[UUID],
                       vector: str) -> dict[UUID, list[float] | None]:
    """The stored named vector of the chunks with these ids that exist (None when not stored)."""
    if not ids:
        return {}
    response = await client.collections.get(collection).query.fetch_objects(
        filters=Filter.by_id().contains_any(list(ids)), limit=len(ids), return_properties=[], include_vector=[vector])
    return {obj.uuid: (obj.vector or {}).get(vector) or None for obj in response.objects}


async def self_in_top_k(client: WeaviateAsyncClient, collection: str, chunk_id: UUID, vector: list[float],
                        vector_name: str, k: int) -> bool:
    """Whether a vector query with the chunk's own vector finds it among the first ``k``."""
    result = await client.collections.get(collection).query.near_vector(
        near_vector=vector, target_vector=vector_name, limit=k, return_properties=[])
    return any(o.uuid == chunk_id for o in result.objects)


async def found_by_id_filter(client: WeaviateAsyncClient, collection: str, chunk_id: UUID, vector: list[float],
                             vector_name: str) -> bool:
    """Whether a vector query restricted to the chunk's own id finds it."""
    result = await client.collections.get(collection).query.near_vector(
        near_vector=vector, target_vector=vector_name, limit=1, return_properties=[],
        filters=Filter.by_id().equal(chunk_id))
    return any(o.uuid == chunk_id for o in result.objects)
