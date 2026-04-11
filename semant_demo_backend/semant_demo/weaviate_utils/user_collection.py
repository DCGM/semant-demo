import semant_demo.schemas as schemas

import logging

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

from semant_demo.schema.collections import Collection

from semant_demo.weaviate_utils.helpers import WeaviateHelpers


class UserCollection():
    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.collectionNames = collectionNames
        self.helpers = WeaviateHelpers(client, collectionNames)

    #######
    # API #
    #######
    async def create(self, req: schemas.UserCollectionReqTemplate) -> str:
        """
        Create user collection (contains chunks user choose)
        """
        logging.info(
            f"Adding user collection\nUser: {req.user_id}\nCollection name: {req.collection_name}")
        # check if user collection with same properties already exists
        filters = (
            Filter.by_property("name").equal(req.collection_name) &
            Filter.by_property("user_id").equal(req.user_id)
        )
        results = await self.client.collections.get(self.collectionNames.user_collection_name).query.fetch_objects(
            filters=filters
        )
        if results.objects is not None:
            if len(results.objects) > 0:
                return results.objects[0].uuid

        # if no match found, create new collection
        new_collection_uuid = await self.client.collections.get(self.collectionNames.user_collection_name).data.insert(
            properties={
                "name": req.collection_name,
                "user_id": req.user_id
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
                            userId=props.get("user_id"),
                            description=props.get("description"),
                            createdAt=props.get("created_at"),
                            updatedAt=props.get("updated_at"),
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
