import logging

from weaviate.classes.query import Filter

from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction
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

async def tag_chunks_with_llm(searcher: WeaviateAbstraction, tag_request: schemas.TaggingTaskReqTemplate, task_id: str, session=None) -> schemas.TagResponse:
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
            
            tag_objects = await searcher.tag.helpers.fetch_tags(tag_filters)
            tag_uuid = tag_objects[0].uuid
            
            positive_responses = re.compile("^(True|Ano|Áno|Yes)", re.IGNORECASE) # prepare regex for check if the text is tagged be llm
            
            # filter to tag just chunks in selected user collection
            filters_by_collection =(
                Filter.by_ref(link_on=searcher.collectionNames.user_collection_link_name).by_property("name").equal(collection_name)
            )
            filters_by_tag = ((
                        Filter.by_ref(link_on="automaticTag").by_id().equal(tag_uuid) |
                        Filter.by_ref(link_on="positiveTag").by_id().equal(tag_uuid) |
                        Filter.by_ref(link_on="negativeTag").by_id().equal(tag_uuid) ) &
                        Filter.by_ref(link_on=searcher.collectionNames.user_collection_link_name).by_property("name").equal(collection_name)
                    )

            # query weaviate db for chunks of chosen collection
            results = await searcher.textChunk.helpers.fetch_chunks(filters_by_collection)
            resultsFiltered = await searcher.textChunk.helpers.fetch_chunks(filters_by_tag)

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
                            await searcher.textChunk.helpers.create_reference(obj.uuid, searcher.collectionNames.chunks_collection_name, property_name="automaticTag", target_collection_id=tag_uuid)
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

async def tag_and_store(tagReq: schemas.TaggingTaskReqTemplate, task_id: str, searcher: WeaviateAbstraction, sessionmaker):
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