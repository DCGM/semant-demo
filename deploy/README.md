# deploy — Docker Compose service management

This folder manages the full application stack — backend, embedding service, and Weaviate database.

## Contents

| File | Purpose |
|---|---|
| `docker-compose.app.yaml` | Production app stack: backend + built frontend |
| `docker-compose.app-test.yml` | Test app stack for CI/CD preview environments |
| `docker-compose.database.yml` | Weaviate database container (production) |
| `docker-compose.database-test.yml` | Weaviate database container (test) |
| `docker-compose.embedder.yml` | GPU embedding service container |
| `Dockerfile` | Multi-stage build for the backend + frontend |
| `Dockerfile.embedder` | Build for the embedding service |
| `update.sh` | Wrapper script — loads `.env`, sets variables and forwards arguments to `docker compose` |
| `.env.example` | Environment variables template for production |
| `.env.test.example` | Environment variables template for test/CI environments |

## Folder structure

```
deploy/
├─ .env.example                  # production environment template
├─ .env.test.example             # test/CI environment template
├─ docker-compose.app.yaml       # production app stack
├─ docker-compose.app-test.yml   # test app stack (CI preview)
├─ docker-compose.database.yml   # Weaviate database (production)
├─ docker-compose.database-test.yml  # Weaviate database (test)
├─ docker-compose.embedder.yml   # GPU embedding service
├─ Dockerfile                    # multi-stage build for backend + frontend
├─ Dockerfile.embedder           # build for the embedding service
├─ update.sh                     # helper wrapper to run docker compose with .env
└─ README.md                     # this file
```

## Services

The stack is split across several compose files that are started independently and communicate via shared Docker networks:

| Compose file | Service | Network | Notes |
|---|---|---|---|
| `docker-compose.database.yml` | `weaviate` | `semant_demo_database` | Production Weaviate (REST :8080, gRPC :50051) |
| `docker-compose.database-test.yml` | `weaviate-test` | `semant_demo_test_database` | Shared Weaviate for **all** test instances (REST :8082, gRPC :50053) |
| `docker-compose.embedder.yml` | `embedding-service` | `semant_demo_embedder` | Single GPU embedder shared by **production and all test instances** (port 8001) |
| `docker-compose.app.yaml` | `app` | `web`, `semant_demo_database`, `semant_demo_embedder` | Production app instance; own `tasks.db` mounted via `$SQL_DB_PATH` |
| `docker-compose.app-test.yml` | `app` | `web`, `semant_demo_test_database`, `semant_demo_embedder` | One container per test instance (CI/CD managed); each has its own `tasks.db` mounted via `$SQL_DB_PATH` |

**Note on `SQL_DB_PATH` construction:**
- **Production** (`ci-cd.yml`): `SQL_DB_PATH` is set directly to `$SQL_DB_DIR` from GitHub variables
- **Test** (`ci-cd-test.yml`): `SQL_DB_PATH` is constructed per instance as a unique subdirectory under `$SQL_DB_DIR_TEST`:
  - `test-main`: `${SQL_DB_DIR_TEST}/test-main`
  - `test-pr-{N}`: `${SQL_DB_DIR_TEST}/test-pr-${PR_NUMBER}`

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
| `SQL_DB_PATH` | `/mnt/ssd2/semant_demo_app_data` | Directory for the SQLite `tasks.db` database (mounted into the container) |
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

---

## CI/CD — GitHub Actions

Deployment is fully automated via GitHub Actions on a self-hosted runner (`semant-server`).

### Workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| `ci-cd.yml` | Push of a `v*.*.*` tag from `main` | Deploy to production |
| `ci-cd-test.yml` | Push to `main` | Deploy/update `test-main` preview |
| `ci-cd-test.yml` | PR opened / updated | Deploy ephemeral `test-pr-<N>` preview |
| `ci-cd-test.yml` | PR closed | Tear down `test-pr-<N>` preview and remove its database |

### Required GitHub Variables

Set these in **Settings → Secrets and variables → Actions → Variables**:

| Variable | Example value | Description |
|---|---|---|
| `BASE_DOMAIN` | `demo.semant.cz` | Base domain; `DOMAIN`, `BACKEND_URL`, `ALLOWED_ORIGIN` are derived from it |
| `RUNNER_WORKDIR` | `/home/runner/semant-demo` | Working directory on the runner |
| `DEPLOY_SUBDIR` | `semant-demo` | Subdirectory under `RUNNER_WORKDIR` for the production deploy |
| `SQL_DB_DIR` | `/mnt/ssd2/semant_demo_app_data` | Production SQLite database directory (must exist, owned by `runner`) |
| `SQL_DB_DIR_TEST` | `/mnt/ssd2/semant_demo_app_test_data` | Test SQLite database root (subdirectories are created per instance) |

### Required GitHub Secrets

| Secret | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI / OpenRouter API key |

### First-time Server Setup

Create the database directories and grant the runner user ownership:

```bash
sudo mkdir -p /mnt/ssd2/semant_demo_app_data
sudo mkdir -p /mnt/ssd2/semant_demo_app_test_data
sudo chown runner:runner /mnt/ssd2/semant_demo_app_data
sudo chown runner:runner /mnt/ssd2/semant_demo_app_test_data
```

### Production Deployment

```bash
git tag v1.2.3
git push origin v1.2.3
```

The workflow validates the database directory, clones the tagged deploy files, builds and starts the containers, runs a health check, and rolls back automatically if the health check fails.