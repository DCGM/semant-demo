import os
import openai
import logging

from fastapi import APIRouter, Depends, HTTPException

from semant_demo import schemas
from semant_demo.config import config
from semant_demo.summarization.templated import TemplatedSearchResultsSummarizer
from semant_demo.weaviate_search import WeaviateSearch
# from semant_demo.rag.rag_generator import RagGenerator
from time import time
import asyncio

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import openai
from semant_demo import schemas
from semant_demo.config import config
import logging
from semant_demo.weaviate_search import WeaviateSearch
import asyncio
from semant_demo.tagging.tagging_task import tag_and_store
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

from semant_demo.tagging.sql_utils import DBError, update_task_status
from semant_demo.tagging.tagging_task import getTaskByName


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

exp_router = APIRouter()

@exp_router.post("/api/tag", response_model=schemas.CreateResponse)
async def create_tag(tagReq: schemas.TagReqTemplate, tagger: WeaviateSearch = Depends(get_search),
                     session: AsyncSession = Depends(get_async_session)) -> schemas.CreateResponse:
    """
    Creates tag in weaviate db, or not if the same tag already exists
    """
    try:
        tag_id = await tagger.add_or_get_tag(tagReq)
        return {"created": True, "message": f"Tag {tagReq.tag_name} created with tag id {tag_id}"}
    except Exception as e:
        logging.error(e)
        return {"created": False, "message": f"Tag {tagReq.tag_name} not created becacause of: {e}"}


@exp_router.post("/api/tagging_task", response_model=schemas.TagStartResponse)
async def start_tagging(tagReq: schemas.TagReqTemplate,
                        tagger: WeaviateSearch = Depends(get_search),
                        session: AsyncSession = Depends(get_async_session)) -> schemas.TagStartResponse:
    """
    Starts tagging task in form of asyncio.create_task
    """
    logging.info("Tagging...")
    taskId = str(uuid.uuid4())  # generate id for current task
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


@exp_router.get("/api/all_tasks")
async def get_tag_tasks(session: AsyncSession = Depends(get_async_session)):
    """
    Get task info to see history of tasks
    """
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
                             "timestamp": task.time_updated.replace(
                                 tzinfo=timezone.utc).isoformat() if task.time_updated else None})

        logging.info(f"Retrieved tasks")
        return {"taskData": response}

    except exc.SQLAlchemyError as e:
        logging.exception(f'Failed loading object from database. While loading all tasks ids.')
        raise DBError(f'Failed loading all tasks ids from database.') from e


@exp_router.get("/api/tag_status/{taskId}")
async def check_status(taskId: str, session: AsyncSession = Depends(get_async_session)):
    """
    Polling to check task status
    """
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

    return {"taskId": taskId, "status": task.status, "result": task.result, "all_texts_count": task.all_texts_count,
            "processed_count": task.processed_count, "tag_id": task.tag_id,
            "tag_processing_data": task.tag_processing_data}


@exp_router.delete("/api/tagging_task/{taskId}", response_model=schemas.CancelTaskResponse)
async def cancel_task(taskId: str, session: AsyncSession = Depends(get_async_session)) -> schemas.CancelTaskResponse:
    """
    Cancel running task
    """
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


@exp_router.get("/api/all_tags", response_model=schemas.GetTagsResponse)
async def get_tags(tagger: WeaviateSearch = Depends(get_search)) -> schemas.GetTagsResponse:
    """
    Retrieve all tags
    """
    response = await tagger.get_all_tags()
    return {"tags_lst": response}

@exp_router.delete("/api/whole_tags", response_model=schemas.RemoveTagsResponse)
async def remove_tags(chosenTagUUIDs: schemas.RemoveTagReq,
                      tagger: WeaviateSearch = Depends(get_search)) -> schemas.RemoveTagsResponse:
    """
    Removes whole tags
    """
    try:
        response = await tagger.remove_tags(chosenTagUUIDs)
        return response
    except Exception as e:
        logging.error(f"{e}")


@exp_router.delete("/api/automatic_tags", response_model=schemas.RemoveTagsResponse)
async def remove_automatic_tags(chosenTagUUIDs: schemas.RemoveTagReq,
                                tagger: WeaviateSearch = Depends(get_search)) -> schemas.RemoveTagsResponse:
    """
    Removes automatic tags
    """
    try:
        response = await tagger.remove_automatic_tags(chosenTagUUIDs)
        return response
    except Exception as e:
        logging.error(f"{e}")


@exp_router.put("/api/tag_approval", response_model=schemas.ApproveTagResponse)
async def approve_selected_tag_chunk(approveData: schemas.ApproveTagReq,
                                     tagger: WeaviateSearch = Depends(get_search)) -> schemas.ApproveTagResponse:
    """
    User approve or disapprove a tag, changes the reference of the tag
    """
    try:
        logging.info("Approving...")
        response = await tagger.approve_tag(approveData)
        logging.info(f"{response}")
        return {"successful": response, "approved": approveData.approved}
    except Exception as e:
        logging.error(f"{e}")
        return {"successful": False, "approved": approveData.approved}


@exp_router.post("/api/filter_tags", response_model=schemas.FilterChunksByTagsResponse)
async def filter_chunks_by_tags(requestedData: schemas.FilterChunksByTagsRequest,
                                tagger: WeaviateSearch = Depends(get_search)) -> schemas.FilterChunksByTagsResponse:
    """
    Filter chunks by given tags and positive or/and automatic flags
    """
    response = await tagger.filterChunksByTags(requestedData)
    return response

@exp_router.post("/api/tagged_texts", response_model=schemas.GetTaggedChunksResponse)
async def get_selected_tags_chunks(chosenTagUUIDs: schemas.GetTaggedChunksReq,
                                   tagger: WeaviateSearch = Depends(get_search)) -> schemas.GetTagsResponse:
    """
    Returns chunks which are tagged by certain type of tag (automatic, positive, negative)
    """
    try:
        logging.info(f"In get tagged text {chosenTagUUIDs}")
        response = await tagger.get_tagged_chunks(chosenTagUUIDs)
        return response
    except Exception as e:
        logging.error(f"{e}")
