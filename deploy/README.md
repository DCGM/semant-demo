# deploy — Docker Compose service management

This folder holds the Docker Compose files, Dockerfiles and environment templates of the deployed stack (app, Weaviate, embedding service, Topicer) and documents CI/CD and server setup.

## Contents

| File | Purpose |
|---|---|
| `docker-compose.app.yaml` | Production app: backend + built frontend |
| `docker-compose.app-test.yml` | Test app for `test-main` and PR previews (CI/CD managed) |
| `docker-compose.database.yml` / `docker-compose.database-test.yml` | Weaviate for production / for all test instances |
| `docker-compose.embedder.yml` | GPU embedding service |
| `docker-compose.topicer.yml` / `docker-compose.topicer-test.yml` | Topicer service, started manually with `update.sh` (CI/CD does not deploy it, but the app compose files require its external networks). They build from a `Dockerfile.topicer` that is not in this repository ([#299](https://github.com/DCGM/semant-demo/issues/299)) |
| `Dockerfile` | Multi-stage build of backend + frontend (`npm ci` and the committed generated API client, not regenerated) |
| `Dockerfile.embedder` | Build of the embedding service |
| `update.sh` | Named shortcuts for the `docker compose` commands below |
| `.env.example` / `.env.test.example` | Environment templates for production / test instances |

## Services

The stack is split across several compose files that are started independently and communicate via shared Docker networks:

| Compose file | Service | Network | Notes |
|---|---|---|---|
| `docker-compose.database.yml` | `weaviate` | `semant_demo_database` | Production Weaviate (REST :8080, gRPC :50051) |
| `docker-compose.database-test.yml` | `weaviate` | `semant_demo_test_database` | Shared Weaviate for **all** test instances (REST :8082, gRPC :50053) |
| `docker-compose.embedder.yml` | `embedding-service` | `semant_demo_embedder` | Single GPU embedder shared by **production and all test instances** (port 8001) |
| `docker-compose.app.yaml` | `app` | `web`, `semant_demo_database`, `semant_demo_embedder`, `semant_demo_topicer` | Production app instance; own `tasks.db` mounted via `$SQL_DB_PATH` |
| `docker-compose.app-test.yml` | `app` | `web`, `semant_demo_test_database`, `semant_demo_embedder`, `semant_demo_test_topicer` | One container per test instance (CI/CD managed); each has its own `tasks.db` mounted via `$SQL_DB_PATH` |

**`SQL_DB_PATH`** (set by `.github/workflows/ci-cd.yml`; the `tasks.db` file must exist):
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
| `SQL_DB_PATH` | `/mnt/ssd2/semant_demo_app_data` | Host directory whose `tasks.db` is mounted into the container |
| `GEMMA_MODEL`, `GPU_DEVICE` | `BAAI/bge-multilingual-gemma2`, `0` | Embedding service model and GPU |
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
| `./update.sh embedder-up` / `embedder-down` / `embedder-build` | embedding service |
| `./update.sh topicer-*` / `test-topicer-*` | Topicer (see the note in [Contents](#contents)) |

Other operations use `docker compose` with the same project and file, for example:

```bash
docker compose -p semant-demo -f docker-compose.app.yaml logs -f app
docker compose -p semant-demo -f docker-compose.app.yaml ps
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
