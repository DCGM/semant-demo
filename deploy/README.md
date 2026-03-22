# deploy — Docker Compose service management

This folder manages the full application stack — backend, embedding service, and Weaviate database.

## Contents

| File | Purpose |
|---|---|
| `docker-compose.yaml` | Defines three services: `semant-demo`, `embedding-service`, `weaviate` |
| `Dockerfile` | Multi-stage build for the backend and embedding service |
| `update.sh` | Wrapper script — loads `.env`, sets variables and forwards arguments to `docker compose` |
| `.env.example` | Template for environment variables |

## Folder structure

```
deploy/
├─ .env.example        # environment template
├─ docker-compose.yaml # compose definition for services
├─ Dockerfile          # multi-stage build for backend/frontend/embedding
├─ update.sh           # helper wrapper to run docker compose with .env
└─ README.md           # this file
```

## Services

- **`semant-demo`** — backend + built frontend (port 8000, behind Traefik)
- **`embedding-service`** — GPU embedding model, BAAI/bge-multilingual-gemma2 (port 8001)
- **`weaviate`** — vector database (REST :8080, gRPC :50051)

## Requirements

- Docker Engine + Docker Compose plugin
- NVIDIA GPU + nvidia-container-toolkit (for the embedding service)

---

## Configuration

Before the first run, create `.env` from the template and fill in the values:

```bash
cp .env.example .env
```

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| **Build arguments** | | |
| `REPO` | `https://github.com/DCGM/semant-demo.git` | Git repository to clone |
| `BRANCH` | `main` | Branch to build from |
| `BACKEND_URL` | `https://demo.semant.cz` | Public backend URL baked into the frontend bundle at build time |
| `DOMAIN` | `demo.semant.cz` | Domain name for the Traefik Host rule |
| **Weaviate** | | |
| `WEAVIATE_HOST` | `weaviate` | Weaviate hostname (in Docker Compose network) |
| `WEAVIATE_REST_PORT` | `8080` | Weaviate HTTP port |
| `WEAVIATE_GRPC_PORT` | `50051` | Weaviate gRPC port |
| **Embedding service** | | |
| `EMBEDDING_SERVICE_HOST` | `embedding-service` | Embedding service hostname (in Docker Compose network) |
| `EMBEDDING_SERVICE_PORT` | `8001` | Embedding service port |
| `GEMMA_MODEL` | `BAAI/bge-multilingual-gemma2` | HuggingFace embedding model name |
| `GPU_DEVICE` | `0` | GPU index visible to the container (`CUDA_VISIBLE_DEVICES`) |
| **Ollama** | | |
| `OLLAMA_URLS` | `http://localhost:11434` | Comma-separated Ollama endpoints |
| `OLLAMA_MODEL` | `gemma3:12b` | Ollama model |
| **OpenAI / OpenRouter** | | |
| `OPENAI_API_KEY` | _(empty)_ | OpenAI API key (works with both OpenAI and OpenRouter endpoints) |
| `OPENAI_API_URL` | `https://openrouter.ai/api/v1` | API endpoint URL ( https://api.openai.com/v1 for OpenAI, https://openrouter.ai/api/v1 for OpenRouter) |
| `OPENAI_MODEL` | `gpt-4o-mini` | Default OpenAI model |
| **Google** | | |
| `GOOGLE_API_KEY` | _(empty)_ | Google Gemini key |
| `GOOGLE_MODEL` | `gemini-2.5-pro` | Default Google model |
| **Shared LLM** | | |
| `RAG_CONFIGS_PATH` | `rag/rag_configs/configs` | Directory with RAG YAML configs |
| `SEARCH_SUMMARIZER_CONFIG` | `configs/search_summarizer.yaml` | Summariser config path |
| `MODEL_TEMPERATURE` | `0.0` | Default LLM temperature |
| `LANGCHAIN_API_KEY` | _(empty)_ | LangChain/LangSmith tracing key (optional) |
| **Application** | | |
| `ALLOWED_ORIGIN` | `https://demo.semant.cz` | CORS origin for frontend |
| `PORT` | `8000` | Backend listen port |
| `STATIC_PATH` | `./static` | Path to built frontend assets (production) |

---

> **ℹ️ Universal Configuration:** Methods using the OpenAI Python package use `OPENAI_API_KEY` and `OPENAI_API_URL`. Set `OPENAI_API_URL=https://openrouter.ai/api/v1` to use OpenRouter, or the OpenAI endpoint to use OpenAI directly. Seamless integration via `ChatOpenAI` in LangChain.

## Commands

All commands are run **from the `deploy/` directory** via the `update.sh` wrapper, which automatically loads `.env` and sets the `now` build variable.

### Start (build + run)

```bash
cd deploy
./update.sh up -d --build
```

### Rebuild and restart (force recreate)

```bash
./update.sh up -d --build --force-recreate
```

### Stop containers

```bash
./update.sh down
```

### Commands for individual containers

```bash
# Stop only a container
./update.sh stop container_name

# Start only a container
./update.sh up -d container_name

# Stop multiple containers
./update.sh stop container_name1 container_name2

# Restart a single container
./update.sh restart container_name
```

### Build only (without starting)

```bash
./update.sh build
```

### Logs

```bash
# all services
./update.sh logs -f

# specific service (semant-demo | embedding-service | weaviate)
./update.sh logs -f semant-demo
```

### Container status

```bash
./update.sh ps
```

### Recovering / Rebuilding the Database

If the Weaviate database is corrupted or deleted, you can restore it while keeping the rest of the stack running:

```bash
# 1. Stop and remove Weaviate container (other services keep running)
cd deploy
./update.sh stop weaviate

# 2. Clear the database storage
rm -r /mnt/ssd2/weaviate_semant/*

# 3. Restart Weaviate in the stack (it initializes fresh)
./update.sh up -d weaviate

# 4. Reload data (stack is running in the background)
cd ../weaviate_utils
python db_insert_jsonl.py --source-dir /path/to/jsonl_data --delete-old
```

The script connects to `localhost:8080` while the stack continues running—nothing breaks.