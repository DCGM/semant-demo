
FROM alpine AS git

RUN apk add --no-cache git 

ARG REPO=https://github.com/DCGM/semant-demo.git
ARG BRANCH=main
ARG NOW=x

RUN mkdir -p /tmp/repo && \
    git clone ${REPO} /tmp/repo && \
    cd /tmp/repo && \
    git checkout ${BRANCH} && \
    git pull


FROM python:3.12-slim AS embedding-service
COPY --from=git /tmp/repo/embedding_service /app/embedding_service
WORKDIR /app/embedding_service
RUN pip install --no-cache-dir -r requirements.txt
ENTRYPOINT ["python", "run.py"]


FROM python:3.12-slim AS backend-openapi
COPY --from=git /tmp/repo/semant_demo_backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY --from=git /tmp/repo/semant_demo_backend /app
WORKDIR /app
RUN python export_openapi.py --output /tmp/openapi.json


FROM node:22 AS node-build
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jre-headless && \
    rm -rf /var/lib/apt/lists/*
RUN npm install -g @quasar/cli
COPY --from=git /tmp/repo/ /repo/
WORKDIR /repo/semant_demo_frontend
RUN npm install
COPY --from=backend-openapi /tmp/openapi.json /repo/semant_demo_backend/openapi.json
RUN npm run sync-client
ARG BACKEND_URL
RUN BACKEND_URL=${BACKEND_URL} npx quasar build



FROM python:3.12 AS python-builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ build-essential && \
    rm -rf /var/lib/apt/lists/*
COPY --from=git /tmp/repo/semant_demo_backend/requirements.txt /tmp/requirements.txt
RUN pip install --user --no-cache-dir -r /tmp/requirements.txt



FROM python:3.12-slim AS backend
COPY --from=python-builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
COPY --from=git /tmp/repo/semant_demo_backend /app
COPY --from=node-build /repo/semant_demo_frontend/dist/spa /app/static
WORKDIR /app
ENTRYPOINT ["python", "run.py"]
