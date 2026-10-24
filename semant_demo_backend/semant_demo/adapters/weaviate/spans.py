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

Derived fields (#328, ``features/annotations/derivation.py`` and ``enrichment.py``) live
on the same objects: ``revision`` counts boundary changes; ``text``, the contexts and
positions with ``enrichmentStatus``, ``enrichedRevision`` and ``derivationVersion``; the
contextual named vector with ``vectorStatus``, ``vectorRevision`` and ``vectorConfig``.
Derived data is current only for the revision it names, so a late or stale write is
recognizable instead of trusted. They are written only when the service passes them
(the collection holds them, ``enrichment_schema``); ``add_enrichment_schema`` adds them
to an existing collection on the operator's request.

Attributes (#331): ``attributeValues`` (accepted categorical assignments as ``<attribute id>:<value id>``
elements, ``features/attributes/codec.py``) and ``attributeVersion`` (assignment writes since
creation, separate from ``editVersion``). Read and written only when the collection holds them
(``SpanRepository.attributes``, set at startup from ``attribute_schema``); ``add_attribute_schema`` adds
them on the operator's request.

Provenance (#460): ``origin``, ``createdBy``/``createdAt``, ``reviewedBy``/``reviewedAt``,
``lastEditedBy``/``lastEditedAt``, ``aiRunId`` and ``editVersion`` (span writes since
creation). They are read and written only when the collection holds them
(``SpanRepository.provenance``, set at startup from ``provenance_schema``);
``add_provenance_schema`` adds them on the operator's request. Spans without them have
``origin`` unknown and version 0.
"""
import asyncio
import logging
import weakref
from typing import Awaitable, Callable, TypeVar
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.config import Configure, DataType, Property, ReferenceProperty, Tokenization
from weaviate.classes.aggregate import GroupByAggregate
from weaviate.classes.query import Filter, MetadataQuery, Sort
from weaviate.classes.tenants import Tenant, TenantActivityStatus
from weaviate.exceptions import WeaviateBaseError

from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.adapters.weaviate.chunk_tags import ChunkTag
from semant_demo.adapters.weaviate.document_cleanup import resolve_collection
from semant_demo.adapters.weaviate.paging import fetch_all
from semant_demo.adapters.weaviate.writes import NoProgressError
from semant_demo.features.annotations.schemas import (
    AnnotationQuery, AnnotationRow, PatchSpan, PostSpan, SpanType, TagSpan,
)
from semant_demo.features.attributes import codec

logger = logging.getLogger(__name__)

T = TypeVar("T")

_PROPERTIES = ["start", "end", "type", "reason", "confidence", "tagId", "chunkId"]
DEFAULT_VECTOR_NAME = "contextual"
# Deleting the spans of a tag repeats delete_many until none match; it removes at most
# QUERY_MAXIMUM_RESULTS objects per call.
_MAX_DELETE_ROUNDS = 1000


def tenant_name(collection_id: UUID) -> str:
    """The annotation tenant of a user collection: its UUID in canonical form."""
    return str(UUID(str(collection_id)))


def is_tenant_not_found(exc: Exception) -> bool:
    """Whether Weaviate refused a request because the tenant does not exist."""
    return isinstance(exc, WeaviateBaseError) and "tenant not found" in str(exc)


def _searchable(name: str) -> Property:
    return Property(name=name, data_type=DataType.TEXT)


def _status(name: str) -> Property:
    return Property(name=name, data_type=DataType.TEXT, tokenization=Tokenization.FIELD, index_searchable=False)


def _position(name: str) -> Property:
    return Property(name=name, data_type=DataType.INT, index_range_filters=True)


ENRICHMENT_PROPERTIES: list[Property] = [
    Property(name="revision", data_type=DataType.INT),
    _searchable("text"), _searchable("leftContext"), _searchable("rightContext"),
    _position("documentStartChar"), _position("documentEndChar"),
    _position("documentStartWord"), _position("documentEndWord"),
    _status("enrichmentStatus"),
    Property(name="enrichedRevision", data_type=DataType.INT),
    Property(name="derivationVersion", data_type=DataType.INT),
    _status("vectorStatus"),
    Property(name="vectorRevision", data_type=DataType.INT),
    _status("vectorConfig"),
]
"""Derived properties of #328, in the order ``add_enrichment_schema`` adds them. (Collections
enriched before #463 also declare ``positionSegment``, which is no longer read or written.)"""

PROVENANCE_PROPERTIES: list[Property] = [
    _status("origin"),
    Property(name="createdBy", data_type=DataType.UUID),
    Property(name="createdAt", data_type=DataType.DATE),
    Property(name="reviewedBy", data_type=DataType.UUID),
    Property(name="reviewedAt", data_type=DataType.DATE),
    Property(name="lastEditedBy", data_type=DataType.UUID),
    Property(name="lastEditedAt", data_type=DataType.DATE),
    Property(name="aiRunId", data_type=DataType.UUID),
    Property(name="editVersion", data_type=DataType.INT),
]
"""Provenance properties of #460, in the order ``add_provenance_schema`` adds them."""

ATTRIBUTE_PROPERTIES: list[Property] = [
    # Whole-element tokenization: a filter matches an element exactly (or by the ``<attribute id>:``
    # prefix with ``like``), never a part of one. Filterable only; nothing searches the text.
    Property(name="attributeValues", data_type=DataType.TEXT_ARRAY, tokenization=Tokenization.FIELD,
             index_searchable=False, index_filterable=True),
    Property(name="attributeVersion", data_type=DataType.INT),
]
"""Attribute properties of #331, in the order ``add_attribute_schema`` adds them."""

_ROW = ["chunkId", "tagId", "documentId", "start", "end", "type", "revision", "enrichmentStatus",
        "enrichedRevision", "derivationVersion", "vectorStatus", "vectorRevision", "vectorConfig", "text",
        "leftContext", "rightContext", "documentStartChar", "documentEndChar",
        "documentStartWord", "documentEndWord"]


_PROVENANCE = [p.name for p in PROVENANCE_PROPERTIES]
_ATTRIBUTES = [p.name for p in ATTRIBUTE_PROPERTIES]
_ROW_FIELDS = {*_ROW, *_PROVENANCE, *_ATTRIBUTES}


def _contextual_vector(name: str):
    # A flat index per tenant: tenants hold a collection's annotations, few enough to scan.
    return Configure.Vectors.self_provided(name=name, vector_index_config=Configure.VectorIndex.flat())


async def create_annotation_collection(client: WeaviateAsyncClient, names: CollectionNames,
                                       annotation_vector: str | None = DEFAULT_VECTOR_NAME) -> None:
    """Create the empty multi-tenant annotation collection (the migration's ``--create-schema``).

    No tenant is created here. Vectors are self-provided: ``default`` (flat index, unused)
    and the contextual vector ``annotation_vector`` (#328; ``None``: none). The derived
    properties of #328, the provenance of #460 and the attributes of #331 are included. A reference cannot target an alias, so when the chunk
    collection name is an alias (production: ``Chunks`` -> ``Chunks_test``) the reference
    targets the collection it names.
    """
    uuid = DataType.UUID
    chunk_target = await resolve_collection(client, names.chunks_collection_name)
    vectors = [Configure.Vectors.self_provided(name="default", vector_index_config=Configure.VectorIndex.flat())]
    if annotation_vector is not None:
        vectors.append(_contextual_vector(annotation_vector))
    await client.collections.create(
        names.annotation_collection_name,
        multi_tenancy_config=Configure.multi_tenancy(
            enabled=True, auto_tenant_creation=False, auto_tenant_activation=True),
        vector_config=vectors,
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
            *ENRICHMENT_PROPERTIES,
            *PROVENANCE_PROPERTIES,
            *ATTRIBUTE_PROPERTIES,
        ],
        references=[ReferenceProperty(name="text_chunk", target_collection=chunk_target)],
    )


async def enrichment_schema(client: WeaviateAsyncClient, names: CollectionNames,
                            annotation_vector: str | None) -> tuple[list[str], bool]:
    """The derived properties the annotation collection lacks, and whether it holds the
    named vector ``annotation_vector`` (False for ``None``)."""
    config = await client.collections.get(names.annotation_collection_name).config.get()
    present = {p.name for p in config.properties}
    missing = [p.name for p in ENRICHMENT_PROPERTIES if p.name not in present]
    return missing, annotation_vector is not None and annotation_vector in (config.vector_config or {})


async def add_enrichment_schema(client: WeaviateAsyncClient, names: CollectionNames,
                                annotation_vector: str | None) -> list[str]:
    """Add the missing derived properties and the named vector to the existing annotation
    collection; returns what was added. Existing objects and vectors are not changed."""
    missing, has_vector = await enrichment_schema(client, names, annotation_vector)
    config = client.collections.get(names.annotation_collection_name).config
    for prop in ENRICHMENT_PROPERTIES:
        if prop.name in missing:
            await config.add_property(prop)
    added = list(missing)
    if annotation_vector is not None and not has_vector:
        await config.add_vector(vector_config=_contextual_vector(annotation_vector))
        added.append(f"vector:{annotation_vector}")
    return added


async def provenance_schema(client: WeaviateAsyncClient, names: CollectionNames) -> list[str]:
    """The provenance properties (#460) the annotation collection lacks."""
    config = await client.collections.get(names.annotation_collection_name).config.get()
    present = {p.name for p in config.properties}
    return [p.name for p in PROVENANCE_PROPERTIES if p.name not in present]


async def add_provenance_schema(client: WeaviateAsyncClient, names: CollectionNames) -> list[str]:
    """Add the missing provenance properties to the existing annotation collection; returns
    what was added. Existing objects are not changed (their provenance stays unknown)."""
    missing = await provenance_schema(client, names)
    config = client.collections.get(names.annotation_collection_name).config
    for prop in PROVENANCE_PROPERTIES:
        if prop.name in missing:
            await config.add_property(prop)
    return missing


async def attribute_schema(client: WeaviateAsyncClient, names: CollectionNames) -> list[str]:
    """The attribute properties (#331) the annotation collection lacks."""
    config = await client.collections.get(names.annotation_collection_name).config.get()
    present = {p.name for p in config.properties}
    return [p.name for p in ATTRIBUTE_PROPERTIES if p.name not in present]


async def add_attribute_schema(client: WeaviateAsyncClient, names: CollectionNames) -> list[str]:
    """Add the missing attribute properties to the existing annotation collection; returns what
    was added. Existing objects are not changed (they have no accepted values, version 0)."""
    missing = await attribute_schema(client, names)
    config = client.collections.get(names.annotation_collection_name).config
    for prop in ATTRIBUTE_PROPERTIES:
        if prop.name in missing:
            await config.add_property(prop)
    return missing


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
        editVersion=props.get("editVersion") or 0,
        attributes={str(a): [str(v) for v in vs] for a, vs in codec.group(props.get("attributeValues")).items()},
        attributeVersion=props.get("attributeVersion") or 0,
    )


