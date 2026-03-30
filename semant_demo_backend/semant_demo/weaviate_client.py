
from datetime import datetime, timezone

from semant_demo.weaviate_search import WeaviateSearch
from semant_demo.schemas import CollectionResponse, PatchCollectionRequest, PostCollectionRequest, DocumentResponse, DocumentBrowseResponse
from uuid import UUID

from weaviate.classes.query import Filter, Sort
import logging


class WeaviateClient(WeaviateSearch):
    async def get_all_collections(self, user_id: str) -> list[CollectionResponse]:
        """
        Retrieves all collections for given user
        """
        usercollection_collection = self.client.collections.get("UserCollection")

        filters = (
            Filter.by_property("user_id").equal(user_id)
        )
        response = await usercollection_collection.query.fetch_objects(
            filters=filters
        )
        collections = []
        for obj in response.objects:
            props = obj.properties
            collections.append(CollectionResponse(
                id=obj.uuid,
                name=props.get("name"),
                userId=props.get("user_id"),
                description=props.get("description"),
                createdAt=props.get("created_at"),
                updatedAt=props.get("updated_at"),
                color=props.get("color")
            ))
        return collections
    
    async def get_collection_by_id(self, collection_id: UUID) -> CollectionResponse | None:
        """
        Retrieves collection by its id, returns None if collection with given id does not exist
        """
        
        usercollection_collection = self.client.collections.get("UserCollection")
        response = await usercollection_collection.query.fetch_object_by_id(collection_id)
        if response is None:
            return None
        props = response.properties
        return CollectionResponse(
            id=response.uuid,
            name=props.get("name"),
            userId=props.get("user_id"),
            description=props.get("description"),
            createdAt=props.get("created_at"),
            updatedAt=props.get("updated_at"),
            color=props.get("color")
        )
    
    async def create_collection(self, collection: PostCollectionRequest) -> UUID:
        """
        Creates new collection and returns its id
        """
        usercollection_collection = self.client.collections.get("UserCollection")
        now = datetime.now(timezone.utc)
        
        uuid = await usercollection_collection.data.insert(
            properties={
                "name": collection.name,
                "user_id": collection.user_id,
                "description": collection.description,
                "color": collection.color,
                "created_at": now,
                "updated_at": now
            }
        )
        return uuid

    async def update_collection(self, collection_id: UUID, collection: PatchCollectionRequest):
        """"
        Updates collection with given id, raises exception if collection with given id does not exist
        """
        usercollection_collection = self.client.collections.get("UserCollection")
        now = datetime.now(timezone.utc)

        # PATCH semantics: update only fields that were actually sent by the client.
        properties = collection.model_dump(exclude_unset=True)
        properties["updated_at"] = now

        await usercollection_collection.data.update(
            uuid=collection_id,
            properties=properties
        )

    async def delete_collection(self, collection_id: UUID) -> None:
        """
        Deletes collection with given id.
        """
        usercollection_collection = self.client.collections.get("UserCollection")
        await usercollection_collection.data.delete_by_id(collection_id)
        
    async def get_document_by_id(self, document_id: str) -> DocumentResponse | None:
        """
        Retrieves document by its id, returns None if document with given id does not exist
        """
        document_collection = self.client.collections.get("Documents")
        response = await document_collection.query.fetch_object_by_id(document_id)
        if response is None:
            return None
        props = response.properties
        return DocumentResponse(
            id=response.uuid,
            **props
        )
        
    async def get_all_documents(self, collection_id: UUID | None = None) -> list[DocumentResponse]:
        """
        Retrieves all documents - optionally can be filtered by collection id
        """
        document_collection = self.client.collections.get("Documents")
        filters = None
        if collection_id is not None:
            filters = (
                Filter.by_ref("collection").by_id().equal(collection_id)
            )
        response = await document_collection.query.fetch_objects(
            filters=filters
        )
        documents = []
        for obj in response.objects:
            props = obj.properties
            documents.append(DocumentResponse(
                id=obj.uuid,
                **props
            ))
        return documents

    async def browse_documents(
        self,
        limit: int = 50,
        offset: int = 0,
        sort_by: str | None = None,
        sort_desc: bool = False,
        collection_id: UUID | None = None,
        title: str | None = None,
        author: str | None = None,
        publisher: str | None = None,
        document_type: str | None = None
    ) -> DocumentBrowseResponse:
        """
        Retrieves documents in pages with optional filters for browsing large datasets.
        """
        document_collection = self.client.collections.get("Documents")
        filters = None

        def append_filter(current_filter, new_filter):
            return new_filter if current_filter is None else current_filter & new_filter

        if collection_id is not None:
            filters = append_filter(
                filters,
                Filter.by_ref("collection").by_id().equal(collection_id)
            )

        if title:
            filters = append_filter(filters, Filter.by_property("title").like(f"*{title}*"))
        if author:
            filters = append_filter(filters, Filter.by_property("author").like(f"*{author}*"))
        if publisher:
            filters = append_filter(filters, Filter.by_property("publisher").like(f"*{publisher}*"))
        if document_type:
            filters = append_filter(filters, Filter.by_property("documentType").like(f"*{document_type}*"))

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
            DocumentResponse(
                id=obj.uuid,
                **obj.properties
            )
            for obj in objects
        ]

        return DocumentBrowseResponse(
            items=items,
            hasMore=has_more,
            nextOffset=(offset + limit) if has_more else None,
            totalCount=total_count,
        )

    async def add_document_to_collection(self, document_id: UUID, collection_id: UUID) -> bool:
        """
        Adds a document to a collection by creating a reference between them.
        """
        document_collection = self.client.collections.get("Documents")
        try:
            await document_collection.data.reference_add(
                from_uuid=document_id,
                from_property="collection",
                to=collection_id,
            )
            return True
        except Exception as e:
            logging.error(f"Failed to add document {document_id} to collection {collection_id}: {e}")
            return False

    async def remove_document_from_collection(self, document_id: UUID, collection_id: UUID) -> bool:
        """
        Removes a document from a collection by deleting the reference between them.
        """
        document_collection = self.client.collections.get("Documents")
        try:
            await document_collection.data.reference_delete(
                from_uuid=document_id,
                from_property="collection",
                to=collection_id,
            )
            return True
        except Exception as e:
            logging.error(f"Failed to remove document {document_id} from collection {collection_id}: {e}")
            return False