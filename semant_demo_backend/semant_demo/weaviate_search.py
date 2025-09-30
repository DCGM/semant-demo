import logging
import weaviate
from time import time
from weaviate import use_async_with_custom, WeaviateAsyncClient
from weaviate.classes.query import Filter
from semant_demo import schemas
from semant_demo.config import Config
from semant_demo.gemma_embedding import get_query_embedding
from weaviate.classes.query import QueryReference
import weaviate.collections.classes.internal
from weaviate.collections.classes.filters import Filter
from weaviate.classes.query import QueryReference
from uuid import UUID
from .ollama_proxy import OllamaProxy
from .config import config
import asyncio

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM
from langchain_core.documents import Document
from langchain.prompts import ChatPromptTemplate
from langchain.schema.runnable import Runnable

from langchain_core.prompt_values import PromptValue
from langchain_core.messages import BaseMessage

import logging
import re
import json

from sqlalchemy import update
from sqlalchemy import exc
from semant_demo.schemas import Task, TasksBase

import time as timeSleep

from weaviate.collections.classes.grpc import QueryReference

class DBError(Exception):
    pass

class OllamaProxyRunnable(Runnable):
    def __init__(self, proxy, model_name):
        self.proxy = proxy
        self.model_name = model_name

    async def ainvoke(self, input, config=None):
        # Handle PromptValue (e.g. from ChatPromptTemplate)
        if isinstance(input, PromptValue):
            input = input.to_string()

        # Handle list of messages
        elif isinstance(input, list) and all(isinstance(m, BaseMessage) for m in input):
            input = "\n".join([m.content for m in input])

        # Now input is guaranteed to be a string
        response = await self.proxy.call_ollama(self.model_name, input)
        return response

    def invoke(self, input, config=None):
        return asyncio.run(self.ainvoke(input, config))

class WeaviateSearch:
    def __init__(self, client: WeaviateAsyncClient):
        self.client = client
        self.ollama_proxy = OllamaProxy(config.OLLAMA_URLS)
        self.ollama_model = config.OLLAMA_MODEL
        # collections.get() is synchronous, no await needed
        self.chunk_col = self.client.collections.get("Chunks")
        self.title_prompt = "Generate a title in Czech from the following text: \"{text}\" \n " \
                "The title should be relevant for this search query: \"{query}\" \n" \
                "If the the text is not relavant, write \"N/A\" \n"
        self.summary_prompt = "Generate a sort summary in Czech from the following text: \"{text}\" \n " \
                "The summary should be in a list of concise facts extracted from the text which are relevant for this search query: \"{query}\""           
        self.tag_template = "You are given a document, decide whether tag \"{tag_name}\" belongs to the document. \n " \
                "The tag's definition is: \"{tag_definition}\". \n " \
                "Here are examples of texts belonging to the tag: {tag_examples}. \n " \
                "Output Ano if the tag belongs or Ne if it does not belong to the document, do not output anything else. \n " \
                "Be benevolent and output True if there is some connection between tag and the text of the document. \n " \
                "Document: \n " \
                "{content}"
                #"Do not output any explanation just True or False. \n " \
                #"Consider meaning of the tag. \n " \
                #"Ignore exact punctuation or minor wording differences. Decide based on the meaning of the tag. \n " \
        
