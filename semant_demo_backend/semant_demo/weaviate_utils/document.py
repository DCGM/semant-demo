from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter, Sort
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

import semant_demo.schemas as schemas
from semant_demo.weaviate_utils.helpers import WeaviateHelpers
from semant_demo.schema.documents import DocumentBrowse, Document as DocumentSchema


class Document():
    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.collectionNames = collectionNames
        self.helpers = WeaviateHelpers(client, collectionNames)

    #######
    # API #
    #######
    async def read(self, document_id: str) -> DocumentSchema | None:
        """
        Retrieves document by its id, returns None if document with given id does not exist
        """
        document_collection = self.client.collections.get(self.collectionNames.document_collection_name)
        response = await document_collection.query.fetch_object_by_id(document_id)
        if response is None:
            return None
        props = response.properties
        return DocumentSchema(
            id=response.uuid,
            **props
        )
    
    def read_all():
        pass

    def search():
        pass

    async def browse_documents(
        self,
        collection_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str | None = None,
        sort_desc: bool = False,
        title: str | None = None,
        author: str | None = None,
        publisher: str | None = None,
        document_type: str | None = None
    ):
        """
        Retrieves documents in pages with optional filters for browsing large datasets.
        """
        document_collection = self.client.collections.get(
            self.collectionNames.document_collection_name)
        filters = None

        def append_filter(current_filter, new_filter):
            return new_filter if current_filter is None else current_filter & new_filter

        if collection_id is not None:
            filters = append_filter(
                filters,
                Filter.by_ref("collection").by_id().equal(collection_id)
            )

        if title:
            filters = append_filter(
                filters, Filter.by_property("title").like(f"*{title}*"))
        if author:
            filters = append_filter(
                filters, Filter.by_property("author").like(f"*{author}*"))
        if publisher:
            filters = append_filter(filters, Filter.by_property(
                "publisher").like(f"*{publisher}*"))
        if document_type:
            filters = append_filter(filters, Filter.by_property(
                "documentType").like(f"*{document_type}*"))

        sort = None
        if sort_by:
            sort = Sort.by_property(sort_by, ascending=not sort_desc)

        count_response = await document_collection.aggregate.over_all(
            filters=filters,
            total_count=True,
        )
        total_count = count_response.total_count or 0

        response = await document_collection.query.fetch_objects(
            filters=filters,
            limit=limit + 1,
            offset=offset,
            sort=sort,
        )

        objects = response.objects
        has_more = len(objects) > limit
        if has_more:
            objects = objects[:limit]

        items = [
            DocumentSchema(
                id=obj.uuid,
                **obj.properties
            )
            for obj in objects
        ]

        return DocumentBrowse(
            items=items,
            has_more=has_more,
            next_offset=(offset + limit) if has_more else None,
            total_count=total_count,
        )

    ###########
    # Helpers #
    ###########
