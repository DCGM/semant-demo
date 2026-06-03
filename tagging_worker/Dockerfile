FROM python:3.12-slim

WORKDIR /app

# Copy requirements first for better caching
COPY tagging_worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . .

# Set working directory to the tagging_worker
WORKDIR /app/tagging_worker

CMD ["celery", "-A", "worker", "worker", "--loglevel=info", "--concurrency=2"]