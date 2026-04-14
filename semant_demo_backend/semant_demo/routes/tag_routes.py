import os
import logging

from fastapi import APIRouter, Depends, HTTPException, status, Response

from semant_demo import schemas
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction
# from semant_demo.rag.rag_generator import RagGenerator
import asyncio
#import aiofiles # load multiple files simultaneously

from semant_demo.tagging.tagging_utils import tag_and_store
import uuid
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, asc
#import db
from sqlalchemy import exc
from datetime import timezone

import logging

from semant_demo.schemas import Task, TasksBase

import json
import yaml

from semant_demo.tagging.sql_utils import DBError, update_task_status
from semant_demo.tagging.tagging_utils import getTaskByName

#import dependencies
from semant_demo.routes.dependencies import get_async_session, get_engine, get_search
from semant_demo.schema.tags import PatchTag, Tag, PostTag
from semant_demo_backend.semant_demo.weaviate_exceptions import WeaviateOperationError

logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parents[1]
TAG_CONFIG_DIR = BASE_DIR / "tagging" / "configs"
#TAG_CONFIG_DIR = r"semant_demo_backend\semant_demo\tagging\configs"

exp_router = APIRouter()

@exp_router.post("/api/tags", response_model=Tag, status_code=status.HTTP_201_CREATED)
async def create_tag(collection_id: UUID, tag: PostTag, 
                     searcher: WeaviateAbstraction = Depends(get_search)) -> Tag:
    """
    Creates a tag in weaviate db, or not if the same tag already exists
    """
    try:
        return await searcher.tag.create(collection_id=collection_id, tag=tag)
    except WeaviateOperationError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from exc
    
@exp_router.get("/api/tags", response_model=schemas.GetTagsResponse)
async def get_tags(searcher: WeaviateAbstraction = Depends(get_search)) -> schemas.GetTagsResponse:
    """
    Retrieve all tags
    """
    response = await searcher.tag.read_all()
    return {"tags_lst": response}

@exp_router.get("/api/tags/{tag_uuid}", response_model=Tag)
async def get_tag(tag_uuid: UUID, searcher: WeaviateAbstraction = Depends(get_search)) -> Tag:
    """
    Retrieve tag by its id
    """
    response = await searcher.tag.read(tag_uuid)
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tag with id {tag_uuid} not found")
    return response

@exp_router.delete("/api/tags/{tag_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(tag_uuid: UUID,
                      searcher: WeaviateAbstraction = Depends(get_search)) -> None:
    """
    Deletes tag
    """
    await searcher.tag.delete(tag_uuid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@exp_router.patch("/api/tags/{tag_uuid}", response_model=Tag)
async def update_tag(tag_uuid: UUID, tag_update: PatchTag,
                      searcher: WeaviateAbstraction = Depends(get_search)) -> Tag:
    """
    Updates a tag
    """
    try:
        response = await searcher.tag.update(tag_uuid, tag_update)
        return response
    except WeaviateOperationError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from exc

@exp_router.post("/api/tag/task", response_model=schemas.TagStartResponse)
async def start_tagging(tagReq: schemas.TaggingTaskReqTemplate,
                        searcher: WeaviateAbstraction = Depends(get_search),
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

        _, global_async_session_maker = get_engine()

        task = asyncio.create_task(tag_and_store(tagReq, taskId, searcher, global_async_session_maker))
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

@exp_router.get("/api/tag/configs", response_model=schemas.GetConfigsResponse)
async def get_configs() -> schemas.GetConfigsResponse:
    """
    Load all config files
    """
    logging.debug(f"Loading config")
    configs = []
    for file in os.listdir(TAG_CONFIG_DIR):
        if file.endswith((".yml", ".yaml")): # load only yaml files
            file_pth = os.path.join(TAG_CONFIG_DIR, file)
            with open(file_pth, "r", encoding="utf-8") as f:
                configs.append(schemas.TaggingConfig(**yaml.safe_load(f))) # parse into schema
    
    return {"configs": configs}

@exp_router.get("/api/tag/tasks/info")
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

@exp_router.get("/api/tag/task/status/{taskId}")
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


@exp_router.delete("/api/tag/task/{taskId}", response_model=schemas.CancelTaskResponse)
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

@exp_router.delete("/api/tags/automatic", response_model=schemas.RemoveTagsResponse)
async def remove_automatic_tags(chosenTagUUIDs: schemas.RemoveTagReq,
                                searcher: WeaviateAbstraction = Depends(get_search)) -> schemas.RemoveTagsResponse:
    """
    Removes automatic tags
    """
    try:
        response = await searcher.tag.helpers.remove_tag_refs(chosenTagUUIDs, tag_type="automaticTag")
        return response
    except Exception as e:
        logging.error(f"{e}")

@exp_router.put("/api/tag/approve", response_model=schemas.ApproveTagResponse)
async def approve_selected_tag_chunk(approveData: schemas.ApproveTagReq,
                                     searcher: WeaviateAbstraction = Depends(get_search)) -> schemas.ApproveTagResponse:
    """
    User approve a tag, changes the reference of the tag
    """
    try:
        logging.info("Approving...")
        response = await searcher.textChunk.approve_tag(approveData)
        logging.info(f"{response}")
        return {"successful": response, "approved": approveData.approved}
    except Exception as e:
        logging.error(f"{e}")
        return {"successful": False, "approved": approveData.approved}
    
@exp_router.put("/api/tag/disapprove", response_model=schemas.ApproveTagResponse)
async def approve_selected_tag_chunk(approveData: schemas.ApproveTagReq,
                                     searcher: WeaviateAbstraction = Depends(get_search)) -> schemas.ApproveTagResponse:
    """
    User disapprove a tag, changes the reference of the tag
    """
    try:
        logging.info("Approving...")
        response = await searcher.textChunk.disapprove_tag(approveData)
        logging.info(f"{response}")
        return {"successful": response, "approved": approveData.approved}
    except Exception as e:
        logging.error(f"{e}")
        return {"successful": False, "approved": approveData.approved}

@exp_router.post("/api/tags/filter", response_model=schemas.FilterChunksByTagsResponse)
async def filter_chunks_by_tags(requestedData: schemas.FilterChunksByTagsRequest,
                                searcher: WeaviateAbstraction = Depends(get_search)) -> schemas.FilterChunksByTagsResponse:
    """
    Filter chunks by given tags and positive or/and automatic flags
    """
    response = await searcher.textChunk.filterChunksByTags(requestedData, searcher)
    return response

@exp_router.post("/api/tag/textChunks", response_model=schemas.GetTaggedChunksResponse)
async def get_selected_tags_chunks(chosenTagUUIDs: schemas.GetTaggedChunksReq,
                                   searcher: WeaviateAbstraction = Depends(get_search)) -> schemas.GetTagsResponse:
    """
    Returns chunks which are tagged by certain type of tag (automatic, positive, negative)
    """
    try:
        logging.info(f"In get tagged text {chosenTagUUIDs}")
        response = await searcher.textChunk.get_chunks_by_tags(chosenTagUUIDs)
        return response
    except Exception as e:
        logging.error(f"{e}")
