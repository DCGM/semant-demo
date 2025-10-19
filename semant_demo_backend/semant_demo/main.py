from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import openai
from semant_demo import schemas
from semant_demo.config import config
import logging
from semant_demo.weaviate_search import WeaviateSearch
import asyncio
from semant_demo.tagging import tag_and_store
import uuid

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
#from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, String, JSON
from glob import glob  
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy import select, update, bindparam, asc 
from typing import AsyncGenerator   
#import db
from sqlalchemy import exc
from datetime import timezone

import logging  

from semant_demo.schemas import Task, TasksBase

import json

from semant_demo.weaviate_search import DBError, update_task_status


"""
if os.path.exists(config.SQL_DB_URL):
    os.remove(config.SQL_DB_URL)
    print("Deleted old database file")
"""

"""
from semant_demo.celery_tagging import tag_and_store
from celery.result import AsyncResult
"""

logging.basicConfig(level=logging.INFO)

global_engine = None
global_async_session_maker = None

# Dependency
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    global global_engine, global_async_session_maker
    if global_engine is None:
        global_engine = create_async_engine(config.SQL_DB_URL, pool_size=20, max_overflow=60)
        global_async_session_maker = async_sessionmaker(global_engine, autocommit=False, autoflush=True, expire_on_commit=False)
    async with global_async_session_maker() as session:
        yield session    

openai_client = openai.AsyncOpenAI(api_key=config.OPENAI_API_KEY)

global_searcher = None
async def get_search() -> WeaviateSearch:
    global global_searcher
    if global_searcher is None:
        global_searcher = await WeaviateSearch.create(config)
    return global_searcher
app = FastAPI()

# Create tables on startup
@app.on_event("startup")
async def startup():
    global global_engine, global_async_session_maker
    global_engine = create_async_engine(config.SQL_DB_URL, pool_size=20, max_overflow=60)
    global_async_session_maker = async_sessionmaker(global_engine, autocommit=False, autoflush=False)
    async with global_engine.begin() as conn:
        # drop all tables first
        #await conn.run_sync(TasksBase.metadata.drop_all)
        # create tables
        await conn.run_sync(TasksBase.metadata.create_all)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.ALLOWED_ORIGIN],  # http://localhost:9000
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/search", response_model=schemas.SearchResponse)
async def search(req: schemas.SearchRequest, searcher: WeaviateSearch = Depends(get_search)) -> schemas.SearchResponse:
    print("Searching", flush=True)
    response = await searcher.search(req)
    return response


@app.post("/api/summarize/{summary_type}", response_model=schemas.SummaryResponse)
async def summarize(search_response: schemas.SearchResponse, summary_type: str) -> schemas.SummaryResponse:
    # build your snippets with IDs
    snippets = [
        f"[doc{i+1}]" + res.text.replace('\\n', ' ')
        for i, res in enumerate(search_response.results)
    ]

    system_prompt = "\n".join([
        "You are a summarization assistant.",
        "You will be given text snippets, each labeled with a unique ID like [doc1], [doc2], … [doc15].",
        "You should produce a single, concise summary that covers all the key points relevant to a user search query.",
        "After every fact that you extract from a snippet, append the snippet’s ID in square brackets—for example: “The gene ABC is upregulated in tumor cells [doc3].”",
        "If multiple snippets support the same fact, list all their IDs separated by commas: “This approach improved accuracy by 12% [doc2, doc7, doc11].”",
        "Do not introduce any facts that are not in the snippets. Focus on information that is relevant to the user query.",
        "Write the summary clearly and concisely.",
        "Keep the summary under 200 words."
    ])

    user_prompt = "\n".join([
        f'The user query is: "{search_response.search_request.query}"',
        "Here are the retrieved text snippets:",
        *snippets,
        "",
        "Please summarize these contexts, tagging each statement with its source ID. Do not add any other text."
    ])

    try:
        resp = await openai_client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=300,
        )
    except openai.OpenAIError as e:
        # turn any SDK error into a 502
        logging.error(e)
        raise HTTPException(status_code=502, detail=str(e))

    summary_text = resp.choices[0].message.content.strip()

    return schemas.SummaryResponse(
        summary=summary_text,
        time_spent=search_response.time_spent,
    )


