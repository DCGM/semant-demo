# Deployment & Configuration

This document is the backend configuration reference and describes a manual standalone setup.
The Docker Compose stacks, CI/CD, previews, Topicer deployment and server setup are documented in
[deploy/README.md](../deploy/README.md). For local development (the seeded local application
started with `make dev-up`, and the optional advanced snapshot workflow), see
[DEVELOPMENT.md](DEVELOPMENT.md).

## Prerequisites

| Component | Version | Notes |
|---|---|---|
| Python | ≥ 3.12 | Backend and embedding service |
| Node.js | 22 | Frontend build (`package.json` engines) |
| Docker + Docker Compose | Latest | Weaviate container |
| GPU (optional for standalone setup) | CUDA-capable | Required for the deployed Qwen embedder and GPU-based Topicer configurations |
| Ollama | Latest | If using local LLM models |

## Service Ports (Defaults)

| Service | Port | Protocol |
|---|---|---|
| Weaviate HTTP | 8080 | REST |
| Weaviate gRPC | 50051 | gRPC |
| Legacy Embedding Service (standalone) | 8001 | HTTP |
| Topicer API (separate service) | 8089 | HTTP |
| Backend API | 8000 | HTTP |
| Frontend (dev) | 9000 | HTTP |
| Ollama | 11434 | HTTP |

---

## Docker / Production Deployment

For server deployments, use the compose files in `deploy/` instead of the manual steps below; see [deploy/README.md](../deploy/README.md). CI/CD deploys production from a `v*.*.*` tag on `main`, a persistent `test-main` instance from `main`, and an ephemeral preview per PR (deployed even when checks fail, with separate preview credentials).

