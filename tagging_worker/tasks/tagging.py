"""""
import logging
from worker import celery

logger = logging.getLogger(__name__)

@celery.task(name="tag_and_store", bind=True)
def tag_and_store(self, tagReq: dict, task_id: str):
    logger.info(f"Starting task {task_id}: {tagReq}")

    # Initialize clients here (separate process — no shared state from FastAPI)
    # from semant_demo.weaviate_tag import WeaviateSearchAndTag
    # tagger = WeaviateSearchAndTag(...)
    # tagger.run(tagReq, task_id)

    # Update SQLite task status via sync SQLAlchemy
    # update_task_status_sync(task_id=task_id, status="DONE")

    return {"status": "done", "task_id": task_id}
"""

import os
import re
import logging
import json
from celery import Task
from weaviate.classes.query import Filter, QueryReference
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from worker import celery
from worker.redis_client import redis_client
from semant_demo import schemas
from semant_demo.config import config

logger = logging.getLogger(__name__)

PAGE_LIMIT = 100
POSITIVE_RESPONSES = re.compile("^(True|Ano|Áno)", re.IGNORECASE)


def redis_key(task_id: str) -> str:
    return f"task:{task_id}"


def set_status(task_id: str, status: str, **kwargs):
    """Write task state to Redis."""
    data = {"status": status, "task_id": task_id, **kwargs}
    redis_client.set(redis_key(task_id), json.dumps(data), ex=86400)  # TTL 24h


def get_status(task_id: str) -> dict:
    raw = redis_client.get(redis_key(task_id))
    return json.loads(raw) if raw else {}


def get_processed_ids(task_id: str) -> set:
    """Return chunk UUIDs already processed — used for resuming."""
    raw = redis_client.get(f"task:{task_id}:processed")
    return set(json.loads(raw)) if raw else set()


def mark_processed(task_id: str, chunk_id: str):
    key = f"task:{task_id}:processed"
    raw = redis_client.get(key)
    ids = json.loads(raw) if raw else []
    ids.append(chunk_id)
    redis_client.set(key, json.dumps(ids), ex=86400)