@app.post("/api/question/{question_text}", response_model=schemas.SummaryResponse)
async def question(search_response: schemas.SearchResponse, question_text: str) -> schemas.SummaryResponse:
    # build your snippets with IDs
    snippets = [
        f"[doc{i+1}]" + res.text.replace('\\n', ' ')
        for i, res in enumerate(search_response.results)
    ]

    system_prompt = "\n".join([
        "You are a summarization assistant.",
        "You will be given text snippets, each labeled with a unique ID like [doc1], [doc2], … [doc15].",
        "When answering, rely only on the information in the snippets. Do not include any information that is not in the snippets.",
        "Any information you provide must be supported by the snippets and the snipet labels must be included as much as possible."
    ])

    user_prompt = "\n".join([
        "Here are the text snippets I want to talk about:",
        *snippets,
    ])

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
        {"role": "user", "content": question_text},
    ]
    print(messages)

    try:
        resp = await openai_client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
            temperature=0.0,
            max_tokens=300,
        )
    except openai.OpenAIError as e:
        logging.error(e)
        raise HTTPException(status_code=502, detail=str(e))

    summary_text = resp.choices[0].message.content.strip()

    return schemas.SummaryResponse(
        summary=summary_text,
        time_spent=search_response.time_spent,
    )


@app.post("/api/create_tag", response_model=schemas.CreateResponse)
async def create_tag(tagReq: schemas.TagReqTemplate, tagger: WeaviateSearch = Depends(get_search), session: AsyncSession = Depends(get_async_session)) -> schemas.CreateResponse:
    """
    creates tag in weaviate db, or not if the same tag already exists
    """
    try:
        tag_id = await tagger.add_or_get_tag(tagReq)
        return {"created": True, "message": f"Tag {tagReq.tag_name} created with tag id {tag_id}"}
    except Exception as e:
        logging.error(e)
        return {"created": False, "message": f"Tag {tagReq.tag_name} not created becacause of: {e}"}

@app.post("/api/tagging_task", response_model=schemas.TagStartResponse)
async def start_tagging(tagReq: schemas.TagReqTemplate, background_tasks: BackgroundTasks, tagger: WeaviateSearch = Depends(get_search), session: AsyncSession = Depends(get_async_session)) -> schemas.TagStartResponse:
    """
    Starts tagging task in form of asyncio.create_task
    """
    print("Tagging...")
    print(tagReq)
    taskId = str(uuid.uuid4()) # generate id for current task
    try:
        try:
            async with session.begin():
                session.add(Task(taskId=taskId))
                await session.commit()
        except exc.SQLAlchemyError as e:
            logging.exception(f'Failed adding object to database. Task ID={taskId}')
            raise DBError(f'Failed adding new task object to database. Task ID={taskId}') from e

        task = asyncio.create_task(tag_and_store(tagReq, taskId, tagger, global_async_session_maker))
        taskName = task.get_name()
        # store the task name into DB
        try:
            async with session.begin():
                await session.execute(
                    update(Task)
                    .where(Task.taskId == taskId)
                    .values(task_name=taskName)
                )
        except exc.SQLAlchemyError as e:
            logging.exception(f'Failed adding object to database. Task ID={taskId}')
            raise DBError(f'Failed adding new task object to database. Task ID={taskId}') from e

        return {"job_started": True, "task_id": taskId, "message": "Tagging task started in the background"}
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=500, detail=str(e))

"""
# get task ids to see history of tasks
@app.get("/api/all_tasks_id", response_model=schemas.TagTasksResponse)
async def get_tag_tasks(session: AsyncSession = Depends(get_async_session)) -> schemas.TagTasksResponse:
    try:
        logging.info(f"Fetching")
        stmt = select(Task.taskId).order_by(asc(Task.time_updated))
        data = await session.execute(stmt)
        tasks_ids = data.scalars().all()
        logging.info(f"Retrieved tasks ids: {tasks_ids}")
        return { "taskIDs": tasks_ids }
    
    except exc.SQLAlchemyError as e:
        logging.exception(f'Failed loading object from database. While loading all tasks ids.')
        raise DBError(f'Failed loading all tasks ids from database.') from e
"""