The backend image installs `semant_demo_backend/requirements-runtime.lock` with `--require-hashes`: the same Python package versions that CI tests, with no resolution at build time (see [CONTRIBUTING.md](../CONTRIBUTING.md) for updating the locks). To audit a running instance, run `docker compose -p <project> -f <compose file> exec app python -m pip freeze --user` and compare it with the lock. The lock does not freeze the floating `python:3.12` / `python:3.12-slim` base images (OS packages and patch release). Production uses a pinned vLLM image and model revision for Qwen embeddings ([deploy/README](../deploy/README.md#qwen-embedding-service-385)), not the legacy `deploy/Dockerfile.embedder` (which still installs unpinned requirements). Topicer is built separately from upstream `main` with independently resolved dependencies ([Topicer deployment](../deploy/README.md#topicer)); it is not covered by the backend lock.

---

## Manual Standalone Setup

This section builds a standalone environment from scratch, e.g. to construct a corpus database
on a server. It is not needed for development: run the application locally with the seeded
environment (`make dev-up`, [DEVELOPMENT.md](DEVELOPMENT.md#1-quick-start-the-seeded-local-application)),
which also covers test-owned stores. Working against a copy of real data is the separate,
explicitly authorized [snapshot workflow](DEVELOPMENT.md#5-advanced-an-authorized-realistic-snapshot).

### 1. Weaviate

Start an empty Weaviate for building a database:

```bash
cd weaviate_utils
docker compose up -d
```

Data is persisted to `./weaviate_db`. The compose file enables anonymous access and configures
HNSW indexing. It pins Weaviate **1.40.1**, the version of the deployments, the test stores and
the local development environment.

To verify:

```bash
curl http://localhost:8080/v1/.well-known/ready
```

It publishes the default ports 8080/50051, which a running snapshot Weaviate also uses; the
development Weaviate of `make dev-up` uses 8180/50151 and does not conflict.

### 2. Data Ingestion

Load documents and chunks with `weaviate_utils/db_insert_jsonl.py`; the input format and
options are in [DATABASE.md](DATABASE.md#data-ingestion). The script connects to
`localhost:8080`, and `--delete-old` drops and recreates the collections: verify the endpoint
first.

### 3. Embedding Service

This runs the **former** Gemma service, which the default `configs/search_vectors.yaml` targets. The deployed embedder is Qwen3-Embedding-0.6B on vLLM ([deploy/README](../deploy/README.md#qwen-embedding-service-385)); use it with `SEARCH_VECTORS_CONFIG` pointing at `configs/search_vectors_qwen.yaml` (adjust its `base_url`).

```bash
cd embedding_service
pip install -r requirements.txt
# Optionally set model:
export GEMMA_MODEL="BAAI/bge-multilingual-gemma2"
python run.py
```

Runs on port 8001. First startup downloads the model (~4 GB). GPU is recommended for reasonable latency.

### 4. Ollama (for local LLM)

```bash
# Install Ollama: https://ollama.ai
ollama pull gemma3:12b
ollama serve
```

`OLLAMA_URLS` accepts a comma-separated list, but only the first URL is used; a tier in `configs/llm_models.yaml` may also set its own endpoint.

### 5. Backend

```bash
cd semant_demo_backend
pip install --require-hashes -r requirements-runtime.lock
python run.py
```

`run.py` starts `uvicorn` in reload mode on `PORT` (8000) for local development. The Docker image runs `python -m uvicorn semant_demo.main:app --host 0.0.0.0 --port $PORT` without the reloader. On startup the application:
1. Creates missing SQL tables (`user`, `rag_user_feedback`, the LLM quota ledger `llm_quota_day`, `llm_quota_operation`, `llm_quota_call`, and `annotation_tenant_activity`); existing tables and rows are kept
2. Connects to Weaviate (startup fails if it is not ready) and logs an error when the multi-tenant `Annotation` collection does not exist; it never creates or migrates it ([annotation migration](DATA_MAINTENANCE.md#annotation-migration-annotation_migration-327))
3. Loads all RAG configurations from `RAG_CONFIGS_PATH` (default `configs/rag/demo_configs/*.yaml`)
4. Mounts static files from `STATIC_PATH` if the directory exists

### 6. Frontend

#### Development

```bash
cd semant_demo_frontend
npm ci
npx quasar dev
```

#### Production Build

```bash
npx quasar build
```

Output goes to `dist/spa/`. To serve from the backend, copy to the backend's `STATIC_PATH`:

```bash
cp -r dist/spa/* ../semant_demo_backend/static/
```

The backend's `main.py` will auto-mount the directory and serve the SPA.

#### Frontend Environment

Set `BACKEND_URL` environment variable before building to point to your backend:

```bash
BACKEND_URL=https://your-server.example.com npx quasar build
```

If unset, `quasar.config.js` uses `http://localhost:8000`, which only suits local development. Every API request (generated client and NDJSON streams) goes to `BACKEND_URL` + `/api/...` (`src/shared/api/config.ts`).

---

## Environment Variables Reference

### Backend (`semant_demo_backend`)

`semant_demo/config.py` reads these once at startup. Paths default to files inside the
`semant_demo` package. Docker deployments set them in `deploy/.env` (templates:
`deploy/.env.example`, `deploy/.env.test.example`).

| Variable | Default | Description |
|---|---|---|
| `WEAVIATE_HOST` / `WEAVIATE_REST_PORT` / `WEAVIATE_GRPC_PORT` | `localhost` / `8080` / `50051` | Weaviate endpoint |
| `EMBEDDING_SERVICE_HOST` / `EMBEDDING_SERVICE_PORT` | `embedding-service` / `8001` | Embedding service endpoint |
| `SQL_DB_URL` | `sqlite+aiosqlite:///tasks.db` | User accounts, RAG answer feedback and the daily LLM allowance ledger; the default is `tasks.db` in the working directory (the name is historical). The app Compose files set `sqlite+aiosqlite:////app/sql_data/tasks.db`, in the mounted instance directory that also holds the rollback journal ([deploy/README](../deploy/README.md#sqlite-database-directory-406)) |
| `JWT_SECRET` | placeholder | **Must be overridden** with a long random string outside local development; tokens are valid for 7 days |
| `ALLOWED_ORIGIN` | `http://localhost:9000` | CORS origin of the frontend |
| `PORT` | `8000` | Listen port of `run.py` and of the Docker image's uvicorn |
| `STATIC_PATH` | `./static` | Built frontend served by the backend when the directory exists |
| `LOG_LEVEL` | `INFO` | Python and OTLP log level |
| `LLM_MODELS_CONFIG` | `configs/llm_models.yaml` | Server-side model, reasoning profile, temperature support, price estimate (or `local_rate` of a self-hosted tier), permitted feature tiers and per-feature limits ([ARCHITECTURE.md](ARCHITECTURE.md#llm-gateway-adaptersllm)). Shipped tiers use OpenRouter; see [the October 2026 review](LLM_MODEL_SELECTION_2026-10.md). |
| `LLM_TIMEOUT_SECONDS` / `LLM_MAX_RETRIES` | `120` / `1` | Timeout and SDK retries of one LLM provider request (Ollama does not retry) |
| `OPENAI_API_KEY` / `OPENAI_API_URL` | empty / `https://openrouter.ai/api/v1` | **OpenRouter key and endpoint required by all shipped LLM tiers.** The adapter is OpenAI-compatible; override the endpoint only when custom models/credentials support it. |
| `OLLAMA_URLS` | `http://localhost:11434` | Default endpoint of `ollama` tiers (only the first URL is used) |
| `GOOGLE_API_KEY` | empty | Key of `google` tiers |
| `RAG_CONFIGS_PATH` | `configs/rag/demo_configs` | Directory of the RAG configurations offered to users |
| `LLM_QUOTA_GUEST_DAILY_USD` / `LLM_QUOTA_ACCOUNT_DAILY_USD` | `0.25` / `1.00` | Daily (UTC) LLM allowance of a guest and of a signed-in account, in USD-equivalent estimates, not a bill; provisional test values ([ARCHITECTURE.md](ARCHITECTURE.md#daily-llm-allowances-featuresquota-adapterssqlquotapy)). Must be positive |
| `LLM_QUOTA_NEAR_LIMIT_RATIO` | `0.8` | Share of the allowance used from which `GET /api/quota` reports `near_limit` |
| `LLM_QUOTA_GUEST_COOKIE_DAYS` / `LLM_QUOTA_GUEST_COOKIE_SECURE` | `30` / https `ALLOWED_ORIGIN` | Lifetime of the guest identity cookie (`semant_guest`); whether it is sent over HTTPS only |
| `RAG_HISTORY_LIMIT` | `20` | Most recent RAG/Explain chat history messages sent to the model |
| `SEARCH_SUMMARIZER_CONFIG` | `configs/search_summarizer.yaml` | Summary prompts, fallbacks, options and `max_generated_results` (results of one search that get titles and per-result summaries) |
| `SEARCH_FILTERS_CONFIG` | `configs/search_filters.yaml` | Search filters ([SEARCH_FILTERS.md](SEARCH_FILTERS.md)) |
| `SEARCH_VECTORS_CONFIG` | `configs/search_vectors.yaml` | Weaviate named vectors Search and RAG may query, their query embedding and the default ([ARCHITECTURE.md](ARCHITECTURE.md#search-pipeline)); validated at startup. List a vector only after it is populated in the chunk collection |
| `ANNOTATION_VECTOR_CONFIG` | `configs/annotation_vector.yaml` | Contextual vector of span annotations (#328): its `id`, Weaviate `target_vector`, input template and embedding ([ARCHITECTURE.md](ARCHITECTURE.md#annotation-derived-data-328)); validated at startup; empty configures none. Used only once the annotation collection has the vector ([DATA_MAINTENANCE.md](DATA_MAINTENANCE.md#annotation-derived-data-annotation_enrichment-328)) |
| `EMBEDDING_API_KEY` | (empty) | Bearer key sent to the OpenAI-compatible embedding endpoints of search vectors; empty sends none |
| `TOPICER_URL` / `TOPICER_CONFIG_NAME` / `TOPICER_TIMEOUT` | `http://topicer:8089` / `openai` / `600` | External Topicer span-proposal service; deployed separately ([Topicer deployment](../deploy/README.md#topicer)) |
| `TOPICER_MAX_CHUNKS_PER_TAG` | `40` | Most chunks one optimized AI suggestion run evaluates per tag, sent to Topicer as `max_chunks` (backend policy; the frontend reads it from document stats for its size warning). Positive integer; must not exceed the Topicer config's `max_chunks_ceiling` (default 200), which Topicer answers with 422 |
| `TOPICER_RESERVE_USD_PER_CHUNK` | `0.005` | Daily-allowance reservation for one Topicer chunk evaluation (a thorough chunk; an optimized tag reserves it × `TOPICER_MAX_CHUNKS_PER_TAG`); unknown Topicer usage is charged at least this. Must be positive ([ARCHITECTURE.md](ARCHITECTURE.md#daily-llm-allowances-featuresquota-adapterssqlquotapy)) |
| `ANNOTATION_TENANT_TOUCH_SECONDS` | `60` | How often (at most, per tenant and process) a use of a collection's annotation tenant is recorded in `annotation_tenant_activity`; long operations repeat it at this interval |
| `ANNOTATION_TENANT_IDLE_SECONDS` / `ANNOTATION_TENANT_DEACTIVATION_ENABLED` | `3600` / `false` | Idle time after which `maintenance.annotation_tenants deactivate-idle` deactivates a tenant, and whether it may (keep `false` until rehearsed, [DATA_MAINTENANCE.md](DATA_MAINTENANCE.md#annotation-tenants-annotation_tenants-327)) |
| `SPAN_CHAT_TEMPERATURE` / `SPAN_CHAT_MAX_TOKENS` | `0.4` / `1024` | Span discussion replies (`span_chat` tier; the tokens are capped by its `max_output_tokens`) |
| `SPAN_CHAT_CONTEXT_CHARS` / `SPAN_CHAT_HISTORY_LIMIT` | `1500` / `20` | Context window around the span; chat messages forwarded |
| `CORPUS_OVERVIEW_MAX_AGE` | `600` | Seconds a computed corpus overview (`/api/analytics/corpus/overview`) is served again before it is recomputed; `0` computes it on every request |
| `FEEDBACK_LOG_PATH` | `semant_demo/feedback.log.jsonl` | JSONL file receiving in-app feedback. An empty value means the default. Deployed instances use `/app/feedback/feedback.log.jsonl`, a host directory mounted from the instance data ([deploy/README](../deploy/README.md#in-app-feedback-storage)) |
| `FEEDBACK_WEBHOOK_URL` | empty | Optional webhook that also receives in-app feedback |
| `OTEL_ENABLED`, `OTEL_*`, `DEPLOYMENT_ENVIRONMENT` | off | Telemetry export; see [OBSERVABILITY.md](OBSERVABILITY.md#runtime-configuration) |

A tier whose provider has no key refuses calls before sending them. `PRODUCTION` is read but
not used. `LANGCHAIN_API_KEY` in the `.env` templates is not read by the application; LangChain
uses it only if LangSmith tracing is enabled (`LANGCHAIN_TRACING_V2`), which would send
prompts and texts to LangSmith. `SQL_DB_PATH` and the build arguments are used by Docker
Compose only ([deploy/README.md](../deploy/README.md#environment-variables)).

### Embedding Service (former Gemma service)

| Variable | Default | Description |
|---|---|---|
| `GEMMA_MODEL` | `BAAI/bge-multilingual-gemma2` | Sentence-transformer model name |

---

## Debugging

### Backend

- Run with `uvicorn` reload mode (default in `run.py`, not used by the Docker image): changes auto-reload
- FastAPI auto-generates interactive docs at `http://localhost:8000/docs` (Swagger) and `http://localhost:8000/redoc`
- Enable debug logging with `LOG_LEVEL=DEBUG` (RAG pipeline progress is logged at `DEBUG`)
- Check Weaviate connectivity: `curl http://localhost:8080/v1/.well-known/ready`
- Inspect DB state: `python weaviate_utils/inspect_chunks.py` / `inspect_documents.py`

### Frontend

- Vue DevTools browser extension for component/store inspection
- Quasar dev mode includes HMR and source maps
- Network tab to inspect API calls and responses

### RAG Debugging

- Each RAG config can be tested independently by sending requests to `POST /api/rag` with the config's `id`
- `python -m semant_demo.features.rag.run_demo` runs one configuration without the application (it calls the configured Weaviate, embedding service and providers)
- Route tests use the `TestRag` class (a fixed answer, no retrieval or model calls)

### AI Suggestion Debugging

- Suggestion runs are request-scoped NDJSON streams (`/api/ai/suggest_spans/*`); the last line is an `end` event with the outcome and counts (saved, rejected, failed saves, provider failures). A stream without it was interrupted.
- Saved suggestions are ordinary `auto` spans; reload them with `GET /api/tag_spans?collection_id=...`.

---

## Production Considerations

1. **No reload mode** — `run.py` runs uvicorn with `reload=True` for development; outside Docker run `uvicorn semant_demo.main:app` instead, as the image does
2. **Configure CORS** — set `ALLOWED_ORIGIN` to your actual frontend domain
3. **Use HTTPS** — put a reverse proxy (nginx, Caddy) in front of the backend
4. **One backend process** — chunk tag synchronization is serialized only within one process ([TODO.md](TODO.md#correctness-and-behavior)); SQLite holds only user accounts, RAG feedback, the LLM quota ledger (its admissions are atomic across connections) and the annotation tenant activity record
5. **Weaviate backups** — use Weaviate's backup API or snapshot the `weaviate_db` volume
6. **Annotation migration before #327** — the first release with multi-tenant annotation storage reads and writes only `Annotation`. Every store it runs on (production, the shared test store of `test-main` and the PR previews) needs the operator-run migration during a write pause first ([cutover](DATA_MAINTENANCE.md#cutover-production-test-store)); otherwise annotations appear empty and cannot be saved
7. **SQLite backups** — back up `tasks.db` (users, feedback, LLM quota) separately; production uses a daily host cron job with `sqlite3 .backup` ([deploy/README](../deploy/README.md#sqlite-backup-399))
8. **Embedding service** — the deployed embedder is Qwen3-Embedding-0.6B on vLLM (`deploy/docker-compose.embedder.yml`, #385), reached through an `openai` search vector (`configs/search_vectors_qwen.yaml`); settings and cutover order: [deploy/README](../deploy/README.md#qwen-embedding-service-385). `EMBEDDING_SERVICE_HOST` / `EMBEDDING_SERVICE_PORT` locate the former Gemma service (`embedding_service/`, the `embedding_service` provider of the default `search_vectors.yaml`).