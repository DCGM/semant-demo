"""Document metadata synchronization: the ``Documents`` schema, reads by page or id, updates (#257).

Never creates, drops or alters a collection; ``add_text_property`` only adds a property,
on explicit request.
"""
from collections.abc import AsyncIterator, Sequence
from typing import Any
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.config import DataType, Property, Tokenization
from weaviate.classes.query import Filter, Sort
from weaviate.exceptions import WeaviateUnsupportedFeatureError

from semant_demo.adapters.weaviate.names import CollectionNames


def _documents(client: WeaviateAsyncClient, names: CollectionNames):
    return client.collections.get(names.document_collection_name)


async def document_property_types(client: WeaviateAsyncClient, names: CollectionNames) -> dict[str, str] | None:
    """Declared property name -> Weaviate data type (``text``, ``text[]``, ``int``, ``number``,
    ``date``, ``boolean``, ``uuid``, ...) of the documents collection; None if it does not exist.
    References are not included."""
    if not await client.collections.exists(names.document_collection_name):
        return None
    config = await _documents(client, names).config.get()
    return {prop.name: prop.data_type.value for prop in config.properties}


async def read_document_page(client: WeaviateAsyncClient, names: CollectionNames,
                             after: UUID | None, limit: int) -> list[tuple[UUID, dict[str, Any]]]:
    """Up to ``limit`` documents (id, properties) following ``after`` in id order."""
    response = await _documents(client, names).query.fetch_objects(limit=limit, after=after)
    return [(obj.uuid, dict(obj.properties)) for obj in response.objects]


async def read_documents(client: WeaviateAsyncClient, names: CollectionNames,
                         ids: Sequence[UUID]) -> dict[UUID, dict[str, Any]]:
    """The properties of the documents with these ids that exist."""
    if not ids:
        return {}
    response = await _documents(client, names).query.fetch_objects(
        filters=Filter.by_id().contains_any(list(ids)), limit=len(ids))
    return {obj.uuid: dict(obj.properties) for obj in response.objects}


async def update_document(client: WeaviateAsyncClient, names: CollectionNames,
                          document_id: UUID, properties: dict[str, Any]) -> None:
    """Set these properties of the document; others are kept."""
    await _documents(client, names).data.update(uuid=document_id, properties=properties)


async def add_text_property(client: WeaviateAsyncClient, names: CollectionNames, name: str) -> None:
    """Declare a text property on the documents collection, matched as a whole value (``field``
    tokenization: a filter on ``cuni`` does not match ``cuni_fsv``); existing documents have no value.
    An alias (e.g. ``Documents`` -> ``Documents_test`` in the deployment) is resolved first: Weaviate
    1.34 serves reads through an alias but not schema updates."""
    collection = names.document_collection_name
    try:
        alias = await client.alias.get(alias_name=collection)
    except WeaviateUnsupportedFeatureError:  # before 1.32: no aliases
        alias = None
    await client.collections.get(alias.collection if alias else collection).config.add_property(
        Property(name=name, data_type=DataType.TEXT, tokenization=Tokenization.FIELD))


async def read_start_pages(client: WeaviateAsyncClient, names: CollectionNames,
                           document_id: UUID, limit: int) -> tuple[list[Any], bool]:
    """The ``start_page_id`` values (as stored, possibly missing or invalid) of up to ``limit``
    chunks of the document, and whether it has more chunks. Reads no text or vectors."""
    response = await client.collections.get(names.chunks_collection_name).query.fetch_objects(
        filters=Filter.by_ref("document").by_id().equal(document_id),
        limit=limit + 1, return_properties=["start_page_id"])
    return [obj.properties.get("start_page_id") for obj in response.objects[:limit]], len(response.objects) > limit


START_PAGE_BATCH = 1000


class IncompleteRead(RuntimeError):
    """Not every chunk of the document could be read."""


async def iter_start_pages(client: WeaviateAsyncClient, names: CollectionNames, document_id: UUID,
                           page_size: int = START_PAGE_BATCH) -> AsyncIterator[list[Any]]:
    """The ``start_page_id`` values (as stored) of every chunk of the document, in batches of
    at most ``page_size``. Reads no text or vectors.

    Keyset paging on ``order`` (``order >= last``, sorted by ``order``; the chunks already
    returned at ``last`` are skipped), so the read has no offset limit and stays stable. Raises
    ``IncompleteRead`` when a chunk has no ``order``, when more than ``page_size - 1`` chunks
    share one ``order``, or when the number of chunks read differs from the document's chunk
    count (e.g. written during the read): a partial read is never a complete one."""
    if page_size < 2:
        raise ValueError("page_size must be at least 2")
    chunks = client.collections.get(names.chunks_collection_name)
    by_document = Filter.by_ref("document").by_id().equal(document_id)
    total = (await chunks.aggregate.over_all(filters=by_document, total_count=True)).total_count
    read, last, seen = 0, None, set()
    while True:
        filters = by_document if last is None else by_document & Filter.by_property("order").greater_or_equal(last)
        response = await chunks.query.fetch_objects(filters=filters, limit=page_size, sort=Sort.by_property("order"),
                                                    return_properties=["order", "start_page_id"])
        objects = response.objects
        if any(not isinstance(o.properties.get("order"), int) for o in objects):
            raise IncompleteRead(f"a chunk of {document_id} has no order")
        fresh = [o for o in objects if not (o.properties["order"] == last and o.uuid in seen)]
        if len(objects) == page_size and all(o.properties["order"] == objects[0].properties["order"] for o in objects):
            raise IncompleteRead(f"{page_size} or more chunks of {document_id} share order {objects[0].properties['order']}")
        if fresh:
            read += len(fresh)
            yield [o.properties.get("start_page_id") for o in fresh]
        if len(objects) < page_size:
            break
        top = objects[-1].properties["order"]
        seen = {o.uuid for o in objects if o.properties["order"] == top} | (seen if top == last else set())
        last = top
    if read != total:
        raise IncompleteRead(f"read {read} of {total} chunks of {document_id}")
