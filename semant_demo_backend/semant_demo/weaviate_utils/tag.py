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

import semant_demo.schemas as schemas
from semant_demo.weaviate_utils.helpers import WeaviateHelpers

import logging

class Tag():
    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.collectionNames = collectionNames
        self.helpers = WeaviateHelpers(client, collectionNames)

    #######
    # API #
    #######
    async def create(self, tag: schemas.TagData) -> str:
        """
        Adds new tag to tag-collection. This function calls fetch_tags to prevent duplicates.

        Args:
            tag: structure containing tag data defined in schemas.TagData,
                 also contains name of the collection this tag belongs to
            
        Returns:
            Created tag object UUID
            
        Raises:
            WeaviateConnectError: Cannot connect to Weaviate instance
            WeaviateDataValidationError: Invalid input data (empty name, invalid UUID format, etc.)
            WeaviateDuplicateError: Tag with same name already exists for this user in this collection
            WeaviateSerializationError: Cannot serialize tag data to JSON
            WeaviateServerError: Weaviate server returned an error
        """
        # check if tag with same properties already exists
        # prepare filter
        # Validate input
        if not tag.tag_name or not isinstance(tag.tag_name, str):
                raise WeaviateDataValidationError("tag_name must be a non-empty string")
        if not tag.tag_shorthand or not isinstance(tag.tag_shorthand, str):
                raise WeaviateDataValidationError("tag_shorthand must be a non-empty string")
        if not tag.tag_color or not isinstance(tag.tag_color, str):
                raise WeaviateDataValidationError("tag_color must be a non-empty string")
        try:
            filters =(
                Filter.by_property("tag_name").equal(tag.tag_name) &
                Filter.by_property("tag_shorthand").equal(tag.tag_shorthand)&
                Filter.by_property("tag_color").equal(tag.tag_color)
            )
            # query weaviate
            existing_tags = await self.helpers.fetch_tags(filters)
            # iterate over fetched results and check for equality
            for existing_tag in existing_tags:
                if (existing_tag.properties["tag_name"] == tag.tag_name and
                    existing_tag.properties["tag_shorthand"] == tag.tag_shorthand and
                    existing_tag.properties["tag_color"] == tag.tag_color):
                    return existing_tag.uuid # return existing tag UUID
            # no exact match found, create new tag
            new_tag_uuid = await self.client.collections.get("Tag").data.insert(
                properties={
                    "tag_name": tag.tag_name,
                    "tag_shorthand": tag.tag_shorthand,
                    "tag_color": tag.tag_color,
                    "tag_pictogram": tag.tag_pictogram,
                    "tag_definition": tag.tag_definition,
                    "tag_examples": tag.tag_examples,
                    "collection_name": tag.collection_name
                }
            )
            return new_tag_uuid  
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

    async def read(self):
        results = await self.helpers.fetch_tags()
        response = []
        # format the response
        for result in results:
            print(result)
            props = result.properties
            response.append({
                "tag_name": props["tag_name"],
                "tag_shorthand": props["tag_shorthand"],
                "tag_color": props["tag_color"],
                "tag_pictogram": props["tag_pictogram"],
                "tag_definition": props["tag_definition"],
                "tag_examples": props["tag_examples"],
                "collection_name": props["collection_name"],
                "tag_uuid": str(result.uuid)
            })
        
        return response

    def update():
        pass

    async def delete(self, chosenTagUUIDs):
        return await self.helpers.remove_tags(chosenTagUUIDs)

    def read_spans():
        pass

    def search_spans():
        pass

    ###########
    # Helpers #
    ###########