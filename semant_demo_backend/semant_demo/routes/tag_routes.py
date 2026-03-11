import os
import logging
import asyncio
import uuid
import json
import yaml
from pathlib import Path
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, asc, exc

from semant_demo import schemas
from semant_demo.schemas import Task, TasksBase
from semant_demo.weaviate_tag import WeaviateSearchAndTag
from semant_demo.tagging.redis_client import redis_client
from semant_demo.tagging.celery_client import celery
from semant_demo.tagging.sql_utils import DBError, update_task_status
from semant_demo.tagging.tagging_task import getTaskByName
from semant_demo.routes.dependencies import get_async_session, get_tag, get_engine

logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parents[1]
TAG_CONFIG_DIR = BASE_DIR / "tagging" / "configs"
#TAG_CONFIG_DIR = r"semant_demo_backend\semant_demo\tagging\configs"

exp_router = APIRouter()

@exp_router.post("/api/tag", response_model=schemas.CreateResponse)
async def create_tag(tagReq: schemas.TagReqTemplate, tagger: WeaviateSearchAndTag = Depends(get_tag),
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
async def start_tagging(tagReq: schemas.TaggingTaskReqTemplate,
                        session: AsyncSession = Depends(get_async_session)):
    """
    Queues a tagging task to the Celery worker.
    Task status is tracked in Redis.
    """
    task_id = str(uuid.uuid4())

    # Write initial state to Redis
    redis_client.set(
        f"task:{task_id}",
        json.dumps({"status": "PENDING", "task_id": task_id}),
        ex=86400  # 24h TTL
    )

    # Send task to Celery worker via RabbitMQ
    celery.send_task(
        "tag_and_store",
        args=[tagReq.model_dump(), task_id],
        queue="default"
    )
    
    return {"job_started": True, "task_id": task_id, "message": "Tagging task queued"}


@exp_router.get("/api/tagging_task/{task_id}")
async def get_task_status(task_id: str):
    """
    Get the status of a tagging task from Redis.
    """
    raw = redis_client.get(f"task:{task_id}")
    if not raw:
        raise HTTPException(status_code=404, detail="Task not found")
    return json.loads(raw)


@exp_router.get("/api/configs", response_model=schemas.GetConfigsResponse)
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
async def get_tags(tagger: WeaviateSearchAndTag = Depends(get_tag)) -> schemas.GetTagsResponse:
    """
    Retrieve all tags
    """
    response = await tagger.get_all_tags()
    return {"tags_lst": response}

@exp_router.delete("/api/whole_tags", response_model=schemas.RemoveTagsResponse)
async def remove_tags(chosenTagUUIDs: schemas.RemoveTagReq,
                      tagger: WeaviateSearchAndTag = Depends(get_tag)) -> schemas.RemoveTagsResponse:
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
                                tagger: WeaviateSearchAndTag = Depends(get_tag)) -> schemas.RemoveTagsResponse:
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
                                     tagger: WeaviateSearchAndTag = Depends(get_tag)) -> schemas.ApproveTagResponse:
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
                                tagger: WeaviateSearchAndTag = Depends(get_tag)) -> schemas.FilterChunksByTagsResponse:
    """
    Filter chunks by given tags and positive or/and automatic flags
    """
    response = await tagger.filterChunksByTags(requestedData)
    return response

@exp_router.post("/api/tagged_texts", response_model=schemas.GetTaggedChunksResponse)
async def get_selected_tags_chunks(chosenTagUUIDs: schemas.GetTaggedChunksReq,
                                   tagger: WeaviateSearchAndTag = Depends(get_tag)) -> schemas.GetTagsResponse:
    """
    Returns chunks which are tagged by certain type of tag (automatic, positive, negative)
    """
    try:
        logging.info(f"In get tagged text {chosenTagUUIDs}")
        response = await tagger.get_tagged_chunks_paged(chosenTagUUIDs) #get_tagged_chunks_limited(chosenTagUUIDs)#
        return response
    except Exception as e:
        logging.error(f"{e}")
