# Local Development

This document describes the standard local development environment for SemANT.

Normal development should use local database state under `local_data/`. Shared server test databases and production databases are not normal development targets.

For deployment and server configuration, see [DEPLOYMENT.md](DEPLOYMENT.md).
If you are new to the project, start with [START_HERE.md](START_HERE.md).

**A database snapshot is not required to contribute or run tests.** With Python 3.12,
Node.js 22 and Make, run `make setup` and `make check` from the repository root.
Integration and browser tests use disposable, synthetic data (Docker required; see
[section 11](#11-testing-versus-development-data)). To use the interactive application
with realistic documents, obtain an authorized, consistent **development** snapshot,
then place it under `local_data/` as shown below. Never use the shared server test store
or production data for ordinary development.

## 1. Local database layout

From the repository root, the expected development data is:

```text
local_data/
├── tasks.db
└── weaviate_semant_test/
```

- `tasks.db` is a local copy of the test SQLite database.
- `weaviate_semant_test/` is a local copy of the test Weaviate persistence directory.

Both are **mutable development data**. They must not be committed.

The copied Weaviate data should originate from a consistent snapshot and should initially be opened with the same Weaviate version used by the server test environment.

The current test deployment uses **Weaviate 1.40.1** (#312).

## 2. Development safety rules

For normal development:

- use `local_data/tasks.db`;
- use `local_data/weaviate_semant_test/`;
- do not connect the backend to production databases;
- do not use the shared server test Weaviate for automated or destructive development work;
- do not run destructive schema/data scripts until the configured Weaviate endpoint has been verified;
- do not commit database files or copied user data.

The local snapshot is intended for realistic manual and exploratory development.

A snapshot taken before #327 holds its annotations only in the legacy `Span` collection; the
backend then shows none and logs an error at startup. Migrate the local copy once, with the
local Weaviate running (the data directory copy you started from is the backup):

```bash
cd semant_demo_backend
../.venv/bin/python -m semant_demo.maintenance.annotation_migration backfill --state local-migration.json \
  --execute --confirm-endpoint localhost:8080 --offline-backup "the original snapshot"
../.venv/bin/python -m semant_demo.maintenance.annotation_migration verify
```

See [DATA_MAINTENANCE.md](DATA_MAINTENANCE.md#annotation-migration-annotation_migration-327).

An `Annotation` collection created before #328 lacks the derived annotation properties: the
backend logs an error and stores no annotation text, positions or vectors. Add them to the local
copy and derive the existing spans (`--no-vectors` when no embedding service is running locally;
set `ANNOTATION_VECTOR_CONFIG=` to an empty value to disable vectors in the backend too):

```bash
../.venv/bin/python -m semant_demo.maintenance.annotation_enrichment add-schema --execute --confirm-endpoint localhost:8080
../.venv/bin/python -m semant_demo.maintenance.annotation_enrichment backfill --limit 100000 --no-vectors \
  --execute --confirm-endpoint localhost:8080
```

Automated fast tests must not depend on this snapshot. Automated integration tests should create and clean up test-owned data, as described in [ADR 0005](adr/0005-testing-contract.md).

## 3. Start local Weaviate

Run Weaviate from the repository root:

```bash
docker run --rm \
  --name semant-weaviate-dev \
  --stop-timeout 120 \
  -p 127.0.0.1:8080:8080 \
  -p 127.0.0.1:50051:50051 \
  --mount type=bind,source="$(pwd)/local_data/weaviate_semant_test",target=/var/lib/weaviate \
  -e QUERY_DEFAULTS_LIMIT=25 \
  -e AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true \
  -e PERSISTENCE_DATA_PATH=/var/lib/weaviate \
  -e ENABLE_API_BASED_MODULES=true \
  -e CLUSTER_HOSTNAME=node1 \
  -e DISK_USE_READONLY_PERCENTAGE=90 \
  -e DISK_USE_WARNING_PERCENTAGE=50 \
  cr.weaviate.io/semitechnologies/weaviate:1.40.1 \
  --host 0.0.0.0 \
  --port 8080 \
  --scheme http
```

This runs Weaviate in the foreground. Stop it with `Ctrl-C`.

The local ports intentionally match the backend defaults:

| Interface | Local endpoint |
|---|---|
| REST | `http://localhost:8080` |
| gRPC | `localhost:50051` |

Verify readiness:

```bash
curl http://localhost:8080/v1/.well-known/ready
```

The response should indicate that Weaviate is ready before starting the backend.

To inspect container logs from another terminal:

```bash
docker logs semant-weaviate-dev
```

### Starting in the background

If needed, add `-d` to the `docker run` command.

Then stop it with:

```bash
docker stop semant-weaviate-dev
```

## 4. Local SQLite database

The backend reads the SQL database URL from `SQL_DB_URL`. The default is:

```text
sqlite+aiosqlite:///tasks.db
```

relative to the backend working directory. To use the local development database, either point `SQL_DB_URL` at it (four slashes: absolute path), for example from `semant_demo_backend/`:

```bash
export SQL_DB_URL="sqlite+aiosqlite:///$(realpath ../local_data/tasks.db)"
```

or keep the default and use a symlink from the backend directory. From the repository root:

```bash
ln -s ../local_data/tasks.db semant_demo_backend/tasks.db
```

Do not overwrite an existing `semant_demo_backend/tasks.db` without first checking what it contains.

Verify the link:

```bash
ls -l semant_demo_backend/tasks.db
```

It should point to:

```text
../local_data/tasks.db
```

Optionally verify the copied SQLite database:

```bash
sqlite3 local_data/tasks.db "PRAGMA quick_check;"
```

A healthy database should return:

```text
ok
```

Check which database a running backend uses before relying on its contents: an unset `SQL_DB_URL` without the symlink silently creates a new empty `tasks.db`.

## 5. Backend setup

Python 3.12 or newer is required.

From the repository root:

```bash
python3.12 -m venv .venv
. .venv/bin/activate

python -m pip install -r semant_demo_backend/requirements-dev.lock
python -m pip install --no-deps -e semant_demo_backend
```

`make setup` runs the same installation (and `npm ci` for the frontend).

Start the backend from `semant_demo_backend/` so the current relative SQLite path resolves correctly:

```bash
cd semant_demo_backend

python -m uvicorn semant_demo.main:app \
  --reload \
  --host 127.0.0.1 \
  --port 8000
```

With the local Weaviate running on ports `8080` and `50051`, no Weaviate environment-variable overrides are required.

The API should then be available at:

```text
http://localhost:8000
```

Swagger UI:

```text
http://localhost:8000/docs
```

Health endpoint:

```bash
curl http://localhost:8000/health
```

## 6. Frontend setup

From another terminal:

```bash
cd semant_demo_frontend
npm ci
npm run dev
```

The development frontend normally runs on:

```text
http://localhost:9000
```

When `BACKEND_URL` is not set, the frontend sends its requests to the backend origin
`http://localhost:8000` (`/api/...`), so no additional configuration is normally required for
local development.

## 7. Embedding service

Vector and hybrid search require an embedding service.

It can be run locally according to [the embedding service README](../embedding_service/README.md).

When using an explicitly authorized server-hosted development embedding service, an SSH tunnel can be used:

```bash
ssh -N \
  -L 8001:localhost:8001 \
  xlogin00@semant.fit.vutbr.cz
```

Then start the backend with:

```bash
EMBEDDING_SERVICE_HOST=localhost \
EMBEDDING_SERVICE_PORT=8001 \
python -m uvicorn semant_demo.main:app --reload
```

A live embedding service is not required for ordinary fast tests. Tests should use fixed vectors where the embedding model itself is not under test.

## 8. AI services

AI-assisted tagging, summarization, RAG, and chat may require Topicer, Ollama, OpenAI-compatible APIs, Gemini, or other configured providers.

These services are optional for routine code changes unless the assigned issue specifically requires them.

Required automated tests should use deterministic fake providers wherever practical. Do not use paid or production AI services merely to make routine tests pass.

## 9. Resetting local database state

The databases under `local_data/` are development copies and may be modified by the application.

Stop Weaviate before replacing its persistence directory:

```bash
docker stop semant-weaviate-dev
```

Then replace:

```text
local_data/weaviate_semant_test/
```

with a fresh consistent copy when a clean realistic snapshot is required.

Likewise, replace:

```text
local_data/tasks.db
```

with a fresh SQLite snapshot when needed.

Do not copy a new Weaviate persistence directory over a running Weaviate instance.

## 10. Destructive database utilities and data maintenance

Some utilities under `weaviate_utils/` drop collections or delete data (for example
`db_insert_jsonl.py --delete-old` and schema reset/build scripts). Before using such a command:

1. verify that local Weaviate is running;
2. verify the configured endpoint is `localhost`;
3. confirm that the operation is intended for the local development copy;
4. stop if the command could reach a shared server or production database.

Agents must not infer that an endpoint is safe merely because it is described as "test".

The reviewed audit/repair commands (chunk tag audit, documents without chunks, Kramerius
metadata sync) and how to practise them on a copy of the snapshot are described in
[DATA_MAINTENANCE.md](DATA_MAINTENANCE.md).

## 11. Testing versus development data

There are two different uses of Weaviate during development:

### Realistic development snapshot

```text
local_data/weaviate_semant_test/
```

Use this for:

- manual development;
- exploratory testing;
- reproducing behavior against realistic data;
- explicit data-compatibility checks when changing schemas or storage adapters.

### Automated integration-test data

Automated integration tests must create or reset the specific data they require.

Tests must not rely on arbitrary existing documents, users, collections, tags, or annotations in `local_data/`.

Two commands run automated tests against real stores (both need Docker):

```bash
make test-integration   # pytest -m integration against a throwaway Weaviate
make test-e2e           # Playwright smoke suite against the deterministic app profile
```

They never use the development container or `local_data/`:

- `scripts/with-test-weaviate.sh` starts a uniquely named Weaviate container with no volume
  (with the `backup-filesystem` module; its backups stay inside the container)
  on random loopback ports, passes them to the tests as `SEMANT_TEST_WEAVIATE_HOST`,
  `SEMANT_TEST_WEAVIATE_REST_PORT` and `SEMANT_TEST_WEAVIATE_GRPC_PORT` together with a
  fresh random `SEMANT_TEST_STORE_TOKEN`, and removes the container afterwards. The
  application's own `WEAVIATE_*` settings are not used. The CI job sets its own token.
- Before creating or deleting anything, the tests verify that the instance belongs to the
  current run (`semant_demo_backend/tests/weaviate_store.py`): an empty instance is claimed
  with a marker collection holding the token, an instance whose marker holds the same
  token is accepted, and everything else is refused, including a marker left by another
  run. Pointing the variables at the development snapshot therefore fails without changing
  it. Hosts other than loopback are refused unless `SEMANT_TEST_WEAVIATE_ALLOW_NONLOCAL=1`
  (CI service container).
- Before every integration test the application collections are emptied and seeded with
  the synthetic corpus in `semant_demo_backend/tests/fixtures/corpus.json` (users, three
  collections incl. a shared one, documents in several collections, partial chunk
  membership, manual/automatic/rejected annotations in their collections' annotation tenants
  (the legacy `Span` collection is created empty, for the migration tests) and chunk tag references, Czech
  diacritics, a combining mark and a non-BMP character). The collections are created once
  per run and are dropped and recreated only when their configuration no longer matches
  (e.g. a test dropped one or auto-schema added a property); dropping and recreating them
  for every test was the main cost of the suite and could stall ~20 s in Weaviate. A
  missing or unowned store is an error, never a skip.
- `make test-e2e` builds the frontend into `semant_demo_frontend/dist/e2e` and starts
  `python -m tests.e2e_server` (from `semant_demo_backend`): the same seeded corpus, a
  temporary SQLite database with the corpus users, the built frontend on the same origin,
  and fake embedding/Topicer providers on the next port. The port after that
  (`http://127.0.0.1:8767`, the profile's `ALLOWED_ORIGIN`) serves the same build again, so
  `test/e2e/quota.spec.ts` checks the guest cookie across origins, as in local development
  (:9000 → :8000). All AI provider URLs point at the
  fakes and no API keys are set; unfaked provider routes answer 501.

The profile serves at `http://127.0.0.1:8765`; log in with a corpus user, e.g. `owner` /
`owner-password-1`.

Browser specs set up their state with the shared helpers in
`semant_demo_frontend/test/e2e/support.ts` (conventions and examples at their code):
`useViewport` (wide / narrow / phone, as in the UI captures), `ensureLoggedIn` / `logOut`
from any session state, `search`, `goToResultsPage` and `editSearchResults` for edge cases
the corpus lacks. Every test sets up its own state and passes alone or in any order.

### Fast browser-test loop

`make test-e2e` rebuilds the frontend, starts a new Weaviate and reseeds for every run. While
working on one spec or one UI change, keep a profile running instead
(`scripts/e2e-dev.sh`, opt-in; CI does not use it). Prerequisites are those of
`make test-e2e`: Docker, `make setup` (`.venv`, `node_modules`) and Playwright's Chromium,
which `make e2e-dev-start` installs.

```bash
make e2e-dev-start      # build into dist/e2e-dev, start an owned Weaviate + e2e_server on :8775
make e2e-dev-test ARGS="test/e2e/searchResultCards.spec.ts --grep phone"
make e2e-dev-test ARGS="test/e2e/searchResultCards.spec.ts --grep phone"   # again, ~3 s
make e2e-dev-stop       # stop the server, remove its Weaviate container and temporary files
```

The Make targets call `scripts/e2e-dev.sh start|test|capture|rebuild|restart|status|logs|stop`;
`scripts/e2e-dev.sh test <playwright args>` forwards spec paths, `--grep`, `--headed`,
`--trace on` etc. unchanged. Behaviour:

- **Ownership.** The Weaviate comes from `scripts/with-test-weaviate.sh` (own container, no
  volume, fresh ownership token); nothing touches `local_data/` or the development container.
  `start` and `restart` refuse an inherited `SEMANT_TEST_WEAVIATE_HOST` (with it set, the
  helper would use that external store instead of a disposable one). The profile runs in the background in its own process group; `stop` ends that group
  (also a server left behind by a killed wrapper) and removes only the container recorded in
  `.e2e-dev/server.log`. State (pid, logs, build fingerprints) is in `.e2e-dev/`, ignored by
  git. The port is `E2E_DEV_PORT` (default 8775, fake providers on 8776, the cross-origin frontend on 8777), so the loop does
  not collide with `make test-e2e` on 8765. A running profile keeps the port it was started
  on; commands with a different `E2E_DEV_PORT` are refused until `stop`.
- **No silent widening.** `test` needs a selection, a spec or directory path or `--grep`;
  options alone (`--headed`, `--project=...`) fail, and only `test --all` runs the whole
  suite. A named `*.spec.ts` that does not exist fails; a filter that matches nothing fails
  with Playwright's "No tests found". Playwright never starts its own server in this mode:
  if the profile is not running or does not answer `/health`, `test` fails.
- **Stale code is refused.** `start` and `rebuild` record a fingerprint of the frontend
  sources (tracked and untracked, excluding `test/` and the Playwright config) together
  with the port, since `BACKEND_URL` is compiled into the build; `start`
  records one of the backend package and test-profile code/fixtures. `test` refuses to run
  when the frontend changed since the served build (`make e2e-dev-rebuild`, ~15 s, keeps the
  server and its data) or the backend changed since start (`make e2e-dev-restart`, ~13 s,
  fresh Weaviate and seed). Editing a spec needs neither. The served build is not
  hot-reloaded; only a build made after the edit is tested.
- **Data.** Specs clean up what they create, so one seeded profile serves many runs. If a
  test fails half-way (or you click around in the profile) and leaves data behind,
  `make e2e-dev-restart` reseeds the fixture corpus.
- **Display.** The script runs headless Chromium without `DISPLAY` (unless `--headed`,
  `--debug` or `--ui` is passed): with a forwarded X display (`ssh -X`) Chromium otherwise
  waits ~25 s for its first frame at every browser launch. `make test-e2e` unsets it too.

**UI captures.** `make e2e-dev-capture` runs `semant_demo_frontend/test/capture/views.spec.ts`
in three projects, wide desktop (1920×1000), narrow desktop with both sidebars open
(1280×900, asserted) and phone (390×844), and saves real rendered views as
`semant_demo_frontend/test-results/ui-capture/<view>-<wide|narrow|phone>.png`. Every test in
these projects also keeps its end-of-test screenshot and trace in
`test-results/<test>-<project>/` (`npx playwright show-trace .../trace.zip`). Pass a spec to
run it in these projects instead of the view captures, e.g.
`make e2e-dev-capture ARGS="test/e2e/sidebar.spec.ts --project=narrow"`; specs that set their
own viewport keep it. `test-results/` is ignored by git and emptied on every Playwright run.
Captures are for reviewing UI changes ([UI change checklist](../CONTRIBUTING.md#ui-change-checklist));
nonvisual work does not need them, and `make test-e2e` never runs `test/capture`.

Measured on a workstation for `searchResultCards.spec.ts --grep phone` (one test):

| | setup (once) | each run |
| --- | --- | --- |
| before: `make test-e2e`-style run of one spec | — | 53 s (30 s without the `DISPLAY` stall) |
| fast loop | 27 s `start` with build, 13 s without | 3.4 s |

The whole suite through the loop (`test --all`) took 78 s versus 132 s for `make test-e2e`
before it unset `DISPLAY` and 107 s after (both include the build and the seed).
The loop is for iteration only: run `make test-e2e` (fresh build, store and seed) before
asking for a PR merge. Without the script, `E2E_REUSE_SERVER=1 npx playwright test` still
reuses a profile you started by hand on port 8765 (built with that `BACKEND_URL`).

## 12. Normal local startup sequence

A typical development session is:

```text
1. Start local Weaviate from local_data/weaviate_semant_test
2. Verify /v1/.well-known/ready
3. Set SQL_DB_URL to local_data/tasks.db, or ensure semant_demo_backend/tasks.db points to it
4. Activate the Python environment
5. Start the backend from semant_demo_backend/
6. Start the frontend
7. Start/tunnel optional embedding or AI services only when needed
```

No SSH access to the database server is required for ordinary local development.