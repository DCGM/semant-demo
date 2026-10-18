"""Span annotations in the multi-tenant ``Annotation`` collection (#327).

One tenant per user collection: the tenant name is the collection's UUID
(``tenant_name``), never derived from a user, so sharing reads the same tenant and a
rename or ownership change keeps it. Every method takes the collection whose tenant it
uses; the Annotations service passes the collection it has authorized, so a span id is
only looked up inside that tenant and a guessed id of another collection is not found.

A span is a range on the chunk where it starts, with a tag and a type
(``pos``/``auto``/``neg``). ``tagId``, ``chunkId`` and ``documentId`` are plain UUID
properties, filtered directly: Weaviate 1.40 cannot return the references of a
multi-tenant object to a collection without tenants. The ``text_chunk`` reference is kept
only for the collection-membership filters of the statistics. Offsets are stored as given
(see ``features/annotations/offsets.py``).

Tenants are created lazily, by the first write (``ensure_tenant``); reading a collection
without a tenant returns nothing and creates none. Tenants may be inactive
(``maintenance.annotation_tenants``); the collection activates them on access
(``auto_tenant_activation``). This repository only reads and writes spans; the chunk tag
references derived from them are updated by ``chunk_tags.ChunkTagRepository`` and the
order of these writes is decided by the Annotations service.
"""
import logging
from typing import Awaitable, Callable, TypeVar
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.config import Configure, DataType, Property, ReferenceProperty, Tokenization
from weaviate.classes.query import Filter
from weaviate.classes.tenants import Tenant, TenantActivityStatus
from weaviate.exceptions import WeaviateBaseError

from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.adapters.weaviate.chunk_tags import ChunkTag
from semant_demo.adapters.weaviate.paging import fetch_all
from semant_demo.adapters.weaviate.writes import NoProgressError
from semant_demo.features.annotations.schemas import PatchSpan, PostSpan, SpanType, TagSpan

logger = logging.getLogger(__name__)

T = TypeVar("T")

_PROPERTIES = ["start", "end", "type", "reason", "confidence", "tagId", "chunkId"]
# Deleting the spans of a tag repeats delete_many until none match; it removes at most
# QUERY_MAXIMUM_RESULTS objects per call.
_MAX_DELETE_ROUNDS = 1000


def tenant_name(collection_id: UUID) -> str:
    """The annotation tenant of a user collection: its UUID in canonical form."""
    return str(UUID(str(collection_id)))


def is_tenant_not_found(exc: Exception) -> bool:
    """Whether Weaviate refused a request because the tenant does not exist."""
    return isinstance(exc, WeaviateBaseError) and "tenant not found" in str(exc)


async def create_annotation_collection(client: WeaviateAsyncClient, names: CollectionNames) -> None:
    """Create the empty multi-tenant annotation collection (the migration's ``--create-schema``).

    No tenant is created here. Vectors are self-provided under ``default`` (flat index,
    unused yet); #328 adds the contextual vector as another named vector (``add_vector``,
    supported on 1.40 for an existing collection).
    """
    uuid = DataType.UUID
    await client.collections.create(
        names.annotation_collection_name,
        multi_tenancy_config=Configure.multi_tenancy(
            enabled=True, auto_tenant_creation=False, auto_tenant_activation=True),
        vector_config=Configure.Vectors.self_provided(
            name="default", vector_index_config=Configure.VectorIndex.flat()),
        properties=[
            Property(name="tagId", data_type=uuid),
            Property(name="chunkId", data_type=uuid),
            Property(name="documentId", data_type=uuid),
            Property(name="start", data_type=DataType.INT),
            Property(name="end", data_type=DataType.INT),
            Property(name="type", data_type=DataType.TEXT, tokenization=Tokenization.FIELD,
                     index_searchable=False),
            Property(name="reason", data_type=DataType.TEXT),
            Property(name="confidence", data_type=DataType.NUMBER),
        ],
        references=[ReferenceProperty(name="text_chunk", target_collection=names.chunks_collection_name)],
    )


def _uuid(value) -> UUID | None:
    return UUID(str(value)) if value is not None else None


def to_span(obj) -> TagSpan:
    props = obj.properties
    span_type, confidence = props.get("type"), props.get("confidence")
    chunk, tag = props.get("chunkId"), props.get("tagId")
    return TagSpan(
        id=str(obj.uuid),
        chunkId=str(chunk) if chunk is not None else None,
        tagId=str(tag) if tag is not None else "",
        start=props.get("start"),
        end=props.get("end"),
        type=SpanType(span_type) if isinstance(span_type, str) else None,
        reason=props.get("reason"),
        confidence=float(confidence) if confidence is not None else None,
    )


def pair_of(span: TagSpan) -> ChunkTag:
    """The (chunk, tag) pair whose chunk tag references the span backs."""
    return ChunkTag.of(span.chunkId, span.tagId)


