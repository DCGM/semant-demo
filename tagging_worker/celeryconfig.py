import sys
# for development on windows - solves PermissionError error
if sys.platform == 'win32':
    worker_pool = 'solo'
# broker and backend settings
broker_url = 'pyamqp://guest@localhost//'
result_backend = 'redis://localhost'

task_serializer = 'json'
result_serializer = 'json'
accept_content = ['json']
timezone = 'Europe/Prague'
enable_utc = True