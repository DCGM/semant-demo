from semant_demo import schemas
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import update
from semant_demo.schemas import Task, TasksBase
import asyncio
from semant_demo.weaviate_search import WeaviateSearch
from semant_demo.config import config

# Reuse the same DB engine from main.py
DB_URL = "sqlite+aiosqlite:///tasks.db"
engine = create_async_engine(DB_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def update_task_status(task_id: str, status: str, result=None, collection_name=None):
    async with AsyncSessionLocal() as session:
        # Update the task status in DB
        await session.execute(
            update(Task)
            .where(Task.taskId == task_id)
            .values(status=status, result=result, collection_name=collection_name)
        )
        await session.commit()

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
   # TODO logging module
async def tag_and_store(tagReq: schemas.TagReqTemplate, task_id: str):
    
    try:
        await update_task_status(task_id, "RUNNING", collection_name=tagReq.collection_name)
        
        # TODO replace with Weaviate/LLM operations:
        with open("log.txt", mode="w", encoding="utf-8") as log_file:
            searcher_tag = await WeaviateSearch.create(config) # TODO globalne cez Depends
            response = await searcher_tag.tag(tagReq)
            log_file.write(f"Starting task with data: {str(tagReq)}")
            #await asyncio.sleep(30)  # Simulate work
            log_file.write(f"Task finished. Response: {response}")
            #response = await searcher_tag.tag(tagReq)
            await searcher_tag.close()
        await update_task_status(task_id, "COMPLETED", {"result": response}, collection_name=tagReq.collection_name)
    except Exception as e:
        await update_task_status(task_id, "FAILED", {"error": str(e)}, collection_name=tagReq.collection_name)


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
