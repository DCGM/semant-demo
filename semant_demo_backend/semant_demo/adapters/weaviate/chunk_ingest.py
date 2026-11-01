"""Reads and inserts of the append-only chunk import (#313).

Only two writes exist: inserting an absent ``Documents`` object without properties and
inserting an absent ``Chunks`` object. They use the single-object insert, which Weaviate
refuses for an existing id (``AlreadyExists``). The batch insert (``insert_chunks``)
silently replaces an object with the same id, losing its tags, memberships and vectors, so
the import uses it only with ``--bulk`` into an empty chunk collection. Never updates or
deletes an object, never creates, drops or alters a collection. Reads return properties
and the ``document`` reference, never vectors. Collection names are resolved through
aliases by the caller.
"""
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.data import DataObject
from weaviate.classes.query import Filter, QueryReference
from weaviate.exceptions import UnexpectedStatusCodeError, WeaviateInsertManyAllFailedError

from semant_demo.adapters.weaviate.documents import POSITION_PROPERTIES
from semant_demo.features.documents.positions import ChunkPosition


class AlreadyExists(Exception):
    """The object id is taken; nothing was written."""


@dataclass(frozen=True)
class Schema:
    """Declared property types (``"int"``, ``"text"``, ``"boolean"``, ...) and the target
    collections of each reference."""
    properties: dict[str, str]
    references: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class StoredChunk:
    """A stored chunk as the import compares it: ``fields`` are the requested properties
    (None when absent), ``position`` is None unless all three position properties are stored."""
    id: UUID
    document: UUID | None
    order: int | None
    text: str
    fields: dict[str, Any]
    position: ChunkPosition | None


async def schema(client: WeaviateAsyncClient, collection: str) -> Schema:
    config = await client.collections.get(collection).config.get()
    return Schema({p.name: p.data_type.value for p in config.properties},
                  {r.name: tuple(r.target_collections) for r in config.references})


async def existing_documents(client: WeaviateAsyncClient, collection: str, ids: list[UUID]) -> set[UUID]:
    """The ids of these documents that exist."""
    if not ids:
        return set()
    response = await client.collections.get(collection).query.fetch_objects(
        filters=Filter.by_id().contains_any(ids), limit=len(ids), return_properties=[])
    return {o.uuid for o in response.objects}


def _stored(o, fields: tuple[str, ...]) -> StoredChunk:
    props = o.properties
    refs = (o.references or {}).get("document")
    targets = [t.uuid for t in refs.objects] if refs else []
    values = [props.get(name) for name in POSITION_PROPERTIES]
    position = ChunkPosition(*values) if all(v is not None for v in values) else None
    return StoredChunk(o.uuid, targets[0] if len(targets) == 1 else None, props.get("order"),
                       props.get("text") or "", {name: props.get(name) for name in fields}, position)


def _return_properties(fields: tuple[str, ...]) -> list[str]:
    return ["order", "text", *fields, *POSITION_PROPERTIES]


async def read_chunks(client: WeaviateAsyncClient, collection: str, ids: list[UUID],
                      fields: tuple[str, ...]) -> dict[UUID, StoredChunk]:
    """The chunks with these ids that exist, with their ``document`` reference."""
    if not ids:
        return {}
    response = await client.collections.get(collection).query.fetch_objects(
        filters=Filter.by_id().contains_any(ids), limit=len(ids), return_properties=_return_properties(fields),
        return_references=[QueryReference(link_on="document", return_properties=[])])
    return {o.uuid: _stored(o, fields) for o in response.objects}


async def read_order_range(client: WeaviateAsyncClient, collection: str, document_id: UUID, first: int, last: int,
                           fields: tuple[str, ...]) -> list[StoredChunk]:
    """The document's chunks with ``first <= order <= last``, in order (duplicates included;
    the orders are listed instead of a server-side sort, as in ``chunk_positions``)."""
    response = await client.collections.get(collection).query.fetch_objects(
        filters=Filter.all_of([Filter.by_ref("document").by_id().equal(document_id),
                               Filter.by_property("order").contains_any(list(range(first, last + 1)))]),
        limit=2 * (last - first + 1), return_properties=_return_properties(fields),
        return_references=[QueryReference(link_on="document", return_properties=[])])
    return sorted((_stored(o, fields) for o in response.objects), key=lambda c: c.order)


def _already_exists(e: UnexpectedStatusCodeError) -> bool:
    return e.status_code == 422 and "already exists" in str(e)


async def insert_document(client: WeaviateAsyncClient, collection: str, document_id: UUID) -> None:
    """Insert the document without properties; ``AlreadyExists`` if the id is taken."""
    try:
        await client.collections.get(collection).data.insert(uuid=document_id, properties={})
    except UnexpectedStatusCodeError as e:
        if _already_exists(e):
            raise AlreadyExists(str(document_id)) from e
        raise


async def insert_chunks(client: WeaviateAsyncClient, collection: str,
                        chunks: list[tuple[UUID, UUID, dict[str, Any]]]) -> dict[UUID, str]:
    """Batch-insert ``(chunk id, document id, properties)``; the error of each chunk that was
    refused (for example a reference to a missing document). **Replaces an object with the
    same id without an error**: only for a chunk collection that held nothing at the start."""
    objects = [DataObject(uuid=chunk_id, properties=properties, references={"document": document_id})
               for chunk_id, document_id, properties in chunks]
    try:
        result = await client.collections.get(collection).data.insert_many(objects)
    except WeaviateInsertManyAllFailedError as e:
        return {chunk_id: str(e) for chunk_id, _, _ in chunks}
    return {chunks[index][0]: error.message for index, error in result.errors.items()}


async def insert_chunk(client: WeaviateAsyncClient, collection: str, chunk_id: UUID, document_id: UUID,
                       properties: dict[str, Any]) -> None:
    """Insert the chunk with these properties and its ``document`` reference, no vector;
    ``AlreadyExists`` if the id is taken. Weaviate refuses a reference to a missing document."""
    try:
        await client.collections.get(collection).data.insert(
            uuid=chunk_id, properties=properties, references={"document": document_id})
    except UnexpectedStatusCodeError as e:
        if _already_exists(e):
            raise AlreadyExists(str(chunk_id)) from e
        raise
