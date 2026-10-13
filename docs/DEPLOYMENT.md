# Deployment & Configuration

This document is the backend configuration reference and describes a manual standalone setup.
The Docker Compose stacks, CI/CD, previews and server setup are documented in
[deploy/README.md](../deploy/README.md). For local development, including the local Weaviate
and SQLite snapshot, see [DEVELOPMENT.md](DEVELOPMENT.md).

## Prerequisites

| Component | Version | Notes |
|---|---|---|
| Python | ≥ 3.12 | Backend and embedding service |
| Node.js | 22 | Frontend build (`package.json` engines) |
| Docker + Docker Compose | Latest | Weaviate container |
| GPU (optional) | CUDA-capable | Recommended for embedding service |
| Ollama | Latest | If using local LLM models |

## Service Ports (Defaults)

| Service | Port | Protocol |
|---|---|---|
| Weaviate HTTP | 8080 | REST |
| Weaviate gRPC | 50051 | gRPC |
| Embedding Service | 8001 | HTTP |
| Backend API | 8000 | HTTP |
| Frontend (dev) | 9000 | HTTP |
| Ollama | 11434 | HTTP |

---

## Docker / Production Deployment

For server deployments, use the compose files in `deploy/` instead of the manual steps below; see [deploy/README.md](../deploy/README.md). CI/CD deploys production from a `v*.*.*` tag on `main`, a persistent `test-main` instance from `main`, and an ephemeral preview per PR (deployed even when checks fail, with separate preview credentials).

The backend image installs `semant_demo_backend/requirements-runtime.lock` with `--require-hashes`: the same Python package versions that CI tests, with no resolution at build time (see [CONTRIBUTING.md](../CONTRIBUTING.md) for updating the locks). To audit a running instance, run `docker compose -p <project> -f <compose file> exec app python -m pip freeze --user` and compare it with the lock. The lock does not freeze the floating `python:3.12` / `python:3.12-slim` base images (OS packages and patch release), nor the separate embedding service image (`deploy/Dockerfile.embedder`), which still installs unpinned requirements.

---

## Manual Standalone Setup

For local development and test-owned database rules, see [DEVELOPMENT.md](DEVELOPMENT.md).

The steps below describe how to construct a standalone environment from scratch.

### 1. Weaviate

For normal development, use the local database snapshot under `local_data/` and start Weaviate as described in [DEVELOPMENT.md](DEVELOPMENT.md).

The standalone setup below creates a separate development Weaviate instance from scratch:

```bash
cd weaviate_utils
docker compose up -d
```

Data is persisted to `./weaviate_db`. The compose file enables anonymous access and configures HNSW indexing. It pins Weaviate **1.30.2**; the deployments and test stores use **1.34.4**.

To verify:

```bash
curl http://localhost:8080/v1/.well-known/ready
```

Do not use this empty standalone database when the realistic `local_data/weaviate_semant_test/` development snapshot is required.

### 2. Data Ingestion

