# Tagging celery app
from celery import Celery
from semant_demo import schemas
import logging

logging.basicConfig(filename='celery.log', level=logging.INFO)

celery = Celery(__name__, broker="redis://localhost:6379/0")

@celery.task(name="tag_and_store")
def tag_and_store(tagReq: dict):
    # load from weaviate
    # process using llm
    # store result in the weaviate db
    logging.info(f"Starting task with data: {str(tagReq)}")
    import time
    time.sleep(10)
    logging.info("In tag task")
    logging.info(str(tagReq))
    print('Task finished')
    return True

if __name__ == "__main__":
    result = tag_and_store.delay({
        "tag": "test",
        "description": "test",
        "examples": ["test1"]
    })
    print(f"Task ID: {result.id}")