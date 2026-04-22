from worker import celery

task_result = celery.send_task('tag_and_store', args=[
    {"test": "data"},  # tagReq dict
    "test-task-id-123"  # task_id
])
print(f"Task ID: {task_result.id}")
print(f"Task result: {task_result.get(timeout=10)}")