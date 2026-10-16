# deploy — Docker Compose service management

This folder holds the Docker Compose files, Dockerfiles and environment templates of the deployed stack (app, Weaviate, embedding service, Topicer) and documents CI/CD and server setup.

## Contents

| File | Purpose |
|---|---|
| `docker-compose.app.yaml` | Production app: backend + built frontend |
| `docker-compose.app-test.yml` | Test app for `test-main` and PR previews (CI/CD managed) |
| `docker-compose.database.yml` / `docker-compose.database-test.yml` | Weaviate for production / for all test instances |
| `docker-compose.embedder.yml` | GPU embedding service: Qwen3-Embedding-0.6B on vLLM (#385) |
| `docker-compose.topicer.yml` / `docker-compose.topicer-test.yml` | Topicer service, started manually with `update.sh` (CI/CD does not deploy it, but the app compose files require its external networks). They build from a `Dockerfile.topicer` that is not in this repository ([#299](https://github.com/DCGM/semant-demo/issues/299)) |
| `Dockerfile` | Multi-stage build of backend + frontend (`npm ci` and the committed generated API client, not regenerated) |
| `Dockerfile.embedder` | Build of the former Gemma embedding service (`embedding_service/`); no longer used by `docker-compose.embedder.yml` |
| `update.sh` | Named shortcuts for the `docker compose` commands below |
| `.env.example` / `.env.test.example` | Environment templates for production / test instances |

## Services

The stack is split across several compose files that are started independently and communicate via shared Docker networks:

| Compose file | Service | Network | Notes |
|---|---|---|---|
| `docker-compose.database.yml` | `weaviate` | `semant_demo_database` | Production Weaviate (REST :8080, gRPC :50051) |
| `docker-compose.database-test.yml` | `weaviate` | `semant_demo_test_database` | Shared Weaviate for **all** test instances (REST :8082, gRPC :50053) |
| `docker-compose.embedder.yml` | `qwen-embedder` | `semant_demo_embedder` | Single GPU embedder (vLLM) shared by **production, all test instances and the vector backfill** (`http://qwen-embedder:8000/v1`; host loopback port 8002) |
| `docker-compose.app.yaml` | `app` | `web`, `semant_demo_database`, `semant_demo_embedder`, `semant_demo_topicer` | Production app instance; own `tasks.db` and `feedback/` mounted via `$SQL_DB_PATH` |
| `docker-compose.app-test.yml` | `app` | `web`, `semant_demo_test_database`, `semant_demo_embedder`, `semant_demo_test_topicer` | One container per test instance (CI/CD managed); each has its own `tasks.db` and `feedback/` mounted via `$SQL_DB_PATH` |

**`SQL_DB_PATH`** (set by `.github/workflows/ci-cd.yml`; the `tasks.db` file and the `feedback/` directory must exist, see [In-app feedback storage](#in-app-feedback-storage)):
- **Production:** `$SQL_DB_DIR` from the GitHub variables
- **Test:** a unique subdirectory per instance under `$SQL_DB_DIR_TEST`:
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

The `.env` file holds the backend settings (reference: [DEPLOYMENT.md](../docs/DEPLOYMENT.md#backend-semant_demo_backend);
`.env.example` has the production values, e.g. `WEAVIATE_HOST=weaviate`) and these
deployment-only values:

| Variable | Example | Description |
|---|---|---|
| `REPO` / `BRANCH` | `https://github.com/DCGM/semant-demo.git` / `main` | Source cloned by the image build |
| `COMMIT` | _(empty)_ | Full commit SHA to build. CI sets it to the commit the deploy run is for and copies the Dockerfile, Compose file and `.env` template from that same commit, so a later push cannot change the deployed source. Production: the tagged commit; test-main: the pushed `main` commit (both after the required checks pass on it). PR previews: the PR head, while the PR checks run on GitHub's merge commit. Empty builds the current tip of `BRANCH` |
| `BACKEND_URL` | `https://demo.semant.cz` | Public backend URL baked into the frontend bundle at build time |
| `DOMAIN` | `demo.semant.cz` | Traefik Host rule |
| `SQL_DB_PATH` | `/mnt/ssd2/semant_demo_app_data` | Host directory whose `tasks.db` and `feedback/` are mounted into the container |
| `FEEDBACK_LOG_PATH` | `/app/feedback/feedback.log.jsonl` | In-app feedback log inside the mounted `feedback/` directory; keep this template value |
| `GPU_DEVICE` | `0` | GPU of the embedding service |
| `QWEN_EMBEDDER_PORT`, `QWEN_MAX_MODEL_LEN`, `QWEN_MAX_NUM_BATCHED_TOKENS`, `QWEN_GPU_MEMORY_UTILIZATION` | `8002`, `2048`, `16384`, `0.5` | Optional settings of the Qwen embedding service ([below](#qwen-embedding-service-385)) |
| `EMBEDDING_API_KEY` | _(empty)_ | Optional key of the embedding service: the server requires it when set and the apps send it |
| `GEMMA_MODEL` | `BAAI/bge-multilingual-gemma2` | Model of the former Gemma embedding service |
| `OTEL_ENABLED`, `OTEL_SERVICE_NAME`, `DEPLOYMENT_ENVIRONMENT` | `true`, `semant-demo-app`, `production` | Telemetry of the deployed instances; CI sets the environment per instance ([OBSERVABILITY.md](../docs/OBSERVABILITY.md#runtime-configuration)) |

---

## Commands

CI/CD builds and starts the app instances (below). For manual operation on the server, run
`update.sh` **from the `deploy/` directory**; it accepts only these named commands and prints
them when called without one:

| Command | Runs |
|---|---|
| `./update.sh app-up` / `app-down` / `app-build` | `docker compose -p semant-demo -f docker-compose.app.yaml up -d` / `down` / `build` |
| `./update.sh database-up` / `database-down` | production Weaviate (`docker-compose.database.yml`) |
| `./update.sh test-database-up` / `test-database-down` | test Weaviate (`docker-compose.database-test.yml`, project `semant-demo-test`) |
| `./update.sh embedder-up` / `embedder-down` / `embedder-pull` | Qwen embedding service (pulls the pinned vLLM image) |
| `./update.sh topicer-*` / `test-topicer-*` | Topicer (see the note in [Contents](#contents)) |

Other operations use `docker compose` with the same project and file, for example:

```bash
docker compose -p semant-demo -f docker-compose.app.yaml logs -f app
docker compose -p semant-demo -f docker-compose.app.yaml ps
```

### Qwen embedding service (#385)

`docker-compose.embedder.yml` serves `Qwen/Qwen3-Embedding-0.6B` (1,024 dimensions, pinned
model revision) with vLLM's OpenAI-compatible `/v1/embeddings` (pinned image
`vllm/vllm-openai:v0.31.0`, a CUDA 13.0 build: the host driver must support CUDA 13.0).
The apps reach it as `http://qwen-embedder:8000/v1` on `semant_demo_embedder`; the vector
backfill (`data_tools/embedder`, template `data_tools/embedder/config.qwen.yaml`) uses the
loopback port `http://127.0.0.1:8002/v1`. Nothing starts it automatically.

- **Input length.** At most `QWEN_MAX_MODEL_LEN` = 2048 tokens. A longer input is refused
  (HTTP 400); the backfill asks for truncation to the first 2048 tokens
  (`truncate_prompt_tokens: -1`). Search queries are far shorter.
- **No `dimensions`.** vLLM serves this model without Matryoshka support; requests with
  `dimensions` are refused. Vectors are unit length.
- **Shared GPU.** `QWEN_GPU_MEMORY_UTILIZATION` (default 0.5 of the GPU) bounds vLLM's
  memory. On the RTX 4090 the server sustained about 375 chunks/s (≈330 tokens each) in a
  smoke test; the backfill config keeps 4 concurrent requests to leave room for queries.
- **Key.** Without `EMBEDDING_API_KEY` the server needs no key (reachable only from the
  embedder network and loopback). With one, set the same value in each app's `.env`.

Smoke test before use (2026-10-16, on the production host, throwaway container): 401
without the key when one is set; 1,024 finite unit vectors; the model card's
query/document example scores reproduced within 0.004 (bf16); an input over 2048 tokens
refused, and accepted with truncation.

**Cutover order** (operator, #385). Each step is a separate, explicit action:

1. Stop the old Gemma service and remove its container: `docker stop
   semant-demo-embedding-service-1 && docker rm semant-demo-embedding-service-1`. Do
   **not** use `docker compose ... --remove-orphans`: the `semant-demo` project also holds
   the production app and Weaviate.
2. `./update.sh embedder-pull && ./update.sh embedder-up`; wait until healthy, then check
   `curl -s http://127.0.0.1:8002/v1/models` and one embedding (1,024 values).
3. Add the named vector `Qwen3-Embedding-0-6B` to the physical chunk collection
   (`Chunks_test`) with the chosen index settings (#385, D).
4. Switch the apps with `SEARCH_VECTORS_CONFIG=/app/semant_demo/configs/search_vectors_qwen.yaml`
   (production: set in `.env.example` since 2026-10-16; the test instances not yet).
   CI rebuilds each instance's `.env` from `.env.example` (production, deployed on a
   release tag) or `.env.test.example` (test instances, deployed on merge) on every deploy,
   so set it in those templates through a PR; an edit of a deployed `.env` is lost on the
   next deploy. An instance whose Weaviate lacks the vector fails vector and hybrid search;
   the test instances share the test Weaviate and need the vector there too. Text search is
   unaffected.
5. Start the backfill with a reviewed copy of `data_tools/embedder/config.qwen.yaml`;
   rerun it to resume.

### In-app feedback storage

In-app feedback (`POST /api/v1/feedback`) is appended to `FEEDBACK_LOG_PATH`. The `.env`
templates set it to `/app/feedback/feedback.log.jsonl`, and both app Compose files mount the
host directory `${SQL_DB_PATH}/feedback` at `/app/feedback`, so the log survives container
recreation and redeploys. Without the mount, the log would live inside the container and be
lost when it is recreated; `FEEDBACK_WEBHOOK_URL` is only an optional extra copy.

- **Provisioning.** The mount uses `create_host_path: false`, so the directory must exist
  before `docker compose up`. CI creates it in each deploy job (`mkdir -p
  "$SQL_DB_PATH/feedback"`, as the `runner` user). For a manually managed instance, create it
  yourself next to `tasks.db`.
- **Permissions.** The backend runs as root in the container, so the log file is owned by
  root on the host. Because `runner` owns the `feedback/` directory, it can still remove the
  file (PR teardown deletes the whole `SQL_DB_PATH`). Reading it on the host needs `sudo`
  or root-readable permissions.
- **Retention.** Production and `test-main` keep the log indefinitely; it is not rotated.
  A PR preview's log is deleted with its instance when the PR closes. Feedback may contain
  personal data (message text, optional e-mail, IP address, user agent); prune or archive
  it by hand under your data policy.
- **Migration.** CI recreates `.env` from the template on every deploy, so CI-managed
  instances pick up the new value on their next deploy. A manually maintained `.env` with an
  empty `FEEDBACK_LOG_PATH=` must be changed to `/app/feedback/feedback.log.jsonl` and the
  directory created; an empty value otherwise falls back to the in-container default path.
  Before this change, an empty value made feedback fail, so there is no earlier log to move.

Smoke test after a deploy (writes one feedback entry; use a test instance where possible):

```bash
curl -fsS -X POST "https://<host>/api/v1/feedback" -H 'Content-Type: application/json' \
  -d '{"type":"other","subject":"smoke test","message":"feedback persistence check"}'
docker compose -p <project> -f <compose file> up -d --force-recreate app
sudo tail -n 1 "$SQL_DB_PATH/feedback/feedback.log.jsonl"   # still shows the entry
```

### Recovering / Rebuilding the Weaviate database

This deletes the production store. Do it only with explicit authorization, after a verified
backup, and with the app stopped or expected to fail meanwhile:

```bash
cd deploy
./update.sh database-down
# Clear the storage mounted by docker-compose.database.yml (verify the path first)
rm -r /mnt/ssd2/weaviate_semant/*
./update.sh database-up
# Reload data; db_insert_jsonl.py connects to localhost:8080
cd ../weaviate_utils
python db_insert_jsonl.py --source-dir /path/to/jsonl_data --delete-old
```

See [DATABASE.md](../docs/DATABASE.md#data-ingestion) for the input format and
[DATA_MAINTENANCE.md](../docs/DATA_MAINTENANCE.md) for the reviewed audit/repair commands.

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

Set these in **Settings → Secrets and variables → Actions → Secrets**:

| Secret | Used by | Description |
|---|---|---|
| `OPENAI_API_KEY` | production, `test-main` | OpenAI / OpenRouter API key |
| `JWT_SECRET` | production, `test-main` | JWT signing secret (long random string) |
| `OPENAI_API_KEY_PREVIEW` | PR previews only | Separate provider key with a low spending limit (see below) |
| `JWT_SECRET_PREVIEW` | PR previews only | Separate JWT signing secret, different from `JWT_SECRET` |

### PR preview credentials

PR previews run unreviewed PR code on the deployment runner, so `deploy-test-pr` never
receives the production `OPENAI_API_KEY` or `JWT_SECRET`. It writes `OPENAI_API_KEY_PREVIEW`
and `JWT_SECRET_PREVIEW` into the preview `.env` as `OPENAI_API_KEY` and `JWT_SECRET`, so
the application itself needs no change. If either preview secret is missing, the job's first
step ("Check preview credentials") fails with an error naming it; there is no fallback to
the production secrets. Production and `test-main` keep using the production secrets.

A repository administrator provisions them (only administrators can set Actions secrets):

1. **Provider key:** in the OpenAI / OpenRouter account, create a separate project or key
   used only for previews and give it a low monthly budget / spending limit, so a leaked or
   misused key can cost at most that amount. Never reuse the production key.
2. **JWT secret:** generate a fresh value that is not the production one, e.g.
   `openssl rand -base64 48`.
3. Store each value with **Settings → Secrets and variables → Actions → New repository
   secret**, or `gh secret set OPENAI_API_KEY_PREVIEW` / `gh secret set JWT_SECRET_PREVIEW`,
   which read the value from the prompt or stdin. Do not pass values as command-line
   arguments or paste them into issues, logs or chat.

**Rotation.** Rotate after a suspected leak, when someone with access leaves, or
periodically:

1. Create the new provider key (or JWT value) and update the secret as above.
2. Redeploy open previews by pushing to their PRs or re-running their `deploy-test-pr` job;
   each deploy rewrites the preview `.env`. A preview not redeployed keeps the old values.
3. Revoke the old provider key in the provider console. A new `JWT_SECRET_PREVIEW`
   invalidates existing preview logins once a preview is redeployed; users log in again.

The separate credentials limit what preview code can obtain. They are not full isolation:
previews, test jobs and the other deployments share the same server and Docker daemon, and
code running there with access to that daemon can reach more than its own `.env`. That is a
known scope boundary; host separation is not planned.

**Test results versus preview availability.** `deploy-test-pr` runs with `if: always()`
after the backend tests, so a preview is built and deployed even when backend, frontend,
integration, API client drift or dependency lock checks fail; this lets developers diagnose a
failing PR by hand. A healthy preview (and a green "Deploy test PR" job) does **not** mean
the PR passed CI or can be merged: the failed checks stay visible on the PR, and branch
protection, not the preview, blocks merging. The deploy job's summary repeats this.

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
