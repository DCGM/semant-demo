## New functions
Functions to add to the weaviate search:
```
    def fetch_chunks(filters: Filter):
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
            WeaviateQueryTimeoutError: Query execution exceeded timeout threshold
            WeaviateNotFoundError: No chunks found matching the filters
            WeaviateSerializationError: Cannot deserialize response from Weaviate
            WeaviateServerError: Weaviate server returned an error
        """
        # TODO use instead of:
        # fetch chunks from specific collection (currently used in get_tagged_chunks_paged, get_collection_chunks_paged)
        # fetch chunks by tags (currently used in filterChunksByTags)
        pass

    def fetch_tags(filters: Filter|None = None, ids=None):
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
        pass

    def create_tag(tag: schemas.TagData, collection_name):
        """
        Adds new tag to tag-collection. Use fetch_tags.

        Args:
            name: schemas.TagData of the tag
            collection_name: Name of the collection this tag belongs to
            
        Returns:
            Created tag object with UUID
            
        Raises:
            WeaviateConnectionError: Cannot connect to Weaviate instance
            WeaviateDataValidationError: Invalid input data (empty name, invalid UUID format, etc.)
            WeaviateDuplicateError: Tag with same name already exists for this user in this collection
            WeaviateSerializationError: Cannot serialize tag data to JSON
            WeaviateServerError: Weaviate server returned an error
        """
        # TODO like current add_or_get_tag, but use fetch_tags
        pass

    def create_reference(src_id, property_name, target_id):
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

    def remove_reference(src_id, reference_to_remove): 
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
```
## Changes description
Based on these changes current tagging logic will be adjusted:
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

## Some functions can stay unchanged:
These functions can be moved to weaviate search, because they contain mostly basic weaviate operations. Slight output changes can be performed not to be reliant on the api schemas.
```
    ### moved to weaviate_search TODO: fix reference from rest of the code
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
        ...

    ### moved to weaviate_search TODO: fix reference from rest of the code
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
        ...

    ### moved to weaviate_search TODO: fix reference from rest of the code
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

            ...
    
    ### moved to weaviate_search 
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
            ...
```

## Exception handling
```
class WeaviateOperationError(Exception):
    """Base exception for all weaviate errors."""
    pass

# Specific exceptions

class WeaviateConnectionError(WeaviateOperationError):
    """
    Raised when unable to connect to Weaviate instance.
    """
    pass

class WeaviateSchemaError(WeaviateOperationError):
    """
    Raised when Weaviate client calls invalid schema.
    
    Causes:
    - Collection schema doesn't exist
    - Collection schema is invalid
    """
    pass

class WeaviateDeleteError(WeaviateOperationError):
    """
    Raised when deletion cannot be performed due to not existing object.
    
    Common causes:
    - Attempting to delete already-deleted object
    """
    pass

class WeaviateDuplicateError(WeaviateOperationError):
    """
    Raised when attempting to create a duplicate that should be unique.
    
    Causes:
    - Creating tag with name that already exists for user
    - Creating collection with duplicate name
    """
    pass

class WeaviateFilterError(WeaviateOperationError):
    """
    Raised when filter specification is invalid.
    
    Common causes:
    - Invalid filter syntax
    - Filtering on non-existent property
    - Invalid operator for property type
    - Malformed Filter object
    """
    pass
 
 
class WeaviateQueryError(WeaviateOperationError):
    """
    Raised when query execution fails.
    
    Common causes:
    - Query timeout
    - Invalid query structure
    - Query syntax error
    """
    pass
 
 
class WeaviateReferenceError(WeaviateOperationError):
    """
    Raised when reference operation fails.
    
    Common causes:
    - Creating reference to non-existent object
    - Invalid reference property
    - Reference already exists
    """
    pass
 
class WeaviateNotFoundError(WeaviateOperationError):
    """
    Raised when requested object/s cannot be found.
    
    Common causes:
    - Query returns no results
    - Object UUID doesn't exist
    - Collection name doesn't exist
    - Tag name doesn't exist
    """
    pass 
 
class WeaviateLimitError(WeaviateOperationError):
    """
    Raised when Weaviate limit is exceeded.
    
    Common causes:
    - Too many requests in short time
    - Batch operation too large
    - Insufficient resources on Weaviate server
    """
    pass
 
class WeaviateServerError(WeaviateOperationError):
    """
    Raised when Weaviate server returns an error.
    
    Common causes:
    - Internal server error (5xx)
    - Unexpected server response
    - Protocol error
    """
    pass
 
 
class WeaviateSerializationError(WeaviateOperationError):
    """
    Raised when serializing/deserializing data fails.
    
    Common causes:
    - Non-JSON-serializable object
    - Invalid response format from server
    - Date/time format mismatch
    """
    pass
 
class WeaviateErrorContext:
    """
    Context manager for unified Weaviate error handling and logging.
    
    Usage:
        with WeaviateErrorContext("fetch_chunks"):
            # Weaviate SDK exceptions will be caught and re-raised as custom exceptions
            pass
    """
    
    def __init__(self, operation_name: str):
        self.operation_name = operation_name
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Implementation would map Weaviate SDK exceptions to custom exceptions
        return False
```