# get task info to see history of tasks
@app.get("/api/all_tasks")
async def get_tag_tasks(session: AsyncSession = Depends(get_async_session)):
    try:
        logging.info(f"Fetching")
        stmt = select(Task).order_by(asc(Task.time_updated))
        data = await session.execute(stmt)
        # prepare the result
        tasks = data.scalars().all()
        response = []
        for task in tasks:
            result = task.result
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except Exception:
                    result = None
            response.append({"taskId": task.taskId, 
                             "status": task.status, 
                             "result": result, 
                             "all_texts_count": task.all_texts_count, 
                             "processed_count": task.processed_count, 
                             "tag_id": task.tag_id, 
                             "tag_processing_data": task.tag_processing_data, 
                             "timestamp": task.time_updated.replace(tzinfo=timezone.utc).isoformat() if task.time_updated else None})
        
        logging.info(f"Retrieved tasks")
        return { "taskData": response }
    
    except exc.SQLAlchemyError as e:
        logging.exception(f'Failed loading object from database. While loading all tasks ids.')
        raise DBError(f'Failed loading all tasks ids from database.') from e

# polling to check task status
@app.get("/api/tag_status/{taskId}")
async def check_status(taskId: str, session: AsyncSession = Depends(get_async_session)):
        try:
            task = await session.get(Task, taskId)
        except exc.SQLAlchemyError as e:
            logging.exception(f'Failed loading object from database. Task ID={taskId}')
            raise DBError(f'Failed loading object from database. Task ID={taskId}') from e
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        # prepare the result
        result = task.result
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except Exception:
                result = None

        logging.info(f"Repsonse status: {task.status}")
        logging.info(f"tag_processing_data: {task.tag_processing_data}")

        return {"taskId": taskId, "status": task.status, "result": task.result, "all_texts_count": task.all_texts_count, "processed_count": task.processed_count, "tag_id": task.tag_id, "tag_processing_data": task.tag_processing_data}

def getTaskByName(name):
    for t in asyncio.all_tasks():
        if t.get_name() == name and not t.done():
            return t

# cancel task
@app.delete("/api/tagging_task/{taskId}", response_model=schemas.CancelTaskResponse)
async def cancel_task(taskId: str, session: AsyncSession = Depends(get_async_session)) -> schemas.CancelTaskResponse:
        taskName = ""
        # get task by its name
        try:
            async with session.begin():
                result = await session.execute(
                    select(Task.task_name).where(Task.taskId == taskId)
                )
                task_row = result.scalar_one_or_none() 
                if task_row is None:
                    raise DBError(f'Task ID={taskId} not found in database')
                taskName = task_row
                taskAsyncio = getTaskByName(taskName)

                if taskAsyncio and not taskAsyncio.done():
                    if taskAsyncio.cancel():
                        await update_task_status(task_id=taskId, status="CANCELED", session=session)
                        return {"message": f"Task {taskId} cancelled", "taskCanceled": True}
                    else:
                        return {"message": f"Task {taskId} was not cancelled", "taskCanceled": False}
        except exc.SQLAlchemyError as e:
            logging.exception(f'Failed loading object from database. Task ID={taskId}')
            return {"message": f"Task retrieving failed {taskId}", "taskCanceled": False}
        return {"message": f"No running task {taskId}", "taskCanceled": False}

# retrieve all tags
@app.get("/api/all_tags", response_model=schemas.GetTagsResponse)
async def get_tags(tagger: WeaviateSearch = Depends(get_search)) -> schemas.GetTagsResponse:
    response = await tagger.get_all_tags()
    return {"tags_lst": response}

@app.post("/api/tagged_texts", response_model=schemas.GetTaggedChunksResponse)
async def get_selected_tags_chunks(chosenTagUUIDs: schemas.GetTaggedChunksReq, tagger: WeaviateSearch = Depends(get_search)) -> schemas.GetTagsResponse:
    """
    returns chunks which are tagged by certain type of tag (automatic, positive, negative)
    """
    try:
        logging.info(f"In get tagged text {chosenTagUUIDs}")
        response = await tagger.get_tagged_chunks(chosenTagUUIDs)
        return response
    except Exception as e:
        logging.error(f"{e}")

