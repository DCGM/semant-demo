from celery import Celery
from tagging_worker import worker

# Or directly:
import sys
sys.path.insert(0, 'c:\\Users\\marti\\Music\\semant_tagging\\semant-demo\\tagging_worker')
from worker import celery

# Check active workers
inspect = celery.control.inspect()
stats = inspect.stats()
print("Active workers:", stats)

# Check if worker is responsive
active_tasks = inspect.active()
print("Active tasks:", active_tasks)