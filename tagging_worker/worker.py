from celery import Celery

celery = Celery("tagging_worker")
celery.config_from_object("celeryconfig")

import tasks.tagging