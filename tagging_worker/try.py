import time
from worker import celery
from tasks.tagging import get_status

task = celery.send_task('tag_and_store', args=[{'some': 'data'}, 'test-id-123'])
print(f'Task ID: {task.id}')

# Check status repeatedly with delays
for i in range(10):
    time.sleep(2)
    status = get_status('test-id-123')
    print(f"[{i+1}] Status: {status}")
    if status and status.get('status') in ['DONE', 'FAILED']:
        print("Task completed or failed!")
        break