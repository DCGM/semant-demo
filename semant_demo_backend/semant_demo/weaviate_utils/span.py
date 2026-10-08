from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from uuid import UUID
from typing import cast
import asyncio
import logging
from weaviate.exceptions import (
    WeaviateConnectionError,
    WeaviateTimeoutError,
    WeaviateQueryError,
    WeaviateInvalidInputError,
    UnexpectedStatusCodeError,
    ResponseCannotBeDecodedError,
    WeaviateClosedClientError,
    InsufficientPermissionsError,
)
from semant_demo.weaviate_exceptions import (
    WeaviateConnectError,
    WeaviateDataValidationError,
    WeaviateLimitError,
    WeaviateServerError,
    WeaviateOperationError
)
from weaviate.classes.query import QueryReference

from semant_demo.adapters.weaviate.chunk_tags import ChunkTag, sync_chunk_tags
from semant_demo.weaviate_utils.helpers import WeaviateHelpers, step_failure
from semant_demo.schema.outcomes import StepFailure, WriteResult, outcome_of
import semant_demo.schemas as schemas

from semant_demo.schema.spans import PostSpan, PatchSpan


class Span():
    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.collectionNames = collectionNames
        self.helpers = WeaviateHelpers(client, collectionNames)
        self.span_collection = self.client.collections.get(
            collectionNames.span_collection_name)
        # Whether the optional ``reason``/``confidence`` properties were
        # already ensured to exist on the live Weaviate collection. Set by
        # :meth:`_ensure_ai_properties`; first call performs the check.
        self._ai_props_ensured = False

    async def _ensure_ai_properties(self) -> None:
        """
        Idempotently make sure the ``reason`` (TEXT) and ``confidence``
        (NUMBER) properties exist on the Span collection.

        Older deployments created the collection without these properties.
        Calling ``add_property`` for an already-existing property is a no-op
        from this code's perspective (Weaviate raises and we ignore).
        """
        if self._ai_props_ensured:
            return
        try:
            from weaviate.classes.config import Property, DataType
            try:
                config = await self.span_collection.config.get()
                existing = {p.name for p in (config.properties or [])}
            except Exception:
                existing = set()
            if "reason" not in existing:
                try:
                    await self.span_collection.config.add_property(
                        Property(name="reason", data_type=DataType.TEXT)
                    )
                except Exception:
                    pass
            if "confidence" not in existing:
                try:
                    await self.span_collection.config.add_property(
                        Property(name="confidence", data_type=DataType.NUMBER)
                    )
                except Exception:
                    pass
        finally:
            self._ai_props_ensured = True

    def move(self):
        pass
    
    async def _sync_chunk_tags(self, pairs) -> list[StepFailure]:
        """Re-derive the chunk tag references of the touched (chunk, tag) pairs."""
        _, failed = await sync_chunk_tags(self.client, self.collectionNames, pairs)
        return failed

    async def create(self, span: PostSpan) -> tuple[schemas.TagSpan, list[StepFailure]]:
        """
        Create a new span and link it to the chunk and tag, then add the matching chunk
        tag reference. Returns the span and the chunk tag failures (the span is kept).
        """
        if not self.span_collection:
            raise RuntimeError("Span_test collection not available")

        if span.reason is not None or span.confidence is not None:
            await self._ensure_ai_properties()

        properties: dict = {
            "start": span.start,
            "end": span.end,
            "type": span.type.value if span.type is not None else None,
        }
        # Persist AI metadata only when present so Weaviate auto-schema does
        # not have to handle null property values.
        if span.reason is not None:
            properties["reason"] = span.reason
        if span.confidence is not None:
            properties["confidence"] = float(span.confidence)

        pairs = [ChunkTag.of(span.chunkId, span.tagId)]
        try:
            span_id = await self.span_collection.data.insert(
                properties=properties,
                references={
                    "tag": span.tagId,
                    "text_chunk": span.chunkId
                }
            )
        except Exception:
            # A timed-out insert may still have been stored.
            await self._sync_chunk_tags(pairs)
            raise

        failed = await self._sync_chunk_tags(pairs)
        return schemas.TagSpan(
            id=str(span_id),
            chunkId=span.chunkId,
            tagId=span.tagId,
            start=span.start,
            end=span.end,
            type=span.type,
            reason=span.reason,
            confidence=span.confidence,
        ), failed

    async def delete(self, span_id: str) -> list[StepFailure]:
        """
        Delete a span by its ID, then remove chunk tag references no other span backs.
        Returns the chunk tag failures (the deletion is kept).
        """
        if not self.span_collection:
            raise RuntimeError("Span_test collection not available")

        pairs = self._pairs(await self.read_refs([UUID(str(span_id))]))
        try:
            await self.helpers.delete_span_cascade(span_id=span_id)
        except Exception:
            # A timed-out delete may still have been applied.
            await self._sync_chunk_tags(pairs)
            raise
        return await self._sync_chunk_tags(pairs)

    @staticmethod
    def _pairs(refs: dict[UUID, tuple[list[UUID], list[UUID]]]) -> set[ChunkTag]:
        """(chunk, tag) pairs of spans, from :meth:`read_refs`."""
        return {ChunkTag(c, t) for tags, chunks in refs.values() for t in tags for c in chunks}

    async def read(self, span_id: str) -> schemas.TagSpan:
        """
            Retrieves a tag span by its UUID.
        """
        if not self.span_collection:
            raise RuntimeError("Span_test collection not available")

        response = await self.span_collection.query.fetch_object_by_id(
            uuid=span_id,
            return_properties=["start", "end", "type", "reason", "confidence"],
            return_references=[
                QueryReference(link_on="tag", return_references=[
                    QueryReference(link_on="userCollection")
                ]),
                QueryReference(link_on="text_chunk")
            ]
        )

        if not response or not response.properties:
            raise WeaviateDataValidationError(f"Span with id {span_id} not found")

        tag_ref = response.references.get("tag")
        tag_id = str(tag_ref.objects[0].uuid) if tag_ref and tag_ref.objects else ""

        chunk_ref = response.references.get("text_chunk")
        chunk_id_val = str(chunk_ref.objects[0].uuid) if chunk_ref and chunk_ref.objects else None

        span_type = response.properties.get("type")
        confidence_raw = response.properties.get("confidence")

        return schemas.TagSpan(
            id=str(response.uuid),
            chunkId=chunk_id_val,
            tagId=tag_id,
            start=response.properties.get("start"),
            end=response.properties.get("end"),
            type=schemas.SpanType(span_type) if isinstance(span_type, str) else None,
            reason=response.properties.get("reason"),
            confidence=float(confidence_raw) if confidence_raw is not None else None,
        )

    async def read_refs(self, span_ids: list[UUID]) -> dict[UUID, tuple[list[UUID], list[UUID]]]:
        """
        ``(tag ids, chunk ids)`` referenced by each existing span. Spans that do not exist
        are absent from the result. Used for authorization.
        """
        if not span_ids:
            return {}
        response = await self.span_collection.query.fetch_objects(
            filters=Filter.by_id().contains_any(list(span_ids)),
            limit=len(span_ids),
            return_properties=[],
            return_references=[QueryReference(link_on="tag"), QueryReference(link_on="text_chunk")],
        )
        result: dict[UUID, tuple[list[UUID], list[UUID]]] = {}
        for obj in response.objects:
            refs = obj.references or {}
            tags = refs.get("tag")
            chunks = refs.get("text_chunk")
            result[UUID(str(obj.uuid))] = (
                [UUID(str(r.uuid)) for r in (tags.objects if tags else [])],
                [UUID(str(r.uuid)) for r in (chunks.objects if chunks else [])],
            )
        return result

    async def read_all(self, chunk_id: str = None, collection_id: str = None) -> list[schemas.TagSpan]:
        """
        Get all spans, optionally filtered by chunk_id and collection_id.
        Returns only spans whose tag references a tag that references the given collection.
        """
        if not self.span_collection:
            raise RuntimeError("Span_test collection not available")

        filters = None

        # Prepare filters for chunk_id and collection_id
        if chunk_id:
            try:
                chunk_uuid = UUID(chunk_id)
            except ValueError as exc:
                raise WeaviateDataValidationError(
                    f"Invalid chunk id format: {chunk_id}"
                ) from exc
            filters = Filter.by_ref(link_on="text_chunk").by_id().equal(chunk_uuid)

        # If collection_id is provided, we need to filter spans whose tag references the given collection
        # This requires a nested filter: span -> tag -> collection
        if collection_id:
            try:
                collection_uuid = UUID(collection_id)
            except ValueError as exc:
                raise WeaviateDataValidationError(
                    f"Invalid collection id format: {collection_id}"
                ) from exc
            tag_collection_filter = Filter.by_ref(link_on="tag").by_ref(link_on="userCollection").by_id().equal(collection_uuid)
            if filters:
                filters = filters & tag_collection_filter
            else:
                filters = tag_collection_filter

        PAGE_SIZE = 500
        offset = 0
        spans = []

        while True:
            response = await self.span_collection.query.fetch_objects(
                filters=filters,
                return_properties=["start", "end", "type", "reason", "confidence"],
                return_references=[
                    QueryReference(link_on="tag"),
                    QueryReference(link_on="text_chunk")
                ],
                limit=PAGE_SIZE,
                offset=offset,
            )

            if not response.objects:
                break

            for obj in response.objects:
                tag_ref = obj.references.get("tag")
                tag_id = str(tag_ref.objects[0].uuid) if tag_ref and tag_ref.objects else ""
                span_type = obj.properties.get("type")
                chunk_ref = obj.references.get("text_chunk")
                chunk_id_val = str(chunk_ref.objects[0].uuid) if chunk_ref and chunk_ref.objects else None
                confidence_raw = obj.properties.get("confidence")

                spans.append(
                    schemas.TagSpan(
                        id=str(obj.uuid),
                        chunkId=chunk_id_val,
                        tagId=tag_id,
                        start=cast(int, obj.properties.get("start")),
                        end=cast(int, obj.properties.get("end")),
                        type=schemas.SpanType(span_type) if isinstance(span_type, str) else None,
                        reason=obj.properties.get("reason"),
                        confidence=float(confidence_raw) if confidence_raw is not None else None,
                    )
                )

            if len(response.objects) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

        return spans

    async def read_batch(self, chunk_ids: list[str], collection_id: str = None) -> dict[str, list[schemas.TagSpan]]:
        """
        Get spans for multiple chunk IDs in a single query, optionally filtered by collection_id.
        Returns a dict keyed by chunk_id.
        """

        if not chunk_ids:
            return {}

        try:
            chunk_uuids = [UUID(cid) for cid in chunk_ids]
        except ValueError as exc:
            raise WeaviateDataValidationError(
                f"Invalid chunk id format in batch"
            ) from exc

        filters = Filter.by_ref(link_on="text_chunk").by_id().contains_any(chunk_uuids)

        # If collection_id is provided, we need to filter spans whose tag references the given collection
        if collection_id:
            try:
                collection_uuid = UUID(collection_id)
            except ValueError as exc:
                raise WeaviateDataValidationError(
                    f"Invalid collection id format: {collection_id}"
                ) from exc
            tag_collection_filter = Filter.by_ref(link_on="tag").by_ref(link_on="userCollection").by_id().equal(collection_uuid)
            filters = filters & tag_collection_filter

        # Initialize result with empty lists for all requested chunk_ids
        result: dict[str, list[schemas.TagSpan]] = {cid: [] for cid in chunk_ids}

        PAGE_SIZE = 500
        offset = 0

        while True:
            response = await self.span_collection.query.fetch_objects(
                filters=filters,
                return_properties=["start", "end", "type", "reason", "confidence"],
                return_references=[
                    QueryReference(link_on="tag"),
                    QueryReference(link_on="text_chunk"),
                ],
                limit=PAGE_SIZE,
                offset=offset,
            )

            if not response.objects:
                break

            for obj in response.objects:
                tag_ref = obj.references.get("tag")
                tag_id = str(tag_ref.objects[0].uuid) if tag_ref and tag_ref.objects else ""

                chunk_ref = obj.references.get("text_chunk")
                if not chunk_ref or not chunk_ref.objects:
                    continue
                chunk_id = str(chunk_ref.objects[0].uuid)

                span_type = obj.properties.get("type")
                confidence_raw = obj.properties.get("confidence")

                span = schemas.TagSpan(
                    id=str(obj.uuid),
                    chunkId=chunk_id,
                    tagId=tag_id,
                    start=obj.properties.get("start"),
                    end=obj.properties.get("end"),
                    type=schemas.SpanType(span_type) if isinstance(span_type, str) else None,
                    reason=obj.properties.get("reason"),
                    confidence=float(confidence_raw) if confidence_raw is not None else None,
                )

                if chunk_id in result:
                    result[chunk_id].append(span)

            if len(response.objects) < PAGE_SIZE:
                break

            offset += PAGE_SIZE

        return result

    async def update(self, span_id: str, update_fields: PatchSpan) -> tuple[schemas.TagSpan, list[StepFailure]]:
        """
        Update start or end position, type or tag reference. A type or tag change also
        updates the chunk tag references of the old and new (chunk, tag) pairs. Returns
        the span and the chunk tag failures (the span update is kept).
        """
        pairs = await self._pairs_changed_by(span_ids=[span_id], update_fields=update_fields)
        try:
            span = await self._update(span_id, update_fields)
        except Exception:
            # The update may have been partly applied (or applied despite a timeout).
            await self._sync_chunk_tags(pairs)
            raise
        return span, await self._sync_chunk_tags(pairs)

    async def _pairs_changed_by(self, *, span_ids: list[str], update_fields: PatchSpan) -> set[ChunkTag]:
        """(chunk, tag) pairs whose chunk tags the patch may change: none for offset-only
        patches; for a type or tag change, the spans' current pairs and the new tag's."""
        if update_fields.type is None and update_fields.tagId is None:
            return set()
        pairs = self._pairs(await self.read_refs([UUID(str(s)) for s in span_ids]))
        if update_fields.tagId is not None:
            pairs |= {ChunkTag.of(p.chunk_id, update_fields.tagId) for p in pairs}
        return pairs

    async def _update(self, span_id: str, update_fields: PatchSpan) -> schemas.TagSpan:
        """Update the span only, without its chunk tags."""
        if not self.span_collection:
            raise RuntimeError("Span_test collection is not available")

        dumped_fields = update_fields.model_dump(exclude_none=True)

        if not dumped_fields:
            raise ValueError("No fields provided for update")

        props_to_update = {}
        if "start" in dumped_fields:
            props_to_update["start"] = dumped_fields["start"]
        if "end" in dumped_fields:
            props_to_update["end"] = dumped_fields["end"]
        if "type" in dumped_fields:
            # Used by the AI-assistance flow to approve/reject auto spans:
            #   auto -> pos  (approve)
            #   auto -> neg  (reject; kept as a negative example)
            type_val = dumped_fields["type"]
            props_to_update["type"] = (
                type_val.value if hasattr(type_val, "value") else type_val
            )

        if props_to_update:
            await self.span_collection.data.update(
                uuid=span_id,
                properties=props_to_update
            )

        if "tagId" in dumped_fields:
            await self.span_collection.data.reference_replace(
                from_uuid=span_id,
                from_property="tag",
                to=dumped_fields["tagId"],
            )

        return await self.read(span_id)

    async def bulk_update(
        self,
        span_ids: list[str],
        update_fields: PatchSpan,
    ) -> tuple[list[schemas.TagSpan], list[StepFailure]]:
        """
        Apply the same patch to many spans concurrently.

        Used by the AI-assist "Approve / Reject all selected" action — a
        single HTTP request from the browser fan-outs into one
        :meth:`update` call per span on the server side, so we avoid the
        per-span HTTP round-trip and the browser's 6-conn-per-origin cap.

        Best effort: returns the updated spans and a failure record for each span
        that could not be updated and for each chunk tag update that failed. Completed
        updates are kept. Chunk tags are re-derived once per touched (chunk, tag) pair
        after all span updates, also for spans whose update failed.
        """
        if not span_ids:
            return [], []

        pairs = await self._pairs_changed_by(span_ids=span_ids, update_fields=update_fields)
        results = await asyncio.gather(
            *(self._update(span_id=sid, update_fields=update_fields) for sid in span_ids),
            return_exceptions=True,
        )

        updated: list[schemas.TagSpan] = []
        failed: list[StepFailure] = []
        for sid, res in zip(span_ids, results):
            if isinstance(res, Exception):
                failed.append(step_failure("update_span", sid, res))
            else:
                updated.append(res)
        failed += await self._sync_chunk_tags(pairs)
        return updated, failed

    async def delete_auto_spans_in_scope(
        self,
        *,
        collection_id: str,
        document_id: str,
        tag_ids: list[str],
    ) -> WriteResult:
        """
        Bulk-delete unresolved AI proposals (spans with ``type == 'auto'``)
        within a single (collection, document) scope, restricted to the given
        tag UUIDs.

        Cascades through the standard ``delete_span_cascade`` helper
        (one-by-one) so any cleanup logic (cross-references, indexes, …) is preserved.
        """
        return await self._delete_spans_in_scope(
            collection_id=collection_id,
            document_id=document_id,
            tag_ids=tag_ids,
            type_filter=schemas.SpanType.auto.value,
        )

    async def delete_all_spans_for_tags_in_document(
        self,
        *,
        collection_id: str,
        document_id: str,
        tag_ids: list[str],
    ) -> WriteResult:
        """
        Bulk-delete approved (``type == 'pos'``) spans for the given tag UUIDs
        within a single (collection, document) scope. Used by the "delete all
        annotations of this tag" action in the document detail page — we only
        wipe positives so user feedback (negatives) and unresolved AI
        suggestions (auto) are preserved.
        """
        return await self._delete_spans_in_scope(
            collection_id=collection_id,
            document_id=document_id,
            tag_ids=tag_ids,
            type_filter=schemas.SpanType.pos.value,
        )

    async def _delete_spans_in_scope(
        self,
        *,
        collection_id: str,
        document_id: str,
        tag_ids: list[str],
        type_filter: str | None,
    ) -> WriteResult:
        """
        Internal helper: delete spans within a single (collection, document)
        scope, restricted to the given tag UUIDs and (optionally) a single
        ``type`` value.

        The matching span ids are listed first and then deleted one by one, so spans
        that fail to delete are reported instead of being fetched again forever.
        Completed deletions are kept.
        """
        if not self.span_collection:
            raise RuntimeError("Span_test collection not available")
        if not tag_ids:
            return WriteResult(outcome=outcome_of(0, 0))

        try:
            collection_uuid = UUID(collection_id)
            document_uuid = UUID(document_id)
            tag_uuids = [UUID(tid) for tid in tag_ids]
        except ValueError as exc:
            raise WeaviateDataValidationError(f"Invalid id in scope: {exc}") from exc

        filters = (
            Filter.by_ref(link_on="tag").by_id().contains_any(tag_uuids)
            & Filter.by_ref(link_on="tag").by_ref(link_on="userCollection").by_id().equal(collection_uuid)
            & Filter.by_ref(link_on="text_chunk").by_ref(link_on="document").by_id().equal(document_uuid)
        )
        if type_filter is not None:
            filters = filters & Filter.by_property("type").equal(type_filter)

        PAGE_SIZE = 500
        span_ids: list[str] = []
        pairs: set[ChunkTag] = set()
        while True:
            response = await self.span_collection.query.fetch_objects(
                filters=filters,
                return_properties=[],
                return_references=[QueryReference(link_on="tag"), QueryReference(link_on="text_chunk")],
                limit=PAGE_SIZE,
                offset=len(span_ids),
            )
            objs = response.objects or []
            span_ids.extend(str(o.uuid) for o in objs)
            for o in objs:
                refs = o.references or {}
                tags, chunks = refs.get("tag"), refs.get("text_chunk")
                pairs |= {ChunkTag.of(c.uuid, t.uuid)
                          for t in (tags.objects if tags else []) for c in (chunks.objects if chunks else [])}
            if len(objs) < PAGE_SIZE:
                break

        deleted: list[str] = []
        failed: list[StepFailure] = []
        for span_id in span_ids:
            try:
                await self.helpers.delete_span_cascade(span_id=span_id)
                deleted.append(span_id)
            except Exception as e:
                failed.append(step_failure("delete_span", span_id, e))
        # Re-derived after all deletions, also for spans whose deletion failed.
        tag_failures = await self._sync_chunk_tags(pairs)
        return WriteResult(outcome=outcome_of(len(deleted), len(failed) + len(tag_failures)),
                           succeeded=deleted, failed=failed + tag_failures)
