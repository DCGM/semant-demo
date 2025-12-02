import logging
from time import time
import weaviate
import weaviate.collections.classes.internal
from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter

from semant_demo import schemas
from semant_demo.config import Config
from semant_demo.gemma_embedding import get_query_embedding
from weaviate.classes.query import QueryReference
import weaviate.collections.classes.internal
from uuid import UUID
from .ollama_proxy import OllamaProxy
from .config import config
import asyncio

from langchain_core.prompts import ChatPromptTemplate
from langchain.prompts import ChatPromptTemplate
from semant_demo.tagging.llm_caller import OllamaProxyRunnable

import semant_demo.tagging.prompt_templates as tagging_templates
from semant_demo.tagging.sql_utils import update_task_status

import logging
import re

from weaviate.collections.classes.grpc import QueryReference

class WeaviateSearch:
    def __init__(self, client: WeaviateAsyncClient):
        self.client = client
        # collections.get() is synchronous, no await needed
        self.chunk_col = self.client.collections.get("Chunks")
        self.tag_template = tagging_templates.templates["Basic"]

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
                Filter.by_ref(link_on="document").by_property("yearIssued").greater_than(search_request.min_year)
            )
        if search_request.max_year:
            filters.append(
                Filter.by_ref(link_on="document").by_property("yearIssued").less_than(search_request.max_year)
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
            q_vector = await get_query_embedding(search_request.query)

            # Execute hybrid search
            result = await self.chunk_col.query.hybrid(
                query=search_request.query,
                alpha=1,
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
            q_vector = await get_query_embedding(search_request.query)
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

    # TODO remove
    async def add_or_get_tag(self, tag_request: schemas.TagReqTemplate) -> str:
        """
        Create a new tag or return existing tag UUID if it matches
        """
        logging.info("In the add or get tag")
        logging.info(f"The data: {tag_request}")

        # check if tag with same properties already exists
        filters = (
                Filter.by_property("tag_name").equal(tag_request.tag_name) &
                Filter.by_property("tag_shorthand").equal(tag_request.tag_shorthand) &
                Filter.by_property("tag_color").equal(tag_request.tag_color)
        )
        results = await self.client.collections.get("Tag").query.fetch_objects(
            filters=filters
        )
        existing_tags = results.objects

        # check for exact match
        # TODO check examples
        for existing_tag in existing_tags:
            if (existing_tag.properties["tag_name"] == tag_request.tag_name and
                    existing_tag.properties["tag_shorthand"] == tag_request.tag_shorthand and
                    existing_tag.properties["tag_color"] == tag_request.tag_color and
                    existing_tag.properties["tag_pictogram"] == tag_request.tag_pictogram and
                    existing_tag.properties["collection_name"] == tag_request.collection_name and
                    existing_tag.properties["tag_definition"] == tag_request.tag_definition):
                return existing_tag.uuid  # return existing tag UUID

        # if no exact match found then create new tag
        new_tag_uuid = await self.client.collections.get("Tag").data.insert(
            properties={
                "tag_name": tag_request.tag_name,
                "tag_shorthand": tag_request.tag_shorthand,
                "tag_color": tag_request.tag_color,
                "tag_pictogram": tag_request.tag_pictogram,
                "tag_definition": tag_request.tag_definition,
                "tag_examples": tag_request.tag_examples,
                "collection_name": tag_request.collection_name
            }
        )
        return new_tag_uuid

    async def get_all_tags(self):
        """
        Returns all tags from weaviate
        """
        # TODO add collection to Tag class
        tag_objects = await self.client.collections.get("Tag").query.fetch_objects()
        tag_data = []
        for obj in tag_objects.objects:
            tag_data.append({
                'tag_name': obj.properties["tag_name"],
                'tag_shorthand': obj.properties["tag_shorthand"],
                'tag_color': obj.properties["tag_color"],
                'tag_pictogram': obj.properties["tag_pictogram"],
                'tag_definition': obj.properties["tag_definition"],
                'tag_examples': obj.properties["tag_examples"],
                'collection_name': obj.properties["collection_name"],
                'tag_uuid': obj.uuid,
            })
        return tag_data
    
    async def get_tagged_chunks(self, getChunksReq: schemas.GetTaggedChunksReq) -> schemas.GetTaggedChunksResponse:
        """
        Get tag objects from them extract collection names, in these collections
        search for chunks that refer to any of the selected tags and return chunk
        texts and all tags from selected tags that are referenced from the chunk
        """
        try:
            # get all chunks with at least one tag from chosenTagUUIDs list
            # get tags
            tag_collection = self.client.collections.get("Tag")
            chunk_lst_with_tags = []
            filters = Filter.by_id().contains_any([str(uuid) for uuid in getChunksReq.tag_uuids])

            results = await tag_collection.query.fetch_objects(filters=filters)
            logging.info(f"Results: {results}")
            # get different collection names
            collection_names = {obj.properties["collection_name"] for obj in results.objects}
            userCollectionName = next(iter(collection_names))
            logging.info(f"Tag uuids in get_tagged_chunks: {getChunksReq.tag_uuids} {collection_names} {userCollectionName}")
            # go over chunks, retrieve text chunks and corresponding tags
            try:
                collection_name = "Chunks"
                logging.info(f"collection name: {collection_name}")
                # get all chunks
                chunk_results = await self.client.collections.get(collection_name).query.fetch_objects(
                    return_references=[
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
                    ]
                )
                reference_src = getChunksReq.tag_type.value + "Tag"  # ["automaticTag", "positiveTag", "negativeTag"]
                logging.info(f"Source selected: {reference_src}")
                for chunk_obj in chunk_results.objects:
                    referencedTags = chunk_obj.references.get(reference_src) if chunk_obj.references else None
                    chunk_id = str(chunk_obj.uuid)
                    chunk_text = chunk_obj.properties.get('text', '')
                    corresponding_tags = []
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

                # process the filtered chunks to send them to frontend
                logging.info(f"Chunks and tags info: {chunk_lst_with_tags}")
            except Exception as e:
                logging.error(f"Tags in Chunks error: {e}")
                return {'chunks_with_tags': []}
            return {"chunks_with_tags": chunk_lst_with_tags}
        except Exception as e:
            logging.error(f"No tags assigned yet. {e}")
            return {'chunks_with_tags': []}

    async def remove_tags(self, chosenTagUUIDs: schemas.GetTaggedChunksReq) -> schemas.RemoveTagsResponse:
        """
        Removes tags by:
         - remove all cross-references from Chunks
         - remove the Tag object itself
        """
        try:
            # get tags for collection names
            tag_collection = self.client.collections.get("Tag")
            chunk_lst_with_tags = []
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
                    got = [str(r.uuid) for r in (
                        check.references.get("automaticTag").objects if check.references and check.references.get(
                            "hasTags") else [])]
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

    async def remove_automatic_tags(self, chosenTagUUIDs: schemas.GetTaggedChunksReq) -> schemas.RemoveTagsResponse:
        """
        Removes automatic tags
        """
        try:
            # remove all automatic cross-references from Chunks

            # get tags for collection names
            tag_collection = self.client.collections.get("Tag")
            chunk_lst_with_tags = []
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
                    got = [str(r.uuid) for r in (
                        check.references.get("automaticTag").objects if check.references and check.references.get(
                            "hasTags") else [])]
                    logging.info(f"after: {got}")
                logging.info("deleted references from chunks to tags")

            return {"successful": True}
        except Exception as e:
            logging.error(f"{e}")
            return {"successful": False}

    async def filterChunksByTags(self, requestedData: schemas.FilterChunksByTagsRequest):
        """
        Filters chunks by tags - for search results filtration after initial search
        get tag objects, chunk objects,
        then filter the chunks that has positive tags and automatic tags referces to any of
        the selected tags and return the data
        """

        def get_all_refs(refs):
            """
            transform references to a list
            """
            if refs is None:
                return []
            if isinstance(refs, list):
                return refs
            return [refs]  # wrap single reference to a list

        try:
            # get all chunks from the list and filter them by the tag
            filters = [Filter.by_id().contains_any([str(uuid) for uuid in requestedData.chunkIds])]
            if requestedData.positive:
                filters.append(Filter.by_ref("automaticTag").by_id().contains_any(requestedData.tagIds))
            if requestedData.automatic:
                filters.append(Filter.by_ref("positiveTag").by_id().contains_any(requestedData.tagIds))
            combinedFilters = filters[0]
            for f in filters[1:]:
                combinedFilters |= f

            chunk_results = await self.client.collections.get('Chunks').query.fetch_objects(
                filters=combinedFilters,
                return_references=[
                    QueryReference(
                        link_on="automaticTag",  # the reference property
                        return_properties=["uuid", "tag_name"]  # properties from the referenced tags
                    ),
                    QueryReference(
                        link_on="positiveTag",
                        return_properties=["uuid", "tag_name"]
                    ),
                ]
            )

            # helper to extract UUID strings from reference block
            def ref_uuids(ref_block):
                if not ref_block:
                    return []
                return [str(r.uuid) for r in ref_block.objects]

            resultLst = []
            for chunk in chunk_results.objects:
                refs = chunk.references or {}

                auto_ids = ref_uuids(refs.get("automaticTag"))
                pos_ids = ref_uuids(refs.get("positiveTag"))

                requested_ids = requestedData.tagIds

                auto_ids = list(set(auto_ids) & set(requested_ids))
                pos_ids = list(set(pos_ids) & set(requested_ids))
                resultLst.append(
                    {'chunk_id': str(chunk.uuid), 'positive_tags_ids': pos_ids, 'automatic_tags_ids': auto_ids})
            logging.info(f'"chunkTags": {resultLst} ')
            return {"chunkTags": resultLst}
        except Exception as e:
            logging.error(f"Error in chunk filtering: {e}")
            return {"chunkTags": []}

    async def approve_tag(self, data: schemas.ApproveTagReq):
        try:
            user = "default"  # TODO change when users are added
            logging.info(f"Chunk ID: {data.chunkID}, Tag ID: {data.tagID}")
            # get chunk
            chunks = self.client.collections.get("Chunks")

            async def getChunkObj(data):
                obj = await chunks.query.fetch_object_by_id(data.chunkID,
                        return_references=[
                        QueryReference(
                            link_on="automaticTag"
                        ),
                        QueryReference(
                            link_on="positiveTag"
                        ),
                        QueryReference(
                            link_on="negativeTag"
                        )]
                    )
                return obj

            obj = await getChunkObj(data)
            refs = obj.references or {}

            # helper to extract UUID strings from reference block
            def ref_uuids(ref_block):
                if not ref_block:
                    return []
                return [str(r.uuid) for r in ref_block.objects]

            auto_ids = ref_uuids(refs.get("automaticTag"))
            pos_ids = ref_uuids(refs.get("positiveTag"))
            neg_ids = ref_uuids(refs.get("negativeTag"))

            tag_id = str(data.tagID)

            # helper to remove tag from disapproved and automatic tags
            async def removeTagRef(refName, data):
                obj = await getChunkObj(data)
                refs = obj.references or {}
                current = refs.get(refName)
                currentIDs = [str(r.uuid) for r in (current.objects if current else [])]
                remaining = [tid for tid in currentIDs if tid != data.tagID]
                logging.info(f"Replacing Current{currentIDs} \nRemaning{remaining}")
                logging.info(f"To remove {data.tagID}")
                if len(remaining) != len(currentIDs):
                    logging.info(f"Replacing {currentIDs} {remaining}")
                    await chunks.data.reference_replace(
                        from_uuid=obj.uuid,
                        from_property=refName,
                        to=remaining
                    )

            # create the reference for approved tag
            if data.approved:  # positive tags

                updatedTags = sorted(set(pos_ids + [tag_id]))
                await chunks.data.reference_replace(
                    from_uuid=obj.uuid,
                    from_property="positiveTag",
                    to=updatedTags,
                )
                # remove the reference from the negative tags just in case
                await removeTagRef("negativeTag", data)
            else:  # negative tags

                updatedTags = sorted(set(neg_ids + [tag_id]))
                await chunks.data.reference_replace(
                    from_uuid=obj.uuid,
                    from_property="negativeTag",
                    to=updatedTags,
                )
                # remove the reference from the positive tags just in case
                await removeTagRef("positiveTag", data)

            # remove the reference from the automatic tags
            await removeTagRef("automaticTag", data)
            return True
        except Exception as e:
            logging.error(f"Not changed approval state. Error: {e}")
            return False

    async def add_collection(self, req: schemas.UserCollectionReqTemplate) -> str:
        """
        Create user collection (contains chunks user choose)
        """
        logging.info(f"Adding user collection\nUser: {req.user_id}\nCollection name: {req.collection_name}")
        try:
            usercollection_collection = self.client.collections.get("UserCollection")
        except Exception:
            # UserCollection is not in weaviate
            return None

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

    async def fetch_all_collections(self, userId: str) -> schemas.GetCollectionsResponse:
        """
        Retrieves all collections for given user
        """
        try:
            usercollection_collection = self.client.collections.get("UserCollection")
        except Exception:
            # UserCollection is not in weaviate
            return None
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

    async def add_chunk_to_collection(self, req: schemas.Chunk2CollectionReq) -> bool:
        """
        Creates reference between a chunk and a collection
        """
        try:
            logging.info(f"In add_chunk_to_collection Collection and chunk data: {req}")
            chunks = self.client.collections.get("Chunks")

            async def getChunkObj(chunkID):
                obj = await chunks.query.fetch_object_by_id(chunkID,
                                                            return_references=[
                                                                QueryReference(
                                                                    link_on="userCollection"
                                                                )]
                                                            )
                return obj

            obj = await getChunkObj(req.chunkId)
            refs = obj.references or {}

            # helper to extract UUID strings from reference block
            def ref_uuids(ref_block):
                if not ref_block:
                    return []
                return [str(r.uuid) for r in ref_block.objects]

            collection_ids = ref_uuids(refs.get("userCollection"))
            new_collection_id = str(req.collectionId)

            updatedCollectionIds = sorted(set(collection_ids + [new_collection_id]))
            await chunks.data.reference_replace(
                from_uuid=obj.uuid,
                from_property="userCollection",
                to=updatedCollectionIds,
            )

            return False
        except Exception as e:
            logging.info(e)
            return True

    async def get_collection_chunks(self, collectionId: str, ) ->schemas.GetCollectionChunksResponse:
        """
        Get all chunks belonging to collection with collectionId
        get collection object, in that collection search for chunks that refer to the
        collection and return chunk texts
        """
        try:
            chunk_lst_with_tags = []
            chunks_collection = self.client.collections.use("Chunks")
            # iterate over all chunks find the reference to the user collection
            async for chunk_obj in chunks_collection.iterator(return_references=[QueryReference(link_on="userCollection")]):
                logging.debug(f"collection id: {collectionId}")

                referencedCollections = chunk_obj.references.get("userCollection")
                logging.debug(f"{referencedCollections}")
                if referencedCollections: # check if collection is not none
                    logging.debug(f"Referenced collections: {referencedCollections}")
                    for collect_obj in referencedCollections.objects:
                        logging.info(f"Collection id: {collect_obj.uuid}")
                        logging.debug(collect_obj.uuid)
                        logging.info(f"{collect_obj.uuid} vs {collectionId}")
                        if str(collect_obj.uuid) == collectionId:
                            logging.info(f"Collection id matches")
                            chunk_text = chunk_obj.properties.get('text','')
                            chunk_id = str(chunk_obj.uuid)
                            logging.debug(f"chunk {chunk_id} ref: {collectionId}")
                            chunk_lst_with_tags.append({'text_chunk': chunk_text, "chunk_id": chunk_id, "chunk_collection_name": collectionId})
                else:
                    logging.info(f"No collection referenced")
                logging.info(f"Chunks and tags info: {chunk_lst_with_tags}")
                # test
                print(f"Test - Chunks in collection {collectionId}: {chunk_lst_with_tags}")
                assert all(item['chunk_collection_name'] == collectionId for item in chunk_lst_with_tags), \
                    "Some chunks do not match the collection ID"
            return {"chunks_of_collection": chunk_lst_with_tags}
        except Exception as e:
            logging.error(f"Error: {e}")
            return {'chunks_of_collection': []}

    # TODO add collection to Tag class
    async def get_all_tags(self):
        """
        Gets all tags from weaviate and returns data about the tags
        """
        tag_objects = await self.client.collections.get("Tag").query.fetch_objects()
        tag_data = []
        for obj in tag_objects.objects:
            tag_data.append({
                'tag_name': obj.properties["tag_name"],
                'tag_shorthand': obj.properties["tag_shorthand"],
                'tag_color': obj.properties["tag_color"],
                'tag_pictogram': obj.properties["tag_pictogram"],
                'tag_definition': obj.properties["tag_definition"],
                'tag_examples': obj.properties["tag_examples"],
                'collection_name': obj.properties["collection_name"],
                'tag_uuid': obj.uuid,
            })
        return tag_data


    async def add_or_get_tag(self, tag_request: schemas.TagReqTemplate) -> str:
        """
        Create a new tag or return existing tag UUID if it matches
        """
        logging.info("In the add or get tag")
        logging.info(f"The data: {tag_request}")

        # check if tag with same properties already exists
        filters =(
            Filter.by_property("tag_name").equal(tag_request.tag_name) &
            Filter.by_property("tag_shorthand").equal(tag_request.tag_shorthand)&
            Filter.by_property("tag_color").equal(tag_request.tag_color)
        )
        results = await self.client.collections.get("Tag").query.fetch_objects(
            filters=filters
        )
        existing_tags = results.objects

        # check for exact match
        # TODO check examples
        for existing_tag in existing_tags:
            if (existing_tag.properties["tag_name"] == tag_request.tag_name and
                existing_tag.properties["tag_shorthand"] == tag_request.tag_shorthand and
                existing_tag.properties["tag_color"] == tag_request.tag_color and
                existing_tag.properties["tag_pictogram"] == tag_request.tag_pictogram and
                existing_tag.properties["collection_name"] == tag_request.collection_name and
                existing_tag.properties["tag_definition"] == tag_request.tag_definition) :
                return existing_tag.uuid  # return existing tag UUID

        # if no exact match found then create new tag
        new_tag_uuid = await self.client.collections.get("Tag").data.insert(
            properties={
                "tag_name": tag_request.tag_name,
                "tag_shorthand": tag_request.tag_shorthand,
                "tag_color": tag_request.tag_color,
                "tag_pictogram": tag_request.tag_pictogram,
                "tag_definition": tag_request.tag_definition,
                "tag_examples": tag_request.tag_examples,
                "collection_name": tag_request.collection_name
            }
        )
        return new_tag_uuid

    async def get_all_tags(self):
        """
        Returns all tags from weaviate
        """
        #TODO add collection to Tag class
        tag_objects = await self.client.collections.get("Tag").query.fetch_objects()
        tag_data = []
        for obj in tag_objects.objects:
            tag_data.append({
            'tag_name': obj.properties["tag_name"],
            'tag_shorthand': obj.properties["tag_shorthand"],
            'tag_color': obj.properties["tag_color"],
            'tag_pictogram': obj.properties["tag_pictogram"],
            'tag_definition': obj.properties["tag_definition"],
            'tag_examples': obj.properties["tag_examples"],
            'collection_name': obj.properties["collection_name"],
            'tag_uuid': obj.uuid,
            })
        return tag_data

    async def tag_chunks_with_llm(self, tag_request: schemas.TagReqTemplate, task_id: str, session=None) -> schemas.TagResponse:
        """
        Assigns automatic tags to chunks
        """
        try:
            prompt = ChatPromptTemplate.from_template(self.tag_template)
            model = OllamaProxyRunnable()
            chain = prompt | model

            # get the collection
            collection_name = tag_request.collection_name
            logging.info(f"Collection name: {collection_name}")
            # filter to tag just chunks in selected user collection
            filters =(
                Filter.by_ref(link_on="userCollection").by_property("name").equal(collection_name)
            )
            weaviate_objects = self.client.collections.get("Chunks")

            #weaviate_objects = await chunks_collection.query.fetch_objects(
            #    filters=filters
            #)

            tag_uuid = await self.add_or_get_tag(tag_request) # prepare tag in weaviate

            """
            Filtering for reference equal to certain id results in filtering out chunks without refs
            filters= ( 
                    ( Filter.by_ref(link_on="automaticTag").is_none(True) | Filter.by_ref(link_on="automaticTag").by_id().not_equal(tag_uuid) ) &
                    ( Filter.by_ref(link_on="positiveTag").is_none(True) | Filter.by_ref(link_on="positiveTag").by_id().not_equal(tag_uuid) ) &
                    ( Filter.by_ref(link_on="negativeTag").is_none(True) | Filter.by_ref(link_on="negativeTag").by_id().not_equal(tag_uuid) )
                ),
            weaviate doesnt offer is_none/is_empty or similar
            so I chose to filter after fetching all of them and filter them later
            """
            # query weaviate db for chunks of chosen collection
            query = weaviate_objects.query.fetch_objects(
                return_properties=["text"],  # only return the text field
                return_references=[
                    QueryReference(
                    link_on="automaticTag",
                    return_properties=[] # just need uuids
                ),
                    QueryReference(
                        link_on="positiveTag",
                        return_properties=[] # just need uuids
                    ),
                    QueryReference(
                        link_on="negativeTag",
                        return_properties=[] # just need uuids
                    )
                ],
                filters=filters
            )
            queryFiltered = weaviate_objects.query.fetch_objects(
                return_properties=["text"],  # only return the text field
                filters = (
                    Filter.by_ref(link_on="automaticTag").by_id().equal(tag_uuid) |
                    Filter.by_ref(link_on="positiveTag").by_id().equal(tag_uuid) |
                    Filter.by_ref(link_on="negativeTag").by_id().equal(tag_uuid)
                ),
                return_references=[
                    QueryReference(
                    link_on="automaticTag",
                    return_properties=[] # just need uuids
                ),
                    QueryReference(
                        link_on="positiveTag",
                        return_properties=[] # just need uuids
                    ),
                    QueryReference(
                        link_on="negativeTag",
                        return_properties=[] # just need uuids
                    )
                ]
            )
            results = await query
            resultsFiltered = await queryFiltered
            final_results = results.objects
            # collect the UUIDs from the filtered results
            if resultsFiltered.objects:
                filtered_ids = {obj.uuid for obj in resultsFiltered.objects}

                # filter main results to exclude objects whose id is in filtered_ids
                final_results = [obj for obj in results.objects if obj.uuid not in filtered_ids]

            texts = []
            tags = []
            tag_processing_data = []

            # process with llm and decide if tag belongs to text
            positive_responses = re.compile("^(True|Ano|Áno)", re.IGNORECASE) # prepare regex for check if the text is tagged be llm
            logging.info("Past the add ir get tag")
            all_texts_count = len(final_results)
            processed_count = 0
            for obj in final_results:
                try:
                    # extract text field from the current object
                    text = obj.properties["text"]
                    tag = await chain.ainvoke({"tag_name": tag_request.tag_name, "tag_definition": tag_request.tag_definition, "tag_examples": tag_request.tag_examples, "content": text})

                    # store in weaviate (upload positive tag instances to weaviate)
                    if positive_responses.search(tag): # if the llm response is positive then store the tag data
                        # test if the reference to the tag exists
                        references = obj.references.get("automaticTag") if obj.references else None
                        # if there are no references or there is not any reference to the wanted tag add the new reference
                        if not references or not getattr(references, "objects", None) or not (any(str(tag_obj.uuid) == str(tag_uuid) for tag_obj in references.objects)):
                            # add the new tag data
                            await weaviate_objects.data.reference_add(
                                from_uuid = obj.uuid,
                                from_property="automaticTag",
                                to=tag_uuid
                            )
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
                    pass # TODO revert changes

            # uncomment to test if the references are correct
            #cfg = await self.client.collections.get("Chunks").config.get()
            #logging.info(f"Chunk refs: {[r.name for r in cfg.references]}")

            # uncomment to test if storing works
            #weaviate_objects_test = self.client.collections.get(collection_name)

            #test_results = await weaviate_objects_test.query.fetch_objects(
            #        return_properties=["text"],
            #        return_references=QueryReference(
            #            link_on="automaticTag",
            #            return_properties=["tag_name", "tag_shorthand", "tag_color", "tag_pictogram", "tag_definition", "tag_examples"]
            #        ),
            #        limit=100,
            #    )

            #for obj in test_results.objects:
            #        logging.info(f"Chunk {obj.uuid} | text: {obj.properties.get('text','')[:80]}...")

                    # references in chunks
            #        tags_ref = obj.references.get("automaticTag") if obj.references else None
            #        if tags_ref and getattr(tags_ref, "objects", None):
            #            for tag_obj in tags_ref.objects:
            #                logging.info(
            #                    f"Tag {tag_obj.uuid} | "
            #                    f"name={tag_obj.properties.get('tag_name')} | "
            #                    f"short={tag_obj.properties.get('tag_shorthand')} | "
            #                    f"color={tag_obj.properties.get('tag_color')} | "
            #                    f"pic={tag_obj.properties.get('tag_pictogram')} | "
            #                    f"def={tag_obj.properties.get('tag_definition')} | "
            #                    f"examples={str(tag_obj.properties.get('tag_examples'))}"
            #                )
            #        else:
            #            logging.info("No tags found")
            return {'texts': texts, 'tags': tags}

        except Exception as e:
            logging.error(f"Error fetching texts from collection: {e}")
            return {}

    async def remove_tags(self, chosenTagUUIDs: schemas.GetTaggedChunksReq)->schemas.RemoveTagsResponse:
        """
        Removes tags by:
         - remove all cross-references from Chunks
         - remove the Tag object itself
        """
        try:
            # get tags for collection names
            tag_collection = self.client.collections.get("Tag")
            chunk_lst_with_tags = []
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

    async def remove_automatic_tags(self, chosenTagUUIDs: schemas.GetTaggedChunksReq)->schemas.RemoveTagsResponse:
        """
        Removes automatic tags
        """
        try:
            # remove all automatic cross-references from Chunks

            # get tags for collection names
            tag_collection = self.client.collections.get("Tag")
            chunk_lst_with_tags = []
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

    async def filterChunksByTags(self, requestedData: schemas.FilterChunksByTagsRequest ):
        """
        Filters chunks by tags - for search results filtration after initial search
        get tag objects, chunk objects,
        then filter the chunks that has positive tags and automatic tags referces to any of
        the selected tags and return the data
        """
        def get_all_refs(refs):
            """
            transform references to a list
            """
            if refs is None:
                return []
            if isinstance(refs, list):
                return refs
            return [refs]  # wrap single reference to a list
        try:
            # get all chunks from the list and filter them by the tag
            filters = [Filter.by_id().contains_any([str(uuid) for uuid in requestedData.chunkIds])]
            if requestedData.positive:
                filters.append(Filter.by_ref("automaticTag").by_id().contains_any(requestedData.tagIds))
            if requestedData.automatic:
                filters.append(Filter.by_ref("positiveTag").by_id().contains_any(requestedData.tagIds))
            combinedFilters = filters[0]
            for f in filters[1:]:
                combinedFilters |= f

            chunk_results = await self.client.collections.get('Chunks').query.fetch_objects(
                filters=combinedFilters,
                return_references=[
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

            # helper to extract UUID strings from reference block
            def ref_uuids(ref_block):
                if not ref_block:
                    return []
                return [str(r.uuid) for r in ref_block.objects]

            resultLst = []
            for chunk in chunk_results.objects:
                refs = chunk.references or {}

                auto_ids = ref_uuids(refs.get("automaticTag"))
                pos_ids = ref_uuids(refs.get("positiveTag"))

                requested_ids = requestedData.tagIds

                auto_ids = list(set(auto_ids) & set(requested_ids))
                pos_ids = list(set(pos_ids) & set(requested_ids))
                resultLst.append({'chunk_id': str(chunk.uuid), 'positive_tags_ids': pos_ids, 'automatic_tags_ids': auto_ids})
            logging.info(f'"chunkTags": {resultLst} ')
            return { "chunkTags": resultLst }
        except Exception as e:
            logging.error(f"Error in chunk filtering: {e}")
            return { "chunkTags": [] }

    async def approve_tag(self, data: schemas.ApproveTagReq):
        try:
            user = "default" # TODO change when users are added
            logging.info(f"Chunk ID: {data.chunkID}, Tag ID: {data.tagID}")
            # get chunk
            chunks = self.client.collections.get("Chunks")
            async def getChunkObj(data):
                obj = await chunks.query.fetch_object_by_id(data.chunkID,
                    return_references=[
                    QueryReference(
                        link_on="automaticTag"
                    ),
                    QueryReference(
                        link_on="positiveTag"
                    ),
                    QueryReference(
                        link_on="negativeTag"
                    )]
                )
                return obj

            obj = await getChunkObj(data)
            refs = obj.references or {}

            # helper to extract UUID strings from reference block
            def ref_uuids(ref_block):
                if not ref_block:
                    return []
                return [str(r.uuid) for r in ref_block.objects]

            auto_ids = ref_uuids(refs.get("automaticTag"))
            pos_ids = ref_uuids(refs.get("positiveTag"))
            neg_ids = ref_uuids(refs.get("negativeTag"))

            tag_id = str(data.tagID)

            # helper to remove tag from disapproved and automatic tags
            async def removeTagRef(refName, data):
                obj = await getChunkObj(data)
                refs = obj.references or {}
                current = refs.get(refName)
                currentIDs = [str(r.uuid) for r in (current.objects if current else [])]
                remaining = [tid for tid in currentIDs if tid != data.tagID]
                logging.info(f"Replacing Current{currentIDs} \nRemaning{remaining}")
                logging.info(f"To remove {data.tagID}")
                if len(remaining) != len(currentIDs):
                    logging.info(f"Replacing {currentIDs} {remaining}")
                    await chunks.data.reference_replace(
                        from_uuid=obj.uuid,
                        from_property=refName,
                        to=remaining
                    )

            # create the reference for approved tag
            if data.approved: # positive tags

                updatedTags = sorted(set(pos_ids + [tag_id]))
                await chunks.data.reference_replace(
                    from_uuid=obj.uuid,
                    from_property="positiveTag",
                    to=updatedTags,
                )
                # remove the reference from the negative tags just in case
                await removeTagRef("negativeTag", data)
            else: # negative tags

                updatedTags = sorted(set(neg_ids + [tag_id]))
                await chunks.data.reference_replace(
                    from_uuid=obj.uuid,
                    from_property="negativeTag",
                    to=updatedTags,
                )
                # remove the reference from the positive tags just in case
                await removeTagRef("positiveTag", data)

            # remove the reference from the automatic tags
            await removeTagRef("automaticTag", data)
            return True
        except Exception as e:
            logging.error(f"Not changed approval state. Error: {e}")
            return False

    async def add_chunk_to_collection(self, req: schemas.Chunk2CollectionReq) -> bool:
        """
        Creates reference between a chunk and a collection
        """
        try:
            chunks = self.client.collections.get("Chunks")
            async def getChunkObj(chunkID):
                obj = await chunks.query.fetch_object_by_id(chunkID,
                    return_references=[
                    QueryReference(
                        link_on="userCollection"
                    )]
                )
                return obj

            obj = await getChunkObj(req.chunkId)
            refs = obj.references or {}

            # helper to extract UUID strings from reference block
            def ref_uuids(ref_block):
                if not ref_block:
                    return []
                return [str(r.uuid) for r in ref_block.objects]

            collection_ids = ref_uuids(refs.get("userCollection"))
            new_collection_id = str(req.collectionId)

            updatedCollectionIds = sorted(set(collection_ids + [new_collection_id]))
            await chunks.data.reference_replace(
                    from_uuid=obj.uuid,
                    from_property="userCollection",
                    to=updatedCollectionIds,
            )

            # test
            updated_obj = await getChunkObj(req.chunkId)
            updated_refs = updated_obj.references or {}
            updated_collection_ids = ref_uuids(updated_refs.get("userCollection"))

            print("Test - References after update:", updated_collection_ids)
            assert new_collection_id in updated_collection_ids, "Reference was not added properly"
            print("Test passed: reference successfully updated")

            return False
        except Exception as e:
            logging.info(e)
            return True

    #TODO add collection to Tag class
    async def get_all_tags(self):
        """
        Gets all tags from weaviate and returns data about the tags
        """
        tag_objects = await self.client.collections.get("Tag").query.fetch_objects()
        tag_data = []
        for obj in tag_objects.objects:
            tag_data.append({
            'tag_name': obj.properties["tag_name"],
            'tag_shorthand': obj.properties["tag_shorthand"],
            'tag_color': obj.properties["tag_color"],
            'tag_pictogram': obj.properties["tag_pictogram"],
            'tag_definition': obj.properties["tag_definition"],
            'tag_examples': obj.properties["tag_examples"],
            'collection_name': obj.properties["collection_name"],
            'tag_uuid': obj.uuid,
            })
        return tag_data
