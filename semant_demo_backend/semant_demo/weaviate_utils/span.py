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


class Span():
    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.collectionNames = collectionNames
        self.helpers = WeaviateHelpers(client, collectionNames)
        self.span_collection = self.client.collections.get(
            collectionNames.span_collection_name)

    def move(self):
        pass

    async def read(self, chunk_id: str) -> list[schemas.TagSpan]:
        """
        Get spans by chunk id
        """
        if not self.span_collection:
            raise RuntimeError("Span_test collection not available")

        try:
            chunk_uuid = UUID(chunk_id)
        except ValueError as exc:
            raise WeaviateDataValidationError(
                f"Invalid chunk id format: {chunk_id}"
            ) from exc

        filters = Filter.by_ref(link_on="text_chunk").by_id().equal(chunk_uuid)

        response = await self.span_collection.query.fetch_objects(
            filters=filters,
            return_properties=["start", "end", "type"],
            return_references=[
                QueryReference(link_on="tag")
            ]
        )

        spans = []
        for obj in response.objects:
            tag_ref = obj.references.get("tag")
            tag_id = str(
                tag_ref.objects[0].uuid) if tag_ref and tag_ref.objects else ""
            span_type = obj.properties.get("type")

            spans.append(
                schemas.TagSpan(
                    id=str(obj.uuid),
                    chunkId=chunk_id,
                    tagId=tag_id,
                    start=cast(int, obj.properties.get("start")),
                    end=cast(int, obj.properties.get("end")),
                    type=schemas.SpanType(span_type) if isinstance(span_type, str) else None
                )
            )

        return spans

    async def update(self, span_id: str, update_fields: schemas.TagSpanUpdate):
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
