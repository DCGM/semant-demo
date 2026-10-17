# deploy — Docker Compose service management

This folder holds the Docker Compose files, Dockerfiles and environment templates of the deployed stack (app, Weaviate, embedding service, Topicer) and documents CI/CD and server setup.

## Contents

| File | Purpose |
|---|---|
| `docker-compose.app.yaml` | Production app: backend + built frontend |
| `docker-compose.app-test.yml` | Test app for `test-main` and PR previews (CI/CD managed) |
| `docker-compose.database.yml` / `docker-compose.database-test.yml` | Weaviate for production / for all test instances |
| `docker-compose.embedder.yml` | GPU embedding service: Qwen3-Embedding-0.6B on vLLM (#385) |
| `docker-compose.topicer.yml` / `docker-compose.topicer-test.yml` | Topicer service, started manually with `update.sh` (CI/CD does not deploy it, but the app compose files require its external networks); see [Topicer](#topicer) |
| `Dockerfile.topicer` | Build of the Topicer API from a branch of [DCGM/topicer](https://github.com/DCGM/topicer) |
| `Dockerfile` | Multi-stage build of backend + frontend (`npm ci` and the committed generated API client, not regenerated) |
| `Dockerfile.embedder` | Build of the former Gemma embedding service (`embedding_service/`); no longer used by `docker-compose.embedder.yml` |
| `update.sh` | Named shortcuts for the `docker compose` commands below |
| `sqlite_backup.sh` / `semant-sqlite-backup.cron` / `test_sqlite_backup.sh` | Daily backup of the production `tasks.db` (host cron) and its tests; see [SQLite backup](#sqlite-backup-399) |
| `.env.example` / `.env.test.example` | Environment templates for production / test instances |

## Services

The stack is split across several compose files that are started independently and communicate via shared Docker networks:

| Compose file | Service | Network | Notes |
|---|---|---|---|
| `docker-compose.database.yml` | `weaviate` | `semant_demo_database` | Production Weaviate (REST :8080, gRPC :50051) |
| `docker-compose.database-test.yml` | `weaviate` | `semant_demo_test_database` | Shared Weaviate for **all** test instances (REST :8082, gRPC :50053) |
| `docker-compose.embedder.yml` | `qwen-embedder` | `semant_demo_embedder` | Single GPU embedder (vLLM) shared by **production, all test instances and the vector backfill** (`http://qwen-embedder:8000/v1`; host loopback port 8002) |
| `docker-compose.app.yaml` | `app` | `web`, `semant_demo_database`, `semant_demo_embedder`, `semant_demo_topicer` | Production app instance; own `$SQL_DB_PATH` directory (with `tasks.db` and `feedback/`) mounted at `/app/sql_data` |
| `docker-compose.app-test.yml` | `app` | `web`, `semant_demo_test_database`, `semant_demo_embedder`, `semant_demo_test_topicer` | One container per test instance (CI/CD managed); each has its own `$SQL_DB_PATH` directory (with `tasks.db` and `feedback/`) mounted at `/app/sql_data` |

**`SQL_DB_PATH`** (set by `.github/workflows/ci-cd.yml`; the directory, its `tasks.db` file and the `feedback/` directory must exist, see [SQLite database directory](#sqlite-database-directory-406) and [In-app feedback storage](#in-app-feedback-storage)):
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
| `SQL_DB_PATH` | `/mnt/ssd2/semant_demo_app_data` | Host directory of the instance, mounted at `/app/sql_data`; the app opens `tasks.db` there (`SQL_DB_URL` is set in the Compose file) and writes the feedback log to its `feedback/` (also mounted at `/app/feedback`) |
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
| `./update.sh topicer-up` / `topicer-down` / `topicer-build` (`test-topicer-*` likewise) | Topicer ([below](#topicer)); `build` runs with `--no-cache` |

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
3. Add the named vector `Qwen3_Embedding_0_6B` (letters, digits and `_` only: Weaviate
   builds GraphQL names from vector names, and one name with `-` breaks GraphQL for the whole
   instance, which only dropping that vector on 1.40 repairs) to the physical chunk collection
   (`Chunks_test`) with the chosen index settings (#385, D).
4. Switch the apps with `SEARCH_VECTORS_CONFIG=/app/semant_demo/configs/search_vectors_qwen.yaml`
   (set in `.env.example` and `.env.test.example` since 2026-10-16).
   CI rebuilds each instance's `.env` from `.env.example` (production, deployed on a
   release tag) or `.env.test.example` (test instances, deployed on merge) on every deploy,
   so set it in those templates through a PR; an edit of a deployed `.env` is lost on the
   next deploy. An instance whose Weaviate lacks the vector fails vector and hybrid search;
   the test instances share the test Weaviate and need the vector there too. Text search is
   unaffected.
5. Start the backfill with a reviewed copy of `data_tools/embedder/config.qwen.yaml`;
   rerun it to resume.

### Weaviate 1.40 upgrade and dropping a named vector (#312)

Both `docker-compose.database*.yml` pin Weaviate **1.40.1**. 1.40 refuses a query that names a
property missing from the schema (1.34 ignored it); the app requests only the document
properties the store has, so it runs on both versions. **Deploy the app before upgrading
the database.** There is no downgrade: the backup is the rollback.

1. Back up the data directory, deploy the app, stop Weaviate (`./update.sh database-down`).
2. Start the pinned 1.40.1 (`./update.sh database-up`) on the same data; check the version,
   aliases, schema and object counts.
3. Drop a named vector (its index, its stored vectors and its schema entry; objects,
   properties and references stay) with
   `curl -X DELETE http://127.0.0.1:8080/v1/schema/<PhysicalCollection>/vectors/<vector>/index`.
   It is a background task: wait for `drop-vector: task-completion: dropped vector(s)
   removed from schema` in the Weaviate log before restarting (a restart pauses it; it
   resumes on the next start). Until then the schema lists the vector without an index and
   the Python client's `config.get()` fails. Use the physical name (`Chunks_test`), not the alias.
4. Check `/v1/graphql`, the schema and a sample of objects.
5. A collection whose last named vector was dropped has no vector config, which
   `weaviate-client` 4.23.1 cannot parse (`config.get()` raises `KeyError: 'vectorizer'`).
   Add its new vector right away with `collection.config.add_vector(...)` (it works without
   reading the config first); check the precondition over REST.

Both database compose files set `LIMIT_RESOURCES: "true"`: Weaviate sets its Go memory limit
to 80% of the container's `mem_limit` (1.40 warns that its memory-pressure checks are inert
without one); CPU use is not limited because no CPU quota is set.

Done on the shared test Weaviate on 2026-10-16 (filesystem backup
`pre-1-40-upgrade-2026-10-16` first): upgrade, both `Chunks` vectors dropped in ~35 s,
`Qwen3_Embedding_0_6B` added and filled (3,260 chunks), GraphQL working. Rehearsed earlier on a copy of the test store (3,260 chunks, 2026-10-16): 1.34.4 → 1.40.1 starts in
seconds; dropping two vectors took ~15 s, restored GraphQL, kept 28 properties and the
document references and shrank the chunk data from 289 to 57 MB. Not rehearsed at
production size (startup and drop duration unknown).

### Topicer

`Dockerfile.topicer` clones [DCGM/topicer](https://github.com/DCGM/topicer) at the compose
file's `BRANCH_NAME` (both files: `main`; production built from `semant-debug` until
2026-10-17). Docker caches the clone, so `./update.sh topicer-build` builds with `--no-cache`;
check `git log origin/main` of Topicer before rebuilding, since the build takes its tip. The
production service reserves a GPU (CrossBERT and mDeBERTa configs); the test one does not.

The server's `deploy/data/` is mounted at `/app/data`. At startup the API loads every
`*.yaml` in `TOPICER_API_CONFIGS_DIR` (`/app/data/topicer`) as a config named after the file;
the apps choose one with `TOPICER_CONFIG_NAME` (`openai-xjuric`). **A config that fails to load
is only logged as a warning** (`Failed to load topicer config ...`) and is then missing; after
a rebuild or a config change, check that the log line `Loaded topicer configurations: [...]`
lists all of them. Config files hold provider keys and are not in this repository.

Configs that use embeddings (vector pre-filtering of `POST /v1/tags/propose/db/stream`, topic
discovery) must embed queries with the model of the Weaviate vector they search (#385):

```yaml
embedding_service:
  cls: OpenAIEmbeddingService            # Topicer main since DCGM/topicer#80
  config:
    base_url: "http://qwen-embedder:8000/v1"
    model: "Qwen/Qwen3-Embedding-0.6B"   # Qwen query instruction and truncation are defaults
    timeout: 30
db_connection:
  cls: WeaviateService
  config:
    # host, ports, chunks_limit as before
    vector_name: "Qwen3_Embedding_0_6B"  # default "default", which no longer exists
```

`DefaultEmbeddingService` (the former Gemma service, 3,584 dimensions) cannot query the Qwen
vector. Topicer `main` also requires `stride` (e.g. `32`) in `CrossBertTopicer` configs.

semANT charges AI suggestions to the daily allowance from the usage Topicer reports and sends `max_chunks` (`TOPICER_MAX_CHUNKS_PER_TAG`, 40) with every optimized stream (#408). This needs Topicer with DCGM/topicer#81 (`main` since 2026-10-17, `06d32b9`); an older one ignores `max_chunks` and reports no usage, so every chunk or tag is charged its full reservation. A config's `max_chunks_ceiling` (default 200) must be at least `TOPICER_MAX_CHUNKS_PER_TAG`. For costs below the reservation, the provider must report cost (OpenRouter `usage.cost`) or the config must set `prices` per model; without either, cost is `unknown` and charged at least the reservation.
Switched in production on 2026-10-17: `openai-xjuric` as above, `bert.yaml` with `stride: 32`
(same spans as before on a synthetic check, now with confidences), `openai-xsucha`
(`TagProposalV2`, no embeddings) unchanged.

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

### SQLite database directory (#406)

SQLite keeps a rollback journal, `tasks.db-journal`, beside the database while a write
transaction runs, and deletes it at commit. If the process dies mid-write, the journal stays
behind (a *hot journal*), and the next connection uses it to undo the partly written
transaction. Without it, the database file keeps the uncommitted pages, and
`integrity_check` does not necessarily notice.

Both app Compose files therefore bind-mount the whole instance directory `${SQL_DB_PATH}` at
`/app/sql_data` and set `SQL_DB_URL=sqlite+aiosqlite:////app/sql_data/tasks.db` in the
Compose file itself (it overrides any `SQL_DB_URL` in `.env`). The database, its journal (and
`-wal`/`-shm` files, should the journal mode ever change to WAL) are on host storage together, so a
killed or recreated container leaves the journal for the next start, which rolls it back.
Before #406 only the file `${SQL_DB_PATH}/tasks.db` was mounted at `/app/tasks.db`, so the
journal was in the container's writable layer and was lost when the container was recreated.

- **Paths.** The host file is unchanged (`${SQL_DB_PATH}/tasks.db`, production
  `/mnt/ssd2/semant_demo_app_data/tasks.db`), and so is the [backup](#sqlite-backup-399) job. Each
  test instance still has its own `${SQL_DB_DIR_TEST}/<instance>`. If the directory is
  missing, `docker compose up` fails (`create_host_path: false`); the app does not fall back
  to a new database inside the container.
- **Permissions.** The backend runs as root in the container and creates the journal as root.
  `runner` owns the directory, so PR teardown can still remove it. The app needs write access to
  the directory, not only to the file.
- **Journal mode.** The app does not set `journal_mode`, so it is SQLite's default rollback
  journal (`DELETE`). The host backup only reads the database.
- **After a crash.** Start the app again (or open the file read-write, e.g. `sudo sqlite3
  "$SQL_DB_PATH/tasks.db" "PRAGMA integrity_check;"`). Never delete, move or copy
  `tasks.db` without its `tasks.db-journal` while the journal exists.
- **Tests.** `tests/test_deploy_sqlite_storage.py` checks the Compose mounts and kills a writer
  mid-transaction: reopening the directory restores the committed rows, while the file alone
  keeps the uncommitted ones. `test_sqlite_backup.sh` checks that the backup refuses a database with a hot journal.

**Migration** (once, for the first production release with this change; CI-managed test
instances switch on their next deploy). The old container's journal is only in its writable
layer, which the deploy's `docker compose down` deletes. Stop the container first (stopping
keeps the layer), check for a journal, and take a backup:

```bash
cd "$RUNNER_WORKDIR/$DEPLOY_SUBDIR"   # the production deploy directory
docker compose -p semant-demo -f docker-compose.app.yaml stop app
docker cp semant-demo-app-1:/app/tasks.db-journal /tmp/tasks.db-journal.406 && ls -l /tmp/tasks.db-journal.406
```

- **No journal** (`docker cp` reports that the path does not exist; normal after a clean stop):
  continue.
- **Journal present:** do not discard it. Copy it next to the host file as `tasks.db-journal`
  before anything opens the database, then roll it back by opening the file read-write:
  `sudo install -m 600 /tmp/tasks.db-journal.406 /mnt/ssd2/semant_demo_app_data/tasks.db-journal`,
  then `sudo sqlite3 /mnt/ssd2/semant_demo_app_data/tasks.db "PRAGMA integrity_check;"` (prints `ok`;
  the journal disappears).

Then back up, verify and note the counts:

```bash
sudo BACKUP_MOUNT=/mnt/zfs1 /usr/local/sbin/semant-sqlite-backup /mnt/ssd2/semant_demo_app_data/tasks.db /mnt/zfs1/semant_demo_app_data/sqlite_backups
sudo BACKUP_MOUNT=/mnt/zfs1 /usr/local/sbin/semant-sqlite-backup --check /mnt/ssd2/semant_demo_app_data/tasks.db /mnt/zfs1/semant_demo_app_data/sqlite_backups
sudo sqlite3 -readonly /mnt/ssd2/semant_demo_app_data/tasks.db "SELECT count(*) FROM user; SELECT count(*) FROM rag_user_feedback;"
```

Deploy the release tag ([Production Deployment](#production-deployment)) and validate:

```bash
docker inspect semant-demo-app-1 --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}'   # .../semant_demo_app_data -> /app/sql_data
docker exec semant-demo-app-1 sh -c 'echo "$SQL_DB_URL"; ls -la /app/sql_data; test ! -e /app/tasks.db && echo "no in-container tasks.db"'
sudo sqlite3 -readonly /mnt/ssd2/semant_demo_app_data/tasks.db "PRAGMA integrity_check; SELECT count(*) FROM user; SELECT count(*) FROM rag_user_feedback;"
```

The counts should match (or grow), an existing account can sign in, and the daily
allowance is still shown. If the health check fails, the workflow rolls back to the previous
image with the new Compose file; older releases also read `SQL_DB_URL`, so they open the same
file.

### SQLite backup (#399)

The production `tasks.db` (`$SQL_DB_PATH/tasks.db` = `/mnt/ssd2/semant_demo_app_data/tasks.db`)
holds user accounts, RAG answer feedback and the LLM quota ledger. Weaviate backups do not
include it. As of 2026-10-17, no other host backup covers it either: `/mnt/ssd2` is on the root ext4
RAID (`/dev/md1`), which has no snapshots, and none of the readable cron jobs or systemd timers copy it.

- **What.** `sqlite_backup.sh` copies the database with the SQLite online backup API
  (`sqlite3 .backup` on a read-only connection), so it waits for the app's locks rather than
  copying the file in the middle of a write. It runs `PRAGMA integrity_check` on the copy before
  keeping it. The database uses the rollback journal (not WAL): after a committed write the
  file is the whole database. While a hot journal is left beside it (an interrupted write,
  [#406](#sqlite-database-directory-406)), the read-only copy fails instead of copying
  uncommitted pages; the next read-write open rolls the journal back.
- **Where.** `/mnt/zfs1/semant_demo_app_data/sqlite_backups/tasks_<UTC timestamp>.db`, with
  `latest.db` pointing to the newest. This is a different disk pool from the live file, but the
  same server: it is not an off-site copy. The cron entry sets `BACKUP_MOUNT=/mnt/zfs1`, so a
  run fails (and does not create the directory on the root filesystem) when the pool is not
  mounted.
- **Schedule and retention.** Daily at 03:30 server time (`semant-sqlite-backup.cron`); the
  newest 30 backups are kept (`KEEP`). The database is about 4 MB.
- **Permissions.** The job runs as root with `umask 077`: the directory is `700` and the
  backups are `600`, because they contain password hashes and e-mail addresses. Reading them
  needs `sudo`.
- **Failure visibility.** Every run logs to syslog (tag `semant-sqlite-backup`) and to
  `backup.log`. It writes `RUNNING` to `last_status` when it starts and replaces it with
  `OK <backup>` only after every step succeeded; any failure, including an unexpected command
  error, writes `FAILED: …`. A successful run prints nothing; a failed one prints an error,
  which cron mails to root.

Install or update (copy the script; the cron entry does not depend on a checkout):

```bash
sudo install -m 755 deploy/sqlite_backup.sh /usr/local/sbin/semant-sqlite-backup
sudo install -m 644 deploy/semant-sqlite-backup.cron /etc/cron.d/semant-sqlite-backup
# First backup now, instead of waiting for 03:30
sudo BACKUP_MOUNT=/mnt/zfs1 /usr/local/sbin/semant-sqlite-backup /mnt/ssd2/semant_demo_app_data/tasks.db /mnt/zfs1/semant_demo_app_data/sqlite_backups
```

Did the most recent backup succeed? `--check` exits 1 unless `last_status` is `OK` for the
newest backup (so a failed, unfinished or missing status fails), and also when the newest
backup is older than 26 h (`MAX_AGE_HOURS`), fails `integrity_check`, or `BACKUP_MOUNT` is set
and not mounted:

```bash
sudo BACKUP_MOUNT=/mnt/zfs1 /usr/local/sbin/semant-sqlite-backup --check /mnt/ssd2/semant_demo_app_data/tasks.db /mnt/zfs1/semant_demo_app_data/sqlite_backups
sudo tail -n 5 /mnt/zfs1/semant_demo_app_data/sqlite_backups/backup.log
journalctl -t semant-sqlite-backup --since -2d
```

The script's tests use a synthetic database in a temporary directory and need only `bash` and
`sqlite3`: `bash deploy/test_sqlite_backup.sh`.

Restore test (into a separate path; never write over the production file while testing):

```bash
T=$(mktemp -d) && sudo cp /mnt/zfs1/semant_demo_app_data/sqlite_backups/latest.db "$T/tasks.db" && sudo chown "$USER" "$T/tasks.db"
sqlite3 -readonly "$T/tasks.db" "PRAGMA integrity_check; SELECT count(*) FROM user; SELECT count(*) FROM rag_user_feedback;"
sqlite3 -readonly "$T/tasks.db" "SELECT count(*) FROM llm_quota_day;"   # once a release with #371 has started
rm -r "$T"
```

Restore into production: stop the app, roll back any hot journal of the current file (a
journal left beside the restored file would be applied to it), keep the current file as
evidence, copy a backup over the production file, then start the app:

```bash
cd deploy && ./update.sh app-down
sudo ls -la /mnt/ssd2/semant_demo_app_data/   # with tasks.db-journal: roll it back first (next line), never delete it
sudo sqlite3 /mnt/ssd2/semant_demo_app_data/tasks.db "PRAGMA integrity_check;"   # a read-write open rolls back a hot journal
sudo cp -a /mnt/ssd2/semant_demo_app_data/tasks.db /mnt/ssd2/semant_demo_app_data/tasks.db.before-restore
sudo cp /mnt/zfs1/semant_demo_app_data/sqlite_backups/tasks_<timestamp>.db /mnt/ssd2/semant_demo_app_data/tasks.db
./update.sh app-up
```

Tested on 2026-10-17. A backup of production was restored into a temporary path, and the restored
copy had the same tables and counts as the live file (41 users, 330 feedback rows). It passed
`integrity_check`, and the backend at `b95eb57` opened it and created the quota tables in that
copy. The live file's checksum was unchanged afterwards. The feedback log
(`feedback/feedback.log.jsonl`) is not part of this backup.

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
