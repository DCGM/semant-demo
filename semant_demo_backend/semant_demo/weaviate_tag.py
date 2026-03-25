import logging
import weaviate
from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter

from semant_demo import schemas
from weaviate.classes.query import QueryReference
from .config import config

from langchain_core.prompts import ChatPromptTemplate
from semant_demo.tagging.llm_caller import OllamaProxyRunnable
from langchain_openai import ChatOpenAI

import semant_demo.tagging.configs.prompt_templates as tagging_templates
from semant_demo.tagging.sql_utils import update_task_status

import logging
import re
import os

from weaviate.collections.classes.grpc import QueryReference

from .weaviate_search import WeaviateSearch

PAGE_LIMIT = 1000

class WeaviateSearchAndTag(WeaviateSearch):
    def __init__(self, client: WeaviateAsyncClient):
        super().__init__(client)  # sets self.client and self.chunk_col
        self.tag_template = tagging_templates.templates["Basic"]

    async def get_tagged_chunks_paged(self, getChunksReq: schemas.GetTaggedChunksReq) -> schemas.GetTaggedChunksResponse:
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
            limit = PAGE_LIMIT
            offset = 0
            filters = Filter.by_id().contains_any([str(uuid) for uuid in getChunksReq.tag_uuids])

            results = []
            while True:
                results_partial = await tag_collection.query.fetch_objects(
                        limit=limit,
                        offset=offset,
                        filters=filters
                    )
                results.extend(results_partial.objects)
                # when no objects returned finish cycle - cycled through whole db
                if not results_partial.objects:
                    break
                offset += limit # calculate new offset for next iteration
            logging.info(f"Results: {results}")
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
                offset = 0
                while True:
                    collection_name = "Chunks"
                    logging.info(f"collection name: {collection_name}")
                    # get all chunks
                    chunk_results = await self.client.collections.get(collection_name).query.fetch_objects(
                        limit=limit,
                        offset=offset,
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
                        ],
                        filters=filters
                    )
                    # when no objects returned finish cycle
                    if not chunk_results.objects:
                        break
                    reference_src = getChunksReq.tag_type.value + "Tag"  # ["automaticTag", "positiveTag", "negativeTag"]
                    logging.info(f"Source selected: {reference_src}")
                    for chunk_obj in chunk_results.objects:
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
                    offset += limit # calculate new offset for next iteration
                    # process the filtered chunks to send them to frontend
                    logging.info(f"Chunks and tags info: {chunk_lst_with_tags}")
            except Exception as e:
                #pass
                logging.error(f"Tags in Chunks error: {e}")
                #return {'chunks_with_tags': []}
            return {"chunks_with_tags": chunk_lst_with_tags}
        except Exception as e:
            logging.error(f"No tags assigned yet. {e}")
            return {'chunks_with_tags': []}
    
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
            # iterate over all chunks, retrieve text chunks and corresponding tags
            try:
                collection_name = "Chunks"
                logging.info(f"collection name: {collection_name}")
                reference_src = getChunksReq.tag_type.value + "Tag"  # ["automaticTag", "positiveTag", "negativeTag"]
                logging.info(f"Source selected: {reference_src}")
                weaviate_objects = self.client.collections.get("Chunks")
                async for chunk_obj in weaviate_objects.iterator(return_properties=["text"], return_references=[ QueryReference(link_on="automaticTag",return_properties=[] ), QueryReference(link_on="positiveTag",return_properties=[] ),QueryReference(link_on="negativeTag",return_properties=[] )]):
                    #for chunk_obj in chunk_results.objects:
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

    async def get_collection_chunks_paged(self, collectionId: str, ) ->schemas.GetCollectionChunksResponse:
        """
        Get all chunks belonging to collection with collectionId
        get collection object, in that collection search for chunks that refer to the
        collection and return chunk texts
        """
        try:
            chunk_lst_with_tags = []
            chunks_collection = self.client.collections.use("Chunks")

            limit = PAGE_LIMIT
            offset = 0
            # prepare filter for collection ID
            filters = Filter.by_ref("userCollection").by_id().equal(collectionId)
            # iterate over all chunks find the reference to the user collection
            chunks = await self._fetch_chunks(filters=filters)
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
        
    async def tag_chunks_with_llm_paged(self, tag_request: schemas.TaggingTaskReqTemplate, task_id: str, session=None) -> schemas.TagResponse:
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
                prompt = ChatPromptTemplate.from_template(self.tag_template)
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
            # filter to tag just chunks in selected user collection
            filters =(
                Filter.by_ref(link_on="userCollection").by_property("name").equal(collection_name)
            )
            weaviate_objects = self.client.collections.get("Chunks")

            tag_uuid = await self.add_or_get_tag(tag_request) # prepare tag in weaviate

            final_results = []
            final_results_filtered = []
            limit = PAGE_LIMIT
            offset = 0
            positive_responses = re.compile("^(True|Ano|Áno)", re.IGNORECASE) # prepare regex for check if the text is tagged be llm
            while True:
                # query weaviate db for chunks of chosen collection
                query = weaviate_objects.query.fetch_objects(
                    limit=limit,
                    offset=offset,
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
                    limit=limit,
                    offset=offset,
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

                if not results.objects:
                    break

                final_results.extend(results.objects)
                final_results_filtered.extend(resultsFiltered.objects)
                offset += limit

                
            # collect the UUIDs from the filtered results
            if final_results_filtered:
                filtered_ids = {obj.uuid for obj in final_results_filtered}

                # filter main results to exclude objects whose id is in filtered_ids
                final_results = [obj for obj in final_results if obj.uuid not in filtered_ids]

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
                    logging.error(f"Error in storing result to weaviate: {e}")

            return {'texts': texts, 'tags': tags}

        except Exception as e:
            logging.error(f"Error fetching texts from collection: {e}")
            return {}
        
    async def tag_chunks_with_llm(self, tag_request: schemas.TaggingTaskReqTemplate, task_id: str, session=None) -> schemas.TagResponse:
        """
        Assigns automatic tags to chunks
        Uses iterator
        """
        try:
            # load config data
            # set model from config
            config_model_name = tag_request.task_config.params.model_name

            # load prompt template from the config
            if tag_request.task_config.prompt_template is not None:
                prompt = ChatPromptTemplate.from_template(tag_request.task_config.prompt_template)
            else:
                prompt = ChatPromptTemplate.from_template(self.tag_template)
            # select API
            if tag_request.task_config.params.model_type == schemas.APIType.openai:
                api_key = os.getenv("OPENAI_API_KEY", "")
                #logging.info("API KEY: " + api_key)
                model = ChatOpenAI(
                    model = config_model_name if config_model_name else config.OPENAI_MODEL,
                    api_key = api_key,
                    temperature = tag_request.task_config.params.temperature
                )
            elif tag_request.task_config.params.model_type == schemas.APIType.google:
                pass
            else: # default ollama
                model = OllamaProxyRunnable()
                #logging.info(f"MODEL NAME FROM CONFIG: {tag_request.task_config.params.model_name}")
                #logging.info(f"Whole config passed: {tag_request.task_config}")
                model.set_model(config_model_name)
            # prepare chain
            chain = prompt | model

            # get the collection
            collection_name = tag_request.collection_name
            logging.info(f"Collection name: {collection_name}")
            weaviate_objects = self.client.collections.get("Chunks")

            tag_uuid = await self.add_or_get_tag(tag_request) # prepare tag in weaviate

            texts = []
            tags = []
            tag_processing_data = []

            filters =(
                Filter.by_ref(link_on="userCollection").by_property("name").equal(collection_name)
            )

            # process with llm and decide if tag belongs to text
            positive_responses = re.compile("^(True|Ano|Áno)", re.IGNORECASE) # prepare regex for check if the text is tagged be llm
            all_texts_count = 0
            processed_count = 0
            async for obj in weaviate_objects.iterator(return_properties=["text"], return_references=[QueryReference(link_on="userCollection"), QueryReference(link_on="automaticTag",return_properties=[] ), QueryReference(link_on="positiveTag",return_properties=[] ),QueryReference(link_on="negativeTag",return_properties=[] )]): 
                logging.debug(f"collection id: {collection_name}") 
                referenced = obj.references.get("userCollection")
                if referenced is None:
                    continue
                
                # referenced is a _CrossReference; its targets are in .objects
                collection_objects = referenced.objects  # list of referenced objects
                for ref_obj in collection_objects:
                    print(ref_obj.properties['name'])
                if any(str(ref_obj.properties['name']) == collection_name for ref_obj in collection_objects):
                    all_texts_count += 1
                        
            async for obj in weaviate_objects.iterator(return_properties=["text"], return_references=[QueryReference(link_on="userCollection"), QueryReference(link_on="automaticTag",return_properties=[] ), QueryReference(link_on="positiveTag",return_properties=[] ),QueryReference(link_on="negativeTag",return_properties=[] )]): 
                logging.debug(f"collection id: {collection_name}") 
                referenced = obj.references.get("userCollection")
                if referenced is None:
                    continue
                
                # referenced is a _CrossReference; its targets are in .objects
                collection_objects = referenced.objects  # list of referenced objects
                if any(str(ref_obj.properties['name']) == collection_name for ref_obj in collection_objects):
                    try:
                        # extract text field from the current object
                        text = obj.properties["text"]

                        # print rendered prompt before sending to model
                        logging.info(f"Rendered Prompt: \n{prompt.format(
                                tag_name=tag_request.tag_name,
                                tag_definition=tag_request.tag_definition,
                                tag_examples=tag_request.tag_examples,
                                content=text
                            )}\n")
                        response = await chain.ainvoke({"tag_name": tag_request.tag_name, "tag_definition": tag_request.tag_definition, "tag_examples": tag_request.tag_examples, "content": text})
                        # process response according to the api type
                        if tag_request.task_config.params.model_type == schemas.APIType.openai:
                            tag = response.content
                        else:
                            tag = response
                        logging.info("Response: "+ tag)
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
                        logging.error(f"Error tagging texts: {e}")

            return {'texts': texts, 'tags': tags}

        except Exception as e:
            logging.error(f"Error fetching texts from collection: {e}")
            return {}

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

    #####################

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