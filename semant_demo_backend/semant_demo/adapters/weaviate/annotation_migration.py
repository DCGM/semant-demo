"""Weaviate reads and writes of the annotation migration (#327, ``maintenance.annotation_migration``).

Reads the legacy single-tenant ``Span`` collection page by page in UUID order (the
resumable cursor), the tags, chunks and collections its spans reference, and the
multi-tenant ``Annotation`` collection; inserts copies into the tenants. Never writes the
legacy collection, tags, chunks or collections. Nothing here runs at startup or during
requests.
"""
from dataclasses import dataclass
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.data import DataObject
from weaviate.classes.query import Filter, QueryReference
from weaviate.classes.tenants import Tenant

from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.adapters.weaviate.spans import create_annotation_collection, is_tenant_not_found, tenant_name

LEGACY_PROPERTIES = ["start", "end", "type", "reason", "confidence"]
TARGET_PROPERTIES = ["tagId", "chunkId", "documentId", "start", "end", "type", "reason", "confidence"]


def _ref_ids(obj, prop: str) -> list[UUID]:
    block = (obj.references or {}).get(prop) if obj is not None else None
    return [UUID(str(r.uuid)) for r in (block.objects if block else [])]


@dataclass(frozen=True)
class LegacySpan:
    id: UUID
    properties: dict
    tag_ids: list[UUID]
    chunk_ids: list[UUID]


@dataclass(frozen=True)
class SourceChunk:
    id: UUID
    document_ids: list[UUID]
    collection_ids: list[UUID]


@dataclass(frozen=True)
class TargetSpan:
    id: UUID
    properties: dict


class MigrationStore:
    def __init__(self, client: WeaviateAsyncClient, names: CollectionNames):
        self.client = client
        self.names = names

    def _get(self, name: str):
        return self.client.collections.get(name)

    def _target(self):
        return self._get(self.names.annotation_collection_name)

    # ── Source ────────────────────────────────────────────────────────────

    async def legacy_exists(self) -> bool:
        return await self.client.collections.exists(self.names.span_collection_name)

    async def legacy_count(self) -> int:
        result = await self._get(self.names.span_collection_name).aggregate.over_all(total_count=True)
        return result.total_count or 0

    async def legacy_page(self, after: UUID | None, limit: int) -> list[LegacySpan]:
        """Up to ``limit`` legacy spans with ids after ``after``, in UUID order."""
        response = await self._get(self.names.span_collection_name).query.fetch_objects(
            after=after, limit=limit, return_properties=LEGACY_PROPERTIES,
            return_references=[QueryReference(link_on="tag", return_properties=[]),
                               QueryReference(link_on="text_chunk", return_properties=[])])
        return [LegacySpan(UUID(str(o.uuid)), dict(o.properties), _ref_ids(o, "tag"), _ref_ids(o, "text_chunk"))
                for o in response.objects]

    async def tag_owners(self, tag_ids: list[UUID]) -> dict[UUID, list[UUID]]:
        """The collections each existing tag references; missing tags are absent."""
        if not tag_ids:
            return {}
        response = await self._get(self.names.tag_collection_name).query.fetch_objects(
            filters=Filter.by_id().contains_any(tag_ids), limit=len(tag_ids), return_properties=[],
            return_references=[QueryReference(link_on="userCollection", return_properties=[])])
        return {UUID(str(o.uuid)): _ref_ids(o, "userCollection") for o in response.objects}

    async def all_tag_owners(self) -> dict[UUID, list[UUID]]:
        """Every tag with the collections it references (inventory)."""
        result: dict[UUID, list[UUID]] = {}
        async for obj in self._get(self.names.tag_collection_name).iterator(
                return_properties=[], return_references=[QueryReference(link_on="userCollection", return_properties=[])]):
            result[UUID(str(obj.uuid))] = _ref_ids(obj, "userCollection")
        return result

    async def existing_collections(self, collection_ids: list[UUID]) -> set[UUID]:
        if not collection_ids:
            return set()
        response = await self._get(self.names.user_collection_name).query.fetch_objects(
            filters=Filter.by_id().contains_any(collection_ids), limit=len(collection_ids), return_properties=[])
        return {UUID(str(o.uuid)) for o in response.objects}

    async def all_collection_ids(self) -> set[UUID]:
        return {UUID(str(o.uuid)) async for o in self._get(self.names.user_collection_name).iterator(
            return_properties=[])}

    async def chunks(self, chunk_ids: list[UUID]) -> dict[UUID, SourceChunk]:
        if not chunk_ids:
            return {}
        response = await self._get(self.names.chunks_collection_name).query.fetch_objects(
            filters=Filter.by_id().contains_any(chunk_ids), limit=len(chunk_ids), return_properties=[],
            return_references=[QueryReference(link_on="document", return_properties=[]),
                               QueryReference(link_on=self.names.user_collection_link_name, return_properties=[])])
        return {UUID(str(o.uuid)): SourceChunk(UUID(str(o.uuid)), _ref_ids(o, "document"),
                                               _ref_ids(o, self.names.user_collection_link_name))
                for o in response.objects}

    # ── Target ────────────────────────────────────────────────────────────

    async def target_exists(self) -> bool:
        return await self.client.collections.exists(self.names.annotation_collection_name)

    async def target_is_multi_tenant(self) -> bool:
        config = await self._target().config.get()
        return bool(config.multi_tenancy_config and config.multi_tenancy_config.enabled)

    async def create_target(self) -> None:
        await create_annotation_collection(self.client, self.names)

    async def target_tenants(self) -> list[str]:
        return sorted((await self._target().tenants.get()).keys())

    async def ensure_tenant(self, collection_id: UUID) -> None:
        await self._target().tenants.create([Tenant(name=tenant_name(collection_id))])

    async def target_spans(self, collection_id: UUID, span_ids: list[UUID]) -> dict[UUID, TargetSpan]:
        """The tenant's spans among ``span_ids`` (none when the tenant does not exist)."""
        if not span_ids:
            return {}
        try:
            response = await self._target().with_tenant(tenant_name(collection_id)).query.fetch_objects(
                filters=Filter.by_id().contains_any(span_ids), limit=len(span_ids),
                return_properties=TARGET_PROPERTIES)
        except Exception as e:
            if is_tenant_not_found(e) and await self._target().tenants.get_by_name(tenant_name(collection_id)) is None:
                return {}
            raise
        return {UUID(str(o.uuid)): TargetSpan(UUID(str(o.uuid)), dict(o.properties)) for o in response.objects}

    async def iterate_tenant(self, tenant: str):
        """Every span of a tenant (``verify``); activates an inactive tenant."""
        async for obj in self._target().with_tenant(tenant).iterator(return_properties=TARGET_PROPERTIES):
            yield TargetSpan(UUID(str(obj.uuid)), dict(obj.properties))

    async def insert(self, collection_id: UUID, objects: list[tuple[UUID, dict, UUID]]) -> dict[UUID, str]:
        """Insert ``(id, properties, chunk id)`` objects into the tenant; returns the error
        message of each object Weaviate refused (empty when all were stored).

        A batch insert replaces an object with the same id, so callers insert only ids
        they found absent from the tenant just before.
        """
        result = await self._target().with_tenant(tenant_name(collection_id)).data.insert_many([
            DataObject(uuid=span_id, properties=properties, references={"text_chunk": chunk_id})
            for span_id, properties, chunk_id in objects])
        return {objects[i][0]: (e.message or "insert failed") for i, e in result.errors.items()}
