"""Celery client for sending tasks to the tagging worker."""
from celery import Celery
from semant_demo.config import config

celery = Celery(
    "semant_demo",
    broker="pyamqp://guest:guest@localhost//",
    backend=f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}",
)
