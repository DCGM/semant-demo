# Deployment & Configuration

## Prerequisites

| Component | Version | Notes |
|---|---|---|
| Python | ≥ 3.12 | Backend and embedding service |
| Node.js | 14.19+ / 16+ / 18+ | Frontend build |
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

## Step-by-Step Deployment

### 1. Weaviate

```bash
cd weaviate_utils
docker compose up -d
```

Data is persisted to `./weaviate_db`. The compose file enables anonymous access and configures HNSW indexing. Weaviate version: **1.30.2**.

To verify:
```bash
curl http://localhost:8080/v1/.well-known/ready
```

### 2. Data Ingestion

Prepare input data:
- `*.json` — one file per document containing bibliographic metadata
- `*.jsonl` — one file per document, each line is a chunk with `text`, `from_page`, `to_page`, NER fields, etc.
- `*_embeddings.npy` — numpy arrays of shape `(n_chunks, embedding_dim)` matching the JSONL files

```bash
cd weaviate_utils
pip install -r requirements.txt

python db_insert_jsonl.py \
    --source-dir /path/to/prepared_data \
    --delete-old
```

Options:
- `--delete-old` — drop and recreate all collections
- `--document-collection` / `--chunk-collection` / `--tag-collection` / `--usercollection-collection` — customise collection names
- `--vector-file-suffix` — change the embedding file suffix (default: `_embeddings.npy`)

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

Multiple Ollama instances can be load-balanced by setting `OLLAMA_URLS` to a comma-separated list.

### 5. Backend

```bash
cd semant_demo_backend
pip install -r requirements.txt
python run.py
```

The server starts with `uvicorn` in reload mode on port 8000. On startup it:
1. Creates the SQLite `tasks` table
2. Loads all RAG configurations from `rag/rag_configs/configs/*.yaml`
3. Mounts static files from `STATIC_PATH` if the directory exists

### 6. Frontend

#### Development
```bash
cd semant_demo_frontend
npm install
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

If unset, the Axios client defaults to `http://pcvaskom.fit.vutbr.cz:8024/api` — a development-machine-specific URL that should be overridden (see `src/boot/axios.ts`).

---

## Environment Variables Reference

### Backend (`semant_demo_backend`)

| Variable | Default | Required | Description |
|---|---|---|---|
| `WEAVIATE_HOST` | `localhost` | No | Weaviate server hostname |
| `WEAVIATE_REST_PORT` | `8080` | No | Weaviate HTTP port |
| `WEAVIATE_GRPC_PORT` | `50051` | No | Weaviate gRPC port |
| `OLLAMA_URLS` | `http://localhost:11434` | No | Comma-separated Ollama endpoints |
| `OLLAMA_MODEL` | `gemma3:12b` | No | Default Ollama model |
| `OPENAI_API_KEY` | _(empty)_ | If using OpenAI RAG | OpenAI API key |
| `OPENAI_API_URL` | `https://openrouter.ai/api/v1` | No | OpenAI-compatible endpoint for RAG/OpenAI requests (OpenAI or OpenRouter) |
| `OPENAI_MODEL` | `gpt-4o-mini` | No | Default OpenAI model |
| `GOOGLE_API_KEY` | _(empty)_ | If using Google RAG | Google Gemini API key |
| `GOOGLE_MODEL` | `gemini-2.5-pro` | No | Default Google model |
| `MODEL_TEMPERATURE` | `0.0` | No | Default LLM temperature |
| `ALLOWED_ORIGIN` | `http://localhost:9000` | No | CORS allowed origin |
| `PORT` | `8000` | No | Backend listen port |
| `PRODUCTION` | `false` | No | Production mode flag |
| `STATIC_PATH` | `./static` | No | Built frontend assets path |
| `RAG_CONFIGS_PATH` | `rag/rag_configs/configs` | No | Directory with RAG YAML configs |
| `SEARCH_SUMMARIZER_CONFIG` | `configs/search_summarizer.yaml` | No | Summariser config path |
| `LANGCHAIN_API_KEY` | _(empty)_ | No | LangChain/LangSmith tracing key |

> **Note:** `GEMMA_URL` (embedding service URL) is hardcoded to `http://localhost:8001` in `config.py`. To change it, edit the source directly.

### Embedding Service

| Variable | Default | Description |
|---|---|---|
| `GEMMA_MODEL` | `BAAI/bge-multilingual-gemma2` | Sentence-transformer model name |

---

## Debugging

### Backend
- Run with `uvicorn` reload mode (default in `run.py`): changes auto-reload
- FastAPI auto-generates interactive docs at `http://localhost:8000/docs` (Swagger) and `http://localhost:8000/redoc`
- Enable debug logging: `logging.basicConfig(level=logging.DEBUG)` in `main.py`
- Check Weaviate connectivity: `curl http://localhost:8080/v1/.well-known/ready`
- Inspect DB state: `python weaviate_utils/inspect_chunks.py` / `inspect_documents.py`

### Frontend
- Vue DevTools browser extension for component/store inspection
- Quasar dev mode includes HMR and source maps
- Network tab to inspect API calls and responses

### RAG Debugging
- `adaptive_rag.py` includes `DEBUG_PRINT = True` — set to see LangGraph node transitions in stdout
- Each RAG config can be tested independently by sending requests to `POST /api/rag` with the config's `id`
- Test RAG routing with the `TestRag` class (returns a static response)

### Tagging Debugging
- Poll `GET /api/tag_status/{taskId}` to see `processed_count` / `all_texts_count` progress
- `tag_processing_data` field contains per-chunk tagging decisions
- Check SQLite directly: `sqlite3 tasks.db "SELECT * FROM tasks"`

---

## Production Considerations

1. **Disable reload mode** — change `run.py` to set `reload=False` or use `gunicorn` with `uvicorn.workers.UvicornWorker`
2. **Set `PRODUCTION=true`** — currently only checked in config but can be used for conditional logging
3. **Configure CORS** — set `ALLOWED_ORIGIN` to your actual frontend domain
4. **Use HTTPS** — put a reverse proxy (nginx, Caddy) in front of the backend
5. **SQLite limitations** — consider switching to PostgreSQL for concurrent tagging tasks under load
6. **Weaviate backups** — use Weaviate's backup API or snapshot the `weaviate_db` volume
7. **Embedding service scaling** — can run multiple instances behind a load balancer; however `GEMMA_URL` is currently hardcoded to `http://localhost:8001` in `config.py` and must be changed in source to point to the balancer (see TODO.md for making this configurable)
