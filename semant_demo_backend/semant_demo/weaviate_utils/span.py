from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from uuid import UUID
from typing import cast
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

from semant_demo.weaviate_utils.helpers import WeaviateHelpers
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
    
    async def create(self, span: PostSpan) -> schemas.TagSpan:
        """
        Create a new span and link it to the chunk and tag.
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

        span_id = await self.span_collection.data.insert(
            properties=properties,
            references={
                "tag": span.tagId,
                "text_chunk": span.chunkId
            }
        )

        return schemas.TagSpan(
            id=str(span_id),
            chunkId=span.chunkId,
            tagId=span.tagId,
            start=span.start,
            end=span.end,
            type=span.type,
            reason=span.reason,
            confidence=span.confidence,
        )

    async def delete(self, span_id: str) -> None:
        """
        Delete a span by its ID.
        """
        if not self.span_collection:
            raise RuntimeError("Span_test collection not available")

        await self.helpers.delete_span_cascade(span_id=span_id)

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

    async def update(self, span_id: str, update_fields: PatchSpan) -> schemas.TagSpan:
        """
        Update start or end position or tag reference.
        """
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

    async def delete_auto_spans_in_scope(
        self,
        *,
        collection_id: str,
        document_id: str,
        tag_ids: list[str],
    ) -> int:
        """
        Bulk-delete unresolved AI proposals (spans with ``type == 'auto'``)
        within a single (collection, document) scope, restricted to the given
        tag UUIDs.

        Returns the number of spans deleted. Cascades through the standard
        ``delete_span_cascade`` helper (one-by-one) so any cleanup logic
        (cross-references, indexes, …) is preserved.
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
    ) -> int:
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
    ) -> int:
        """
        Internal helper: delete spans within a single (collection, document)
        scope, restricted to the given tag UUIDs and (optionally) a single
        ``type`` value.

        Returns the number of spans deleted. Cascades through the standard
        ``delete_span_cascade`` helper (one-by-one) so any cleanup logic
        (cross-references, indexes, …) is preserved.
        """
        if not self.span_collection:
            raise RuntimeError("Span_test collection not available")
        if not tag_ids:
            return 0

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
        deleted = 0
        while True:
            response = await self.span_collection.query.fetch_objects(
                filters=filters,
                return_properties=["type"],
                limit=PAGE_SIZE,
            )
            objs = response.objects or []
            if not objs:
                break
            for obj in objs:
                try:
                    await self.helpers.delete_span_cascade(span_id=str(obj.uuid))
                    deleted += 1
                except Exception as e:
                    logging.getLogger(__name__).warning(
                        "Failed to delete span %s: %s", obj.uuid, e
                    )
            if len(objs) < PAGE_SIZE:
                break
        return deleted