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
| `docker-compose.database-test.yml` | `weaviate` | `semant_demo_test_database` | Shared Weaviate for **all** test instances (REST :8082, gRPC :50053) |
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
| `LOG_LEVEL` | `INFO` | Minimum Python/OTLP log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`) |
| **Observability** | | |
| `OTEL_ENABLED` | `true` | Enables OTLP export for production, `test-main`, and PR preview deployments. CI also sets it explicitly. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://lgtm:4318` | Base URL of the OTLP/HTTP receiver on the shared `web` network |
| `OTEL_EXPORTER_OTLP_LOGS_PATH` | `/v1/logs` | OTLP/HTTP path used for log records |
| `OTEL_EXPORTER_OTLP_TRACES_PATH` | `/v1/traces` | OTLP/HTTP path used for traces |
| `OTEL_EXPORTER_OTLP_METRICS_PATH` | `/v1/metrics` | OTLP/HTTP path used for metrics |
| `OTEL_METRIC_EXPORT_INTERVAL_MS` | `10000` | Metric export interval in milliseconds |
| `OTEL_SERVICE_NAME` | `semant-demo-app` | Service label used to find the application in Grafana |
| `DEPLOYMENT_ENVIRONMENT` | `production` | Environment resource attribute (`production`, `test-main`, etc.) |

See [Observability](../docs/OBSERVABILITY.md) for the telemetry architecture, signal inventory, dashboard queries, and instructions for adding application signals.

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

Tests and deployment run on self-hosted GitHub Actions runners, all on **one physical
server** sharing its Docker daemon.

### Runners

| Label | Runners | Jobs |
|---|---|---|
| `semant-ci` | two runners for CI | `test-backend`, `test-frontend`, `test-integration`, `api-client-drift` |
| `semant-server` | the original runner, configured for deployment | `deploy-production`, `deploy-test-main`, `deploy-test-pr`, `teardown-test-pr` |

Jobs select runners with `runs-on: [self-hosted, <label>]`. The two `semant-ci` runners let
the test jobs of one run, or of two runs, execute in parallel, while deployments stay on
the runner that holds their working directory, Compose projects and database paths.

Because all runners share one host, parallel jobs compete for CPU, memory and disk, and
every job's containers (including the per-job Weaviate service of the integration tests)
run on the same Docker daemon. Job containers and service containers are created per
job with unique names and no volumes apart from the shared pip cache below, so jobs do
not see each other's data. Free disk space matters: a full disk fails the Docker builds
of the deploy jobs.

### Workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| `ci-cd.yml` | Push of a `v*.*.*` tag from `main` | Deploy to production |
| `ci-cd.yml` | Push to `main` | Deploy/update `test-main` preview |
| `ci-cd.yml` | PR opened or updated | Deploy/update ephemeral `test-pr-<N>` preview with telemetry enabled |
| `ci-cd.yml` | PR closed | Tear down `test-pr-<N>` preview and remove its database |

### Required GitHub Variables

Set these in **Settings → Secrets and variables → Actions → Variables**:

| Variable | Example value | Description |
|---|---|---|
| `BASE_DOMAIN` | `demo.semant.cz` | Base domain; `DOMAIN`, `BACKEND_URL`, `ALLOWED_ORIGIN` are derived from it |
| `RUNNER_WORKDIR` | `/home/runner/semant-demo` | Working directory on the runner |
| `DEPLOY_SUBDIR` | `semant-demo` | Subdirectory under `RUNNER_WORKDIR` for the production deploy |
| `SQL_DB_DIR` | `/mnt/ssd2/semant_demo_app_data` | Production SQLite database directory (must exist, owned by `runner`) |
| `SQL_DB_DIR_TEST` | `/mnt/ssd2/semant_demo_app_test_data` | Test SQLite database root (subdirectories are created per instance) |
| `CI_PIP_CACHE_DIR` (optional) | `/var/cache/semant-ci/pip` (default) | Host directory for the pip cache shared by the Python CI jobs (see below) |

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

### Shared pip cache for CI jobs

The backend and integration test jobs mount `CI_PIP_CACHE_DIR` (default
`/var/cache/semant-ci/pip`) into their containers as pip's cache (`PIP_CACHE_DIR=/pip-cache`),
so pinned packages are not downloaded on every run. Both `semant-ci` runners use the same
directory: pip writes each cache entry to a temporary file and renames it into place, so
concurrent jobs never read a partial entry. Runners on another host need their own
directory.

The cache is a **trusted directory**; only the CI job containers may write to it. The jobs
install `semant_demo_backend/requirements-dev.lock` with `--require-hashes`, and pip checks
every downloaded archive against the lock's hashes, including archives served from the
cache. That does not cover everything in the cache: a wheel that pip builds locally from a
source distribution is stored under `wheels/` and reused after pip checks only the source
archive hash recorded next to it, not the wheel itself. Today every locked package installs
from a published wheel, and the editable project is built in a temporary cache that is
discarded, so nothing is built into the shared cache.

The job containers run as uid 1025, gid 1027. Setup (already done on the server):

```bash
sudo mkdir -p /var/cache/semant-ci/pip
sudo chown 1025:1027 /var/cache/semant-ci/pip
sudo chmod 775 /var/cache/semant-ci/pip
```

**Checking it works.** Before installing, the "Install pinned dependencies" step tries to
create a file in the cache and prints `pip cache /pip-cache is writable by 1025:1027`. If
that fails it adds a `pip cache unavailable` warning annotation to the run, showing the
directory's owner and mode. pip itself only prints a warning, disables the cache and
downloads everything, so a green job does not prove that the cache works. In a working run,
the step log shows `Using cached …` for the packages, and the cache directory on the host
is not empty:

```bash
sudo du -sh /var/cache/semant-ci/pip
```

**Cleaning it.** pip never prunes the cache, so it grows with dependency updates (about
160 MB for one lock). Clear it when disk space is needed or if you suspect a bad entry;
the next run refills it:

```bash
sudo find /var/cache/semant-ci/pip -mindepth 1 -delete
```

### Production Deployment

```bash
git tag v1.2.3
git push origin v1.2.3
```

The workflow validates the database directory, clones the tagged deploy files, builds and starts the containers, runs a health check, and rolls back automatically if the health check fails.
