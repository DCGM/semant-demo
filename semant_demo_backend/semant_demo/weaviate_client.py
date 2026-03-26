
from datetime import datetime, timezone

from semant_demo.weaviate_search import WeaviateSearch
from semant_demo.schemas import CollectionResponse, PatchCollectionRequest, PostCollectionRequest
from uuid import UUID

from weaviate.classes.query import Filter
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
        logging.info(f"User Id: {user_id}\nRaw results: {response}")
        collections = []
        for obj in response.objects:
            props = obj.properties
            collections.append(CollectionResponse(
                id=obj.uuid,
                name=props.get("name"),
                user_id=props.get("user_id"),
                description=props.get("description"),
                created_at=props.get("created_at"),
                updated_at=props.get("updated_at"),
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
            user_id=props.get("user_id"),
            description=props.get("description"),
            created_at=props.get("created_at"),
            updated_at=props.get("updated_at"),
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

        await usercollection_collection.data.update(
            uuid=collection_id,
            properties={
                "name": collection.name,
                "description": collection.description,
                "color": collection.color,
                "updated_at": now
            }
        )