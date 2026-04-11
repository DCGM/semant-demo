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

from semant_demo.schema.collections import Collection, PostCollection

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

    async def read_all(self, userId: str) -> list[Collection]:
        """
        Retrieves all collections for given user
        """
        try:
            # filter collections by user
            filters = (
                Filter.by_property("user_id").equal(userId)
            )
            results = await self.client.collections.get(self.collectionNames.user_collection_name).query.fetch_objects(
                filters=filters
            )
            logging.info(f"User Id: {userId}\nRaw results: {results}")
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

    def update():
        pass

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
