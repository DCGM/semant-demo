## New functions
Functions to add to the weaviate search:
```
    def fetch_chunks(filters):
        """
        Fetches chunks with filters - tag, user-collection
        """
        # TODO use instead of:
        # fetch chunks from specific collection (currently used in get_tagged_chunks_paged, get_collection_chunks_paged)
        # fetch chunks by tags (currently used in filterChunksByTags)
        pass

    def fetch_tags(filters=None, ids=None):
        """
        Fetches tag collection
        - with specific name OR
        - by list of uuids OR 
        - without filter return all tags
        """
        # TODO use instead of:
        # with specific name (current add_or_get_tag) OR by list of uuids (current get_tagged_chunks_paged) OR without filter return all tags (current get_all_tags)
        pass

    def create_tag():
        """
        Adds new tag to tag-collection. Use fetch_tags.
        """
        # TODO like current add_or_get_tag, but use fetch_tags
        pass

    def create_reference(object, property_name, target_id):
        """
        Creates reference from wevaiate object to other object defined by id
        """
        pass

    def remove_reference(object, reference_to_remove): 
     """
     Removes reference between objects
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
    ### moved here TODO: fix reference from rest of the code
    async def add_collection(self, req: schemas.UserCollectionReqTemplate) -> str:
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
        ...

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

            ...
    
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
            ...
```