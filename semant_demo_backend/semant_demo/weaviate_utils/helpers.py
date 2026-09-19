import logging
from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter

from semant_demo import schemas
from weaviate.classes.query import QueryReference

import logging

from weaviate.collections.classes.grpc import QueryReference
from weaviate.exceptions import (
    WeaviateConnectionError,
    WeaviateTimeoutError,
    WeaviateQueryError,
    WeaviateInvalidInputError,
    UnexpectedStatusCodeError,
    ResponseCannotBeDecodedError,
)
from semant_demo.weaviate_exceptions import WeaviateConnectError, WeaviateDataValidationError, WeaviateLimitError, WeaviateServerError, WeaviateOperationError

import uuid


class WeaviateHelpers:
    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.collectionNames = collectionNames

    async def delete_span_cascade(self, span_id: str) -> None:
        """
        Performs cascade deletion of a span
        """
        logging.info(f"Performing cascade deletion of span {span_id}")
        span_collection = self.client.collections.get(
            self.collectionNames.span_collection_name)

        # delete the span itself
        await span_collection.data.delete_by_id(span_id)

    async def delete_tag_cascade(self, tag_id: str) -> None:
        """
        Performs cascade deletion of a tag
        """
        logging.info(f"Performing cascade deletion of tag {tag_id}")
        tag_collection = self.client.collections.get(
            self.collectionNames.tag_collection_name)

        # delete automatic tag references
        await self.delete_references_from_filtered_objects(
            collection_name=self.collectionNames.chunks_collection_name,
            filters=Filter.by_ref("automaticTag").by_id().equal(tag_id),
            from_property="automaticTag",
            target_object_id=tag_id,
        )
        # delete positive tag references
        await self.delete_references_from_filtered_objects(
            collection_name=self.collectionNames.chunks_collection_name,
            filters=Filter.by_ref("positiveTag").by_id().equal(tag_id),
            from_property="positiveTag",
            target_object_id=tag_id,
        )
        # delete negative tag references
        await self.delete_references_from_filtered_objects(
            collection_name=self.collectionNames.chunks_collection_name,
            filters=Filter.by_ref("negativeTag").by_id().equal(tag_id),
            from_property="negativeTag",
            target_object_id=tag_id,
        )

        # delete spans tagged with this tag
        page_size = 100
        while True:
            span_response = await self.client.collections.get(self.collectionNames.span_collection_name).query.fetch_objects(
                filters=Filter.by_ref("tag").by_id().equal(tag_id),
                limit=page_size,
            )

            if not span_response.objects:
                break

            for span_obj in span_response.objects:
                await self.delete_span_cascade(str(span_obj.uuid))

            if len(span_response.objects) < page_size:
                break

        # finally delete the tag itself
        await tag_collection.data.delete_by_id(tag_id)

    async def delete_user_collection_cascade(self, collection_id: str) -> None:
        """"
        Performs cascade deletion of user collection
        """
        logging.info(
            f"Performing cascade deletion of user collection {collection_id}")
        tag_collection = self.client.collections.get(
            self.collectionNames.tag_collection_name)
        usercollection_collection = self.client.collections.get(
            self.collectionNames.user_collection_name)

        # delete references to collection from chunks
        await self.delete_references_from_filtered_objects(
            collection_name=self.collectionNames.chunks_collection_name,
            filters=Filter.by_ref(
                "userCollection").by_id().equal(collection_id),
            from_property="userCollection",
            target_object_id=collection_id,
        )
        # delete references to collection from documents
        await self.delete_references_from_filtered_objects(
            collection_name=self.collectionNames.document_collection_name,
            filters=Filter.by_ref("collection").by_id().equal(collection_id),
            from_property="collection",
            target_object_id=collection_id,
        )

        # delete tags which belong to that collection and their references
        page_size = 100
        while True:
            tag_response = await tag_collection.query.fetch_objects(
                filters=Filter.by_ref(
                    "userCollection").by_id().equal(collection_id),
                limit=page_size,
            )

            if not tag_response.objects:
                break

            for tag_obj in tag_response.objects:
                await self.delete_tag_cascade(str(tag_obj.uuid))

            if len(tag_response.objects) < page_size:
                break

        # finally delete the collection itself
        await usercollection_collection.data.delete_by_id(collection_id)

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
            references = [
                QueryReference(
                    link_on="automaticTag",  # the reference property
                    # properties from the referenced tags
                    return_properties=["uuid", "tag_name"]
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

    async def fetch_tags(self, filters: Filter | None = None, ids: list[str] | None = None) -> list:
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
            raise WeaviateDataValidationError(
                "Cannot specify both filters and ids. Use one or the other.")
        try:
            # build filter from given IDs
            if ids:
                # validate UUID format
                if not isinstance(ids, list):
                    raise WeaviateDataValidationError(
                        "ids must be a list of strings (UUIDs)")
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

    async def create_reference(self, src_id: str, src_collection_name: str, property_name: str, target_collection_id: str) -> bool:
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
                raise WeaviateDataValidationError(
                    "src_id must be a non-empty string")
            if not src_collection_name or not isinstance(src_collection_name, str):
                raise WeaviateDataValidationError(
                    "src_collection_name must be a non-empty string")
            if not property_name or not isinstance(property_name, str):
                raise WeaviateDataValidationError(
                    "property_name must be a non-empty string")
            if not target_collection_id or not isinstance(target_collection_id, str):
                raise WeaviateDataValidationError(
                    "target_collection_id must be a non-empty string")

            # prepare references list
            return_references = [
                QueryReference(
                    link_on=property_name
                )]
            # fetch the source object by id
            try:
                obj = await self.fetch_object_by_id(object_id=src_id, collection_name=src_collection_name,
                                                    return_references=return_references)
            except WeaviateOperationError:
                logging.error(
                    f"Source object '{src_id}' not found in collection '{src_collection_name}'")
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
            updatedCollectionIds = sorted(
                set(target_collection_ids + [target_collection_id]))
            # update weaviate with the new list
            try:
                await self.client.collections.get(src_collection_name).data.reference_replace(
                    from_uuid=obj.uuid,
                    from_property=property_name,
                    to=updatedCollectionIds,
                )
            except Exception as e:
                logging.error(
                    f"Failed to update reference in Weaviate: {str(e)}")
                raise WeaviateServerError(
                    f"Failed to update reference: {str(e)}")

            # test
            try:
                updated_obj = await self.fetch_object_by_id(object_id=src_id, collection_name=src_collection_name,
                                                            return_references=return_references)
                updated_refs = updated_obj.references or {}
                updated_collection_ids = ref_uuids(
                    updated_refs.get(property_name))

                logging.debug("Test - References after update:",
                              updated_collection_ids)
                assert target_collection_id in updated_collection_ids, "Reference was not added properly"
                # reference added
            except WeaviateServerError:
                raise
            except Exception as e:
                logging.error(f"Failed to verify reference: {str(e)}")
                raise WeaviateServerError(
                    f"Failed to verify reference: {str(e)}")
            # proper end
            return True  # TODO fix in other parts now is switched before False on success
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
        