def to_row(obj) -> AnnotationRow:
    props = obj.properties
    distance = getattr(obj.metadata, "distance", None)
    return AnnotationRow(id=obj.uuid, distance=distance, **{k: props.get(k) for k in props if k in _ROW_FIELDS})


def _query_filter(query: AnnotationQuery, document_ids: list[UUID] | None = None):
    """The Weaviate filter of a concordance query; ``like`` on the word-tokenized text
    matches inside one word and ignores case, only in text ``ready`` under the query's
    derivation version."""
    conditions = [Filter.by_property("type").contains_any([t.value for t in query.types])]
    if query.tag_ids:
        conditions.append(Filter.by_property("tagId").contains_any(list(query.tag_ids)))
    if query.words:
        conditions.append(Filter.by_property("enrichmentStatus").equal("ready"))
        if query.derivation_version is not None:
            conditions.append(Filter.by_property("derivationVersion").equal(query.derivation_version))
    conditions.extend(Filter.by_property("text").like(f"*{word}*") for word in query.words)
    if document_ids is not None:
        conditions.append(Filter.by_property("documentId").contains_any(list(document_ids)))
    if query.ids is not None:
        conditions.append(Filter.by_id().contains_any(list(query.ids)))
    for attribute, values in query.attribute_values.items():
        conditions.append(Filter.by_property("attributeValues").contains_any(
            [codec.encode(attribute, v) for v in values]))
    for attribute in query.attribute_unassigned:
        # Explicit: no stored element carries the attribute's fixed-length id prefix.
        conditions.append(Filter.not_(Filter.by_property("attributeValues").like(codec.attribute_pattern(attribute))))
    return Filter.all_of(conditions)


