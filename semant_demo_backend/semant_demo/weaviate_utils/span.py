from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from uuid import UUID
from typing import cast
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

    def move(self):
        pass
    
    async def create(self, span: PostSpan) -> schemas.TagSpan:
        """
        Create a new span and link it to the chunk and tag.
        """
        if not self.span_collection:
            raise RuntimeError("Span_test collection not available")

        span_id = await self.span_collection.data.insert(
            properties={
                "start": span.start,
                "end": span.end,
                "type": span.type.value if span.type is not None else None,
            },
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
            type=span.type
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
            return_properties=["start", "end", "type"],
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

        return schemas.TagSpan(
            id=str(response.uuid),
            chunkId=chunk_id_val,
            tagId=tag_id,
            start=response.properties.get("start"),
            end=response.properties.get("end"),
            type=schemas.SpanType(span_type) if isinstance(span_type, str) else None
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
                return_properties=["start", "end", "type"],
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

                spans.append(
                    schemas.TagSpan(
                        id=str(obj.uuid),
                        chunkId=chunk_id_val,
                        tagId=tag_id,
                        start=cast(int, obj.properties.get("start")),
                        end=cast(int, obj.properties.get("end")),
                        type=schemas.SpanType(span_type) if isinstance(span_type, str) else None
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
                return_properties=["start", "end", "type"],
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

                span = schemas.TagSpan(
                    id=str(obj.uuid),
                    chunkId=chunk_id,
                    tagId=tag_id,
                    start=obj.properties.get("start"),
                    end=obj.properties.get("end"),
                    type=schemas.SpanType(span_type) if isinstance(span_type, str) else None
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
            raise WeaviateDataValidationError(
                "Updating 'type' field is not allowed, use Approve or Disapprove tag endpoints"
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