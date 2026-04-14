import logging
from time import time
import weaviate
import weaviate.collections.classes.internal
from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter

from semant_demo import schemas
from semant_demo.config import Config
from semant_demo.gemma_embedding import get_query_embedding, get_hyde_document_embedding
from weaviate.classes.query import QueryReference
from semant_demo.config import config

from semant_demo.schema.collections import Collection

import logging

from weaviate.collections.classes.grpc import QueryReference
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
from semant_demo.weaviate_exceptions import WeaviateConnectError, WeaviateDataValidationError, WeaviateLimitError, WeaviateServerError, WeaviateOperationError 

import uuid

class WeaviateHelpers:
    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.collectionNames = collectionNames
    async def fetch_chunks(self, filters: Filter) -> list:
        """
        Fetches chunks with filters - tag, user-collection. Fetch subset of text chunks given by filters.
        
        Filters are built by the public methods using inline like:
            filters = Filter.by_property("name").equal("value")
            
        Args:
            filters: Weaviate Filter object for querying chunks
            
        Returns:
            List of chunk objects matching the filters

        Raises:
            WeaviateConnectError: Cannot connect to Weaviate instance
            WeaviateFilterError: Invalid filter specification or malformed Filter object
            WeaviateQueryError: Query execution failed or query syntax error
            WeaviateNotFoundError: No chunks found matching the filters
            WeaviateSerializationError: Cannot deserialize response from Weaviate
            WeaviateServerError: Weaviate server returned an error
        """
        # TODO use instead of:
        # fetch chunks from specific collection (currently used in get_tagged_chunks_paged, get_collection_chunks_paged)
        # fetch chunks by tags (currently used in filterChunksByTags)

        try:
            # prepare references to fetch in the query (set to None if you do not want to return any)
            references=[
                            QueryReference(
                                link_on="automaticTag",  # the reference property
                                return_properties=["uuid", "tag_name"]  # properties from the referenced tags
                            ),
                            QueryReference(
                                link_on="positiveTag",
                                return_properties=["uuid", "tag_name"]
                            ),
                            QueryReference(
                                link_on="negativeTag",
                                return_properties=["uuid", "tag_name"]
                            ),
                            QueryReference(
                                link_on="userCollection"
                            ),
                        ]
            # returns all properties (except blobs) and specified references
            response = await self.client.collections.get(self.collectionNames.chunks_collection_name).query.fetch_objects(
                return_references=references,
                filters=filters
            )
            if response.objects is None:
                return []
            return response.objects
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

    async def fetch_tags(self, filters: Filter|None = None, ids: list[str]|None = None) -> list:
        """
        Fetches tag collection
        - with specific name OR
        - by list of uuids OR 
        - without filter return all tags

        Filters are built by the public methods using inline like:
            filters = Filter.by_property("name").equal("value")
        
        Args:
            filters: Optional Weaviate Filter object for property matching (by name)
            ids: Optional list of tag UUIDs to fetch specific tags
        
        Returns:
            List of tag objects matching criteria. Returns empty list if no matches found.
            
        Raises:
            WeaviateConnectError: Cannot connect to Weaviate instance
            WeaviateFilterError: Invalid filter specification or malformed Filter object
            WeaviateQueryError: Query execution failed or query syntax error
            WeaviateQueryTimeoutError: Query execution exceeded timeout threshold
            WeaviateDataValidationError: Invalid UUID format in ids parameter
            WeaviateNotFoundError: No tags found matching the criteria
            WeaviateSerializationError: Cannot deserialize response from Weaviate
            WeaviateServerError: Weaviate server returned an error
        """
        if filters is not None and ids is not None:
            raise WeaviateDataValidationError("Cannot specify both filters and ids. Use one or the other.")
        try:
            # build filter from given IDs
            if ids:
                # validate UUID format
                if not isinstance(ids, list):
                    raise WeaviateDataValidationError("ids must be a list of strings (UUIDs)")
                converted_ids = []
                for uid in ids:
                    if isinstance(uid, uuid.UUID):
                        converted_ids.append(str(uid))
                    elif isinstance(uid, str):
                        converted_ids.append(uid)
                    else:
                        raise WeaviateDataValidationError(
                            f"UUID must be UUID object or string, got {type(uid).__name__}"
                        )
                filters = Filter.by_id().contains_any(converted_ids)

            results = await self.client.collections.get(self.collectionNames.tag_collection_name).query.fetch_objects(
                filters=filters
            )
            if results.objects is None:
                return []
            return results.objects
        except WeaviateConnectionError as e:
            logging.error(f"Error: {str(e)}")
            raise WeaviateConnectError(str(e))
        except WeaviateInvalidInputError as e:
            logging.error(f"Error: {str(e)}")
            raise WeaviateDataValidationError(str(e))
        except WeaviateTimeoutError as e:
            logging.error(f"Error: {str(e)}")
            raise WeaviateLimitError(str(e))
        except WeaviateDataValidationError as e:
            raise WeaviateDataValidationError(str(e))
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


    async def create_tag(self, tag: schemas.TagData) -> str:
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
            existing_tags = await self.fetch_tags(filters)
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


    async def fetch_object_by_id(self, object_id: str, collection_name: str = None, 
                               return_references: list = None) -> object:
        """
        Fetches a single Weaviate object by its UUID.
        
        Args:
            object_id: UUID of the object to fetch
            collection_name: Name of collection (defaults to chunks collection)
            return_references: Optional list of QueryReference objects to include
            
        Returns:
            Weaviate object with properties and optionally references
            
        Raises:
            WeaviateConnectError: Cannot connect to Weaviate instance
            WeaviateDataValidationError: Invalid UUID format
            WeaviateObjectNotFoundError: Object with given ID does not exist
            WeaviateServerError: Weaviate server error
        """
        try:
            if not collection_name:
                collection_name = self.collectionNames.chunks_collection_name
                
            # Validate UUID format
            if not isinstance(object_id, str):
                raise WeaviateDataValidationError(f"object_id must be string, got {type(object_id).__name__}")
            
            obj = await self.client.collections.get(collection_name).query.fetch_object_by_id(
                object_id,
                return_references=return_references
            )
            
            if obj is None:
                raise WeaviateOperationError(f"Object with ID '{object_id}' not found in collection '{collection_name}'")
            
            return obj
        
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

    async def delete_references_from_filtered_objects(
        self,
        collection_name: str,
        filters: Filter,
        from_property: str,
        target_object_id: str,
        page_size: int = 100,
    ) -> None:
        """
        Deletes a reference from every object matching the filter.

        The query is repeated without an offset because removing the reference
        changes which objects still match the filter.
        """
        try:
            collection = self.client.collections.get(collection_name)
            target_object_id = str(target_object_id)

            while True:
                response = await collection.query.fetch_objects(
                    filters=filters,
                    limit=page_size,
                )

                if not response.objects:
                    break

                for obj in response.objects:
                    await collection.data.reference_delete(
                        from_uuid=obj.uuid,
                        from_property=from_property,
                        to=target_object_id,
                    )

                if len(response.objects) < page_size:
                    break

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
            logging.error(f"Unexpected error deleting references: {str(e)}")
            raise WeaviateServerError(str(e))

    async def create_reference(self, src_id:str, src_collection_name:str, property_name:str, target_collection_id:str) -> bool:
        """
        Creates reference from weviate object fetched by its id to other object defined by id.

        Args:
            src_id: weaviate source object id (e.g., chunk id)
            src_collection_name: Name of collection where is weaviate source object
            property_name: Name of reference property (e.g., "tagged_with", "inCollection")
            target_collection_id: UUID of target object (e.g., tag UUID)
            
        Returns:
            True if reference created successfully
            
        Raises:
            WeaviateConnectError: Cannot connect to Weaviate instance
            WeaviateDataValidationError: Invalid UUID format in source_id or target_id
            WeaviateReferencedObjectNotFoundError: Target object does not exist
        """
        try:
            # Validate inputs
            if not src_id or not isinstance(src_id, str):
                raise WeaviateDataValidationError("src_id must be a non-empty string")
            if not src_collection_name or not isinstance(src_collection_name, str):
                raise WeaviateDataValidationError("src_collection_name must be a non-empty string")
            if not property_name or not isinstance(property_name, str):
                raise WeaviateDataValidationError("property_name must be a non-empty string")
            if not target_collection_id or not isinstance(target_collection_id, str):
                raise WeaviateDataValidationError("target_collection_id must be a non-empty string")

            # prepare references list
            return_references=[
                    QueryReference(
                        link_on=property_name
                    )]
            # fetch the source object by id
            try:
                obj = await self.fetch_object_by_id(object_id=src_id, collection_name=src_collection_name, 
                                return_references=return_references)
            except WeaviateOperationError:
                logging.error(f"Source object '{src_id}' not found in collection '{src_collection_name}'")
                raise
            # extract references
            refs = obj.references or {}

            # helper to extract UUID strings from reference block
            def ref_uuids(ref_block):
                if not ref_block:
                    return []
                return [str(r.uuid) for r in ref_block.objects]
            
            # extract ids of referenced objects
            target_collection_ids = ref_uuids(refs.get(property_name))
            target_collection_id = str(target_collection_id)
            # add new collection id to list of already referenced collection ids
            updatedCollectionIds = sorted(set(target_collection_ids + [target_collection_id]))
            # update weaviate with the new list
            try:
                await self.client.collections.get(src_collection_name).data.reference_replace(
                        from_uuid=obj.uuid,
                        from_property=property_name,
                        to=updatedCollectionIds,
                )
            except Exception as e:
                logging.error(f"Failed to update reference in Weaviate: {str(e)}")
                raise WeaviateServerError(f"Failed to update reference: {str(e)}")

            # test
            try:
                updated_obj = await self.fetch_object_by_id(object_id=src_id, collection_name=src_collection_name, 
                                return_references=return_references)
                updated_refs = updated_obj.references or {}
                updated_collection_ids = ref_uuids(updated_refs.get(property_name))

                logging.debug("Test - References after update:", updated_collection_ids)
                assert target_collection_id in updated_collection_ids, "Reference was not added properly"
                # reference added
            except WeaviateServerError:
                raise
            except Exception as e:
                logging.error(f"Failed to verify reference: {str(e)}")
                raise WeaviateServerError(f"Failed to verify reference: {str(e)}") 
            # proper end
            return True # TODO fix in other parts now is switched before False on success
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


    async def remove_reference(self, src_id: str, src_collection_name:str, property_name: str, target_collection_id:str) -> bool: 
        """
        Removes reference between objects.

        Args:
            src_id: weaviate source object id (e.g., chunk id)
            src_collection_name: Name of collection where is weaviate source object
            property_name: Name of reference property (e.g., "tagged_with", "inCollection")
            target_collection_id: UUID of target object (e.g., tag UUID)

        Returns:
            True if reference removed successfully
            
        Raises:
            WeaviateConnectError: Cannot connect to Weaviate instance
            WeaviateDataValidationError: Invalid UUID format in source_id or target_id
            WeaviateServerError: Weaviate server returned an error
            WeaviateOperationError: Cannot perform operation over weaviate
        """
        try:
            # Validate inputs
            if not src_id or not isinstance(src_id, str):
                raise WeaviateDataValidationError("src_id must be a non-empty string")
            if not src_collection_name or not isinstance(src_collection_name, str):
                raise WeaviateDataValidationError("src_collection_name must be a non-empty string")
            if not property_name or not isinstance(property_name, str):
                raise WeaviateDataValidationError("property_name must be a non-empty string")
            if not target_collection_id or not isinstance(target_collection_id, str):
                raise WeaviateDataValidationError("target_collection_id must be a non-empty string")

            # prepare references list
            return_references=[
                    QueryReference(
                        link_on=property_name
                    )]
            # fetch the source object by id
            try:
                obj = await self.fetch_object_by_id(object_id=src_id, collection_name=src_collection_name, 
                                return_references=return_references)
            except WeaviateQueryError as e:
                logging.error(f"Source object '{src_id}' not found in collection '{src_collection_name}'")
                raise WeaviateConnectError(str(e))
            # extract references
            refs = obj.references or {}

            current = refs.get(property_name)
            currentIDs = [str(r.uuid) for r in (current.objects if current else [])]
            remaining = [tid for tid in currentIDs if tid != target_collection_id]
            logging.debug(f"Replacing Current{currentIDs} \nRemaning{remaining}")
            logging.debug(f"To remove {target_collection_id}")
            # check length if the id was removed
            if len(remaining) != len(currentIDs):
                logging.info(f"Replacing {currentIDs} {remaining}")
                await self.client.collections.get(src_collection_name).data.reference_replace(
                        from_uuid=obj.uuid,
                        from_property=property_name,
                        to=remaining
                    )
            return True
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

    async def create_collection(self, req: schemas.UserCollectionReqTemplate, collectionName: str) -> str:
        """
        Create user collection (contains chunks user choose)
        """
        logging.info(f"Adding user collection\nUser: {req.user_id}\nCollection name: {req.collection_name}")
        # check if user collection with same properties already exists
        filters = (
                Filter.by_property("name").equal(req.collection_name) &
                Filter.by_property("user_id").equal(req.user_id)
        )
        results = await self.client.collections.get().query.fetch_objects(
            filters=filters
        )
        if results.objects is not None:
            if len(results.objects) > 0:
                return results.objects[0].uuid

        # if no match found, create new collection
        new_collection_uuid = await self.client.collections.get("UserCollection").data.insert(
            properties={
                "name": req.collection_name,
                "user_id": req.user_id
            }
        )
        return new_collection_uuid

    async def remove_tags(self, chosenTagUUIDs: schemas.GetTaggedChunksReq)->schemas.RemoveTagsResponse:
        """
        Removes tags by:
         - remove all cross-references from Chunks
         - remove the Tag object itself
        """
        try:
            # get tags for collection names
            tag_collection = self.client.collections.get(self.collectionNames.tag_collection_name)
            tag_ids = [str(uuid) for uuid in chosenTagUUIDs.tag_uuids]
            filters = Filter.by_id().contains_any(tag_ids)
            
            results = await tag_collection.query.fetch_objects(filters=filters)
            
            # get different collection names
            collection_names = {obj.properties["collection_name"] for obj in results.objects}
            print(collection_names)
            
            self.remove_tag_refs(tag_ids, tag_type="automaticTag")
            self.remove_tag_refs(tag_ids, tag_type="positiveTag")
            self.remove_tag_refs(tag_ids, tag_type="negativeTag")
            
            tagsToRemove = set(chosenTagUUIDs.tag_uuids)
            tagsToRemove = [str(tagID) for tagID in tagsToRemove]

            logging.info("deleted references from chunks to tags")
            # remove the Tag objects itself
            result = await tag_collection.data.delete_many(
                where=Filter.by_id().contains_any(tagsToRemove)
            )
            logging.info(result)

            return {"successful": True}
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
    
    async def remove_tag_refs(self, chosenTagUUIDs: schemas.GetTaggedChunksReq, tag_type: str)->schemas.RemoveTagsResponse:
        """
        Removes selected type of tags and their references
        """
        try:
            # remove all automatic cross-references from Chunks

            # get tags for collection names
            tag_collection = self.client.collections.get("Tag")
            filters = Filter.by_id().contains_any([str(uuid) for uuid in chosenTagUUIDs.tag_uuids])

            results = await tag_collection.query.fetch_objects(filters=filters)

            # get different collection names
            collection_names = {obj.properties["collection_name"] for obj in results.objects}

            # iterate over the collections and retrieve text chunks and corresponding tags
            for collection_name in collection_names:
                # get all chunks
                chunks = self.client.collections.get(collection_name)
                # fetch chunks with hasTags
                res = await chunks.query.fetch_objects(
                    return_references=QueryReference(
                        link_on=tag_type,
                        return_properties=[]
                    )
                )

                tagsToRemove = set(chosenTagUUIDs.tag_uuids)
                tagsToRemove = [str(tagID) for tagID in tagsToRemove]

                # replace hasTags with remaining refs
                for obj in res.objects:
                    refs = obj.references or {}
                    current = refs.get(tag_type)
                    currentIDs = [str(r.uuid) for r in (current.objects if current else [])]
                    remaining = list(filter(lambda tid: tid not in tagsToRemove, currentIDs))
                    logging.info(f"Replacing Current{currentIDs} \nRemaning{remaining}")
                    logging.info(f"To remove {tagsToRemove}")
                    if len(remaining) != len(currentIDs):
                        logging.info(f"Replacing {currentIDs} {remaining}")
                        await chunks.data.reference_replace(
                            from_uuid=obj.uuid,
                            from_property=tag_type,
                            to=remaining
                        )
                    check = await chunks.query.fetch_object_by_id(
                        obj.uuid,
                        return_references=[QueryReference(link_on=tag_type, return_properties=[])]
                    )
                    got = [str(r.uuid) for r in (check.references.get(tag_type).objects if check.references and check.references.get("hasTags") else [])]
                    logging.info(f"after: {got}")
                logging.info("deleted references from chunks to tags")

            return {"successful": True}
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

    async def tag_chunks_with_llm(self, tag_request: schemas.TaggingTaskReqTemplate, task_id: str, session=None) -> schemas.TagResponse:
        """
        Assigns automatic tags to chunks
        """
        try:
            # load config data
            # set model from config
            config_model_name = tag_request.task_config.params.model_name
            config_temperature = tag_request.task_config.params.temperature
            # load prompt template from the config
            if tag_request.task_config.prompt_template is not None:
                prompt = ChatPromptTemplate.from_template(tag_request.task_config.prompt_template)
            else:
                tag_template = tagging_templates.templates["Basic"]
                prompt = ChatPromptTemplate.from_template(tag_template)
            # select API
            if tag_request.task_config.params.model_type == schemas.APIType.openai:
                api_key = os.getenv("OPENAI_API_KEY", "")
                model = ChatOpenAI(
                    model = config_model_name if config_model_name else config.OPENAI_MODEL,
                    api_key = api_key,
                    temperature = config_temperature
                )
            elif tag_request.task_config.params.model_type == schemas.APIType.google:
                pass
            else: # default ollama
                model = OllamaProxyRunnable()
                model.set_model(config_model_name)
                model.set_temperature(config_temperature) # this is preparation, semant_demo_backend\semant_demo\ollama_proxy.py does not support yet
            # prepare chain
            chain = prompt | model

            # get the collection
            collection_name = tag_request.collection_name
            logging.info(f"Collection name: {collection_name}")
            # select filters
            tag_filters =(
                Filter.by_property("tag_name").equal(tag_request.tag_name) &
                Filter.by_property("tag_shorthand").equal(tag_request.tag_shorthand)&
                Filter.by_property("tag_color").equal(tag_request.tag_color)
            )
            
            tag_objects = await searcher.fetch_tags(tag_filters)
            tag_uuid = tag_objects[0].uuid
            
            positive_responses = re.compile("^(True|Ano|Áno|Yes)", re.IGNORECASE) # prepare regex for check if the text is tagged be llm
            
            # filter to tag just chunks in selected user collection
            filters_by_collection =(
                Filter.by_ref(link_on=searcher.user_collection_link_name).by_property("name").equal(collection_name)
            )
            filters_by_tag = ((
                        Filter.by_ref(link_on="automaticTag").by_id().equal(tag_uuid) |
                        Filter.by_ref(link_on="positiveTag").by_id().equal(tag_uuid) |
                        Filter.by_ref(link_on="negativeTag").by_id().equal(tag_uuid) ) &
                        Filter.by_ref(link_on=searcher.user_collection_link_name).by_property("name").equal(collection_name)
                    )

            # query weaviate db for chunks of chosen collection
            results = await searcher.fetch_chunks(filters_by_collection)
            resultsFiltered = await searcher.fetch_chunks(filters_by_tag)

            # collect the UUIDs from the filtered results
            if resultsFiltered:
                filtered_ids = {obj.uuid for obj in resultsFiltered}

                # filter main results to exclude objects whose id is in filtered_ids
                final_results = [obj for obj in results if obj.uuid not in filtered_ids]
            else:
                final_results = results

            texts = []
            tags = []
            tag_processing_data = []

            # process with llm and decide if tag belongs to text
            logging.info("Past the add ir get tag")
            all_texts_count = len(final_results)
            processed_count = 0
            for obj in final_results:
                try:
                    # extract text field from the current object
                    text = obj.properties["text"]
                    tag = await chain.ainvoke({"tag_name": tag_request.tag_name, "tag_definition": tag_request.tag_definition, "tag_examples": tag_request.tag_examples, "content": text})
                    # process response according to the api type
                    if tag_request.task_config.params.model_type == schemas.APIType.openai:
                        tag = tag.content
                    
                    # store in weaviate (upload positive tag instances to weaviate)
                    if positive_responses.search(tag): # if the llm response is positive then store the tag data
                        # test if the reference to the tag exists
                        references = obj.references.get("automaticTag") if obj.references else None
                        # if there are no references or there is not any reference to the wanted tag add the new reference
                        if not references or not getattr(references, "objects", None) or not (any(str(tag_obj.uuid) == str(tag_uuid) for tag_obj in references.objects)):
                            # add the new tag data
                            await searcher.create_reference(obj.uuid, searcher.chunks_collection_name, property_name="automaticTag", target_collection_id=tag_uuid)
                            logging.info("NOT REFERENCED YET")
                    texts.append(text)
                    tags.append(tag)
                    tag_processing_data.append({"chunk_id": str(obj.uuid), "text": text, "tag": str(tag)})
                    logging.info(f"Tag {tag_uuid} processed {processed_count} / {all_texts_count}")
                    # store progress in SQL db
                    processed_count += 1 # increase number of processed chunks
                    await update_task_status(task_id, "RUNNING", result={}, collection_name=tag_request.collection_name, session=session, all_texts_count=all_texts_count, processed_count=processed_count, tag_id=tag_uuid, tag_processing_data=tag_processing_data)
                    logging.info("After update")
                except Exception as e:
                    logging.error(f"Error in storing result to weaviate: {e}")

            return {'texts': texts, 'tags': tags}

        except Exception as e:
            logging.error(f"Error fetching texts from collection: {e}")
            return {}

    async def tag_and_store(tagReq: schemas.TaggingTaskReqTemplate, task_id: str, sessionmaker):
        try:
            session = sessionmaker()
            
            try:
                #await update_task_status(task_id, "RUNNING", collection_name=tagReq.collection_name, sessionmaker=sessionmaker)
                # TODO replace with Weaviate/LLM operations:
                logging.info(f"Starting task with data: {str(tagReq)}")
                response = await tag_chunks_with_llm(searcher, tagReq, task_id, session=session)#tag_chunks_with_llm(tagReq, task_id, session=session)
                logging.info(f"Task finished. Response: {response}")
                await update_task_status(task_id, "COMPLETED", result=response, collection_name=tagReq.collection_name, session=session)
                logging.info("Updated ok")
            except Exception as e:
                await update_task_status(task_id, "FAILED", result={"error": str(e)}, collection_name=tagReq.collection_name, session=session)
                logging.error(f"Error: {e}")
            await session.close()
        except Exception as e:
            logging.error(f"Error: {e}")

    def getTaskByName(name):
        for t in asyncio.all_tasks():
            if t.get_name() == name and not t.done():
                return t
        
    async def fetch_chunks_by_collection(self, collectionId: str) ->schemas.GetCollectionChunksResponse:
        """
        Get all chunks belonging to collection with collectionId
        get collection object, in that collection search for chunks that refer to the
        collection and return chunk texts
        """
        try:
            chunk_lst_with_tags = []
            # prepare filter for collection ID
            filters = Filter.by_ref(self.collectionNames.user_collection_link_name).by_id().equal(collectionId)
            # iterate over all chunks find the reference to the user collection
            chunks = await self.fetch_chunks(filters=filters)
            chunk_lst_with_tags.extend([
                    {
                        'text_chunk': chunk_obj.properties.get('text', ''),
                        'chunk_id': str(chunk_obj.uuid),
                        'chunk_collection_name': collectionId
                    }
                    for chunk_obj in chunks
            ])
            return {"chunks_of_collection": chunk_lst_with_tags}
        except Exception as e:
            logging.error(f"Error: {e}")
            return {'chunks_of_collection': []}

    # helper to remove tag from disapproved and automatic tags
    async def removeTagRef(self, refName, data: schemas.ApproveTagReq, return_references):
                obj = await self.fetch_object_by_id(data.chunkID, self.collectionNames.chunks_collection_name, return_references)
                refs = obj.references or {}
                current = refs.get(refName)
                currentIDs = [str(r.uuid) for r in (current.objects if current else [])]
                remaining = [tid for tid in currentIDs if tid != data.tagID]
                logging.info(f"Replacing Current{currentIDs} \nRemaning{remaining}")
                logging.info(f"To remove {data.tagID}")
                if len(remaining) != len(currentIDs):
                    logging.info(f"Replacing {currentIDs} {remaining}")
                    await self.remove_reference(src_id=str(obj.uuid), 
                                            src_collection_name=self.collectionNames.chunks_collection_name, 
                                            property_name=refName,
                                            target_collection_id=self.collectionNames.tag_collection_name)

    async def get_tagged_chunks(getChunksReq: schemas.GetTaggedChunksReq) -> schemas.GetTaggedChunksResponse:
        """
        Get tag objects from them extract collection names, in these collections
        search for chunks that refer to any of the selected tags and return chunk
        texts and all tags from selected tags that are referenced from the chunk
        """
        try:
            # get all chunks with at least one tag from chosenTagUUIDs list
            # get tags
            
            chunk_lst_with_tags = []
            filters = Filter.by_id().contains_any([str(uuid) for uuid in getChunksReq.tag_uuids])
            results = await searcher.fetch_tags(filters=filters)
            # get different collection names
            collection_names = {obj.properties["collection_name"] for obj in results}
            userCollectionName = next(iter(collection_names))
            logging.info(f"Tag uuids in get_tagged_chunks: {getChunksReq.tag_uuids} {collection_names} {userCollectionName}")
            # go over chunks, retrieve text chunks and corresponding tags
            # filter to get chunks in selected user collection
            filters =(
                Filter.by_ref(link_on="userCollection").by_property("name").equal(userCollectionName)
            )
            try:
                chunk_results = searcher.fetch_chunks(filters=filters)
                reference_src = getChunksReq.tag_type.value + "Tag"  # ["automaticTag", "positiveTag", "negativeTag"]
                logging.info(f"Source selected: {reference_src}")
                for chunk_obj in chunk_results:
                        referencedTags = chunk_obj.references.get(reference_src) if chunk_obj.references else None
                        chunk_id = str(chunk_obj.uuid)
                        chunk_text = chunk_obj.properties.get('text', '')
                        corresponding_tags = []
                        if referencedTags is not None:
                            logging.info(f"Referenced tags: {referencedTags}")
                        # extract tag
                        if referencedTags and getattr(referencedTags, "objects", None):
                            for tag_obj in referencedTags.objects:
                                if tag_obj.uuid in getChunksReq.tag_uuids:
                                    corresponding_tags.append(str(tag_obj.uuid))
                        # check if there is at least one selected tag

                        if corresponding_tags:
                            # extract approval counts
                            for tagID in corresponding_tags:
                                chunk_lst_with_tags.append(
                                    {'tag_uuid': tagID, 'text_chunk': chunk_text, "chunk_id": chunk_id,
                                    "chunk_collection_name": userCollectionName, "tag_type": getChunksReq.tag_type.value})
            except Exception as e:
                logging.error(f"Tags in Chunks error: {e}")
                
            return {"chunks_with_tags": chunk_lst_with_tags}
        except Exception as e:
            logging.error(f"No tags assigned yet. {e}")
            return {'chunks_with_tags': []}