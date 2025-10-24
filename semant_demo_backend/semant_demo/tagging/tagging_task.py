from semant_demo import schemas
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
#from sqlalchemy.orm import sessionmaker
from sqlalchemy import update
from sqlalchemy import exc
from semant_demo.schemas import Task, TasksBase
import asyncio
from semant_demo.weaviate_search import WeaviateSearch
from semant_demo.config import config
import logging
from semant_demo.tagging.sql_utils import update_task_status

async def tag_and_store(tagReq: schemas.TagReqTemplate, task_id: str, tagger: WeaviateSearch, sessionmaker):
    try:
        session = sessionmaker()
        
        try:
            #await update_task_status(task_id, "RUNNING", collection_name=tagReq.collection_name, sessionmaker=sessionmaker)
            # TODO replace with Weaviate/LLM operations:
            logging.info(f"Starting task with data: {str(tagReq)}")
            response = await tagger.tag_chunks_with_llm(tagReq, task_id, session=session)
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