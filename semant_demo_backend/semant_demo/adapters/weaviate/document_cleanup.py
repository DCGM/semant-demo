"""Documents without chunks: reference schema, chunk-existence lookups, deletion (#281).

Reads only ids, creation times and references, never text or vectors. Collection names
are resolved through aliases first (the deployment serves ``Documents`` as an alias of
``Documents_test``), so every read and delete addresses the collection itself. Never
creates, drops or alters a collection.
"""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.backup import BackupStorage
from weaviate.classes.query import Filter, MetadataQuery, QueryReference
from weaviate.exceptions import WeaviateUnsupportedFeatureError


@dataclass(frozen=True)
class DocumentLinks:
    """A document's id, creation time and the user collections it links to (``collection``)."""
    id: UUID
    created: datetime | None
    collection_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class Backup:
    id: str
    status: str
    collections: tuple[str, ...]
    started: datetime | None
    completed: datetime | None


async def resolve_collection(client: WeaviateAsyncClient, name: str) -> str:
    """The collection an alias points to, or ``name`` itself."""
    try:
        alias = await client.alias.get(alias_name=name)
    except WeaviateUnsupportedFeatureError:  # before 1.32: no aliases
        alias = None
    return alias.collection if alias else name


async def reference_schema(client: WeaviateAsyncClient) -> dict[str, dict[str, list[str]]]:
    """Collection -> reference property -> target collections, for every collection."""
    configs = await client.collections.list_all(simple=True)
    return {name: {ref.name: sorted(ref.target_collections) for ref in config.references}
            for name, config in sorted(configs.items())}


async def total_count(client: WeaviateAsyncClient, collection: str) -> int:
    return (await client.collections.get(collection).aggregate.over_all(total_count=True)).total_count or 0


def _links(obj, link: str) -> DocumentLinks:
    refs = (obj.references or {}).get(link)
    return DocumentLinks(obj.uuid, obj.metadata.creation_time,
                         tuple(sorted({o.uuid for o in refs.objects})) if refs else ())


async def read_document_links_page(client: WeaviateAsyncClient, collection: str, link: str,
                                   after: UUID | None, limit: int) -> list[DocumentLinks]:
    """Up to ``limit`` documents following ``after`` in id order (cursor paging)."""
    response = await client.collections.get(collection).query.fetch_objects(
        limit=limit, after=after, return_properties=[], return_metadata=MetadataQuery(creation_time=True),
        return_references=QueryReference(link_on=link, return_properties=[]))
    return [_links(obj, link) for obj in response.objects]


async def read_document_links(client: WeaviateAsyncClient, collection: str, link: str,
                              ids: list[UUID]) -> dict[UUID, DocumentLinks]:
    """The documents with these ids that exist."""
    if not ids:
        return {}
    response = await client.collections.get(collection).query.fetch_objects(
        filters=Filter.by_id().contains_any(ids), limit=len(ids), return_properties=[],
        return_metadata=MetadataQuery(creation_time=True),
        return_references=QueryReference(link_on=link, return_properties=[]))
    return {obj.uuid: _links(obj, link) for obj in response.objects}


async def any_referencing(client: WeaviateAsyncClient, collection: str, link: str, target_id: UUID) -> bool:
    """Whether an object of ``collection`` references ``target_id`` through ``link`` (one-object query)."""
    response = await client.collections.get(collection).query.fetch_objects(
        filters=Filter.by_ref(link).by_id().equal(target_id), limit=1, return_properties=[])
    return bool(response.objects)


async def count_referencing(client: WeaviateAsyncClient, collection: str, link: str, target_id: UUID) -> int:
    """How many objects of ``collection`` reference ``target_id`` through ``link`` (aggregate)."""
    response = await client.collections.get(collection).aggregate.over_all(
        filters=Filter.by_ref(link).by_id().equal(target_id), total_count=True)
    return response.total_count or 0


async def referencing_among(client: WeaviateAsyncClient, collection: str, link: str, target_id: UUID,
                            ids: list[UUID]) -> list[UUID]:
    """Those of ``ids`` (objects of ``collection``) that reference ``target_id`` through ``link``."""
    if not ids:
        return []
    response = await client.collections.get(collection).query.fetch_objects(
        filters=Filter.by_id().contains_any(ids) & Filter.by_ref(link).by_id().equal(target_id),
        limit=len(ids), return_properties=[])
    return [obj.uuid for obj in response.objects]


async def sample_referenced(client: WeaviateAsyncClient, collection: str, link: str, limit: int) -> list[UUID]:
    """Targets of ``link`` on the first ``limit`` objects of ``collection``."""
    response = await client.collections.get(collection).query.fetch_objects(
        limit=limit, return_properties=[], return_references=QueryReference(link_on=link, return_properties=[]))
    return sorted({target for obj in response.objects for target in _links(obj, link).collection_ids})


async def existing_ids(client: WeaviateAsyncClient, collection: str, ids: list[UUID]) -> set[UUID]:
    if not ids:
        return set()
    response = await client.collections.get(collection).query.fetch_objects(
        filters=Filter.by_id().contains_any(ids), limit=len(ids), return_properties=[])
    return {obj.uuid for obj in response.objects}


async def delete_object(client: WeaviateAsyncClient, collection: str, object_id: UUID) -> bool:
    """Delete one object; False if it did not exist. Its own outgoing references go with it."""
    return await client.collections.get(collection).data.delete_by_id(object_id)


async def filesystem_backups(client: WeaviateAsyncClient) -> list[Backup]:
    """The backups of the ``backup-filesystem`` module (raises if the module is not enabled)."""
    backups = await client.backup.list_backups(backend=BackupStorage.FILESYSTEM)
    return [Backup(b.backup_id, b.status.value, tuple(b.collections), b.started_at, b.completed_at)
            for b in backups]