@celery.task(name="tag_and_store", bind=True, max_retries=3)
def tag_and_store(self: Task, tag_req: dict, task_id: str):
    """
    Sync Celery task — no asyncio, no SQLAlchemy.
    Redis tracks status and processed chunk IDs for crash recovery.
    """
    logger.info(f"Starting task {task_id}")
    set_status(task_id, "RUNNING", processed=0, total=0)

    try:
        req = schemas.TaggingTaskReqTemplate(**tag_req)

        # --- Build LangChain chain ---
        prompt = ChatPromptTemplate.from_template(
            req.task_config.prompt_template or config.DEFAULT_TAG_TEMPLATE
        )
        model_name = req.task_config.params.model_name
        temperature = req.task_config.params.temperature

        if req.task_config.params.model_type == schemas.APIType.openai:
            model = ChatOpenAI(
                model=model_name or config.OPENAI_MODEL,
                api_key=os.getenv("OPENAI_API_KEY", ""),
                temperature=temperature,
            )
        else:
            from semant_demo.ollama_proxy import OllamaProxyRunnable
            model = OllamaProxyRunnable()
            model.set_model(model_name)
            model.set_temperature(temperature)

        chain = prompt | model

        # --- Connect to Weaviate (sync) ---
        import weaviate
        weaviate_client = weaviate.connect_to_local(
            host=config.WEAVIATE_HOST,
            port=config.WEAVIATE_PORT,
        )
        chunks_col = weaviate_client.collections.get("Chunks")

        # --- Prepare tag ---
        tag_uuid = _add_or_get_tag_sync(weaviate_client, req)

        # --- Fetch all chunks (paged) ---
        filters = Filter.by_ref(link_on="userCollection").by_property("name").equal(req.collection_name)
        already_tagged_filter = (
            Filter.by_ref(link_on="automaticTag").by_id().equal(tag_uuid) |
            Filter.by_ref(link_on="positiveTag").by_id().equal(tag_uuid) |
            Filter.by_ref(link_on="negativeTag").by_id().equal(tag_uuid)
        )

        all_objects = []
        already_tagged_ids = set()
        offset = 0

        while True:
            page = chunks_col.query.fetch_objects(
                limit=PAGE_LIMIT, offset=offset,
                return_properties=["text"],
                return_references=[
                    QueryReference(link_on="automaticTag", return_properties=[]),
                    QueryReference(link_on="positiveTag", return_properties=[]),
                    QueryReference(link_on="negativeTag", return_properties=[]),
                ],
                filters=filters,
            )
            tagged_page = chunks_col.query.fetch_objects(
                limit=PAGE_LIMIT, offset=offset,
                return_properties=["text"],
                filters=already_tagged_filter,
                return_references=[
                    QueryReference(link_on="automaticTag", return_properties=[]),
                ],
            )
            if not page.objects:
                break
            all_objects.extend(page.objects)
            already_tagged_ids.update(obj.uuid for obj in tagged_page.objects)
            offset += PAGE_LIMIT

        # Exclude already tagged
        to_process = [o for o in all_objects if o.uuid not in already_tagged_ids]

        # Exclude chunks already done in a previous (crashed) run
        previously_processed = get_processed_ids(task_id)
        to_process = [o for o in to_process if str(o.uuid) not in previously_processed]

        total = len(to_process) + len(previously_processed)
        processed_count = len(previously_processed)
        tag_processing_data = []

        set_status(task_id, "RUNNING", processed=processed_count, total=total)
        logger.info(f"Task {task_id}: {len(to_process)} chunks to process, {processed_count} already done")

        # --- Process chunks ---
        for obj in to_process:
            try:
                text = obj.properties["text"]
                result = chain.invoke({  # sync — no asyncio
                    "tag_name": req.tag_name,
                    "tag_definition": req.tag_definition,
                    "tag_examples": req.tag_examples,
                    "content": text,
                })

                tag_text = result.content if req.task_config.params.model_type == schemas.APIType.openai else str(result)

                if POSITIVE_RESPONSES.search(tag_text):
                    refs = obj.references.get("automaticTag") if obj.references else None
                    already_has_ref = (
                        refs and getattr(refs, "objects", None) and
                        any(str(t.uuid) == str(tag_uuid) for t in refs.objects)
                    )
                    if not already_has_ref:
                        chunks_col.data.reference_add(
                            from_uuid=obj.uuid,
                            from_property="automaticTag",
                            to=tag_uuid,
                        )

                tag_processing_data.append({
                    "chunk_id": str(obj.uuid),
                    "text": text,
                    "tag": tag_text,
                })
                mark_processed(task_id, str(obj.uuid))
                processed_count += 1

                # Update progress in Redis
                set_status(task_id, "RUNNING",
                           processed=processed_count, total=total,
                           collection_name=req.collection_name,
                           tag_id=str(tag_uuid))

                logger.info(f"Task {task_id}: {processed_count}/{total}")

            except Exception as e:
                logger.error(f"Chunk {obj.uuid} failed: {e}")
                # continue — don't kill the whole task for one bad chunk

        weaviate_client.close()

        set_status(task_id, "COMPLETED",
                   processed=processed_count, total=total,
                   collection_name=req.collection_name,
                   tag_id=str(tag_uuid),
                   tag_processing_data=tag_processing_data)

        logger.info(f"Task {task_id} completed: {processed_count}/{total}")
        return {"status": "COMPLETED", "task_id": task_id}

    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        set_status(task_id, "FAILED", error=str(e))
        raise self.retry(exc=e, countdown=10)


def _add_or_get_tag_sync(client, req: schemas.TaggingTaskReqTemplate):
    """Sync version of add_or_get_tag — adjust to match your existing logic."""
    from semant_demo.weaviate_tag import WeaviateSearchAndTag
    # Re-use existing logic if it's already sync-compatible, otherwise inline it here
    tagger = WeaviateSearchAndTag.__new__(WeaviateSearchAndTag)
    tagger.client = client
    import asyncio
    return asyncio.run(tagger.add_or_get_tag(req))  # only async call left — isolate here