# Local Development

This document describes the standard local development environment for SemANT: a
**seeded, persistent local application** on your machine, with hot reload and fake AI
providers. It needs no database snapshot, server access, GPU or AI credentials.

For deployment and server configuration, see [DEPLOYMENT.md](DEPLOYMENT.md).
If you are new to the project, start with [START_HERE.md](START_HERE.md).

Shared server test databases and production databases are never development targets. A
realistic database snapshot is an optional, explicitly authorized advanced workflow
([section 5](#5-advanced-an-authorized-realistic-snapshot)), not a prerequisite.

## 1. Quick start: the seeded local application

Prerequisites (Linux; tested on Ubuntu 22.04 with Docker 27): **Python 3.12, Node.js 22, npm, Make,
Docker** (your user can run `docker`) and `curl`. From the repository root:

```bash
make setup          # once, and after dependency changes: .venv and node_modules
make dev-up         # start the development Weaviate; seed it and SQLite on first use only
make dev-backend    # terminal 1: fake AI providers + backend with --reload on :8000
make dev-frontend   # terminal 2: Quasar dev server with hot module replacement on :9000
```

Open <http://localhost:9000> (use `localhost`, not `127.0.0.1`: the backend allows only
the origin `http://localhost:9000`) and log in with one of the seeded accounts:

| Login (username or e-mail) | Password | What the account sees |
|---|---|---|
| `owner` / `owner@example.com` | `owner-password-1` | owns *Kroniky a dopisy* (shared with `annotator`) and *Noviny* |
| `annotator` / `annotator@example.com` | `annotator-password-1` | *Kroniky a dopisy* as a shared member: may annotate, not change documents or membership |
| `outsider` / `outsider@example.com` | `outsider-password-1` | owns only *Outsider notes*; no access to the other collections |
| `admin` / `admin@example.com` | `admin-password-1` | superuser |

`make dev-frontend` also tries to open a browser window (Quasar's `devServer.open`).
The data is the synthetic fixture corpus of the automated tests,
`semant_demo_backend/tests/fixtures/corpus.json`: three documents with seven Czech chunks
(diacritics, a combining mark, a non-BMP character), four tags, manual/automatic/rejected
annotations with their derived text, positions and vectors (#328), chunk tag references and
search classifications. Search for e.g. `Jan Novák`; open *Kroniky a dopisy* to see the
annotated Document view. This small corpus is for checking workflows, not search quality.

**More documents.** For the corpus overview (`/corpus`) three documents are too few:
`make dev-add-documents` adds 2,000 synthetic documents with bibliographic metadata only
(`tests/synthetic_documents.py`): years 1600–2000, mostly 1850–1940; the libraries `mzk`,
`nkp`, `svkhk` and `vkol`; the languages `ces`, its alias `cze`, `deu`, `lat` and `slk`; Czech,
German and Latin titles; and some values missing. It also adds the two outliers of the real
corpus, the years 311 and 2879, unless `OUTLIERS=no`. A larger `COUNT` (at most 1,000,000)
gives a corpus for measuring aggregates; 2,000 documents take a few seconds. The fixture schema
declares `library` as production does (`text`, `field` tokenization, #496); an older store
without it gets it declared the same way first.

**Existing local stores after #496.** The updated schema is used for *newly initialized*
development stores. `make dev-up` preserves an existing store; it does not convert
`Documents.yearIssued` from `number` to `int` or add its range index.
`make dev-add-documents` may add a missing `library` property, but does not change
the year type. To recreate an existing local store with the updated schema, use
`make dev-reset` **only if its local data can be discarded**: it deletes and reseeds
both the local Weaviate and SQLite stores (see [Lifecycle, reset and safety](#2-lifecycle-reset-and-safety)).
If the data must be retained, plan a separate, backed-up migration; the reset and
automated-test tools must never target the shared test or production databases.

Document `n` is always the same and existing ones are skipped, so running again adds
nothing and a larger `COUNT` adds the difference. The documents have no chunks, so Search
and Document view do not show them; `make dev-verify` reports them as one difference and
`make dev-reset` removes them. A running backend keeps its corpus overview for up to
`CORPUS_OVERVIEW_MAX_AGE` seconds (600); restart `make dev-backend` to see them at once.

**Hot reload.** Saving a Vue/TypeScript file updates the open page through Vite HMR. Saving
a Python file under `semant_demo_backend/semant_demo/` restarts the backend (Uvicorn
`--reload`); the databases are not touched. Changes to `semant_demo_backend/tests/`
(fixtures, fake providers) take effect after restarting `make dev-backend`; a changed
fixture corpus reaches the stores only through `make dev-reset`.

**Simulated AI.** `make dev-backend` starts the deterministic fake providers of the browser
tests (`semant_demo_backend/tests/fake_providers.py`) on `127.0.0.1:8009` and points every
provider setting at them, with no API keys:

| Feature | Fake behaviour |
|---|---|
| Vector/hybrid search, annotation vectors | hash-based 16-dimension embeddings: identical text matches, nothing else is semantically meaningful |
| AI tag suggestions (Topicer) | proposes a span wherever a tag example occurs in a chunk; streamed with a 0.5 s pause per chunk |
| Search titles/summaries, RAG, span chat, document summaries | a fixed "Fake summary of N passage(s)" text with token usage; the agentic RAG calls its tools once |
| RAG web search | switched off in the development RAG configurations (it would query a live search engine) |
| Anything else | the fake answers HTTP 501, so the feature fails visibly instead of reaching a live service |

Fake answers check wiring, streaming, persistence, permissions and quota accounting; they
say nothing about model quality. To use a real service, see [section 6](#6-real-embedding-and-ai-services).

## 2. Lifecycle, reset and safety

| Command | Effect |
|---|---|
| `make dev-up` | Start Weaviate. On the first run (empty store, no SQLite file) create the schema, seed both stores and verify them; afterwards keep all data, never reseed. |
| `make dev-backend` / `make dev-frontend` | Foreground servers; stop with Ctrl-C. Refuse to start when their ports are taken or the stores are not initialized. |
| `make dev-down` | Stop Weaviate. Data (yours and the seed) and accounts are kept. |
| `make dev-status` | Container state, object counts, users and whether Weaviate and SQLite belong together. |
| `make dev-verify` | Compare the stores with the seeded corpus (ids, collection owners and shares, users, annotations); non-zero exit when your edits differ from it. |
| `make dev-add-documents` | Add synthetic metadata-only documents (`COUNT`, default 2000; `OUTLIERS=no`), see [More documents](#1-quick-start-the-seeded-local-application). Writes only to this checkout's pair, like the commands above. |
| `make dev-reset` | Show what would be destroyed, then ask you to type `reset`. Non-interactively (agents) use `make dev-reset CONFIRM=yes`. Drops everything in both development stores and reseeds the identical corpus. Refuses while the backend runs, and refuses stores that are not this checkout's pair (see below). |

Where the data lives:

| Store | Location |
|---|---|
| Weaviate 1.40.1 | Docker container `semant-weaviate-local` on the Docker volume `semant-local-weaviate`; REST `127.0.0.1:8180`, gRPC `127.0.0.1:50151` |
| SQLite (accounts, RAG feedback, quota ledger) | `.dev-data/semant.db` (ignored by git), also generated configuration in `.dev-data/config/` and `feedback.log.jsonl` |

The backend gets explicit settings (`python -m tests.local_dev environ` prints them), not
the relative `tasks.db` default. The container is removed by `make dev-down`, so while it
is stopped `docker volume prune -a` would delete the volume; `make dev-up` then refuses the
unpaired SQLite file, which you move away yourself (it may hold accounts you registered).

**Ownership checks.** `make dev-up` creates the volume and container with the label
`org.semant.purpose=local-development`, and the first initialization writes a random token
into both stores (the `SemantLocalDevMarker` collection and the `semant_local_dev_marker`
table). Every writing command first checks that the container and volume carry the label,
that the container publishes the configured REST and gRPC ports on loopback, and that both
stores carry the development marker with the same token
(`semant_demo_backend/tests/local_dev.py`). Initialization writes only into an empty
Weaviate with no SQLite file. A reset destroys only this checkout's pair (the same token in
both stores) or an interrupted initialization (see below). Anything else is refused without
a change, even with `CONFIRM=yes`: a snapshot, an automated-test store (which has its own
marker and token), another checkout's Weaviate, a SQLite file from another initialization
or without its Weaviate, or a file without the marker. The Docker volume is machine-wide
but `.dev-data/` belongs to one checkout, so an unpaired store may be someone's work and is
never discarded automatically. `local_data/` and the containers of `make test-integration`, `make test-e2e` and
`make e2e-dev-*` are never used; those tools refuse the development store in turn.

Repeated resets give the same logical data: fixed ids, timestamps and fake vectors (only
the password hashes differ). An interrupted initialization or reset leaves a marker in
state `initializing`; `make dev-up` then refuses and `make dev-reset` starts over (it
accepts such a marker with this checkout's token, or with no SQLite file created yet).

**One instance per machine.** The container, volume and ports are fixed, so several
checkouts or agents share one development instance; `.dev-data/` belongs to the checkout
that ran `make dev-up`, and another checkout's `make dev-up`, `dev-backend`, `dev-verify`
and `dev-reset` refuse the pair as not its own. Run one checkout's environment at a time:
work in the owning checkout, or, to give the instance to another checkout, discard its
Weaviate data deliberately there first (`make dev-down`, `docker volume rm
semant-local-weaviate`). Ports can be
moved with `SEMANT_DEV_WEAVIATE_REST_PORT`, `SEMANT_DEV_WEAVIATE_GRPC_PORT`,
`SEMANT_DEV_PROVIDER_PORT` and `SEMANT_DEV_BACKEND_PORT` (the frontend stays on :9000);
use the same values for every command.

Coding agents use exactly these targets for interactive work, and disposable test-owned
stores (`make test-integration`, `make test-e2e`, `make e2e-dev-*`) for automated tests.

**Parallel checkouts (e.g. a git worktree per agent or branch).** Another checkout can reuse
this checkout's backend environment: pass `PYTHON=/path/to/first-checkout/.venv/bin/python`
to `make`. The tests, `api-check` and the E2E server still import the code of the checkout
they run in. Run `npm ci` in its `semant_demo_frontend` (seconds with a warm npm cache).
Each test run owns its Weaviate, so `make check` and `make test-integration` can run in
several checkouts at once. `make test-e2e` uses ports 8765–8767 (`E2E_PORT` moves the
first) and `make e2e-dev-*` 8775–8777 (`E2E_DEV_PORT`), so start concurrent runs at least
three ports apart. The development instance above stays one per machine.

## 3. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `port 8180 or 50151 is already in use` | Another service (e.g. a snapshot Weaviate moved there) holds the port; stop it or set the `SEMANT_DEV_*` ports. |
| `port 8000 is already in use` / `port 9000 ...` | An older backend or frontend is still running; stop it. Quasar would otherwise move to another port the backend does not allow. |
| `refused: ... holds data without the local development marker` | The configured port reaches a store that is not the development store; nothing was changed. |
| `refused: Weaviate is empty but .dev-data/semant.db exists` | The Weaviate volume was removed. Move the unpaired database away yourself (e.g. `mv .dev-data/semant.db .dev-data/semant.db.unpaired`), then `make dev-up`. |
| `refused: ... is missing` or `not the same development pair` | The Weaviate data belongs to another checkout (or this checkout's `.dev-data/` was removed). Work in the owning checkout, or discard the Weaviate data deliberately: `make dev-down`, `docker volume rm semant-local-weaviate`, then `make dev-up`. Reset never does this for you. |
| `publishes REST/gRPC on ..., not 127.0.0.1:...` | The container was started with other ports; `make dev-down`, then `make dev-up` with the same `SEMANT_DEV_*` ports as the other commands. |
| `refused: ... has no valid development marker` (SQLite) | `.dev-data/semant.db` is not a development database; move it away yourself. |
| `A previous initialization or reset did not finish` | `make dev-reset`. |
| Requests fail with CORS errors | Open `http://localhost:9000`, not `127.0.0.1:9000`. |
| A feature reports a provider error | It uses a provider route the fakes do not implement (HTTP 501); see the table above. |
| `make dev-backend` says the stores are not initialized | Run `make dev-up` first. |

`make dev-status` shows the state of both stores; `scripts/local-dev.sh logs` the
Weaviate log. Removing everything by hand (only if you want to): `make dev-down`,
`docker volume rm semant-local-weaviate`, `rm -r .dev-data`.

## 4. Testing versus development data

The development stores of sections 1–2 are for interactive work. Automated tests never read
or change them; each creates and removes its own test-owned data. Tests must not rely on
arbitrary existing documents, users, collections, tags or annotations of any development
store (see [ADR 0005](adr/0005-testing-contract.md)).

`make check` needs no database at all. Two commands run automated tests against real
stores (both need Docker); they run independently of `make dev-up`:

```bash
make test-integration   # pytest -m integration against a throwaway Weaviate
make test-e2e           # Playwright smoke suite against the deterministic app profile
```

While iterating, run only the affected integration tests: the container starts in about a
second, so one file takes ~30 s instead of ~4 min for the whole suite, e.g.
`make test-integration ARGS="tests/integration/test_chunk_tags.py -k bulk"` (paths relative
to `semant_demo_backend`). Run the full suite before review when the change needs it.

They never use the development container, `.dev-data/` or `local_data/`:

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
- **Server log.** `make test-e2e` shows only the profile's warnings and errors, not one
  `HTTP request completed` line per request; `E2E_LOG_LEVEL=INFO make test-e2e` shows them.
  The loop keeps them (`E2E_LOG_LEVEL` defaults to `INFO` there) in `.e2e-dev/server.log`,
  which `scripts/e2e-dev.sh logs` prints.

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

## 5. Advanced: an authorized realistic snapshot

Only with explicit authorization to use a **development** snapshot of the Weaviate data
directory and the matching SQLite database (both from one consistent point in time).
Snapshots are **not** created, validated or upgraded by the seeded environment, and the
seeded commands never read or change them. A snapshot must suit the current schema and
Weaviate 1.40.1; older snapshots need the migrations below. Never point this workflow at
the shared server test store or production.

The snapshot Weaviate uses the backend's default ports 8080/50051 and the container name
`semant-weaviate-dev`, so it can run next to the seeded environment (8180/50151,
`semant-weaviate-local`). Start the backend by hand (section 5.5) with `SQL_DB_URL`
pointing at the snapshot's SQLite file; `make dev-backend` always uses the seeded stores.

### 5.1 Snapshot layout

From the repository root, the expected snapshot is:

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

### 5.2 Snapshot safety rules and migrations

When working with a snapshot:

- use `local_data/tasks.db` and `local_data/weaviate_semant_test/` only;
- do not connect the backend to production databases;
- do not use the shared server test Weaviate for automated or destructive development work;
- do not run destructive schema/data scripts until the configured Weaviate endpoint has been verified;
- do not commit database files or copied user data.

The snapshot is intended for realistic manual and exploratory checks, e.g. data
compatibility of a schema or storage change; the seeded environment covers ordinary work.

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

One created before #460 also lacks the provenance properties: the backend then records no
provenance and checks no edit versions. Add them (existing spans keep an unknown origin):

```bash
../.venv/bin/python -m semant_demo.maintenance.annotation_provenance add-schema --execute --confirm-endpoint localhost:8080
```

Chunks without the positions of #463 (`startChar`, `startWord`, `wordOpenAtStart`) leave new or
moved annotations without derived text (`derive_annotation` failures; the backend logs an error at
startup). Add and fill them on the local copy, then restart the backend; a seeded development
store from before #463 is fixed the same way (with its endpoint) or by `make dev-reset`:

```bash
../.venv/bin/python -m semant_demo.maintenance.chunk_positions --write positions.json --confirm-endpoint localhost:8080
```

Automated tests never depend on this snapshot (section 4).

### 5.3 Start the snapshot Weaviate

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

#### Starting in the background

If needed, add `-d` to the `docker run` command.

Then stop it with:

```bash
docker stop semant-weaviate-dev
```

### 5.4 Snapshot SQLite database

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

### 5.5 Backend and frontend by hand

After `make setup` (see [CONTRIBUTING.md](../CONTRIBUTING.md#2-setup-and-commands) for the
same installation without Make), start the backend from `semant_demo_backend/` so the current relative SQLite path resolves correctly:

```bash
cd semant_demo_backend
. ../.venv/bin/activate
python -m uvicorn semant_demo.main:app \
  --reload \
  --host 127.0.0.1 \
  --port 8000
```

With the snapshot Weaviate running on ports `8080` and `50051`, no Weaviate environment-variable overrides are required.
This backend uses the configured real providers (`semant_demo/configs/`): without them, AI
features and vector search fail (section 6).

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

#### Frontend

From another terminal:

```bash
cd semant_demo_frontend
npm run dev
```

The development frontend normally runs on:

```text
http://localhost:9000
```

When `BACKEND_URL` is not set, the frontend sends its requests to the backend origin
`http://localhost:8000` (`/api/...`), so no additional configuration is normally required for
local development.

### 5.6 Replacing the snapshot

The databases under `local_data/` are copies and may be modified by the application. No
`make dev-*` command resets or replaces them.

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

## 6. Real embedding and AI services

The seeded environment uses fakes (section 1). With explicit authorization, a backend
started by hand (section 5.5) can use real services instead.

### Embedding service

Vector and hybrid search require an embedding service whose model matches the named vector
of the snapshot's chunks. The deployed embedder is Qwen3-Embedding-0.6B on vLLM
([deploy/README](../deploy/README.md#qwen-embedding-service-385)), published on the server's
loopback port 8002; the former Gemma service on port 8001 ([embedding_service/](../embedding_service/README.md))
is no longer running there; only `configs/*_gemma.yaml` still target it.

With explicit authorization to use the server's embedder, tunnel its port:

```bash
ssh -N -L 8002:localhost:8002 xlogin00@semant.fit.vutbr.cz
```

Then start the backend with a copy of `configs/search_vectors_qwen.yaml` whose `base_url` is
`http://localhost:8002/v1` (the snapshot's chunks must hold the `Qwen3_Embedding_0_6B` vector):

```bash
SEARCH_VECTORS_CONFIG=/path/to/search_vectors_local.yaml \
python -m uvicorn semant_demo.main:app --reload
```

The default annotation vector (`configs/annotation_vector_qwen.yaml`) uses the deployment's
`qwen-embedder` URL too: point `ANNOTATION_VECTOR_CONFIG` at a copy with the same `base_url`,
or set it empty to configure no annotation vector.

A live embedding service is not required for ordinary fast tests. Tests should use fixed vectors where the embedding model itself is not under test.

### AI services

AI-assisted tagging, summarization, RAG, and chat may require Topicer, Ollama, OpenAI-compatible APIs, Gemini, or other configured providers.

These services are optional for routine code changes unless the assigned issue specifically requires them.

Required automated tests should use deterministic fake providers wherever practical. Do not use paid or production AI services merely to make routine tests pass.

## 7. Destructive database utilities and data maintenance

Some utilities under `weaviate_utils/` drop collections or delete data (for example
`db_insert_jsonl.py --delete-old` and schema reset/build scripts). Before using such a command:

1. verify that the intended local Weaviate is running;
2. verify the configured endpoint is `localhost` and the intended port (8080 snapshot, 8180 seeded environment);
3. confirm that the operation is intended for that local copy;
4. stop if the command could reach a shared server or production database.

Agents must not infer that an endpoint is safe merely because it is described as "test".
To return the seeded environment to its initial state, use `make dev-reset`, not these
utilities.

The reviewed audit/repair commands (chunk tag audit, documents without chunks, Kramerius
metadata sync) and how to practise them on a copy of the snapshot are described in
[DATA_MAINTENANCE.md](DATA_MAINTENANCE.md).
