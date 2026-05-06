from redis_client import redis_client

# Verify Redis is working
ping_response = redis_client.ping()
print(f"Redis ping: {ping_response}")

# Check if any tasks are stored
tasks = redis_client.keys("celery*")
print(f"Celery-related keys in Redis: {tasks}")