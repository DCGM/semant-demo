import semant_demo.schemas as schemas

import logging
from uuid import UUID
from datetime import datetime, timezone

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
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

from semant_demo.schema.collections import Collection, CollectionStats, PatchCollection, PostCollection

from semant_demo.weaviate_utils.helpers import WeaviateHelpers


class UserCollection():
    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.collectionNames = collectionNames
        self.helpers = WeaviateHelpers(client, collectionNames)

    #######
    # API #
    #######
    async def create(self, collection: PostCollection) -> UUID:
        """
        Create user collection (contains chunks user choose)
        """
        logging.info(
            f"Adding user collection\nUser: {collection.user_id}\nCollection name: {collection.name}")

        usercollection_collection = self.client.collections.get(self.collectionNames.user_collection_name)
        
        now = datetime.now(timezone.utc)
        new_collection_uuid = await usercollection_collection.data.insert(
            properties={
                "name": collection.name,
                "user_id": collection.user_id,
                "description": collection.description,
                "color": collection.color,
                "created_at": now,
                "updated_at": now
            }
        )
        return new_collection_uuid
    
    async def read(self, collection_id: UUID) -> Collection | None:
        """
        Retrieves collection by its id, returns None if collection with given id does not exist
        """

        usercollection_collection = self.client.collections.get(
            self.collectionNames.user_collection_name)
        response = await usercollection_collection.query.fetch_object_by_id(collection_id)
        if response is None:
            return None
        props = response.properties
        return Collection(
            id=response.uuid,
            name=props.get("name"),
            user_id=props.get("user_id"),
            description=props.get("description"),
            created_at=props.get("created_at"),
            updated_at=props.get("updated_at"),
            color=props.get("color")
        )
        

    async def read_all(self, user_id: str) -> list[Collection]:
        """
        Retrieves all collections for given user
        """
        try:
            # filter collections by user
            filters = (
                Filter.by_property("user_id").equal(user_id)
            )
            results = await self.client.collections.get(self.collectionNames.user_collection_name).query.fetch_objects(
                filters=filters
            )
            logging.info(f"User Id: {user_id}\nRaw results: {results}")
            collections_response = []
            if results.objects is not None:
                if len(results.objects) > 0:
                    collections = results.objects
                    # map collection data to expected response format
                    for o in collections:
                        props = o.properties
                        collections_response.append(Collection(
                            id=o.uuid,
                            name=props.get("name"),
                            user_id=props.get("user_id"),
                            description=props.get("description"),
                            created_at=props.get("created_at"),
                            updated_at=props.get("updated_at"),
                            color=props.get("color")
                        ))

            return collections_response
        except WeaviateConnectionError as e:
            logging.error(f"Error: {str(e)}")
            raise WeaviateConnectError(str(e))
        except WeaviateInvalidInputError as e:
            logging.error(f"Error: {str(e)}")
            raise WeaviateDataValidationError(str(e))
        except WeaviateTimeoutError as e:
            logging.error(f"Error: {str(e)}")
            raise WeaviateLimitError(str(e))
        except WeaviateQueryError as e:
            logging.error(f"Error: {str(e)}")
            raise WeaviateOperationError(str(e))
        except (UnexpectedStatusCodeError, ResponseCannotBeDecodedError) as e:
            logging.error(f"Error: {str(e)}")
            raise WeaviateServerError(str(e))
        except Exception as e:
            # catch unexpected errors and wrap them
            logging.error(f"Unexpected error fetching chunks: {str(e)}")
            raise WeaviateServerError(str(e))
        
    async def read_collection_stats(self, collection_id: UUID) -> CollectionStats | None:
        """
        Computes aggregate statistics for one collection.
        """

        collection = await self.read(collection_id)
        if collection is None:
            return None

        # Compute documents count
        documents_collection = self.client.collections.get(self.collectionNames.document_collection_name)
        documents_filters = (
            Filter.by_ref("collection").by_id().equal(collection_id)
        )

        documents_count_response = await documents_collection.aggregate.over_all(
            total_count=True,
            filters=documents_filters
        )
        documents_count = documents_count_response.total_count or 0

        # Compute chunks count
        chunks_filters = (
            Filter.by_ref("userCollection").by_id().equal(collection_id)
        )

        chunks_collection = self.client.collections.get(self.collectionNames.chunks_collection_name)
        chunks_count_response = await chunks_collection.aggregate.over_all(
            total_count=True,
            filters=chunks_filters
        )
        chunks_count = chunks_count_response.total_count or 0

        # Compute tags count
        tags_collection = self.client.collections.get(self.collectionNames.tag_collection_name)
        tags_filters = (
            Filter.by_ref("userCollection").by_id().equal(collection_id)
        )
        tags_count_response = await tags_collection.aggregate.over_all(
            total_count=True,
            filters=tags_filters
        )
        tags_count = tags_count_response.total_count or 0

        # Compute annotation stats from Span collection.
        # One annotation = one span object.
        # Span belongs to selected collection if linked chunk OR linked tag belongs to that collection.

        spans_collection = self.client.collections.get(self.collectionNames.span_collection_name)

        spans_filters = (
            Filter.by_ref("text_chunk").by_ref(
                self.collectionNames.user_collection_name).by_id().equal(collection_id)
            |
            Filter.by_ref("tag").by_ref(
                self.collectionNames.user_collection_name).by_id().equal(collection_id)
        )

        annotations_count_response = await spans_collection.aggregate.over_all(
            total_count=True,
            filters=spans_filters,
        )
        annotations_count = annotations_count_response.total_count or 0

        return CollectionStats(
            collection_id=collection_id,
            documents_count=documents_count,
            chunks_count=chunks_count,
            tags_count=tags_count,
            annotations_count=annotations_count,
        )

    async def update(self, collection_id: str, collection: PatchCollection):
        """"
        Updates collection with given id
        """
        usercollection_collection = self.client.collections.get(self.collectionNames.user_collection_name)
        collection_in_db = await self.read(collection_id)
        
        now = datetime.now(timezone.utc)

        # PATCH semantics: update only fields that were actually sent by the client.
        properties = collection.model_dump(exclude_unset=True)
        properties["updated_at"] = now

        await usercollection_collection.data.update(
            uuid=collection_id,
            properties=properties
        )

    def delete():
        pass

    def read_all_tags():
        pass

    async def read_all_chunks(self, collectionId):
        return await self.helpers.fetch_chunks_by_collection(collectionId)

    def read_all_documents():
        pass

    async def add_chunks(self,
                         src_id,
                         target_collection_id):
        return await self.helpers.create_reference(src_id,
                                                   self.collectionNames.chunks_collection_name,
                                                   self.collectionNames.user_collection_link_name,
                                                   target_collection_id)

    def remove_chunks():
        pass

    def share():
        pass

    def unshare():
        pass

    def read_shared_users():
        pass

    ###########
    # Helpers #
    ###########