def pair_of(span: TagSpan) -> ChunkTag:
    """The (chunk, tag) pair whose chunk tag references the span backs."""
    return ChunkTag.of(span.chunkId, span.tagId)


class SpanRepository:
    def __init__(self, client: WeaviateAsyncClient, collectionNames: CollectionNames, provenance: bool = False,
                 attributes: bool = False):
        self.client = client
        self.collectionNames = collectionNames
        self.provenance = provenance
        """The collection holds the provenance properties (#460): they are read, and the
        service writes them. Decided at startup (``bootstrap.detect_provenance``)."""
        self.attributes = attributes
        """The collection holds the attribute properties (#331): they are read, and the attribute
        service writes them. Decided at startup (``bootstrap.detect_attributes``)."""
        # Tenants this process created or saw; a removed tenant is forgotten by ``remove_tenant``.
        self._known_tenants: set[str] = set()
        # A lock exists while some write holds or waits for it.
        self._locks: weakref.WeakValueDictionary[UUID, asyncio.Lock] = weakref.WeakValueDictionary()

    def lock(self, span_id: UUID) -> asyncio.Lock:
        """Serializes, within the process, the writes of one span's revision and derived data:
        a boundary edit and the vector written for an earlier revision cannot interleave."""
        lock = self._locks.get(span_id)
        if lock is None:
            lock = self._locks[span_id] = asyncio.Lock()
        return lock

    def _span_properties(self) -> list[str]:
        return [*_PROPERTIES, *(["editVersion"] if self.provenance else []), *(_ATTRIBUTES if self.attributes else [])]

    def _row_properties(self) -> list[str]:
        return [*_ROW, *(_PROVENANCE if self.provenance else []), *(_ATTRIBUTES if self.attributes else [])]

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

    async def insert(self, collection_id: UUID, span: PostSpan, document_id: UUID | None,
                     derived: dict | None = None, provenance: dict | None = None) -> UUID:
        """Stores the span in the collection's tenant (created if needed) and returns its id.
        ``derived``: derived properties written with it (#328); ``provenance``: its
        provenance properties (#460)."""
        await self.ensure_tenant(collection_id)
        properties: dict = {"start": span.start, "end": span.end, "type": span.type.value,
                            "tagId": UUID(span.tagId), "chunkId": UUID(span.chunkId), **(derived or {}),
                            **(provenance or {})}
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
            obj = await self._tenant(collection_id).query.fetch_object_by_id(span_id, return_properties=self._span_properties())
            return to_span(obj) if obj is not None else None
        return await self._read(collection_id, read, None)

    async def read_many(self, collection_id: UUID, span_ids: list[UUID]) -> dict[UUID, TagSpan]:
        """The collection's spans among ``span_ids``; ids of other collections are absent."""
        if not span_ids:
            return {}

        async def read():
            response = await self._tenant(collection_id).query.fetch_objects(
                filters=Filter.by_id().contains_any(list(span_ids)), limit=len(span_ids),
                return_properties=self._span_properties())
            return {UUID(str(o.uuid)): to_span(o) for o in response.objects}
        return await self._read(collection_id, read, {})

    async def _fetch(self, collection_id: UUID, filters, return_properties=None) -> list:
        return await self._read(collection_id, lambda: fetch_all(
            self._tenant(collection_id), filters=filters, page_size=500,
            return_properties=self._span_properties() if return_properties is None else return_properties), [])

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

    async def update(self, collection_id: UUID, span_id: UUID, patch: PatchSpan, derived: dict | None = None,
                     provenance: dict | None = None) -> None:
        """Sets the patched offsets, type, tag and anchor chunk, and the ``derived`` and
        ``provenance`` properties, in one write. A moved span's ``text_chunk`` reference is
        not changed here (``replace_anchor_reference``)."""
        fields = patch.model_dump(exclude_none=True)
        properties: dict = {k: fields[k] for k in ("start", "end") if k in fields} | (derived or {}) \
            | (provenance or {})
        if patch.type is not None:
            properties["type"] = patch.type.value
        if patch.tagId is not None:
            properties["tagId"] = UUID(patch.tagId)
        if patch.chunkId is not None:
            properties["chunkId"] = UUID(patch.chunkId)
        if properties:
            await self._tenant(collection_id).data.update(uuid=span_id, properties=properties)

    async def write_attributes(self, collection_id: UUID, span_id: UUID, values: list[str], version: int) -> None:
        """Sets the span's accepted attribute assignments (``features/attributes/codec.py``, sorted)
        and ``attributeVersion`` in one write; nothing else of the span changes."""
        await self._tenant(collection_id).data.update(
            uuid=span_id, properties={"attributeValues": sorted(set(values)), "attributeVersion": version})

    async def replace_anchor_reference(self, collection_id: UUID, span_id: UUID, chunk_id: UUID) -> None:
        """Points the span's ``text_chunk`` reference at ``chunk_id`` only (an update would
        add it to the old one)."""
        await self._tenant(collection_id).data.reference_replace(
            from_uuid=span_id, from_property="text_chunk", to=chunk_id)

    async def delete(self, collection_id: UUID, span_id: UUID) -> None:
        await self._tenant(collection_id).data.delete_by_id(span_id)

    # ── Derived data (#328) ───────────────────────────────────────────────

    async def read_row(self, collection_id: UUID, span_id: UUID) -> AnnotationRow | None:
        """The collection's span with its revision and derived fields, or None."""
        async def read():
            obj = await self._tenant(collection_id).query.fetch_object_by_id(span_id, return_properties=self._row_properties())
            return to_row(obj) if obj is not None else None
        return await self._read(collection_id, read, None)

    async def write_derived(self, collection_id: UUID, span_id: UUID, derived: dict,
                            vector: tuple[str, list[float]] | None = None) -> None:
        """Writes derived properties only (never the span's own fields), with the named vector
        ``(name, vector)`` when given."""
        await self._tenant(collection_id).data.update(
            uuid=span_id, properties=derived, vector={vector[0]: vector[1]} if vector is not None else None)

    async def read_rows(self, collection_id: UUID, *, tag_ids: list[UUID] | None = None,
                        document_id: UUID | None = None, limit: int = 100, offset: int = 0) -> list[AnnotationRow]:
        """One page of the collection's spans with their derived fields, optionally of some
        tags or one document. No source chunks are read."""
        conditions = []
        if tag_ids:
            conditions.append(Filter.by_property("tagId").contains_any(list(tag_ids)))
        if document_id is not None:
            conditions.append(Filter.by_property("documentId").equal(document_id))

        async def read():
            response = await self._tenant(collection_id).query.fetch_objects(
                filters=Filter.all_of(conditions) if conditions else None, limit=limit, offset=offset,
                return_properties=self._row_properties())
            return [to_row(o) for o in response.objects]
        return await self._read(collection_id, read, [])

    # ── Concordance queries (#329) ────────────────────────────────────────

    async def count_by_document(self, collection_id: UUID, query: AnnotationQuery, limit: int,
                                document_ids: list[UUID] | None = None) -> dict[UUID, int]:
        """Matching spans per document (of the given documents when ``document_ids`` is not
        None), for at most ``limit`` documents (one aggregation; spans without a document
        are not counted)."""
        if document_ids is not None and not document_ids:
            return {}

        async def count():
            result = await self._tenant(collection_id).aggregate.over_all(
                filters=_query_filter(query, document_ids), group_by=GroupByAggregate(prop="documentId", limit=limit),
                total_count=True)
            return {UUID(str(g.grouped_by.value)): g.total_count or 0 for g in result.groups}
        return await self._read(collection_id, count, {})

    async def count_rows(self, collection_id: UUID, query: AnnotationQuery,
                         document_ids: list[UUID] | None = None) -> int:
        """Matching spans, of the given documents when ``document_ids`` is not None."""
        if document_ids is not None and not document_ids:
            return 0

        async def count():
            result = await self._tenant(collection_id).aggregate.over_all(
                filters=_query_filter(query, document_ids), total_count=True)
            return result.total_count or 0
        return await self._read(collection_id, count, 0)

    async def query_rows(self, collection_id: UUID, query: AnnotationQuery, *, by_text: bool,
                         document_ids: list[UUID] | None = None, limit: int, offset: int = 0) -> list[AnnotationRow]:
        """One page of matching spans (of the given documents when ``document_ids`` is not
        None) with their derived fields, by annotated text or by position in the document,
        each ending with the span id."""
        if document_ids is not None and not document_ids:
            return []
        sort = (Sort.by_property("text") if by_text else
                Sort.by_property("documentStartChar").by_property("documentEndChar"))

        async def read():
            response = await self._tenant(collection_id).query.fetch_objects(
                filters=_query_filter(query, document_ids), sort=sort.by_property("_id"), limit=limit, offset=offset,
                return_properties=self._row_properties())
            return [to_row(o) for o in response.objects]
        return await self._read(collection_id, read, [])

    async def query_ids(self, collection_id: UUID, query: AnnotationQuery, *,
                        document_ids: list[UUID] | None = None, limit: int) -> dict[UUID, tuple[int, int]]:
        """The ids of at most ``limit`` matching spans (of the given documents when
        ``document_ids`` is not None), by id, with their ``editVersion`` (#460) and
        ``attributeVersion`` (#331)."""
        if (document_ids is not None and not document_ids) or (query.ids is not None and not query.ids):
            return {}

        async def read():
            response = await self._tenant(collection_id).query.fetch_objects(
                filters=_query_filter(query, document_ids), sort=Sort.by_property("_id"), limit=limit,
                return_properties=[*(["editVersion"] if self.provenance else []),
                                   *(["attributeVersion"] if self.attributes else [])])
            return {UUID(str(o.uuid)): (o.properties.get("editVersion") or 0, o.properties.get("attributeVersion") or 0)
                    for o in response.objects}
        return await self._read(collection_id, read, {})

    async def near_vector(self, collection_id: UUID, target_vector: str, vector: list[float], config_id: str,
                          limit: int, tag_ids: list[UUID] | None = None) -> list[AnnotationRow]:
        """The collection's spans nearest to ``vector`` among those whose vector is ``ready``
        and of configuration ``config_id``, nearest first, with ``distance``. The caller
        still checks that each vector belongs to the span's current revision."""
        filters = (Filter.by_property("vectorStatus").equal("ready")
                   & Filter.by_property("vectorConfig").equal(config_id))
        if tag_ids:
            filters = filters & Filter.by_property("tagId").contains_any(list(tag_ids))

        async def read():
            response = await self._tenant(collection_id).query.near_vector(
                near_vector=vector, target_vector=target_vector, limit=limit, filters=filters,
                return_properties=self._row_properties(), return_metadata=MetadataQuery(distance=True))
            return [to_row(o) for o in response.objects]
        return await self._read(collection_id, read, [])

    async def iterate_rows(self, collection_id: UUID):
        """Every span of the collection with its revision and derived data (cursor order;
        nothing when the collection has no tenant)."""
        if not await self.tenant_exists(collection_id):
            return
        async for obj in self._tenant(collection_id).iterator(return_properties=self._row_properties()):
            yield to_row(obj)

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

    # ── Attributes (#331) ─────────────────────────────────────────────────

    async def count_attribute_use(self, collection_id: UUID, attribute_id: UUID, value_id: UUID | None = None) -> int:
        """Annotations of the collection holding an accepted value of the attribute (of this value
        when given), whatever their type."""
        values = Filter.by_property("attributeValues")
        where = (values.contains_any([codec.encode(attribute_id, value_id)]) if value_id is not None
                 else values.like(codec.attribute_pattern(attribute_id)))

        async def count():
            result = await self._tenant(collection_id).aggregate.over_all(filters=where, total_count=True)
            return result.total_count or 0
        return await self._read(collection_id, count, 0)

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
