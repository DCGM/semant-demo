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