class SpanRepository:
    def __init__(self, client: WeaviateAsyncClient, collectionNames: CollectionNames):
        self.client = client
        self.collectionNames = collectionNames
        # Tenants this process created or saw; a removed tenant is forgotten by ``remove_tenant``.
        self._known_tenants: set[str] = set()

    def _collection(self):
        return self.client.collections.get(self.collectionNames.annotation_collection_name)

    def _tenant(self, collection_id: UUID):
        return self._collection().with_tenant(tenant_name(collection_id))

    # ── Tenants ───────────────────────────────────────────────────────────

    async def ensure_tenant(self, collection_id: UUID) -> None:
        """Create the collection's tenant unless it exists. Creating it is idempotent in
        Weaviate, also when several requests or workers do it at the same time."""
        name = tenant_name(collection_id)
        if name in self._known_tenants:
            return
        await self._collection().tenants.create([Tenant(name=name)])
        self._known_tenants.add(name)

    async def tenant_exists(self, collection_id: UUID) -> bool:
        """Whether the tenant exists (read without activating it); raises if the lookup fails."""
        return await self._collection().tenants.get_by_name(tenant_name(collection_id)) is not None

    async def tenant_status(self, collection_id: UUID) -> TenantActivityStatus | None:
        tenant = await self._collection().tenants.get_by_name(tenant_name(collection_id))
        return tenant.activity_status if tenant is not None else None

    async def list_tenants(self) -> dict[str, TenantActivityStatus]:
        """Every annotation tenant with its status (read without activating any)."""
        return {name: t.activity_status for name, t in (await self._collection().tenants.get()).items()}

    async def deactivate_tenant(self, name: str) -> None:
        """Mark the tenant inactive (its data stays on disk; the next access activates it)."""
        await self._collection().tenants.update([Tenant(name=name, activity_status=TenantActivityStatus.INACTIVE)])

    async def remove_tenant(self, collection_id: UUID) -> None:
        """Delete the tenant with all its spans, then confirm that it is gone.

        Removing a tenant that does not exist succeeds in Weaviate, so only the lookup
        afterwards shows the result; a failed lookup raises rather than counting as done.
        """
        name = tenant_name(collection_id)
        self._known_tenants.discard(name)
        await self._collection().tenants.remove([name])
        if await self.tenant_exists(collection_id):
            raise RuntimeError(f"Annotation tenant {name} still exists after its removal")

    async def _read(self, collection_id: UUID, read: Callable[[], Awaitable[T]], empty: T) -> T:
        """``read()``, or ``empty`` when the collection has no tenant (confirmed by a lookup)."""
        try:
            return await read()
        except Exception as e:
            if is_tenant_not_found(e) and not await self.tenant_exists(collection_id):
                return empty
            raise

    # ── Spans ─────────────────────────────────────────────────────────────

    async def insert(self, collection_id: UUID, span: PostSpan, document_id: UUID | None) -> UUID:
        """Stores the span in the collection's tenant (created if needed) and returns its id."""
        await self.ensure_tenant(collection_id)
        properties: dict = {"start": span.start, "end": span.end, "type": span.type.value,
                            "tagId": UUID(span.tagId), "chunkId": UUID(span.chunkId)}
        if document_id is not None:
            properties["documentId"] = document_id
        # AI metadata only when present.
        if span.reason is not None:
            properties["reason"] = span.reason
        if span.confidence is not None:
            properties["confidence"] = float(span.confidence)
        try:
            return await self._tenant(collection_id).data.insert(
                properties=properties, references={"text_chunk": span.chunkId})
        except Exception as e:
            if not is_tenant_not_found(e):
                raise
        # Known here, but removed since (by another worker): nothing was written, so
        # creating the tenant again and repeating the insert is safe.
        self._known_tenants.discard(tenant_name(collection_id))
        await self.ensure_tenant(collection_id)
        return await self._tenant(collection_id).data.insert(
            properties=properties, references={"text_chunk": span.chunkId})

    async def read(self, collection_id: UUID, span_id: UUID) -> TagSpan | None:
        """The collection's span with this id, or None."""
        async def read():
            obj = await self._tenant(collection_id).query.fetch_object_by_id(span_id, return_properties=_PROPERTIES)
            return to_span(obj) if obj is not None else None
        return await self._read(collection_id, read, None)

    async def read_many(self, collection_id: UUID, span_ids: list[UUID]) -> dict[UUID, TagSpan]:
        """The collection's spans among ``span_ids``; ids of other collections are absent."""
        if not span_ids:
            return {}

        async def read():
            response = await self._tenant(collection_id).query.fetch_objects(
                filters=Filter.by_id().contains_any(list(span_ids)), limit=len(span_ids),
                return_properties=_PROPERTIES)
            return {UUID(str(o.uuid)): to_span(o) for o in response.objects}
        return await self._read(collection_id, read, {})

    async def _fetch(self, collection_id: UUID, filters, return_properties=None) -> list:
        return await self._read(collection_id, lambda: fetch_all(
            self._tenant(collection_id), filters=filters, page_size=500,
            return_properties=_PROPERTIES if return_properties is None else return_properties), [])

    async def read_by_collection(self, collection_id: UUID, chunk_id: UUID | None = None) -> list[TagSpan]:
        """All spans of the collection, optionally only those starting on one chunk."""
        filters = Filter.by_property("chunkId").equal(chunk_id) if chunk_id is not None else None
        return [to_span(o) for o in await self._fetch(collection_id, filters)]

    async def read_by_chunks(self, collection_id: UUID, chunk_ids: list[UUID]) -> dict[str, list[TagSpan]]:
        """The collection's spans starting on each of the chunks, keyed by chunk id (all chunks present)."""
        result: dict[str, list[TagSpan]] = {str(c): [] for c in chunk_ids}
        if not chunk_ids:
            return result
        for obj in await self._fetch(collection_id, Filter.by_property("chunkId").contains_any(list(chunk_ids))):
            span = to_span(obj)
            if span.chunkId in result:
                result[span.chunkId].append(span)
        return result

    async def update(self, collection_id: UUID, span_id: UUID, patch: PatchSpan) -> None:
        """Sets the patched offsets, type and tag in one write."""
        fields = patch.model_dump(exclude_none=True)
        properties: dict = {k: fields[k] for k in ("start", "end") if k in fields}
        if patch.type is not None:
            properties["type"] = patch.type.value
        if patch.tagId is not None:
            properties["tagId"] = UUID(patch.tagId)
        if properties:
            await self._tenant(collection_id).data.update(uuid=span_id, properties=properties)

    async def delete(self, collection_id: UUID, span_id: UUID) -> None:
        await self._tenant(collection_id).data.delete_by_id(span_id)

    async def list_in_document(self, collection_id: UUID, document_id: UUID, tag_ids: list[UUID],
                               span_type: SpanType) -> dict[UUID, set[ChunkTag]]:
        """
        Ids of the collection's spans of one type and the given tags that start on a chunk
        of the document, with their (chunk, tag) pairs. Listed completely before the
        caller writes, so failed deletions cannot make the listing loop.
        """
        if not tag_ids:
            return {}
        filters = (Filter.by_property("tagId").contains_any(list(tag_ids))
                   & Filter.by_property("documentId").equal(document_id)
                   & Filter.by_property("type").equal(span_type.value))
        return {UUID(str(o.uuid)): {pair_of(to_span(o))} for o in await self._fetch(collection_id, filters)}

    async def types_on_pair(self, collection_id: UUID, pair: ChunkTag) -> set[str]:
        """Types of the collection's spans with the pair's tag anchored on its chunk."""
        filters = (Filter.by_property("tagId").equal(pair.tag_id)
                   & Filter.by_property("chunkId").equal(pair.chunk_id))
        return {o.properties.get("type") for o in await self._fetch(collection_id, filters, ["type"])}

    async def delete_by_tag(self, collection_id: UUID, tag_id: UUID) -> int:
        """Delete every span of the tag; returns how many were deleted.

        Raises ``NoProgressError`` when a round deletes nothing although spans still
        match, and ``RuntimeError`` when some deletions failed, so the caller reports an
        incomplete cascade instead of looping.
        """
        tenant = self._tenant(collection_id)
        where = Filter.by_property("tagId").equal(tag_id)
        deleted = 0
        for _ in range(_MAX_DELETE_ROUNDS):
            try:
                result = await tenant.data.delete_many(where=where)
            except Exception as e:
                if is_tenant_not_found(e) and not await self.tenant_exists(collection_id):
                    return deleted
                raise
            deleted += result.successful
            if result.failed:
                raise RuntimeError(f"{result.failed} of {result.matches} span deletions failed")
            if not result.matches:
                return deleted
            if not result.successful:
                raise NoProgressError(f"{result.matches} spans matched and none was deleted")
        raise NoProgressError("Spans of the tag still match after the maximum number of delete rounds")

    # ── Statistics ────────────────────────────────────────────────────────

    async def count_approved(self, collection_id: UUID, document_id: UUID | None = None) -> int:
        """Approved (``pos``) spans anchored on a chunk that belongs to the collection
        (and to the document, when given)."""
        link = self.collectionNames.user_collection_link_name
        filters = (Filter.by_property("type").equal(SpanType.pos.value)
                   & Filter.by_ref("text_chunk").by_ref(link).by_id().equal(collection_id))
        if document_id is not None:
            filters = filters & Filter.by_property("documentId").equal(document_id)

        async def count():
            result = await self._tenant(collection_id).aggregate.over_all(total_count=True, filters=filters)
            return result.total_count or 0
        return await self._read(collection_id, count, 0)

    async def approved_tag_ids(self, collection_id: UUID, document_id: UUID) -> set[UUID]:
        """Distinct tags of the spans ``count_approved`` counts for the document."""
        link = self.collectionNames.user_collection_link_name
        filters = (Filter.by_property("type").equal(SpanType.pos.value)
                   & Filter.by_property("documentId").equal(document_id)
                   & Filter.by_ref("text_chunk").by_ref(link).by_id().equal(collection_id))
        return {_uuid(o.properties.get("tagId")) for o in await self._fetch(collection_id, filters, ["tagId"])
                if o.properties.get("tagId") is not None}
