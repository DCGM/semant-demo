from worker import celery

# Send a simple test task
result = celery.send_task('celery.ping')
print(f"Ping result: {result.get(timeout=5)}")