# Tagging worker

The worker processes tagging tasks. The tagging tasks find tags in chunks of documents using LLM.

Celery distributed task queue is selected as the main part of this worker. Redis is used as both the broker and result backend for storing the output of tagging tasks.

Currently set static 2 concurrent workers at the same time.

From semant a user can call the tagging task

TODOs:
- add topicer
- remove the sqlite code
- test

## Setup

To worker on server run:
```
docker compose up --build
```
For development run Redis in Docker and Celery worker directly on your machine:
```
docker compose up redis -d
celery -A worker worker --loglevel=info
```

## Use the Python interactive shell or a test script
```
python -c "
from worker import celery
task = celery.send_task('tag_and_store', args=[{'some': 'data'}, 'test-id-123'])
print(f'Task ID: {task.id}')
"
```
## To check task status
```
python -c "
from tasks.tagging import get_status
status = get_status('test-id-123')
print(status)
"
```