"""The document visibility copied to text chunks: ``Chunks.documentPublic`` (#793, #279).

``Chunks.documentPublic`` (``bool``, filterable) is an eligibility index derived from the
referenced document's ``Documents.public``: ``true`` only when the document is explicitly
``public=true``; ``false`` for a restricted or unknown document and for a chunk without
exactly one existing document. A missing value is never public: searches select
``documentPublic == true``. ``Documents.public`` stays the source of truth.

Reads return ids, the flag and the document reference, never text or vectors. Writes are
merges of the single property (text, vectors, references and other properties are kept).
Collection names are resolved through aliases by the caller. Never creates, drops or alters
a collection; ``add_property`` only adds the property, on explicit request.
"""
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.config import DataType, Property
from weaviate.classes.query import Filter, QueryReference

PROPERTY = "documentPublic"
DOCUMENT_PUBLIC = "public"
DOCUMENT_LINK = "document"


@dataclass(frozen=True)
class ChunkVisibility:
    """A chunk's id, its stored flag (None when absent) and the documents it references."""
    id: UUID
    public: Any
    document_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class FlagProperty:
    data_type: str
    filterable: bool


async def flag_property(client: WeaviateAsyncClient, collection: str) -> FlagProperty | None:
    """The declared ``documentPublic`` of the collection, None if it is not declared."""
    config = await client.collections.get(collection).config.get()
    for prop in config.properties:
        if prop.name == PROPERTY:
            return FlagProperty(prop.data_type.value, bool(prop.index_filterable))
    return None


async def add_property(client: WeaviateAsyncClient, collection: str) -> None:
    """Declare ``documentPublic`` (``bool``, filterable); existing chunks have no value."""
    await client.collections.get(collection).config.add_property(
        Property(name=PROPERTY, data_type=DataType.BOOL, index_filterable=True))


async def read_all_document_public(client: WeaviateAsyncClient, collection: str, page_size: int) -> dict[UUID, Any]:
    """Document id -> stored ``public`` (None when absent), for every document."""
    documents = client.collections.get(collection)
    values: dict[UUID, Any] = {}
    after = None
    while True:
        response = await documents.query.fetch_objects(limit=page_size, after=after,
                                                       return_properties=[DOCUMENT_PUBLIC])
        for obj in response.objects:
            values[obj.uuid] = obj.properties.get(DOCUMENT_PUBLIC)
        if len(response.objects) < page_size:
            return values
        after = response.objects[-1].uuid


async def read_document_public(client: WeaviateAsyncClient, collection: str, ids: list[UUID]) -> dict[UUID, Any]:
    """Document id -> stored ``public`` (None when absent), for the documents that exist."""
    if not ids:
        return {}
    response = await client.collections.get(collection).query.fetch_objects(
        filters=Filter.by_id().contains_any(ids), limit=len(ids), return_properties=[DOCUMENT_PUBLIC])
    return {obj.uuid: obj.properties.get(DOCUMENT_PUBLIC) for obj in response.objects}


def _chunk(obj) -> ChunkVisibility:
    refs = (obj.references or {}).get(DOCUMENT_LINK)
    return ChunkVisibility(obj.uuid, obj.properties.get(PROPERTY),
                           tuple(sorted({o.uuid for o in refs.objects})) if refs else ())


def _returned(declared: bool) -> dict[str, Any]:
    return dict(return_properties=[PROPERTY] if declared else [],
                return_references=QueryReference(link_on=DOCUMENT_LINK, return_properties=[]))


async def read_chunk_page(client: WeaviateAsyncClient, collection: str, after: UUID | None, limit: int,
                          declared: bool = True) -> list[ChunkVisibility]:
    """Up to ``limit`` chunks following ``after`` in id order (cursor paging). Without
    ``declared`` (the property does not exist yet) every flag reads as None."""
    response = await client.collections.get(collection).query.fetch_objects(
        limit=limit, after=after, **_returned(declared))
    return [_chunk(obj) for obj in response.objects]


async def read_chunks(client: WeaviateAsyncClient, collection: str, ids: list[UUID],
                      declared: bool = True) -> dict[UUID, ChunkVisibility]:
    """The chunks with these ids that exist."""
    if not ids:
        return {}
    response = await client.collections.get(collection).query.fetch_objects(
        filters=Filter.by_id().contains_any(ids), limit=len(ids), **_returned(declared))
    return {obj.uuid: _chunk(obj) for obj in response.objects}


def _of_document(document_id: UUID) -> Filter:
    return Filter.by_ref(DOCUMENT_LINK).by_id().equal(document_id)


async def document_chunks_differing(client: WeaviateAsyncClient, collection: str, document_id: UUID,
                                    value: bool, limit: int) -> list[UUID]:
    """Up to ``limit`` ids of the document's chunks whose flag is not ``value`` (also those
    without a flag)."""
    response = await client.collections.get(collection).query.fetch_objects(
        filters=_of_document(document_id) & Filter.by_property(PROPERTY).not_equal(value),
        limit=limit, return_properties=[])
    return [obj.uuid for obj in response.objects]


async def count_document_chunks(client: WeaviateAsyncClient, collection: str, document_id: UUID,
                                value: bool | None = None) -> int:
    """The document's chunks, or with ``value`` those whose flag equals it."""
    filters = _of_document(document_id)
    if value is not None:
        filters = filters & Filter.by_property(PROPERTY).equal(value)
    result = await client.collections.get(collection).aggregate.over_all(filters=filters, total_count=True)
    return result.total_count or 0


async def set_chunk_public(client: WeaviateAsyncClient, collection: str, chunk_id: UUID, value: bool) -> None:
    """Set the chunk's ``documentPublic`` (a merge: other properties, references and the vector
    are kept)."""
    await client.collections.get(collection).data.update(uuid=chunk_id, properties={PROPERTY: value})


async def count_flag(client: WeaviateAsyncClient, collection: str, value: bool | None = None) -> int:
    """Chunks whose flag equals ``value``; with None, all chunks."""
    filters = None if value is None else Filter.by_property(PROPERTY).equal(value)
    result = await client.collections.get(collection).aggregate.over_all(filters=filters, total_count=True)
    return result.total_count or 0