Load documents and chunks with `weaviate_utils/db_insert_jsonl.py`; the input format and
options are in [DATABASE.md](DATABASE.md#data-ingestion). The script connects to
`localhost:8080`, and `--delete-old` drops and recreates the collections: verify the endpoint
first.

### 3. Embedding Service

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

`run.py` starts `uvicorn` in reload mode on `PORT` (8000); the Docker image uses the same entry point. On startup the application:
1. Creates missing SQL tables (`user`, `rag_user_feedback`); existing tables and rows are kept
2. Connects to Weaviate (startup fails if it is not ready)
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
| `SQL_DB_URL` | `sqlite+aiosqlite:///tasks.db` | User accounts and RAG answer feedback; the default is `tasks.db` in the working directory (the name is historical) |
| `JWT_SECRET` | placeholder | **Must be overridden** with a long random string outside local development; tokens are valid for 7 days |
| `ALLOWED_ORIGIN` | `http://localhost:9000` | CORS origin of the frontend |
| `PORT` | `8000` | Listen port used by `run.py` (the Docker entry point) |
| `STATIC_PATH` | `./static` | Built frontend served by the backend when the directory exists |
| `LOG_LEVEL` | `INFO` | Python and OTLP log level |
| `LLM_MODELS_CONFIG` | `configs/llm_models.yaml` | Model tier catalog: provider, model and estimated prices per tier, and the tiers each feature may use; the only place models are chosen |
| `OPENAI_API_KEY` / `OPENAI_API_URL` | empty / `https://openrouter.ai/api/v1` | Key and default endpoint of `openai` tiers (any OpenAI-compatible API; model names must match the endpoint) |
| `OLLAMA_URLS` | `http://localhost:11434` | Default endpoint of `ollama` tiers (only the first URL is used) |
| `GOOGLE_API_KEY` | empty | Key of `google` tiers |
| `RAG_CONFIGS_PATH` | `configs/rag/demo_configs` | Directory of the RAG configurations offered to users |
| `SEARCH_SUMMARIZER_CONFIG` | `configs/search_summarizer.yaml` | Summary prompts, fallbacks and options |
| `SEARCH_FILTERS_CONFIG` | `configs/search_filters.yaml` | Search filters ([SEARCH_FILTERS.md](SEARCH_FILTERS.md)) |
| `TOPICER_URL` / `TOPICER_CONFIG_NAME` / `TOPICER_TIMEOUT` | `http://topicer:8089` / `openai` / `600` | External Topicer span-proposal service |
| `SPAN_CHAT_TEMPERATURE` / `SPAN_CHAT_MAX_TOKENS` | `0.4` / `1024` | Span discussion replies (`span_chat` tier) |
| `SPAN_CHAT_CONTEXT_CHARS` / `SPAN_CHAT_HISTORY_LIMIT` | `1500` / `20` | Context window around the span; chat messages forwarded |
| `FEEDBACK_LOG_PATH` | `semant_demo/feedback.log.jsonl` | JSONL file receiving in-app feedback. An empty value (as in the `.env` templates) is used as is, not replaced by the default, and makes feedback delivery fail ([#300](https://github.com/DCGM/semant-demo/issues/300)) |
| `FEEDBACK_WEBHOOK_URL` | empty | Optional webhook that also receives in-app feedback |
| `OTEL_ENABLED`, `OTEL_*`, `DEPLOYMENT_ENVIRONMENT` | off | Telemetry export; see [OBSERVABILITY.md](OBSERVABILITY.md#runtime-configuration) |

A tier whose provider has no key refuses calls before sending them. `PRODUCTION` is read but
not used. `LANGCHAIN_API_KEY` in the `.env` templates is not read by the application; LangChain
uses it only if LangSmith tracing is enabled (`LANGCHAIN_TRACING_V2`), which would send
prompts and texts to LangSmith. `SQL_DB_PATH` and the build arguments are used by Docker
Compose only ([deploy/README.md](../deploy/README.md#environment-variables)).

### Embedding Service

| Variable | Default | Description |
|---|---|---|
| `GEMMA_MODEL` | `BAAI/bge-multilingual-gemma2` | Sentence-transformer model name |

---

## Debugging

### Backend

- Run with `uvicorn` reload mode (default in `run.py`): changes auto-reload
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

1. **Reload mode** — `run.py`, also the Docker image's entry point, runs uvicorn with `reload=True`; outside Docker run `uvicorn semant_demo.main:app` instead ([#298](https://github.com/DCGM/semant-demo/issues/298))
2. **Configure CORS** — set `ALLOWED_ORIGIN` to your actual frontend domain
3. **Use HTTPS** — put a reverse proxy (nginx, Caddy) in front of the backend
4. **One backend process** — chunk tag synchronization is serialized only within one process ([TODO.md](TODO.md#correctness-and-behavior)); SQLite holds only user accounts and RAG feedback
5. **Weaviate backups** — use Weaviate's backup API or snapshot the `weaviate_db` volume
6. **Embedding service scaling** — can run multiple instances behind a load balancer. The endpoint is built from `EMBEDDING_SERVICE_HOST` (default `embedding-service` in Docker, `localhost` outside) and `EMBEDDING_SERVICE_PORT` (default `8001`); point both at your load balancer to scale.