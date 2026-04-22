# Tagging worker

The worker processes tagging tasks. The tagging tasks find tags in chunks of documents using LLM.

Celery distributed task queue is selected as the main part of this worker. Redis is used as both the broker and result backend for storing the output of tagging tasks.

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
