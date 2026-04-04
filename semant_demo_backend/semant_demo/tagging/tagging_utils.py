import logging

from weaviate.classes.query import Filter

from semant_demo.weaviate_search import WeaviateSearch
from weaviate.classes.query import QueryReference
from semant_demo import schemas
from semant_demo import schemas
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
#from sqlalchemy.orm import sessionmaker
from sqlalchemy import update
from sqlalchemy import exc
from semant_demo.schemas import Task, TasksBase
import asyncio
#from semant_demo.weaviate_tag import WeaviateSearchAndTag
from semant_demo.config import config
import logging
from semant_demo.tagging.sql_utils import update_task_status

import re
import os

# llm calling
from langchain_core.prompts import ChatPromptTemplate
from semant_demo.tagging.llm_caller import OllamaProxyRunnable
from langchain_openai import ChatOpenAI
import semant_demo.tagging.configs.prompt_templates as tagging_templates

async def tag_chunks_with_llm(searcher: WeaviateSearch, tag_request: schemas.TaggingTaskReqTemplate, task_id: str, session=None) -> schemas.TagResponse:
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

async def tag_and_store(tagReq: schemas.TaggingTaskReqTemplate, task_id: str, searcher: WeaviateSearch, sessionmaker):
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
        
async def fetch_chunks_by_collection(collectionId: str, searcher: WeaviateSearch) ->schemas.GetCollectionChunksResponse:
        """
        Get all chunks belonging to collection with collectionId
        get collection object, in that collection search for chunks that refer to the
        collection and return chunk texts
        """
        try:
            chunk_lst_with_tags = []
            # prepare filter for collection ID
            filters = Filter.by_ref("userCollection").by_id().equal(collectionId)
            # iterate over all chunks find the reference to the user collection
            chunks = await searcher.fetch_chunks(filters=filters)
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

async def approve_tag(data: schemas.ApproveTagReq, searcher):
        try:
            logging.info(f"Chunk ID: {data.chunkID}, Tag ID: {data.tagID}")
            # get chunk
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
            obj = await searcher.fetch_object_by_id(data.chunkID, searcher.chunks_collection_name, return_references)
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
                obj = await searcher.fetch_object_by_id(data.chunkID, searcher.chunks_collection_name, return_references)
                refs = obj.references or {}
                current = refs.get(refName)
                currentIDs = [str(r.uuid) for r in (current.objects if current else [])]
                remaining = [tid for tid in currentIDs if tid != data.tagID]
                logging.info(f"Replacing Current{currentIDs} \nRemaning{remaining}")
                logging.info(f"To remove {data.tagID}")
                if len(remaining) != len(currentIDs):
                    logging.info(f"Replacing {currentIDs} {remaining}")
                    await searcher.remove_reference(src_id=obj.uuid, 
                                            src_collection_name=searcher.chunks_collection_name, 
                                            property_name=refName,
                                            target_collection_id=remaining)

            # create the reference for approved tag
            if data.approved: # positive tags

                updatedTags = sorted(set(pos_ids + [tag_id]))
                await searcher.create_reference(src_id=obj.uuid, 
                                            src_collection_name=searcher.chunks_collection_name, 
                                            property_name="positiveTag",
                                            target_collection_id=updatedTags)
                # remove the reference from the negative tags just in case
                await removeTagRef("negativeTag", data)
            else: # negative tags

                updatedTags = sorted(set(neg_ids + [tag_id]))
                await searcher.create_reference(src_id=obj.uuid, 
                                            src_collection_name=searcher.chunks_collection_name, 
                                            property_name="negativeTag",
                                            target_collection_id=updatedTags)
                # remove the reference from the positive tags just in case
                await removeTagRef("positiveTag", data)

            # remove the reference from the automatic tags
            await removeTagRef("automaticTag", data)
            return True
        except Exception as e:
            logging.error(f"Not changed approval state. Error: {e}")
            return False
        
async def filterChunksByTags(requestedData: schemas.FilterChunksByTagsRequest, searcher: WeaviateSearch ):
        """
        Filters chunks by tags - for search results filtration after initial search
        get tag objects, chunk objects,
        then filter the chunks that has positive tags and automatic tags referces to any of
        the selected tags and return the data
        """
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

            chunk_results = await searcher.fetch_chunks(filters=combinedFilters)

            # helper to extract UUID strings from reference block
            def ref_uuids(ref_block):
                if not ref_block:
                    return []
                return [str(r.uuid) for r in ref_block.objects]

            resultLst = []
            for chunk in chunk_results:
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
        
async def get_tagged_chunks(getChunksReq: schemas.GetTaggedChunksReq, searcher: WeaviateSearch) -> schemas.GetTaggedChunksResponse:
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