#"Do not tag document when tag is not associated with it, but tag document if the tag is associated with the content. \n " \

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

    async def _process_with_llm(self, search_results: list[schemas.TextChunkWithDocument], search_request: schemas.SearchRequest) -> list[schemas.TextChunkWithDocument]:

        title_prompt_template = search_request.search_title_prompt if search_request.search_title_prompt else self.title_prompt
        summary_prompt_template = search_request.search_summary_prompt if search_request.search_summary_prompt else self.summary_prompt

        if search_request.search_title_generate:
            title_responses = [self.ollama_proxy.call_ollama(
                self.ollama_model,
                title_prompt_template.format(text=chunk.text, query=search_request.query)
            ) for chunk in search_results]
            title_responses = await asyncio.gather(*title_responses)
            for search_result, generated_title in zip(search_results, title_responses):
                search_result.query_title = generated_title

        if search_request.search_summary_generate:
            summary_responses = [self.ollama_proxy.call_ollama(
                self.ollama_model,
                summary_prompt_template.format(text=chunk.text, query=search_request.query)
            ) for chunk in search_results]
            summary_responses = await asyncio.gather(*summary_responses)
            for search_result, generated_summary in zip(search_results, summary_responses):
                search_result.query_summary = generated_summary

        return search_results
  

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
            #filters = [Filter.by_id().contains_any([str(uuid) for uuid in search_request.chunkIds])]
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
                return_references=[QueryReference(link_on="document", return_properties=None),
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
            print("HERE in text search")
            result = await self.chunk_col.query.bm25(
                query=search_request.query,
                limit=search_request.limit,
                filters=combined_filter,
                return_references=[QueryReference(link_on="document", return_properties=None),
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
                return_references=[QueryReference(link_on="document", return_properties=None),
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

        print("RESULT is:")
        print(result)

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
            print(chunk)
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

        # Process with LLM if needed
        if search_request.search_title_generate or search_request.search_summary_generate:
            results = await self._process_with_llm(results, search_request)

        response = schemas.SearchResponse(
            results=results,
            search_request=search_request,
            time_spent=search_time,
            search_log=[log_entry],
            tags_result=tags_result,
        )
        logging.info(f'Response created in {time() - t1:.2f} seconds')
        return response

    async def add_or_get_tag(self, tag_request: schemas.TagReqTemplate) -> str:
        """
        Create a new tag or return existing tag UUID if it matches
        """
        logging.info("In the add or get tag")
        try:
            tag_collection = self.client.collections.get("Tag")
        except Exception:
            # collection does not exist so create it
            tag_collection = await self.client.collections.create(
                name="Tag",
                properties=[
                    {"name": "tag_name", "dataType": "string"},
                    {"name": "tag_shorthand", "dataType": "string"},
                    {"name": "tag_color", "dataType": "string"},
                    {"name": "tag_pictogram", "dataType": "string"},
                    {"name": "tag_definition", "dataType": "string"},
                    {"name": "tag_examples", "dataType": "string[]"},
                    {"name": "collection_name", "dataType": "string"},
                ]
            )
        
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
    
    #TODO add collection to Tag class
    async def get_all_tags(self):
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

    async def tag(self, tag_request: schemas.TagReqTemplate, task_id: str, session=None) -> schemas.TagResponse:
        # tags chunks
        try:
            prompt = ChatPromptTemplate.from_template(self.tag_template)
            model = OllamaProxyRunnable(self.ollama_proxy, self.ollama_model)
            chain = prompt | model

            # get the collection
            collection_name = tag_request.collection_name
            weaviate_objects = self.client.collections.get(collection_name)
            tag_uuid = await self.add_or_get_tag(tag_request) # prepare tag in weaviate

            """
            filtering for reference equal to certain id results in filtering out chunks without refs
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
                ]
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

            """
            def safe_references(obj, key: str):
                ref_block = obj.references.get(key) if obj.references else None
                return ref_block.objects if ref_block else []
            filtered_results = [
                obj for obj in results.objects
                if not any(ref.uuid == tag_uuid for ref in safe_references(obj, "automaticTag"))
                and not any(ref.uuid == tag_uuid for ref in safe_references(obj, "positiveTag"))
                and not any(ref.uuid == tag_uuid for ref in safe_references(obj, "negativeTag"))
            ]
            """

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
                    # TODO store progress in SQL db
                    processed_count += 1 # increase number of processed chunks
                    await update_task_status(task_id, "RUNNING", result={}, collection_name=tag_request.collection_name, session=session, all_texts_count=all_texts_count, processed_count=processed_count, tag_id=tag_uuid, tag_processing_data=tag_processing_data)
                    logging.info("After update")
                    #await timeSleep.sleep(2)
                except Exception as e:
                    pass # TODO revert changes
                
            # check if the references are correct TODO remove this
            cfg = await self.client.collections.get("Chunks").config.get()
            logging.info(f"Chunk refs: {[r.name for r in cfg.references]}")

            # check stored TODO remove this part
            weaviate_objects_test = self.client.collections.get(collection_name)

            test_results = await weaviate_objects_test.query.fetch_objects(
                    return_properties=["text"],
                    return_references=QueryReference(
                        link_on="automaticTag",
                        return_properties=["tag_name", "tag_shorthand", "tag_color", "tag_pictogram", "tag_definition", "tag_examples"]
                    ),
                    limit=100,
                )

            for obj in test_results.objects:
                    logging.info(f"Chunk {obj.uuid} | text: {obj.properties.get('text','')[:80]}...")

                    # references in chunks
                    tags_ref = obj.references.get("automaticTag") if obj.references else None
                    if tags_ref and getattr(tags_ref, "objects", None):
                        for tag_obj in tags_ref.objects:
                            logging.info(
                                f"Tag {tag_obj.uuid} | "
                                f"name={tag_obj.properties.get('tag_name')} | "
                                f"short={tag_obj.properties.get('tag_shorthand')} | "
                                f"color={tag_obj.properties.get('tag_color')} | "
                                f"pic={tag_obj.properties.get('tag_pictogram')} | "
                                f"def={tag_obj.properties.get('tag_definition')} | "
                                f"examples={str(tag_obj.properties.get('tag_examples'))}"
                            )
                    else:
                        logging.info("No tags found")
            return {'texts': texts, 'tags': tags}
            
        except Exception as e:
            print(f"Error fetching texts from collection {collection_name}: {e}")
            return {}
        
    async def get_tagged_chunks(self, getChunksReq: schemas.GetTaggedChunksReq)->schemas.GetTaggedChunksResponse:
        """
        get tag objects from them extract collection names, in these collections 
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
            ChunkTagApprovalCollection = self.client.collections.get("ChunkTagApproval")

            # iterate over the collections and retrieve text chunks and corresponding tags
            for collection_name in collection_names:
                # get all chunks
                chunk_results = await self.client.collections.get(collection_name).query.fetch_objects(
                    return_references=[
                        QueryReference(
                            link_on="automaticTag",                 # the reference property
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
                reference_src = getChunksReq.tag_type.value + "Tag" #["automaticTag", "positiveTag", "negativeTag"]
                logging.info(f"Source selected: {reference_src}")
                for chunk_obj in chunk_results.objects:
                        referencedTags = chunk_obj.references.get(reference_src) if chunk_obj.references else None
                        chunk_id = str(chunk_obj.uuid)
                        chunk_text = chunk_obj.properties.get('text','')
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
                                chunk_lst_with_tags.append({'tag_uuid': tagID, 'text_chunk': chunk_text, "chunk_id": chunk_id, "chunk_collection_name": collection_name, "tag_type": getChunksReq.tag_type.value })
                                
                """
                            filters = (
                                Filter.by_ref("hasTag").by_id().equal(tagID) &
                                Filter.by_ref("hasChunk").by_id().equal(chunk_id)
                            )
                            
                            chunkTagApproval = await ChunkTagApprovalCollection.query.fetch_objects(
                                filters=filters,
                                return_properties=["approved"]
                            )
                            approved_count = 0
                            disapproved_count = 0
                            try:
                                for chunkTApprovO in chunkTagApproval.objects:
                                    if chunkTApprovO.properties.get('approved') is not None:
                                        if chunkTApprovO.properties.get('approved') == True:
                                            approved_count += 1
                                        else:
                                            disapproved_count += 1
                            except:
                                pass
                            chunk_lst_with_tags.append({'tag_uuid': tagID, 'text_chunk': chunk_text, "chunk_id": chunk_id, "chunk_collection_name": collection_name, "approved_count": approved_count, "disapproved_count": disapproved_count})
                """   
            # process the filtered chunks to send them to frontend
                logging.info(f"Chunks and tags info: {chunk_lst_with_tags}")
            return {"chunks_with_tags": chunk_lst_with_tags}
        except Exception as e:
            logging.error(f"No tags assigned yet. {e}")
            return {'chunks_with_tags': []}

    async def remove_tags(self, chosenTagUUIDs: schemas.GetTaggedChunksReq)->schemas.RemoveTagsResponse:
        try:
            # remove ChunkTagApproval
            # remove all cross-references from Chunks
            # remove the Tag object itself

            # remove ChunkTagApproval
            """
            ChunkTagApprovalCollection = self.client.collections.get("ChunkTagApproval")
            filters = (
                Filter.by_ref("hasTag").by_id().contains_any(chosenTagUUIDs.tag_uuids)
            )
            await ChunkTagApprovalCollection.data.delete_many(where=filters)
            logging.info("deleted ChunkTagApproval objects")
            """
            # remove all cross-references from Chunks

            # get tags for collection names
            tag_collection = self.client.collections.get("Tag")
            chunk_lst_with_tags = []
            filters = Filter.by_id().contains_any([str(uuid) for uuid in chosenTagUUIDs.tag_uuids])
            
            results = await tag_collection.query.fetch_objects(filters=filters)

            # get different collection names
            collection_names = {obj.properties["collection_name"] for obj in results.objects}
            #ChunkTagApprovalCollection = self.client.collections.get("ChunkTagApproval")

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
        try:
            # remove all automatic cross-references from Chunks

            # get tags for collection names
            tag_collection = self.client.collections.get("Tag")
            chunk_lst_with_tags = []
            filters = Filter.by_id().contains_any([str(uuid) for uuid in chosenTagUUIDs.tag_uuids])
            
            results = await tag_collection.query.fetch_objects(filters=filters)

            # get different collection names
            collection_names = {obj.properties["collection_name"] for obj in results.objects}
            #ChunkTagApprovalCollection = self.client.collections.get("ChunkTagApproval")

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
                """                # get tags the chunk reference as positive
                positiveRefs = get_all_refs(chunk.references.get("positiveTag"))
                positiveTags = [t.uuid for t in positiveRefs]
                # get tags the chunk reference as automatic
                automaticRefs = get_all_refs(chunk.references.get("automaticTag"))
                automaticTags = [t.uuid for t in automaticRefs]
                """
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
            #Filter.by_ref("hasTag").by_id().equal(data.tagID)
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

            """
            # remove the reference from the automatic tags
            current = refs.get("automaticTag")
            currentIDs = [str(r.uuid) for r in (current.objects if current else [])]
            remaining = [tid for tid in currentIDs if tid != data.tagID]
            logging.info(f"Replacing Current{currentIDs} \nRemaning{remaining}")
            logging.info(f"To remove {data.tagID}")
            if len(remaining) != len(currentIDs):
                logging.info(f"Replacing {currentIDs} {remaining}")
                await chunks.data.reference_replace(
                    from_uuid=obj.uuid,
                    from_property="automaticTag",
                    to=remaining
                )
            
                # TODO remove (just checks)
                chunks = self.client.collections.get("Chunks")
                check = await chunks.query.fetch_object_by_id(
                    obj.uuid,
                    return_references=[QueryReference(link_on="automaticTag", return_properties=[])]
                )
                got = [str(r.uuid) for r in (check.references.get("automaticTag").objects if check.references and check.references.get("hasTags") else [])]
                logging.info(f"after: {got}")
            """
            return True
        except Exception as e:
            logging.error(f"Not changed approval state. Error: {e}")
            return False
        """
        # test if an object of approval for tagID chunkID and user exists
        filters = (
            Filter.by_property("user").equal(user) &
            Filter.by_ref("hasTag").by_id().equal(data.tagID) &
            Filter.by_ref("hasChunk").by_id().equal(data.chunkID)
        )
        
        ChunkTagApprovalCollection = self.client.collections.get("ChunkTagApproval")

        chunkTagApproval = await ChunkTagApprovalCollection.query.fetch_objects(
            filters=filters
        )
        new_approve_obj_uuid = ""
        if chunkTagApproval.objects:
            # update the object
            approval_obj = chunkTagApproval.objects[0]
            await ChunkTagApprovalCollection.data.update(
                uuid=approval_obj.uuid,
                properties={
                    "approved": data.approved,  # new value from UI
                }
            )
            new_approve_obj_uuid = approval_obj.uuid
        else:
            # create object with approval record
            new_approve_obj_uuid = await ChunkTagApprovalCollection.data.insert(
                properties={
                    "approved": data.approved, # pass the value from the UI
                    "user": user, 
                },
                references={
                    "hasTag": data.tagID,
                    "hasChunk": data.chunkID
                }
            )
        
        return new_approve_obj_uuid   
        """     

async def update_task_status(task_id: str, status: str, result={}, collection_name=None, session=None, all_texts_count=-1, processed_count=-1, tag_id=None, tag_processing_data=None):
        try:
            values_to_update = {
                "status": status
            }

            if collection_name is not None:
                values_to_update["collection_name"] = collection_name

            if result != {}:
                values_to_update["result"] = result

            if all_texts_count > -1:
                values_to_update["all_texts_count"] = int(all_texts_count)

            if processed_count > -1:
                values_to_update["processed_count"] = int(processed_count)    

            if tag_id is not None:
                values_to_update["tag_id"] = str(tag_id)

            if tag_processing_data is not None:
                values_to_update["tag_processing_data"] = tag_processing_data

            stmt = update(Task).where(Task.taskId == task_id).values(**values_to_update)
            
            # execute the update           
            await session.execute(stmt)
            await session.commit()

            logging.info("Data updated")
    
        except exc.SQLAlchemyError as e:
            logging.exception(f'Failed updating object in database. Task id ={task_id}')
            await session.rollback()  # rollback broken transaction
            raise DBError(f'Failed updating object in database. Task id ={task_id}') from e         


"""
        test: INFO:root:Objects: 038b29a5-776d-4865-9891-df3f2576e8ea, orig_text Jak informuje náš washingtonský zpravodaj Miroslav Konvalina, Bush v rozhlase uvedl: "V nutnosti odzbrojit Irák jsou Spojené Státy zajedno a Kongres je v této otázce zajedno. Amerika mluví jedním hlasem. Irák musí odzbrojit a podřídit se všem rezolucím OSN, nebo k tomu bude donucen". I přesto, že prezident Bush považuje Irák za naprostou prioritu, řada politických vůdců ve Spojených Státech opakovaně upozorňuje, že na domácím poli by měl Bush svést důležitější bitvy, zejména se stagnující ekonomikou. Demokraté chtějí v následujících dnech před listopadovými kongresovými volbami ostře vystoupit proti republikánskému řízení hospodářství. Demokraté také chtějí svolat ekonomické fórum a vyzvali Bushovi poradce, aby odstoupili. Prezident Bush dává v ekonomice přednost smířlivějšímu tónu a vyzval demokratickou opozici v Kongresu, aby se republikány sjednotila kolem hospodářství tak, jak se to podařilo v případě Irácké rezoluce. tag: {'tag_name': 'Prezident', 'tag_definition': 'Hlava statu', 'content': 'Jak informuje náš washingtonský zpravodaj Miroslav Konvalina, Bush v rozhlase uvedl: "V nutnosti odzbrojit Irák jsou Spojené Státy zajedno a Kongres je v této otázce zajedno. Amerika mluví jedním hlasem. Irák musí odzbrojit a podřídit se všem rezolucím OSN, nebo k tomu bude donucen". I přesto, že prezident Bush považuje Irák za naprostou prioritu, řada politických vůdců ve Spojených Státech opakovaně upozorňuje, že na domácím poli by měl Bush svést důležitější bitvy, zejména se stagnující ekonomikou. Demokraté chtějí v následujících dnech před listopadovými kongresovými volbami ostře vystoupit proti republikánskému řízení hospodářství. Demokraté také chtějí svolat ekonomické fórum a vyzvali Bushovi poradce, aby odstoupili. Prezident Bush dává v ekonomice přednost smířlivějšímu tónu a vyzval demokratickou opozici v Kongresu, aby se republikány sjednotila kolem hospodářství tak, jak se to podařilo v případě Irácké rezoluce.', 'tag_examples': ['EU Cesko']}
INFO:root:Objects: 0afae9a3-9226-4bae-a3ea-43e6bf05724a, orig_text Václav Havel: Nepleťte si ekonomiku s účetnictvím Na druhý den byl ve Smetanově síni avizován projev exprezidenta a dramatika Václava Havla. Poselstvím a hlavním tématem jeho slov byla schopnost mladých perspektivních manažerů umění rozlišit zisk spočitatelný od nespočitatelného, ono kulturní dědictví či ztráty, jež nelze vyčíslil v účetního tabulkách. tag: None
INFO:root:Objects: 0b8d98fa-749c-4e73-87c9-ddb9e49a830b, orig_text V obsáhlé řeči, ve které se opíral o témata Praha, globalizace, konkurence post sovětských zemí v EU, uvedl, že management budoucnosti by neměl stavět své pilíře na agresivních jedincích a na Darwinově teorii Boje druhů. Běžnému zaměstnanci by se neměl utahovat opasek ve prospěch manažerů. "Je nutné trvale kultivovat lidský kapitál," vyslal jako poselství Jiří Paroubek mladým elitám současnosti. V pondělí na závěr prvního bloku zaujal svým energickým a vyčerpávajícím projevem publicista a spolupředseda poslanecké skupiny Evropského parlamentu a člen komise Evropského parlamentu Daniel Cohn-Bendit. Takřka hodinu mluvil o historickém pozadí Evropy, kterou přirovnával ke krásné bytosti, které se chtějí všichni dotknout, ale zároveň se bojí k ní přiblížit. Do prostoru vznesl i zásadní otázku:"Proč potřebujeme Evropu. Potřebujeme ji vůbec?!" Přemýšlel nad problémem národních identit, nad tím, že žádný stát v Evropě by neměl být víc a že národnost konec konců znamená právě ty pomyslné hranice v Evropě. tag: {'tag_examples': ['EU Cesko'], 'tag_definition': 'Hlava statu', 'content': 'V obsáhlé řeči, ve které se opíral o témata Praha, globalizace, konkurence post sovětských zemí v EU, uvedl, že management budoucnosti by neměl stavět své pilíře na agresivních jedincích a na Darwinově teorii Boje druhů. Běžnému zaměstnanci by se neměl utahovat opasek ve prospěch manažerů. "Je nutné trvale kultivovat lidský kapitál," vyslal jako poselství Jiří Paroubek mladým elitám současnosti. V pondělí na závěr prvního bloku zaujal svým energickým a vyčerpávajícím projevem publicista a spolupředseda poslanecké skupiny Evropského parlamentu a člen komise Evropského parlamentu Daniel Cohn-Bendit. Takřka hodinu mluvil o historickém pozadí Evropy, kterou přirovnával ke krásné bytosti, které se chtějí všichni dotknout, ale zároveň se bojí k ní přiblížit. Do prostoru vznesl i zásadní otázku:"Proč potřebujeme Evropu. Potřebujeme ji vůbec?!" Přemýšlel nad problémem národních identit, nad tím, že žádný stát v Evropě by neměl být víc a že národnost konec konců znamená právě ty pomyslné hranice v Evropě.', 'tag_name': 'Prezident'}
INFO:root:Objects: 453b0a91-07c1-485e-8ed7-a163747e4ea5, orig_text Věřím ve vás, v mladší generaci, která se bude dívat dál do budoucna, za úzký soudobý horizont." Na Successor's European Youth Summit 2006 se sešlo se takřka 400 mladých manažerů z celého světa. Účastníci summitu zastávají v mladém věku významné posty v oblasti obchodu, vědy, výzkumu či umění. V Obecním době na panelových diskuzích debatovali o globalizace, nových teoriích růstu, světové bídě i Evropské unii. Panely vedly osobnosti z tuzemské manažerské špičky: generální ředitel Czechinvest Tomáš Hruda, hlavní ekonom Raiffeisen Bank, člen představenstva Škoda Auto Martin Jahn, bývalý ministr financí Pavel Mertlík, poradce premiéra ČR Valtr Komárek či viceprezident společnosti Microsoft pro Evropu, Blízký východ a Afriku Jan Mühlfeit nebo před velkým sálem promluvili i bývalý československý ministr zahraničních věcí Jiří Dienstbier.. tag: {'tag_examples': ['EU Cesko'], 'tag_definition': 'Hlava statu', 'content': 'Věřím ve vás, v mladší generaci, která se bude dívat dál do budoucna, za úzký soudobý horizont." Na Successor\'s European Youth Summit 2006 se sešlo se takřka 400 mladých manažerů z celého světa. Účastníci summitu zastávají v mladém věku významné posty v oblasti obchodu, vědy, výzkumu či umění. V Obecním době na panelových diskuzích debatovali o globalizace, nových teoriích růstu, světové bídě i Evropské unii. Panely vedly osobnosti z tuzemské manažerské špičky: generální ředitel Czechinvest Tomáš Hruda, hlavní ekonom Raiffeisen Bank, člen představenstva Škoda Auto Martin Jahn, bývalý ministr financí Pavel Mertlík, poradce premiéra ČR Valtr Komárek či viceprezident společnosti Microsoft pro Evropu, Blízký východ a Afriku Jan Mühlfeit nebo před velkým sálem promluvili i bývalý československý ministr zahraničních věcí Jiří Dienstbier..', 'tag_name': 'Prezident'}
INFO:root:Objects: 787683f5-4378-4aa2-bf98-89856fc7f839, orig_text "Přestat si plést ekonomiku s účetnictvím - to by měl být cíl mladých perspektivních manažerů, kteří budou již brzo řídit hospodářství svých zemí," uvedl mírně skepticky exprezident Václav Havel a dodal, "existuje bezpočet zisků, které nelze žádným sebelepším účetním systémem zjistit, a je i mnoho ztrát, které nelze tímto způsobem zjistit." Města halí postmoderní nic, řekl Havel Havel se zamýšlel i nad konzumní propastí, do které se dostávají lidé a jejich města: "Česká a moravská města obklíčily zvláštní zóny, kde jsou rozcapené jakési veliké jednopodlažní tovární haly, další chrámy konzumu - supermarkety, podivná sídliště, která si hrají na vilky, ale ve skutečnosti jsou anonymní. Jsou zde ohromné skladovací plochy, ohromná parkoviště a mezitím step, step a step. Dohromady to nenazvete ničím Není to pole, ani louka ani les, ani vesnice, ani město. Je to jakési postmoderní nic." Přestože jeho projev měl pesimistickou a posmutnělou dikcí, na závěr tomuto Havel opanoval:"Jsem optimista. tag: {'tag_examples': ['EU Cesko'], 'tag_definition': 'Hlava statu', 'content': '"Přestat si plést ekonomiku s účetnictvím - to by měl být cíl mladých perspektivních manažerů, kteří budou již brzo řídit hospodářství svých zemí," uvedl mírně skepticky exprezident Václav Havel a dodal, "existuje bezpočet zisků, které nelze žádným sebelepším účetním systémem zjistit, a je i mnoho ztrát, které nelze tímto způsobem zjistit." Města halí postmoderní nic, řekl Havel Havel se zamýšlel i nad konzumní propastí, do které se dostávají lidé a jejich města: "Česká a moravská města obklíčily zvláštní zóny, kde jsou rozcapené jakési veliké jednopodlažní tovární haly, další chrámy konzumu - supermarkety, podivná sídliště, která si hrají na vilky, ale ve skutečnosti jsou anonymní. Jsou zde ohromné skladovací plochy, ohromná parkoviště a mezitím step, step a step. Dohromady to nenazvete ničím Není to pole, ani louka ani les, ani vesnice, ani město. Je to jakési postmoderní nic." Přestože jeho projev měl pesimistickou a posmutnělou dikcí, na závěr tomuto Havel opanoval:"Jsem optimista.', 'tag_name': 'Prezident'}
INFO:root:Objects: fc65adff-b1b8-4310-80a0-c93d819bef53, orig_text Bush požádal zákonodárce o rychlé odhlasování několika ekonomických zákonů, například krytí teroristických hrozeb pojišťovnami. Neexistence této legislativy podle něho zbrzdila nebo znemožnila přes 15 miliard transakcí s nemovitostmi a ve druhém plánu to vedlo ke ztrátě více než 300.000 pracovních příležitostí. Průzkumy veřejného mínění ukazují, že Američané se zajímají více o ekonomiku než o případnou intervenci jejich armády proti Iráku. O Iráku začne otevřeně diskutovat ve středu Rada bezpečnosti OSN. V tomto typu debaty tak budou moci sdělit své stanovisko zástupci všech členských zemí Světové organizace.. tag: None
Is ok compared:
Results:
1. Ano : Jak informuje náš washingtonský zpravodaj Miroslav Konvalina, Bush v rozhlase uvedl: "V nutnosti odzbrojit Irák jsou Spojené Státy zajedno a Kongres je v této otázce zajedno. Amerika mluví jedním hlasem. Irák musí odzbrojit a podřídit se všem rezolucím OSN, nebo k tomu bude donucen". I přesto, že prezident Bush považuje Irák za naprostou prioritu, řada politických vůdců ve Spojených Státech opakovaně upozorňuje, že na domácím poli by měl Bush svést důležitější bitvy, zejména se stagnující ekonomikou. Demokraté chtějí v následujících dnech před listopadovými kongresovými volbami ostře vystoupit proti republikánskému řízení hospodářství. Demokraté také chtějí svolat ekonomické fórum a vyzvali Bushovi poradce, aby odstoupili. Prezident Bush dává v ekonomice přednost smířlivějšímu tónu a vyzval demokratickou opozici v Kongresu, aby se republikány sjednotila kolem hospodářství tak, jak se to podařilo v případě Irácké rezoluce.
2. Ne : Václav Havel: Nepleťte si ekonomiku s účetnictvím Na druhý den byl ve Smetanově síni avizován projev exprezidenta a dramatika Václava Havla. Poselstvím a hlavním tématem jeho slov byla schopnost mladých perspektivních manažerů umění rozlišit zisk spočitatelný od nespočitatelného, ono kulturní dědictví či ztráty, jež nelze vyčíslil v účetního tabulkách.
3. True : V obsáhlé řeči, ve které se opíral o témata Praha, globalizace, konkurence post sovětských zemí v EU, uvedl, že management budoucnosti by neměl stavět své pilíře na agresivních jedincích a na Darwinově teorii Boje druhů. Běžnému zaměstnanci by se neměl utahovat opasek ve prospěch manažerů. "Je nutné trvale kultivovat lidský kapitál," vyslal jako poselství Jiří Paroubek mladým elitám současnosti. V pondělí na závěr prvního bloku zaujal svým energickým a vyčerpávajícím projevem publicista a spolupředseda poslanecké skupiny Evropského parlamentu a člen komise Evropského parlamentu Daniel Cohn-Bendit. Takřka hodinu mluvil o historickém pozadí Evropy, kterou přirovnával ke krásné bytosti, které se chtějí všichni dotknout, ale zároveň se bojí k ní přiblížit. Do prostoru vznesl i zásadní otázku:"Proč potřebujeme Evropu. Potřebujeme ji vůbec?!" Přemýšlel nad problémem národních identit, nad tím, že žádný stát v Evropě by neměl být víc a že národnost konec konců znamená právě ty pomyslné hranice v Evropě.
4. Ano : Věřím ve vás, v mladší generaci, která se bude dívat dál do budoucna, za úzký soudobý horizont." Na Successor's European Youth Summit 2006 se sešlo se takřka 400 mladých manažerů z celého světa. Účastníci summitu zastávají v mladém věku významné posty v oblasti obchodu, vědy, výzkumu či umění. V Obecním době na panelových diskuzích debatovali o globalizace, nových teoriích růstu, světové bídě i Evropské unii. Panely vedly osobnosti z tuzemské manažerské špičky: generální ředitel Czechinvest Tomáš Hruda, hlavní ekonom Raiffeisen Bank, člen představenstva Škoda Auto Martin Jahn, bývalý ministr financí Pavel Mertlík, poradce premiéra ČR Valtr Komárek či viceprezident společnosti Microsoft pro Evropu, Blízký východ a Afriku Jan Mühlfeit nebo před velkým sálem promluvili i bývalý československý ministr zahraničních věcí Jiří Dienstbier..
5. Ano : "Přestat si plést ekonomiku s účetnictvím - to by měl být cíl mladých perspektivních manažerů, kteří budou již brzo řídit hospodářství svých zemí," uvedl mírně skepticky exprezident Václav Havel a dodal, "existuje bezpočet zisků, které nelze žádným sebelepším účetním systémem zjistit, a je i mnoho ztrát, které nelze tímto způsobem zjistit." Města halí postmoderní nic, řekl Havel Havel se zamýšlel i nad konzumní propastí, do které se dostávají lidé a jejich města: "Česká a moravská města obklíčily zvláštní zóny, kde jsou rozcapené jakési veliké jednopodlažní tovární haly, další chrámy konzumu - supermarkety, podivná sídliště, která si hrají na vilky, ale ve skutečnosti jsou anonymní. Jsou zde ohromné skladovací plochy, ohromná parkoviště a mezitím step, step a step. Dohromady to nenazvete ničím Není to pole, ani louka ani les, ani vesnice, ani město. Je to jakési postmoderní nic." Přestože jeho projev měl pesimistickou a posmutnělou dikcí, na závěr tomuto Havel opanoval:"Jsem optimista.
6. Ne : Bush požádal zákonodárce o rychlé odhlasování několika ekonomických zákonů, například krytí teroristických hrozeb pojišťovnami. Neexistence této legislativy podle něho zbrzdila nebo znemožnila přes 15 miliard transakcí s nemovitostmi a ve druhém plánu to vedlo ke ztrátě více než 300.000 pracovních příležitostí. Průzkumy veřejného mínění ukazují, že Američané se zajímají více o ekonomiku než o případnou intervenci jejich armády proti Iráku. O Iráku začne otevřeně diskutovat ve středu Rada bezpečnosti OSN. V tomto typu debaty tak budou moci sdělit své stanovisko zástupci všech členských zemí Světové organizace..

        try:
            # Get the collection
            collection_name = "Chunks"
            collection = self.client.collections.get(collection_name)
            
            # Query with filters (if provided)
            query = collection.query.fetch_objects(
                limit=limit,
                return_properties=["text"],  # Only return the "text" field
                # Add filters if provided
                filters=additional_filters if additional_filters else None,
            )
            
            results = await query
            
            # Extract the 'text' field from each object
            texts = [obj.properties["text"] for obj in results.objects]
            return texts
            
        except Exception as e:
            print(f"Error fetching texts from collection {collection_name}: {e}")
            return []
        
        str(self.chunk_col)
        return {'texts': ['test', 'test1'], 'tags': ['tagtest', 'teg_test2']}

INFO:root:Got past add new object
INFO:httpx:HTTP Request: POST http://localhost:8080/v1/objects/Chunks/0b8d98fa-749c-4e73-87c9-ddb9e49a830b/references/hasTags "HTTP/1.1 200 OK"
INFO:httpx:HTTP Request: GET http://localhost:8080/v1/schema/Chunks "HTTP/1.1 200 OK"
INFO:root:Chunk refs: ['document', 'hasTags']
INFO:root:Objects: 038b29a5-776d-4865-9891-df3f2576e8ea, orig_text Jak informuje náš washingtonský zpravodaj Miroslav Konvalina, Bush v rozhlase uvedl: "V nutnosti odzbrojit Irák jsou Spojené Státy zajedno a Kongres je v této otázce zajedno. Amerika mluví jedním hlasem. Irák musí odzbrojit a podřídit se všem rezolucím OSN, nebo k tomu bude donucen". I přesto, že prezident Bush považuje Irák za naprostou prioritu, řada politických vůdců ve Spojených Státech opakovaně upozorňuje, že na domácím poli by měl Bush svést důležitější bitvy, zejména se stagnující ekonomikou. Demokraté chtějí v následujících dnech před listopadovými kongresovými volbami ostře vystoupit proti republikánskému řízení hospodářství. Demokraté také chtějí svolat ekonomické fórum a vyzvali Bushovi poradce, aby odstoupili. Prezident Bush dává v ekonomice přednost smířlivějšímu tónu a vyzval demokratickou opozici v Kongresu, aby se republikány sjednotila kolem hospodářství tak, jak se to podařilo v případě Irácké rezoluce.
INFO:root:Properties: {'text': 'Jak informuje náš washingtonský zpravodaj Miroslav Konvalina, Bush v rozhlase uvedl: "V nutnosti odzbrojit Irák jsou Spojené Státy zajedno a Kongres je v této otázce zajedno. Amerika mluví jedním hlasem. Irák musí odzbrojit a podřídit se všem rezolucím OSN, nebo k tomu bude donucen". I přesto, že prezident Bush považuje Irák za naprostou prioritu, řada politických vůdců ve Spojených Státech opakovaně upozorňuje, že na domácím poli by měl Bush svést důležitější bitvy, zejména se stagnující ekonomikou. Demokraté chtějí v následujících dnech před listopadovými kongresovými volbami ostře vystoupit proti republikánskému řízení hospodářství. Demokraté také chtějí svolat ekonomické fórum a vyzvali Bushovi poradce, aby odstoupili. Prezident Bush dává v ekonomice přednost smířlivějšímu tónu a vyzval demokratickou opozici v Kongresu, aby se republikány sjednotila kolem hospodářství tak, jak se to podařilo v případě Irácké rezoluce.', 'tag': {'tag_examples': ['EU Cesko'], 'tag_definition': 'Hlava statu', 'content': 'Jak informuje náš washingtonský zpravodaj Miroslav Konvalina, Bush v rozhlase uvedl: "V nutnosti odzbrojit Irák jsou Spojené Státy zajedno a Kongres je v této otázce zajedno. Amerika mluví jedním hlasem. Irák musí odzbrojit a podřídit se všem rezolucím OSN, nebo k tomu bude donucen". I přesto, že prezident Bush považuje Irák za naprostou prioritu, řada politických vůdců ve Spojených Státech opakovaně upozorňuje, že na domácím poli by měl Bush svést důležitější bitvy, zejména se stagnující ekonomikou. Demokraté chtějí v následujících dnech před listopadovými kongresovými volbami ostře vystoupit proti republikánskému řízení hospodářství. Demokraté také chtějí svolat ekonomické fórum a vyzvali Bushovi poradce, aby odstoupili. Prezident Bush dává v ekonomice přednost smířlivějšímu tónu a vyzval demokratickou opozici v Kongresu, aby se republikány sjednotila kolem hospodářství tak, jak se to podařilo v případě Irácké rezoluce.', 'tag_name': 'Prezident'}, 'to_page': '2', 'from_page': '1', 'start_page_id': '87615e80-7370-43a6-832d-ed5970170327'}
INFO:root:No tags found, 'NoneType' object is not subscriptable
INFO:root:Objects: 0afae9a3-9226-4bae-a3ea-43e6bf05724a, orig_text Václav Havel: Nepleťte si ekonomiku s účetnictvím Na druhý den byl ve Smetanově síni avizován projev exprezidenta a dramatika Václava Havla. Poselstvím a hlavním tématem jeho slov byla schopnost mladých perspektivních manažerů umění rozlišit zisk spočitatelný od nespočitatelného, ono kulturní dědictví či ztráty, jež nelze vyčíslil v účetního tabulkách.
INFO:root:Properties: {'text': 'Václav Havel: Nepleťte si ekonomiku s účetnictvím Na druhý den byl ve Smetanově síni avizován projev exprezidenta a dramatika Václava Havla. Poselstvím a hlavním tématem jeho slov byla schopnost mladých perspektivních manažerů umění rozlišit zisk spočitatelný od nespočitatelného, ono kulturní dědictví či ztráty, jež nelze vyčíslil v účetního tabulkách.', 'tag': None, 'to_page': '3', 'from_page': '2', 'start_page_id': '5263d30b-12bc-404a-86e3-077a58023d76'}
INFO:root:No tags found, 'NoneType' object is not subscriptable
INFO:root:Objects: 0b8d98fa-749c-4e73-87c9-ddb9e49a830b, orig_text V obsáhlé řeči, ve které se opíral o témata Praha, globalizace, konkurence post sovětských zemí v EU, uvedl, že management budoucnosti by neměl stavět své pilíře na agresivních jedincích a na Darwinově teorii Boje druhů. Běžnému zaměstnanci by se neměl utahovat opasek ve prospěch manažerů. "Je nutné trvale kultivovat lidský kapitál," vyslal jako poselství Jiří Paroubek mladým elitám současnosti. V pondělí na závěr prvního bloku zaujal svým energickým a vyčerpávajícím projevem publicista a spolupředseda poslanecké skupiny Evropského parlamentu a člen komise Evropského parlamentu Daniel Cohn-Bendit. Takřka hodinu mluvil o historickém pozadí Evropy, kterou přirovnával ke krásné bytosti, které se chtějí všichni dotknout, ale zároveň se bojí k ní přiblížit. Do prostoru vznesl i zásadní otázku:"Proč potřebujeme Evropu. Potřebujeme ji vůbec?!" Přemýšlel nad problémem národních identit, nad tím, že žádný stát v Evropě by neměl být víc a že národnost konec konců znamená právě ty pomyslné hranice v Evropě.
INFO:root:Properties: {'text': 'V obsáhlé řeči, ve které se opíral o témata Praha, globalizace, konkurence post sovětských zemí v EU, uvedl, že management budoucnosti by neměl stavět své pilíře na agresivních jedincích a na Darwinově teorii Boje druhů. Běžnému zaměstnanci by se neměl utahovat opasek ve prospěch manažerů. "Je nutné trvale kultivovat lidský kapitál," vyslal jako poselství Jiří Paroubek mladým elitám současnosti. V pondělí na závěr prvního bloku zaujal svým energickým a vyčerpávajícím projevem publicista a spolupředseda poslanecké skupiny Evropského parlamentu a člen komise Evropského parlamentu Daniel Cohn-Bendit. Takřka hodinu mluvil o historickém pozadí Evropy, kterou přirovnával ke krásné bytosti, které se chtějí všichni dotknout, ale zároveň se bojí k ní přiblížit. Do prostoru vznesl i zásadní otázku:"Proč potřebujeme Evropu. Potřebujeme ji vůbec?!" Přemýšlel nad problémem národních identit, nad tím, že žádný stát v Evropě by neměl být víc a že národnost konec konců znamená právě ty pomyslné hranice v Evropě.', 'tag': {'tag_examples': ['EU Cesko'], 'tag_definition': 'Hlava statu', 'content': 'V obsáhlé řeči, ve které se opíral o témata Praha, globalizace, konkurence post sovětských zemí v EU, uvedl, že management budoucnosti by neměl stavět své pilíře na agresivních jedincích a na Darwinově teorii Boje druhů. Běžnému zaměstnanci by se neměl utahovat opasek ve prospěch manažerů. "Je nutné trvale kultivovat lidský kapitál," vyslal jako poselství Jiří Paroubek mladým elitám současnosti. V pondělí na závěr prvního bloku zaujal svým energickým a vyčerpávajícím projevem publicista a spolupředseda poslanecké skupiny Evropského parlamentu a člen komise Evropského parlamentu Daniel Cohn-Bendit. Takřka hodinu mluvil o historickém pozadí Evropy, kterou přirovnával ke krásné bytosti, které se chtějí všichni dotknout, ale zároveň se bojí k ní přiblížit. Do prostoru vznesl i zásadní otázku:"Proč potřebujeme Evropu. Potřebujeme ji vůbec?!" Přemýšlel nad problémem národních identit, nad tím, že žádný stát v Evropě by neměl být víc a že národnost konec konců znamená právě ty pomyslné hranice v Evropě.', 'tag_name': 'Prezident'}, 'to_page': '2', 'from_page': '1', 'start_page_id': '5263d30b-12bc-404a-86e3-077a58023d76'}
INFO:root:No tags found, 'NoneType' object is not subscriptable
INFO:root:Objects: 453b0a91-07c1-485e-8ed7-a163747e4ea5, orig_text Věřím ve vás, v mladší generaci, která se bude dívat dál do budoucna, za úzký soudobý horizont." Na Successor's European Youth Summit 2006 se sešlo se takřka 400 mladých manažerů z celého světa. Účastníci summitu zastávají v mladém věku významné posty v oblasti obchodu, vědy, výzkumu či umění. V Obecním době na panelových diskuzích debatovali o globalizace, nových teoriích růstu, světové bídě i Evropské unii. Panely vedly osobnosti z tuzemské manažerské špičky: generální ředitel Czechinvest Tomáš Hruda, hlavní ekonom Raiffeisen Bank, člen představenstva Škoda Auto Martin Jahn, bývalý ministr financí Pavel Mertlík, poradce premiéra ČR Valtr Komárek či viceprezident společnosti Microsoft pro Evropu, Blízký východ a Afriku Jan Mühlfeit nebo před velkým sálem promluvili i bývalý československý ministr zahraničních věcí Jiří Dienstbier..
INFO:root:Properties: {'text': 'Věřím ve vás, v mladší generaci, která se bude dívat dál do budoucna, za úzký soudobý horizont." Na Successor\'s European Youth Summit 2006 se sešlo se takřka 400 mladých manažerů z celého světa. Účastníci summitu zastávají v mladém věku významné posty v oblasti obchodu, vědy, výzkumu či umění. V Obecním době na panelových diskuzích debatovali o globalizace, nových teoriích růstu, světové bídě i Evropské unii. Panely vedly osobnosti z tuzemské manažerské špičky: generální ředitel Czechinvest Tomáš Hruda, hlavní ekonom Raiffeisen Bank, člen představenstva Škoda Auto Martin Jahn, bývalý ministr financí Pavel Mertlík, poradce premiéra ČR Valtr Komárek či viceprezident společnosti Microsoft pro Evropu, Blízký východ a Afriku Jan Mühlfeit nebo před velkým sálem promluvili i bývalý československý ministr zahraničních věcí Jiří Dienstbier..', 'tag': {'tag_examples': ['Beneš, prezident, je v EU'], 'tag_pictogram': 'key', 'tag_shorthand': 'cz', 'tag_color': '#03a9f4', 'tag_definition': 'Stát, krajina kde žijou lidi', 'content': 'Věřím ve vás, v mladší generaci, která se bude dívat dál do budoucna, za úzký soudobý horizont." Na Successor\'s European Youth Summit 2006 se sešlo se takřka 400 mladých manažerů z celého světa. Účastníci summitu zastávají v mladém věku významné posty v oblasti obchodu, vědy, výzkumu či umění. V Obecním době na panelových diskuzích debatovali o globalizace, nových teoriích růstu, světové bídě i Evropské unii. Panely vedly osobnosti z tuzemské manažerské špičky: generální ředitel Czechinvest Tomáš Hruda, hlavní ekonom Raiffeisen Bank, člen představenstva Škoda Auto Martin Jahn, bývalý ministr financí Pavel Mertlík, poradce premiéra ČR Valtr Komárek či viceprezident společnosti Microsoft pro Evropu, Blízký východ a Afriku Jan Mühlfeit nebo před velkým sálem promluvili i bývalý československý ministr zahraničních věcí Jiří Dienstbier..', 'tag_name': 'Cesko'}, 'to_page': '5', 'from_page': '4', 'start_page_id': '5263d30b-12bc-404a-86e3-077a58023d76'}
INFO:root:No tags found, 'NoneType' object is not subscriptable
INFO:root:Objects: 787683f5-4378-4aa2-bf98-89856fc7f839, orig_text "Přestat si plést ekonomiku s účetnictvím - to by měl být cíl mladých perspektivních manažerů, kteří budou již brzo řídit hospodářství svých zemí," uvedl mírně skepticky exprezident Václav Havel a dodal, "existuje bezpočet zisků, které nelze žádným sebelepším účetním systémem zjistit, a je i mnoho ztrát, které nelze tímto způsobem zjistit." Města halí postmoderní nic, řekl Havel Havel se zamýšlel i nad konzumní propastí, do které se dostávají lidé a jejich města: "Česká a moravská města obklíčily zvláštní zóny, kde jsou rozcapené jakési veliké jednopodlažní tovární haly, další chrámy konzumu - supermarkety, podivná sídliště, která si hrají na vilky, ale ve skutečnosti jsou anonymní. Jsou zde ohromné skladovací plochy, ohromná parkoviště a mezitím step, step a step. Dohromady to nenazvete ničím Není to pole, ani louka ani les, ani vesnice, ani město. Je to jakési postmoderní nic." Přestože jeho projev měl pesimistickou a posmutnělou dikcí, na závěr tomuto Havel opanoval:"Jsem optimista.
INFO:root:Properties: {'text': '"Přestat si plést ekonomiku s účetnictvím - to by měl být cíl mladých perspektivních manažerů, kteří budou již brzo řídit hospodářství svých zemí," uvedl mírně skepticky exprezident Václav Havel a dodal, "existuje bezpočet zisků, které nelze žádným sebelepším účetním systémem zjistit, a je i mnoho ztrát, které nelze tímto způsobem zjistit." Města halí postmoderní nic, řekl Havel Havel se zamýšlel i nad konzumní propastí, do které se dostávají lidé a jejich města: "Česká a moravská města obklíčily zvláštní zóny, kde jsou rozcapené jakési veliké jednopodlažní tovární haly, další chrámy konzumu - supermarkety, podivná sídliště, která si hrají na vilky, ale ve skutečnosti jsou anonymní. Jsou zde ohromné skladovací plochy, ohromná parkoviště a mezitím step, step a step. Dohromady to nenazvete ničím Není to pole, ani louka ani les, ani vesnice, ani město. Je to jakési postmoderní nic." Přestože jeho projev měl pesimistickou a posmutnělou dikcí, na závěr tomuto Havel opanoval:"Jsem optimista.', 'tag': {'tag_name': 'Cesko', 'tag_pictogram': 'key', 'tag_shorthand': 'cz', 'tag_color': '#03a9f4', 'tag_definition': 'Stát, krajina kde žijou lidi', 'content': '"Přestat si plést ekonomiku s účetnictvím - to by měl být cíl mladých perspektivních manažerů, kteří budou již brzo řídit hospodářství svých zemí," uvedl mírně skepticky exprezident Václav Havel a dodal, "existuje bezpočet zisků, které nelze žádným sebelepším účetním systémem zjistit, a je i mnoho ztrát, které nelze tímto způsobem zjistit." Města halí postmoderní nic, řekl Havel Havel se zamýšlel i nad konzumní propastí, do které se dostávají lidé a jejich města: "Česká a moravská města obklíčily zvláštní zóny, kde jsou rozcapené jakési veliké jednopodlažní tovární haly, další chrámy konzumu - supermarkety, podivná sídliště, která si hrají na vilky, ale ve skutečnosti jsou anonymní. Jsou zde ohromné skladovací plochy, ohromná parkoviště a mezitím step, step a step. Dohromady to nenazvete ničím Není to pole, ani louka ani les, ani vesnice, ani město. Je to jakési postmoderní nic." Přestože jeho projev měl pesimistickou a posmutnělou dikcí, na závěr tomuto Havel opanoval:"Jsem optimista.', 'tag_examples': ['Beneš, prezident, je v EU']}, 'to_page': '4', 'from_page': '3', 'start_page_id': '5263d30b-12bc-404a-86e3-077a58023d76'}
INFO:root:No tags found, 'NoneType' object is not subscriptable
INFO:root:Objects: fc65adff-b1b8-4310-80a0-c93d819bef53, orig_text Bush požádal zákonodárce o rychlé odhlasování několika ekonomických zákonů, například krytí teroristických hrozeb pojišťovnami. Neexistence této legislativy podle něho zbrzdila nebo znemožnila přes 15 miliard transakcí s nemovitostmi a ve druhém plánu to vedlo ke ztrátě více než 300.000 pracovních příležitostí. Průzkumy veřejného mínění ukazují, že Američané se zajímají více o ekonomiku než o případnou intervenci jejich armády proti Iráku. O Iráku začne otevřeně diskutovat ve středu Rada bezpečnosti OSN. V tomto typu debaty tak budou moci sdělit své stanovisko zástupci všech členských zemí Světové organizace..
INFO:root:Properties: {'text': 'Bush požádal zákonodárce o rychlé odhlasování několika ekonomických zákonů, například krytí teroristických hrozeb pojišťovnami. Neexistence této legislativy podle něho zbrzdila nebo znemožnila přes 15 miliard transakcí s nemovitostmi a ve druhém plánu to vedlo ke ztrátě více než 300.000 pracovních příležitostí. Průzkumy veřejného mínění ukazují, že Američané se zajímají více o ekonomiku než o případnou intervenci jejich armády proti Iráku. O Iráku začne otevřeně diskutovat ve středu Rada bezpečnosti OSN. V tomto typu debaty tak budou moci sdělit své stanovisko zástupci všech členských zemí Světové organizace..', 'tag': None, 'to_page': '3', 'from_page': '2', 'start_page_id': '87615e80-7370-43a6-832d-ed5970170327'}
INFO:root:No tags found, 'NoneType' object is not subscriptable
INFO:root:Task finished. Response: {'texts': ['Jak informuje náš washingtonský zpravodaj Miroslav Konvalina, Bush v rozhlase uvedl: "V nutnosti odzbrojit Irák jsou Spojené Státy zajedno a Kongres je v této otázce zajedno. Amerika mluví jedním hlasem. Irák musí odzbrojit a podřídit se všem rezolucím OSN, nebo k tomu bude donucen". I přesto, že prezident Bush považuje Irák za naprostou prioritu, řada politických vůdců ve Spojených Státech opakovaně upozorňuje, že na domácím poli by měl Bush svést důležitější bitvy, zejména se stagnující ekonomikou. Demokraté chtějí v následujících dnech před listopadovými kongresovými volbami ostře vystoupit proti republikánskému řízení hospodářství. Demokraté také chtějí svolat ekonomické fórum a vyzvali Bushovi poradce, aby odstoupili. Prezident Bush dává v ekonomice přednost smířlivějšímu tónu a vyzval demokratickou opozici v Kongresu, aby se republikány sjednotila kolem hospodářství tak, jak se to podařilo v případě Irácké rezoluce.', 'Václav Havel: Nepleťte si ekonomiku s účetnictvím Na druhý den byl ve Smetanově síni avizován projev exprezidenta a dramatika Václava Havla. Poselstvím a hlavním tématem jeho slov byla schopnost mladých perspektivních manažerů umění rozlišit zisk spočitatelný od nespočitatelného, ono kulturní dědictví či ztráty, jež nelze vyčíslil v účetního tabulkách.', 'V obsáhlé řeči, ve které se opíral o témata Praha, globalizace, konkurence post sovětských zemí v EU, uvedl, že management budoucnosti by neměl stavět své pilíře na agresivních jedincích a na Darwinově teorii Boje druhů. Běžnému zaměstnanci by se neměl utahovat opasek ve prospěch manažerů. "Je nutné trvale kultivovat lidský kapitál," vyslal jako poselství Jiří Paroubek mladým elitám současnosti. V pondělí na závěr prvního bloku zaujal svým energickým a vyčerpávajícím projevem publicista a spolupředseda poslanecké skupiny Evropského parlamentu a člen komise Evropského parlamentu Daniel Cohn-Bendit. Takřka hodinu mluvil o historickém pozadí Evropy, kterou přirovnával ke krásné bytosti, které se chtějí všichni dotknout, ale zároveň se bojí k ní přiblížit. Do prostoru vznesl i zásadní otázku:"Proč potřebujeme Evropu. Potřebujeme ji vůbec?!" Přemýšlel nad problémem národních identit, nad tím, že žádný stát v Evropě by neměl být víc a že národnost konec konců znamená právě ty pomyslné hranice v Evropě.', 'Věřím ve vás, v mladší generaci, která se bude dívat dál do budoucna, za úzký soudobý horizont." Na Successor\'s European Youth Summit 2006 se sešlo se takřka 400 mladých manažerů z celého světa. Účastníci summitu zastávají v mladém věku významné posty v oblasti obchodu, vědy, výzkumu či umění. V Obecním době na panelových diskuzích debatovali o globalizace, nových teoriích růstu, světové bídě i Evropské unii. Panely vedly osobnosti z tuzemské manažerské špičky: generální ředitel Czechinvest Tomáš Hruda, hlavní ekonom Raiffeisen Bank, člen představenstva Škoda Auto Martin Jahn, bývalý ministr financí Pavel Mertlík, poradce premiéra ČR Valtr Komárek či viceprezident společnosti Microsoft pro Evropu, Blízký východ a Afriku Jan Mühlfeit nebo před velkým sálem promluvili i bývalý československý ministr zahraničních věcí Jiří Dienstbier..', '"Přestat si plést ekonomiku s účetnictvím - to by měl být cíl mladých perspektivních manažerů, kteří budou již brzo řídit hospodářství svých zemí," uvedl mírně skepticky exprezident Václav Havel a dodal, "existuje bezpočet zisků, které nelze žádným sebelepším účetním systémem zjistit, a je i mnoho ztrát, které nelze tímto způsobem zjistit." Města halí postmoderní nic, řekl Havel Havel se zamýšlel i nad konzumní propastí, do které se dostávají lidé a jejich města: "Česká a moravská města obklíčily zvláštní zóny, kde jsou rozcapené jakési veliké jednopodlažní tovární haly, další chrámy konzumu - supermarkety, podivná sídliště, která si hrají na vilky, ale ve skutečnosti jsou anonymní. Jsou zde ohromné skladovací plochy, ohromná parkoviště a mezitím step, step a step. Dohromady to nenazvete ničím Není to pole, ani louka ani les, ani vesnice, ani město. Je to jakési postmoderní nic." Přestože jeho projev měl pesimistickou a posmutnělou dikcí, na závěr tomuto Havel opanoval:"Jsem optimista.', 'Bush požádal zákonodárce o rychlé odhlasování několika ekonomických zákonů, například krytí teroristických hrozeb pojišťovnami. Neexistence této legislativy podle něho zbrzdila nebo znemožnila přes 15 miliard transakcí s nemovitostmi a ve druhém plánu to vedlo ke ztrátě více než 300.000 pracovních příležitostí. Průzkumy veřejného mínění ukazují, že Američané se zajímají více o ekonomiku než o případnou intervenci jejich armády proti Iráku. O Iráku začne otevřeně diskutovat ve středu Rada bezpečnosti OSN. V tomto typu debaty tak budou moci sdělit své stanovisko zástupci všech členských zemí Světové organizace..'], 'tags': ['Ne', 'Ne', 'Ano', 'Ne.', 'Ne', 'Ne']}
INFO:root:Updated ok
"""