# List active workers
celery -A worker inspect active_queues

# Check worker stats
celery -A worker inspect stats

# Check if a specific task is running
celery -A worker inspect active

# Monitor worker in real-time
celery -A worker events

# Check reserved/scheduled tasks
celery -A worker inspect reserved