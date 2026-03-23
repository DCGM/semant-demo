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
from .config import config

import logging

from weaviate.collections.classes.grpc import QueryReference
from weaviate_exceptions import *

import uuid

class WeaviateSearch:
    def __init__(self, client: WeaviateAsyncClient, 
                 chunks_collection: str = "Chunks", 
                 tag_collection_name: str = "Tag"):
        self.client = client
        # collections.get() is synchronous, no await needed
        self.chunk_col = self.client.collections.get("Chunks")
        self.chunks_collection = chunks_collection
        self.tag_collection_name = tag_collection_name

    @classmethod
    async def create(cls, config:Config) -> "WeaviateSearch":
        # Instantiate async client with custom params
        async_client = weaviate.use_async_with_custom(
            http_host=config.WEAVIATE_HOST, http_port=config.WEAVIATE_REST_PORT, http_secure=False,
            grpc_host=config.WEAVIATE_HOST, grpc_port=config.WEAVIATE_GRPC_PORT, grpc_secure=False,
        )
        # Connect and verify readiness
        await async_client.connect()  # :contentReference[oaicite:0]{index=0}
        if not await async_client.is_ready():  # :contentReference[oaicite:1]{index=1}
            logging.error("Weaviate is not ready.")
            await async_client.close()
            exit(-1)
        return cls(async_client)

    async def close(self):
        await self.client.close()  # :contentReference[oaicite:2]{index=2}

    async def search(self, search_request: schemas.SearchRequest) -> schemas.SearchResponse:
        # Build filters
        filters = []
        if search_request.min_year:
            filters.append(
                Filter.by_ref(link_on="document").by_property("yearIssued").greater_or_equal(search_request.min_year)
            )
        if search_request.max_year:
            filters.append(
                Filter.by_ref(link_on="document").by_property("yearIssued").less_or_equal(search_request.max_year)
            )
        if search_request.language:
            filters.append(Filter.by_property("language").equal(search_request.language))

        tagFilters = []
        if search_request.tag_uuids:
            logging.info(search_request.tag_uuids)
            if search_request.automatic:
                tagFilters.append(Filter.by_ref("automaticTag").by_id().contains_any(search_request.tag_uuids))
            if search_request.positive:
                tagFilters.append(Filter.by_ref("positiveTag").by_id().contains_any(search_request.tag_uuids))

        combined_tag_filters = None
        if tagFilters:
            combined_tag_filters = tagFilters[0]
            for f in tagFilters[1:]:
                combined_tag_filters = combined_tag_filters | f

        if combined_tag_filters:
            filters.append(combined_tag_filters)
            
        # Combine with AND logic
        combined_filter = None
        if filters:
            combined_filter = filters[0]
            for f in filters[1:]:
                combined_filter &= f

        document_properties_to_return = [
                "library", "title", "subTitle", "partNumber", "partName",
                "yearIssued", "dateIssued", "authors", "publisher", "description",
                "url", "public", "documentType", "keywords", "genre", "placeTerm",
                "section", "region", "id_code"
        ]

        t1 = time()
        if search_request.type == schemas.SearchType.hybrid:
            if search_request.is_hyde == False:
                q_vector = await get_query_embedding(search_request.query)
            else:
                q_vector = await get_hyde_document_embedding(search_request.query)

            # Execute hybrid search
            result = await self.chunk_col.query.hybrid(
                query=search_request.query,
                alpha=search_request.hybrid_search_alpha,
                vector=q_vector,
                limit=search_request.limit,
                filters=combined_filter,
                return_references=[QueryReference(link_on="document", return_properties=document_properties_to_return),
                    # TODO: Do not fetch tags if not needed. (xtomas36)
                    QueryReference(
                        link_on="automaticTag",                 # the reference property
                        return_properties=["uuid", "tag_name"]  # properties from the referenced tags
                    ),
                    QueryReference(
                        link_on="positiveTag",
                        return_properties=["uuid", "tag_name"]
                    ),
                ]
            )
        elif search_request.type == schemas.SearchType.text:
            # Execute text search
            result = await self.chunk_col.query.bm25(
                query=search_request.query,
                limit=search_request.limit,
                filters=combined_filter,
                return_references=[QueryReference(link_on="document", return_properties=document_properties_to_return),
                         QueryReference(
                        link_on="automaticTag",                 # the reference property
                        return_properties=["uuid", "tag_name"]  # properties from the referenced tags
                    ),
                    QueryReference(
                        link_on="positiveTag",
                        return_properties=["uuid", "tag_name"]
                    ),
                ]
            )
        elif search_request.type == schemas.SearchType.vector:
            if search_request.is_hyde == False:
                q_vector = await get_query_embedding(search_request.query)
            else:
                q_vector = await get_hyde_document_embedding(search_request.query)

            result = await self.chunk_col.query.near_vector(
                near_vector=q_vector,
                limit=search_request.limit,
                filters=combined_filter,
                return_references=[QueryReference(link_on="document", return_properties=document_properties_to_return),
                    QueryReference(
                        link_on="automaticTag",                 # the reference property
                        return_properties=["uuid", "tag_name"]  # properties from the referenced tags
                    ),
                    QueryReference(
                        link_on="positiveTag",
                        return_properties=["uuid", "tag_name"]
                    ),
                ]
            )
        else:
            raise ValueError(f"Unknown search type: {search_request.type}")

        search_time = time() - t1

        # Parse results
        results: list[schemas.TextChunkWithDocument] = []
        log_entry = (
            f"Top {len(result.objects)} results for “{search_request.query}”. "
            f"Retrieved in {search_time:.2f} seconds:"
        )
        logging.info(log_entry)

        # helper to extract UUID strings from reference block
        def ref_uuids(ref_block):
            if not ref_block:
                return []
            return [str(r.uuid) for r in ref_block.objects]
        tags_result = []

        for obj in result.objects:
            chunk_data = obj.properties
            doc_objs = obj.references.get("document").objects
            if not doc_objs:
                continue
            first_doc = doc_objs[0]
            if "library" not in first_doc.properties or not first_doc.properties["library"]:
                first_doc.properties["library"] = "mzk"

            document_obj = schemas.Document(
                id=first_doc.uuid,
                **first_doc.properties,
            )
            chunk = schemas.TextChunkWithDocument(
                id=obj.uuid,
                **chunk_data,
                document_object=document_obj,
                document=first_doc.uuid
            )
            chunk.text = chunk.text.replace("-\n", "").replace("\n", " ")
            results.append(chunk)

            # add tag info for this chunk
            refs = obj.references or {}

            auto_ids = ref_uuids(refs.get("automaticTag"))
            pos_ids = ref_uuids(refs.get("positiveTag"))

            requested_ids = search_request.tag_uuids

            auto_ids = list(set(auto_ids) & set(requested_ids))
            pos_ids = list(set(pos_ids) & set(requested_ids))
            tags_result.append({'chunk_id': str(chunk.id), 'positive_tags_ids': pos_ids, 'automatic_tags_ids': auto_ids})

        response = schemas.SearchResponse(
            results=results,
            search_request=search_request,
            time_spent=search_time,
            search_log=[log_entry],
            tags_result=tags_result,
        )
        logging.info(f'Response created in {time() - t1:.2f} seconds')
        return response
    
    async def _fetch_chunks(self, filters: Filter) -> list:
        """
        Fetches chunks with filters - tag, user-collection. Fetch subset of text chunks given by filters.
        
        Filters are built by the public methods using inline like:
            filters = Filter.by_property("name").equal("value")
            
        Args:
            filters: Weaviate Filter object for querying chunks
            
        Returns:
            List of chunk objects matching the filters

        Raises:
            WeaviateConnectionError: Cannot connect to Weaviate instance
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
                        ],
            # returns all properties (except blobs) and specified references
            response = await self.client.collections.get(self.chunks_collection).query.fetch_objects(
                return_references=references,
                filters=filters
            )
            if response.objects is None:
                return []
            return response.objects
        except (WeaviateConnectionError, WeaviateFilterError, WeaviateNotFoundError,
                WeaviateQueryError, WeaviateSerializationError) as e:
            # log the error for debugging
            logging.error(f"Failed to fetch chunks from {self.chunks_collection}: {str(e)}")
            raise
        except Exception as e:
            # catch unexpected errors and wrap them
            logging.error(f"Unexpected error fetching chunks: {str(e)}")
            raise WeaviateServerError(f"Failed to fetch chunks: {str(e)}")

    async def _fetch_tags(self, filters: Filter|None = None, ids: list[str]|None = None) -> list:
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
            WeaviateConnectionError: Cannot connect to Weaviate instance
            WeaviateFilterError: Invalid filter specification or malformed Filter object
            WeaviateQueryError: Query execution failed or query syntax error
            WeaviateQueryTimeoutError: Query execution exceeded timeout threshold
            WeaviateDataValidationError: Invalid UUID format in ids parameter
            WeaviateNotFoundError: No tags found matching the criteria
            WeaviateSerializationError: Cannot deserialize response from Weaviate
            WeaviateServerError: Weaviate server returned an error
        """
        # TODO use instead of:
        # with specific name (current add_or_get_tag) OR by list of uuids (current get_tagged_chunks_paged) OR without filter return all tags (current get_all_tags)
        try:
            # check for conflict of defining both filters and IDs
            if filters is not None and ids is not None:
                raise WeaviateDataValidationError("Cannot specify both filters and ids. Use one or the other.")

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

            results = await self.client.collections.get(self.tag_collection_name).query.fetch_objects(
                filters=filters
            )
            if results.objects is None:
                return []
            return results.objects
        except (WeaviateFilterError, WeaviateQueryError, WeaviateSerializationError) as e:
            # Log expected Weaviate errors
            logging.error(f"Failed to fetch tags from {self.tag_collection_name}: {str(e)}")
            raise
        except WeaviateDataValidationError as e:
            # Log validation errors
            logging.error(f"Invalid input for tag fetch: {str(e)}")
            raise
        except WeaviateConnectionError as e:
            # Log connection errors
            logging.error(f"Cannot connect to Weaviate: {str(e)}")
            raise
        except Exception as e:
            # Catch unexpected errors and wrap them
            logging.error(f"Unexpected error fetching tags: {str(e)}")
            raise WeaviateServerError(f"Failed to fetch tags: {str(e)}")

    def _create_tag(self, tag: schemas.TagData, collection_name:str) -> str:
        """
        Adds new tag to tag-collection. This function calls fetch_tags to prevent duplicates.

        Args:
            name: schemas.TagData of the tag
            collection_name: Name of the collection this tag belongs to
            
        Returns:
            Created tag object UUID
            
        Raises:
            WeaviateConnectionError: Cannot connect to Weaviate instance
            WeaviateDataValidationError: Invalid input data (empty name, invalid UUID format, etc.)
            WeaviateDuplicateError: Tag with same name already exists for this user in this collection
            WeaviateSerializationError: Cannot serialize tag data to JSON
            WeaviateServerError: Weaviate server returned an error
        """
        # TODO like current add_or_get_tag, but use fetch_tags
        pass

    def _create_reference(self, src_id:str, property_name:str, target_id:str) -> bool:
        """
        Creates reference from weviate object fetched by its id to other object defined by id.

        Args:
            src_id: weaviate source object id (e.g., chunk id)
            property_name: Name of reference property (e.g., "tagged_with", "inCollection")
            target_id: UUID of target object (e.g., tag UUID)
            
        Returns:
            True if reference created successfully
            
        Raises:
            WeaviateConnectionError: Cannot connect to Weaviate instance
            WeaviateDataValidationError: Invalid UUID format in source_id or target_id
            WeaviateObjectNotFoundError: Source object does not exist
            WeaviateReferencedObjectNotFoundError: Target object does not exist
            WeaviateReferencePropertyError: Reference property does not exist in schema or is not a reference 
        """
        pass

    def _remove_reference(self, src_id: str, reference_to_remove: str) -> bool: 
        """
        Removes reference between objects.

        Args:
            source_id: UUID of source object (e.g., chunk UUID)
            property_name: Name of reference property to remove from (e.g., "tagged_with", "inCollection")
            
        Returns:
            True if reference removed successfully
            
        Raises:
            WeaviateConnectionError: Cannot connect to Weaviate instance
            WeaviateDataValidationError: Invalid UUID format in source_id or target_id
            WeaviateObjectNotFoundError: Source object does not exist
            WeaviateReferencePropertyError: Reference property does not exist in schema
            WeaviateStateError: Reference does not exist or cannot be removed
            WeaviateSerializationError: Cannot serialize removal data
            WeaviateServerError: Weaviate server returned an error
        """
        pass

    # TODO
    """
    - change get_tagged_chunks_paged
        - call fetch_tags - fetch specific mode, fetch_chunks
        - keep preparing filters, chunk selection logic

    - change get_collection_chunks_paged 
        - call fetch_chunks

    - change tag_chunks_with_llm_paged 
        - keep separate llm calling and config
        - will call fetch_tags, fetch_chunks, create_reference

    - change filterChunksByTags
        - keep filter preparation and result processing
        - will call fetch_chunks

    - change approve_tag
        - will call fetch_chunks, remove_reference, create_reference
        
    - instead add_chunk_to_collection call create_reference

    - change add_or_get_tag to create_tag
    
    - change get_all_tags 
        - calls fetch_tags - fetch all mode
        - keep parse result
    """

    # Some functions can stay unchanged:

    ### moved here TODO: fix reference from rest of the code (renamed from add_collection)
    async def create_collection(self, req: schemas.UserCollectionReqTemplate) -> str:
        """
        Create user collection (contains chunks user choose)
        """
        logging.info(f"Adding user collection\nUser: {req.user_id}\nCollection name: {req.collection_name}")
        # check if user collection with same properties already exists
        filters = (
                Filter.by_property("name").equal(req.collection_name) &
                Filter.by_property("user_id").equal(req.user_id)
        )
        results = await self.client.collections.get("UserCollection").query.fetch_objects(
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

    ### moved here TODO: fix reference from rest of the code
    async def fetch_all_collections(self, userId: str) -> schemas.GetCollectionsResponse:
        """
        Retrieves all collections for given user
        """
        # filter collections by user
        filters = (
            Filter.by_property("user_id").equal(userId)
        )
        results = await self.client.collections.get("UserCollection").query.fetch_objects(
            filters=filters
        )
        logging.info(f"User Id: {userId}\nRaw results: {results}")
        collections = []
        collections_respone = []
        if results.objects is not None:
            if len(results.objects) > 0:
                collections = results.objects
                # map collection data to expected response format
                for o in collections:
                    collections_respone.append(
                        {'id': str(o.uuid), 'name': o.properties['name'], 'user_id': o.properties.get('user_id')})

        return {"collections": collections_respone, "userId": userId}   

    ### moved here TODO: fix reference from rest of the code
    async def remove_tags(self, chosenTagUUIDs: schemas.GetTaggedChunksReq)->schemas.RemoveTagsResponse:
        """
        Removes tags by:
         - remove all cross-references from Chunks
         - remove the Tag object itself
        """
        try:
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
                        link_on="automaticTag",
                        return_properties=[]
                    )
                )

                tagsToRemove = set(chosenTagUUIDs.tag_uuids)
                tagsToRemove = [str(tagID) for tagID in tagsToRemove]

                # replace hasTags with remaining refs
                for obj in res.objects:
                    refs = obj.references or {}
                    current = refs.get("automaticTag")
                    currentIDs = [str(r.uuid) for r in (current.objects if current else [])]
                    remaining = list(filter(lambda tid: tid not in tagsToRemove, currentIDs))
                    logging.info(f"Replacing Current{currentIDs} \nRemaning{remaining}")
                    logging.info(f"To remove {tagsToRemove}")
                    if len(remaining) != len(currentIDs):
                        logging.info(f"Replacing {currentIDs} {remaining}")
                        await chunks.data.reference_replace(
                            from_uuid=obj.uuid,
                            from_property="automaticTag",
                            to=remaining
                        )
                    check = await chunks.query.fetch_object_by_id(
                        obj.uuid,
                        return_references=[QueryReference(link_on="automaticTag", return_properties=[])]
                    )
                    got = [str(r.uuid) for r in (check.references.get("automaticTag").objects if check.references and check.references.get("hasTags") else [])]
                    logging.info(f"after: {got}")
                logging.info("deleted references from chunks to tags")

            # remove the Tag objects itself
            result = await tag_collection.data.delete_many(
                where=Filter.by_id().contains_any(tagsToRemove)
            )
            logging.info(result)

            return {"successful": True}
        except Exception as e:
            logging.error(f"{e}")
            return {"successful": False}
    
    ### moved here 
    # TODO rename to remove_tag_refs
    # TODO fix reference from rest of the code
    # TODO make it not only automatic but select which reference type should be removed
    async def remove_automatic_tags(self, chosenTagUUIDs: schemas.GetTaggedChunksReq)->schemas.RemoveTagsResponse:
        """
        Removes automatic tags
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
                        link_on="automaticTag",
                        return_properties=[]
                    )
                )

                tagsToRemove = set(chosenTagUUIDs.tag_uuids)
                tagsToRemove = [str(tagID) for tagID in tagsToRemove]

                # replace hasTags with remaining refs
                for obj in res.objects:
                    refs = obj.references or {}
                    current = refs.get("automaticTag")
                    currentIDs = [str(r.uuid) for r in (current.objects if current else [])]
                    remaining = list(filter(lambda tid: tid not in tagsToRemove, currentIDs))
                    logging.info(f"Replacing Current{currentIDs} \nRemaning{remaining}")
                    logging.info(f"To remove {tagsToRemove}")
                    if len(remaining) != len(currentIDs):
                        logging.info(f"Replacing {currentIDs} {remaining}")
                        await chunks.data.reference_replace(
                            from_uuid=obj.uuid,
                            from_property="automaticTag",
                            to=remaining
                        )
                    check = await chunks.query.fetch_object_by_id(
                        obj.uuid,
                        return_references=[QueryReference(link_on="automaticTag", return_properties=[])]
                    )
                    got = [str(r.uuid) for r in (check.references.get("automaticTag").objects if check.references and check.references.get("hasTags") else [])]
                    logging.info(f"after: {got}")
                logging.info("deleted references from chunks to tags")

            return {"successful": True}
        except Exception as e:
            logging.error(f"{e}")
            return {"successful": False}