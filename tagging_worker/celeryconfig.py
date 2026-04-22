import os

# broker and backend settings
redis_host = os.getenv("REDIS_HOST", "localhost")
broker_url = f'redis://{redis_host}:6379/0'
result_backend = f'redis://{redis_host}'

task_serializer = 'json'
result_serializer = 'json'
accept_content = ['json']
timezone = 'Europe/Prague'
enable_utc = True

