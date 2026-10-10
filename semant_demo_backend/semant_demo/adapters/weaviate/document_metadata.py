"""Document metadata synchronization: the ``Documents`` schema, reads by page or id, updates (#257).

Only reads the schema; never creates, alters or drops a collection or property.
"""
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter

import semant_demo.schemas as schemas


def _documents(client: WeaviateAsyncClient, names: schemas.CollectionNames):
    return client.collections.get(names.document_collection_name)


async def document_property_types(client: WeaviateAsyncClient, names: schemas.CollectionNames) -> dict[str, str] | None:
    """Declared property name -> Weaviate data type (``text``, ``text[]``, ``int``, ``number``,
    ``date``, ``boolean``, ``uuid``, ...) of the documents collection; None if it does not exist.
    References are not included."""
    if not await client.collections.exists(names.document_collection_name):
        return None
    config = await _documents(client, names).config.get()
    return {prop.name: prop.data_type.value for prop in config.properties}


async def read_document_page(client: WeaviateAsyncClient, names: schemas.CollectionNames,
                             after: UUID | None, limit: int) -> list[tuple[UUID, dict[str, Any]]]:
    """Up to ``limit`` documents (id, properties) following ``after`` in id order."""
    response = await _documents(client, names).query.fetch_objects(limit=limit, after=after)
    return [(obj.uuid, dict(obj.properties)) for obj in response.objects]


async def read_documents(client: WeaviateAsyncClient, names: schemas.CollectionNames,
                         ids: Sequence[UUID]) -> dict[UUID, dict[str, Any]]:
    """The properties of the documents with these ids that exist."""
    if not ids:
        return {}
    response = await _documents(client, names).query.fetch_objects(
        filters=Filter.by_id().contains_any(list(ids)), limit=len(ids))
    return {obj.uuid: dict(obj.properties) for obj in response.objects}


async def update_document(client: WeaviateAsyncClient, names: schemas.CollectionNames,
                          document_id: UUID, properties: dict[str, Any]) -> None:
    """Set these properties of the document; others are kept."""
    await _documents(client, names).data.update(uuid=document_id, properties=properties)
