
FROM alpine AS git
LABEL project=semant-demo

RUN apk add --no-cache git 

ARG REPO=https://github.com/DCGM/semant-demo.git
ARG BRANCH=main
# Full commit SHA to build. CI sets it to the commit the deploy run is for (the same commit its
# deploy files come from), so a later push to BRANCH cannot change what is deployed.
# Empty: build the current tip of BRANCH.
ARG COMMIT=

RUN if [ -n "${COMMIT}" ]; then \
        git init -q /tmp/repo && \
        git -C /tmp/repo fetch --depth 1 "${REPO}" "${COMMIT}" && \
        git -C /tmp/repo checkout -q FETCH_HEAD && \
        test "$(git -C /tmp/repo rev-parse HEAD)" = "${COMMIT}"; \
    else \
        git clone --branch "${BRANCH}" --depth 1 "${REPO}" /tmp/repo; \
    fi


# The frontend is built from the committed generated API client (src/generated/api), which
# CI checks against a fresh generation (api-client-drift); it is not regenerated here.
FROM node:22.23.4-bookworm@sha256:18a6d90fd60542269850c80ca03b29b1d9b14d6b221ac7ee8e35b0d33ef904bd AS node-build
COPY --from=git /tmp/repo/ /repo/
WORKDIR /repo/semant_demo_frontend
RUN npm ci
ARG BACKEND_URL
RUN BACKEND_URL=${BACKEND_URL} npx quasar build



FROM python:3.12 AS python-builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ build-essential && \
    rm -rf /var/lib/apt/lists/*
# Install the hashed runtime lock, which pins the same versions as the CI-tested dev lock;
# --require-hashes also rejects any dependency the lock does not pin, so nothing is resolved
# here. requirements.txt only declares the direct dependencies (#139).
COPY --from=git /tmp/repo/semant_demo_backend/requirements-runtime.lock /tmp/requirements-runtime.lock
RUN pip install --user --no-cache-dir --require-hashes -r /tmp/requirements-runtime.lock && \
    pip check



FROM python:3.12-slim AS backend
COPY --from=python-builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
COPY --from=git /tmp/repo/semant_demo_backend /app
COPY --from=node-build /repo/semant_demo_frontend/dist/spa /app/static
WORKDIR /app
# Production server without the reloader (#298); run.py is the local development entry point.
ENTRYPOINT ["sh", "-c", "exec python -m uvicorn semant_demo.main:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
