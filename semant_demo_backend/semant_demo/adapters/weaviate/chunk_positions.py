"""The absolute position of each chunk in its document: ``Chunks`` schema, reads, updates (#463).

``startChar`` (``int``), ``startWord`` (``int``) and ``wordOpenAtStart`` (``boolean``) are
defined and computed in ``features/documents/positions.py``. Reads return ids, order,
text and these properties, never vectors. Collection names are resolved through aliases
by the caller. Never creates, drops or alters a collection; ``add_position_properties``
only adds the properties, on explicit request.
"""
from dataclasses import dataclass
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.config import DataType, Property
from weaviate.classes.query import Filter, Metrics

from semant_demo.adapters.weaviate.documents import POSITION_PROPERTIES
from semant_demo.features.documents.positions import ChunkPosition

PROPERTY_TYPES = {"startChar": DataType.INT, "startWord": DataType.INT, "wordOpenAtStart": DataType.BOOL}
"""The declared type of each position property (the keys of ``POSITION_PROPERTIES``)."""


@dataclass(frozen=True)
class StoredChunk:
    """A chunk's id, order, text and stored position (None when it has none, or only part of one)."""
    id: UUID
    order: int
    text: str
    position: ChunkPosition | None
    partial: bool
    """Some, but not all, position properties are stored."""


@dataclass(frozen=True)
class OrderStats:
    count: int
    first: int | None
    last: int | None


async def declared_types(client: WeaviateAsyncClient, collection: str) -> dict[str, str]:
    """The declared position properties of the collection and their data types."""
    config = await client.collections.get(collection).config.get()
    return {p.name: p.data_type.value for p in config.properties if p.name in PROPERTY_TYPES}


async def add_position_properties(client: WeaviateAsyncClient, collection: str, names: list[str]) -> None:
    """Declare the position properties ``names``; existing chunks have no value."""
    config = client.collections.get(collection).config
    for name in names:
        await config.add_property(Property(name=name, data_type=PROPERTY_TYPES[name]))


async def read_document_page(client: WeaviateAsyncClient, collection: str, after: UUID | None,
                             limit: int) -> list[UUID]:
    """Up to ``limit`` document ids following ``after`` in id order (cursor paging)."""
    response = await client.collections.get(collection).query.fetch_objects(
        limit=limit, after=after, return_properties=[])
    return [o.uuid for o in response.objects]


def _of_document(document_id: UUID) -> Filter:
    return Filter.by_ref("document").by_id().equal(document_id)


async def order_stats(client: WeaviateAsyncClient, collection: str, document_id: UUID) -> OrderStats:
    """The number of the document's chunks and their least and greatest ``order``."""
    response = await client.collections.get(collection).aggregate.over_all(
        filters=_of_document(document_id), total_count=True,
        return_metrics=[Metrics("order").integer(minimum=True, maximum=True)])
    order = response.properties["order"]
    count = response.total_count or 0
    return OrderStats(count, order.minimum if count else None, order.maximum if count else None)


def _position(props: dict) -> tuple[ChunkPosition | None, bool]:
    values = [props.get(name) for name in POSITION_PROPERTIES]
    if all(v is None for v in values):
        return None, False
    if any(v is None for v in values):
        return None, True
    return ChunkPosition(*values), False


async def read_order_range(client: WeaviateAsyncClient, collection: str, document_id: UUID, first: int, last: int,
                           with_positions: bool) -> list[StoredChunk]:
    """The document's chunks with ``first <= order <= last``, in order (duplicates included;
    no server-side sort; the orders are listed, see ``DocumentRepository.read_chunk_texts_in_range``).
    Without ``with_positions`` (not declared yet) every position is None."""
    response = await client.collections.get(collection).query.fetch_objects(
        filters=Filter.all_of([_of_document(document_id),
                               Filter.by_property("order").contains_any(list(range(first, last + 1)))]),
        limit=2 * (last - first + 1),
        return_properties=["order", "text", *(POSITION_PROPERTIES if with_positions else ())])
    chunks = []
    for o in response.objects:
        position, partial = _position(o.properties)
        chunks.append(StoredChunk(o.uuid, o.properties["order"], o.properties.get("text") or "", position, partial))
    return sorted(chunks, key=lambda c: c.order)


async def read_positions(client: WeaviateAsyncClient, collection: str,
                         ids: list[UUID]) -> dict[UUID, ChunkPosition | None]:
    """The stored positions of the chunks with these ids that exist."""
    if not ids:
        return {}
    response = await client.collections.get(collection).query.fetch_objects(
        filters=Filter.by_id().contains_any(ids), limit=len(ids), return_properties=list(POSITION_PROPERTIES))
    return {o.uuid: _position(o.properties)[0] for o in response.objects}


async def write_position(client: WeaviateAsyncClient, collection: str, chunk_id: UUID,
                         position: ChunkPosition) -> None:
    """Store the chunk's position; text, other properties, references and vectors are kept (a merge)."""
    await client.collections.get(collection).data.update(uuid=chunk_id, properties={
        name: getattr(position, field) for name, field in POSITION_PROPERTIES.items()})


async def count_chunks(client: WeaviateAsyncClient, collection: str) -> int:
    """All chunks of the collection."""
    response = await client.collections.get(collection).aggregate.over_all(total_count=True)
    return response.total_count or 0
