"""Span annotations: a range on a chunk, with a tag and a type (``pos``/``auto``/``neg``).

A span references its tag (``tag``) and the chunk it starts on (``text_chunk``); its
collection is the tag's collection. Offsets are stored as given (see
``features/annotations/offsets.py``). This repository only reads and writes spans; the
chunk tag references derived from them are updated by ``chunk_tags.ChunkTagRepository``
and the order of these writes is decided by the Annotations service.
"""
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.config import DataType, Property
from weaviate.classes.query import Filter, QueryReference

import semant_demo.schemas as schemas
from semant_demo.adapters.weaviate.chunk_tags import ChunkTag
from semant_demo.adapters.weaviate.paging import fetch_all
from semant_demo.features.annotations.schemas import PatchSpan, PostSpan, SpanType, TagSpan

_PROPERTIES = ["start", "end", "type", "reason", "confidence"]
_REFERENCES = [QueryReference(link_on="tag", return_properties=[]),
               QueryReference(link_on="text_chunk", return_properties=[])]


def _ref_ids(obj, prop: str) -> list[UUID]:
    block = (obj.references or {}).get(prop)
    return [UUID(str(r.uuid)) for r in (block.objects if block else [])]


def to_span(obj) -> TagSpan:
    props = obj.properties
    tags, chunks = _ref_ids(obj, "tag"), _ref_ids(obj, "text_chunk")
    span_type, confidence = props.get("type"), props.get("confidence")
    return TagSpan(
        id=str(obj.uuid),
        chunkId=str(chunks[0]) if chunks else None,
        tagId=str(tags[0]) if tags else "",
        start=props.get("start"),
        end=props.get("end"),
        type=SpanType(span_type) if isinstance(span_type, str) else None,
        reason=props.get("reason"),
        confidence=float(confidence) if confidence is not None else None,
    )


def pairs_of(obj) -> set[ChunkTag]:
    """(chunk, tag) pairs of a span object read with its references."""
    return {ChunkTag(c, t) for t in _ref_ids(obj, "tag") for c in _ref_ids(obj, "text_chunk")}