@app.delete("/api/whole_tags", response_model=schemas.RemoveTagsResponse)
async def remove_tags(chosenTagUUIDs: schemas.RemoveTagReq, tagger: WeaviateSearch = Depends(get_search)) -> schemas.RemoveTagsResponse:
    try:
        response = await tagger.remove_tags(chosenTagUUIDs)
        return response
    except Exception as e:
        logging.error(f"{e}")

@app.delete("/api/automatic_tags", response_model=schemas.RemoveTagsResponse)
async def remove_automatic_tags(chosenTagUUIDs: schemas.RemoveTagReq, tagger: WeaviateSearch = Depends(get_search)) -> schemas.RemoveTagsResponse:
    try:
        response = await tagger.remove_automatic_tags(chosenTagUUIDs)
        return response
    except Exception as e:
        logging.error(f"{e}")        

@app.put("/api/tag_approval", response_model=schemas.ApproveTagResponse)
async def approve_selected_tag_chunk(approveData: schemas.ApproveTagReq, tagger: WeaviateSearch = Depends(get_search)) -> schemas.ApproveTagResponse:
    """
    User approve or disapprove a tag, changes the reference of the tag
    """
    try:
        logging.info("Approving...")
        response = await tagger.approve_tag(approveData)
        logging.info(f"{response}")
        return { "successful": response, "approved": approveData.approved}
    except Exception as e:
        logging.error(f"{e}")
        return { "successful": False, "approved": approveData.approved}
    
@app.post("/api/filter_tags", response_model=schemas.FilterChunksByTagsResponse)
async def filter_chunks_by_tags(requestedData: schemas.FilterChunksByTagsRequest, tagger: WeaviateSearch = Depends(get_search)) -> schemas.FilterChunksByTagsResponse:
    """
    Filter chunks by given tags and positive or/and automatic flags
    """
    response = await tagger.filterChunksByTags(requestedData)
    return response

@app.post("/api/user_collection", response_model=schemas.CreateResponse)
async def create_user_collection(collectionReq: schemas.UserCollectionReqTemplate, tagger: WeaviateSearch = Depends(get_search), session: AsyncSession = Depends(get_async_session)) -> schemas.CreateResponse:
    """
    creates user collection in weaviate db, or not if the same user collection already exists
    """
    try:
        collection_id = await tagger.add_collection(collectionReq)
        if collection_id is None:
            raise Exception("weaviate error")
        return {"created": True, "message": f"Collection {collectionReq.collection_name} created with collection id {collection_id}"}
    except Exception as e:
        logging.error(e)
        return {"created": False, "message": f"Collection {collectionReq.collection_name} not created becacause of: {e}"}

@app.get("/api/collections", response_model=schemas.GetCollectionsResponse)
async def fetch_collections(userId: str, tagger: WeaviateSearch = Depends(get_search)) -> schemas.GetCollectionsResponse:
    """
    retrieves all collections for given user
    """
    response = await tagger.fetch_all_collections(userId)
    return response

@app.post("/api/chunk_2_collection", response_model=schemas.CreateResponse)
async def add_chunk_2_collection(req: schemas.Chunk2CollectionReq, tagger: WeaviateSearch = Depends(get_search), session: AsyncSession = Depends(get_async_session)) -> schemas.CreateResponse:
    """
    creates user collection in weaviate db, or not if the same user collection already exists
    """
    try:
        err = await tagger.add_chunk_to_collection(req)
        if err:
            raise Exception("weaviate error")
        return {"created": True, "message": f"Chunk added to collection"}
    except Exception as e:
        logging.error(e)
        return {"created": False, "message": f"Chunk not added to collection becacause of: {e}"}

@app.get("/api/chunks_of_collection", response_model=schemas.GetCollectionChunksResponse)
async def get_collection_chunks(collectionId: str, tagger: WeaviateSearch = Depends(get_search)) -> schemas.GetCollectionChunksResponse:
    """
    returns chunks which belong to collection given by id
    """
    try:
        logging.info(f"In get collection chunks {collectionId}")
        response = await tagger.get_collection_chunks(collectionId)
        return response
    except Exception as e:
        logging.error(f"{e}")

# http://localhost:8002/docs#

# TODO now only automatic are shown, show positive and negative add filtering (print in FE useing chunkDataPositive/Negative)
# pridat do tagFormManage tag_type alebo aspon pridat nejaky select