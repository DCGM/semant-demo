"""The named vectors a chunk stores, listed in ``Chunks.haveVector`` (#805, #560, #590).

``Chunks.haveVector`` (``text[]``, ``field`` tokenization, filterable, not searchable) holds
the names of the named vectors computed for the chunk, e.g. ``["Qwen3_Embedding_0_6B"]``. An
embedder selects the chunks lacking a vector with ``haveVector contains_none([name])``.

Reads return the id, the list and whether the given named vector is stored. Writes are merges
of the single property (text, vectors, references and other properties are kept). Collection
names are resolved through aliases by the caller. Never creates, drops or alters a collection;
``add_property`` only adds the property, on explicit request.
"""
from dataclasses import dataclass
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.config import DataType, Property, Tokenization
from weaviate.classes.query import Filter

PROPERTY = "haveVector"


@dataclass(frozen=True)
class Declared:
    data_type: str
    tokenization: str | None
    filterable: bool
    searchable: bool


EXPECTED = Declared("text[]", "field", True, False)
"""The declaration ``add_property`` makes and the backfill accepts."""


@dataclass(frozen=True)
class ChunkVectors:
    """A chunk's id, its stored list (None when absent) and whether the vector is stored."""
    id: UUID
    listed: tuple[str, ...] | None
    has_vector: bool


async def declared(client: WeaviateAsyncClient, collection: str) -> Declared | None:
    """The declared ``haveVector`` of the collection, None if it is not declared."""
    config = await client.collections.get(collection).config.get()
    for prop in config.properties:
        if prop.name == PROPERTY:
            return Declared(prop.data_type.value, prop.tokenization.value if prop.tokenization else None,
                            bool(prop.index_filterable), bool(prop.index_searchable))
    return None


async def vector_names(client: WeaviateAsyncClient, collection: str) -> list[str]:
    config = await client.collections.get(collection).config.get()
    return sorted((config.vector_config or {}).keys())


async def add_property(client: WeaviateAsyncClient, collection: str) -> None:
    """Declare ``haveVector`` as ``EXPECTED`` on ``collection`` (a real collection name, not an
    alias); existing chunks have no value."""
    await client.collections.get(collection).config.add_property(Property(
        name=PROPERTY, data_type=DataType.TEXT_ARRAY, tokenization=Tokenization.FIELD,
        index_filterable=True, index_searchable=False))


def _chunk(obj, vector: str) -> ChunkVectors:
    listed = obj.properties.get(PROPERTY)
    stored = (obj.vector or {}).get(vector)
    return ChunkVectors(obj.uuid, None if listed is None else tuple(listed), bool(stored))


def _returned(vector: str, is_declared: bool) -> dict:
    return dict(return_properties=[PROPERTY] if is_declared else [], include_vector=[vector])


async def read_chunk_page(client: WeaviateAsyncClient, collection: str, vector: str, after: UUID | None,
                          limit: int, is_declared: bool = True) -> list[ChunkVectors]:
    """Up to ``limit`` chunks following ``after`` in id order (cursor paging), with the named
    vector read to learn whether it is stored. Without ``is_declared`` every list reads as None."""
    response = await client.collections.get(collection).query.fetch_objects(
        limit=limit, after=after, **_returned(vector, is_declared))
    return [_chunk(obj, vector) for obj in response.objects]


async def read_chunks(client: WeaviateAsyncClient, collection: str, vector: str, ids: list[UUID],
                      is_declared: bool = True) -> dict[UUID, ChunkVectors]:
    """The chunks with these ids that exist."""
    if not ids:
        return {}
    response = await client.collections.get(collection).query.fetch_objects(
        filters=Filter.by_id().contains_any(ids), limit=len(ids), **_returned(vector, is_declared))
    return {obj.uuid: _chunk(obj, vector) for obj in response.objects}


async def set_listed(client: WeaviateAsyncClient, collection: str, chunk_id: UUID, names: list[str]) -> None:
    """Replace the chunk's ``haveVector`` list (a merge: other properties, references and the
    vectors are kept)."""
    await client.collections.get(collection).data.update(uuid=chunk_id, properties={PROPERTY: names})


async def count(client: WeaviateAsyncClient, collection: str, vector: str | None = None,
                listed: bool = True) -> int:
    """All chunks; with ``vector`` those whose list contains it (``listed``) or does not
    (``contains_none``, the embedder's selection; also the chunks without a list)."""
    filters = None
    if vector is not None:
        prop = Filter.by_property(PROPERTY)
        filters = prop.contains_any([vector]) if listed else prop.contains_none([vector])
    result = await client.collections.get(collection).aggregate.over_all(filters=filters, total_count=True)
    return result.total_count or 0
