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
from semant_demo.weaviate_search import update_task_status

async def tag_and_store(tagReq: schemas.TagReqTemplate, task_id: str, tagger: WeaviateSearch, sessionmaker):
    try:
        #await update_task_status(task_id, "RUNNING", collection_name=tagReq.collection_name, sessionmaker=sessionmaker)
        
        # TODO replace with Weaviate/LLM operations:
        logging.info(f"Starting task with data: {str(tagReq)}")
        response = await tagger.tag(tagReq, task_id, sessionmaker=sessionmaker)
        logging.info(f"Task finished. Response: {response}")
        await update_task_status(task_id, "COMPLETED", result=response, collection_name=tagReq.collection_name, sessionmaker=sessionmaker)
        logging.info("Updated ok")
    except Exception as e:
        await update_task_status(task_id, "FAILED", result={"error": str(e)}, collection_name=tagReq.collection_name, sessionmaker=sessionmaker)
        logging.error(f"Error: {e}")
    
"""
async def async_tag_and_store(tagReq: schemas.TagReqTemplate, task_id: str, session: AsyncSession):
    try:
        await update_task_status(task_id, "RUNNING")
        
        # TODO replace with Weaviate/LLM operations:
        with open("log.txt", mode="w", encoding="utf-8") as log_file:
            searcher_tag = await WeaviateSearch.create(config)
            response = await searcher_tag.tag(tagReq)
            log_file.write(f"Starting task with data: {str(tagReq)}")
            await asyncio.sleep(30)  # Simulate work
            log_file.write(f"Task finished. Response: {response}")
            response = await searcher_tag.tag(tagReq)
            await searcher_tag.close()
        await update_task_status(task_id, "COMPLETED", {"result": "success"})
    except Exception as e:
        await update_task_status(task_id, "FAILED", {"error": str(e)})
"""    

"""

    #Thread-safe entry point
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            _run_isolated(tagReq, task_id)
        )
    finally:
        loop.close()

async def _run_isolated(tagReq, task_id):
    async with AsyncSessionLocal() as session:
        await async_tag_and_store(tagReq, task_id, session)
"""
        


"""
def tag_and_store(tagReq: schemas.TagReqTemplate, task_id: str, searcher: WeaviateSearch):
    #Synchronous wrapper for async operations
    async def _run():
        async with AsyncSessionLocal() as session:
            await async_tag_and_store(tagReq, task_id, searcher, session)
    
    try:
        # Create new loop for the background thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_run())
    except Exception as e:
        print(e)
    finally:
        if loop.is_running():
            loop.stop()
        loop.close()
"""
"""
def tag_and_store(tagReq: schemas.TagReqTemplate, task_id: str, searcher: WeaviateSearch):
    # Create a new event loop for the background thread
    print(f"Task {task_id} started")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(async_tag_and_store(tagReq, task_id, searcher))
    finally:
        loop.close()
"""