class SpanRepository:
    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.collectionNames = collectionNames
        # Whether ``reason``/``confidence`` were already ensured on the live collection.
        self._ai_props_ensured = False

    def _spans(self):
        return self.client.collections.get(self.collectionNames.span_collection_name)

    async def _ensure_ai_properties(self) -> None:
        """Add the ``reason``/``confidence`` properties when an older collection lacks them.

        Kept from the legacy adapter (older deployments created the collection without
        them). Runs once per repository, before the first span with AI metadata.
        """
        if self._ai_props_ensured:
            return
        spans = self._spans()
        try:
            try:
                existing = {p.name for p in ((await spans.config.get()).properties or [])}
            except Exception:
                existing = set()
            for name, data_type in (("reason", DataType.TEXT), ("confidence", DataType.NUMBER)):
                if name not in existing:
                    try:
                        await spans.config.add_property(Property(name=name, data_type=data_type))
                    except Exception:
                        pass
        finally:
            self._ai_props_ensured = True

    async def insert(self, span: PostSpan) -> UUID:
        """Stores the span as given and returns its id."""
        if span.reason is not None or span.confidence is not None:
            await self._ensure_ai_properties()
        properties: dict = {"start": span.start, "end": span.end, "type": span.type.value}
        # AI metadata only when present, so auto-schema never sees null values.
        if span.reason is not None:
            properties["reason"] = span.reason
        if span.confidence is not None:
            properties["confidence"] = float(span.confidence)
        return await self._spans().data.insert(
            properties=properties, references={"tag": span.tagId, "text_chunk": span.chunkId})

    async def read(self, span_id: UUID) -> TagSpan | None:
        """The span with this id, or None if it does not exist."""
        obj = await self._spans().query.fetch_object_by_id(
            span_id, return_properties=_PROPERTIES, return_references=_REFERENCES)
        return to_span(obj) if obj is not None else None

    async def read_refs(self, span_ids: list[UUID]) -> dict[UUID, tuple[list[UUID], list[UUID]]]:
        """
        ``(tag ids, chunk ids)`` referenced by each existing span. Spans that do not exist
        are absent from the result. Used for authorization and for the chunk tag pairs a
        write touches.
        """
        if not span_ids:
            return {}
        response = await self._spans().query.fetch_objects(
            filters=Filter.by_id().contains_any(list(span_ids)),
            limit=len(span_ids),
            return_properties=[],
            return_references=_REFERENCES,
        )
        return {UUID(str(o.uuid)): (_ref_ids(o, "tag"), _ref_ids(o, "text_chunk")) for o in response.objects}

    async def read_by_collection(self, collection_id: UUID, chunk_id: UUID | None = None) -> list[TagSpan]:
        """All spans of the collection's tags, optionally only those starting on one chunk."""
        filters = Filter.by_ref("tag").by_ref("userCollection").by_id().equal(collection_id)
        if chunk_id is not None:
            filters = Filter.by_ref("text_chunk").by_id().equal(chunk_id) & filters
        objects = await fetch_all(self._spans(), filters=filters, page_size=500,
                                  return_properties=_PROPERTIES, return_references=_REFERENCES)
        return [to_span(o) for o in objects]

    async def read_by_chunks(self, collection_id: UUID, chunk_ids: list[UUID]) -> dict[str, list[TagSpan]]:
        """The collection's spans starting on each of the chunks, keyed by chunk id (all chunks present)."""
        result: dict[str, list[TagSpan]] = {str(c): [] for c in chunk_ids}
        if not chunk_ids:
            return result
        filters = (Filter.by_ref("text_chunk").by_id().contains_any(list(chunk_ids))
                   & Filter.by_ref("tag").by_ref("userCollection").by_id().equal(collection_id))
        objects = await fetch_all(self._spans(), filters=filters, page_size=500,
                                  return_properties=_PROPERTIES, return_references=_REFERENCES)
        for obj in objects:
            span = to_span(obj)
            if span.chunkId in result:
                result[span.chunkId].append(span)
        return result

    async def update(self, span_id: UUID, patch: PatchSpan) -> None:
        """Sets the patched offsets/type, then replaces the tag reference if a tag is given.

        Two writes: when the second fails the first is kept.
        """
        fields = patch.model_dump(exclude_none=True)
        properties = {k: fields[k] for k in ("start", "end") if k in fields}
        if patch.type is not None:
            properties["type"] = patch.type.value
        if properties:
            await self._spans().data.update(uuid=span_id, properties=properties)
        if patch.tagId is not None:
            await self._spans().data.reference_replace(from_uuid=span_id, from_property="tag", to=patch.tagId)

    async def delete(self, span_id: UUID) -> None:
        await self._spans().data.delete_by_id(span_id)

    async def list_in_document(self, collection_id: UUID, document_id: UUID, tag_ids: list[UUID],
                               span_type: SpanType) -> dict[UUID, set[ChunkTag]]:
        """
        Ids of the spans of one type and the given tags of the collection that start on a
        chunk of the document, with their (chunk, tag) pairs. Listed completely before
        the caller writes, so failed deletions cannot make the listing loop.
        """
        if not tag_ids:
            return {}
        filters = (
            Filter.by_ref("tag").by_id().contains_any(list(tag_ids))
            & Filter.by_ref("tag").by_ref("userCollection").by_id().equal(collection_id)
            & Filter.by_ref("text_chunk").by_ref("document").by_id().equal(document_id)
            & Filter.by_property("type").equal(span_type.value)
        )
        objects = await fetch_all(self._spans(), filters=filters, page_size=500,
                                  return_properties=[], return_references=_REFERENCES)
        return {UUID(str(o.uuid)): pairs_of(o) for o in objects}
