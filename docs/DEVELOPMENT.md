# Local Development

This document describes the standard local development environment for SemANT.

Normal development should use local database state under `local_data/`. Shared server test databases and production databases are not normal development targets.

For deployment and server configuration, see [DEPLOYMENT.md](DEPLOYMENT.md).

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

The current test deployment uses **Weaviate 1.34.4**.

## 2. Development safety rules

For normal development:

- use `local_data/tasks.db`;
- use `local_data/weaviate_semant_test/`;
- do not connect the backend to production databases;
- do not use the shared server test Weaviate for automated or destructive development work;
- do not run destructive schema/data scripts until the configured Weaviate endpoint has been verified;
- do not commit database files or copied user data.

The local snapshot is intended for realistic manual and exploratory development.

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
  cr.weaviate.io/semitechnologies/weaviate:1.34.4 \
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

When `BACKEND_URL` is not set, the current frontend configuration uses:

```text
http://localhost:8000/api
```

so no additional backend URL configuration is normally required for local development.

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

## 10. Destructive database utilities

Some utilities under `weaviate_utils/` can drop collections or delete data.

In particular, commands using options such as:

```text
--delete-old
```

and schema reset/build scripts may be destructive.

Before using such a command:

1. verify that local Weaviate is running;
2. verify the configured endpoint is `localhost`;
3. confirm that the operation is intended for the local development copy;
4. stop if the command could reach a shared server or production database.

Agents must not infer that an endpoint is safe merely because it is described as "test".

### Chunk tag audit and cleanup

`python -m semant_demo.maintenance.chunk_tag_audit` (run in `semant_demo_backend/`)
compares the chunk `automaticTag` / `positiveTag` / `negativeTag` references with the spans
(ADR 0004). Without options it only reads and prints counts; `--report FILE` also writes
the list of `unbacked` references (no matching span) and `missing` references (a span
exists, the chunk lacks the reference). It uses the `WEAVIATE_*` settings.

Correcting data is a separate, reviewed step: review the report, back up the data, then

```bash
python -m semant_demo.maintenance.chunk_tag_audit --apply FILE \
  --remove-unbacked [--add-missing] --confirm-endpoint localhost:8080
```

It refuses to run unless `--confirm-endpoint` and the report's endpoint equal the
configured endpoint, and it re-checks every listed (chunk, tag) pair against the spans
stored at that moment. Never run `--apply` against a shared or production database
without explicit authorization for that task.

### Kramerius metadata sync

`python -m semant_demo.maintenance.metadata_sync` (run in `semant_demo_backend/`) copies
document metadata from the Kramerius PostgreSQL mirror (`meta_records`, maintained by the
`librarymetadata` project) to the `Documents` collection (#257). The field mapping is in
[DATABASE.md](DATABASE.md#document-metadata-from-the-kramerius-mirror); all options are in
the module docstring (`--help`). Writing to the deployed test or production stores is a
separately authorized operation (#259); this section covers the local check.

**Source library rule.** Each document uses only the mirror row of its own source library,
`(id, library)`; values that row lacks are never taken from another library, and the "most
complete" row is never chosen. The library is, in order:

1. an approved correction (`--library-override FILE`);
2. a verified map (`--library-map FILE`; a different stored library is a `library_conflict`);
3. page evidence (`--infer-library-from-pages`, below); it replaces a stored library it
   contradicts;
4. the stored `library`, unless listed by `--distrust-stored` (e.g. `mzk`, which older code
   wrote as a default and the API still shows for documents without one);
5. with `--infer-library-from-mirror`, for documents without page evidence (no chunks, or no
   page reaching the document): the mirror's only library for the id (`mirror_unique`),
   else the first library of `--library-priority` the mirror has (`mirror_priority`).

`--library-priority LIB,LIB,...` (highest first) encodes which libraries hold partial copies
of others; it chooses only among libraries that have the document (that its pages reach, or,
in 5, that have a row). Inferred libraries (3 and 5) are applied like the others; each entry
records `library_from` and its evidence, and `--inferred FILE` writes them (document,
library, method, confidence, verified pages, stored library) as a CSV for sampling. A wrong
line can be corrected and passed back with `--library-override`. Documents with no library,
a conflict, several mirror libraries none of which is in the priority list, or no row for
their library are `unresolved`. Map files are CSV `document_id,library` (further columns are
ignored).

**Page evidence** (`--infer-library-from-pages`). For each document the command reads the
distinct `Chunks.start_page_id` values of up to 1000 of its chunks (one query per document,
16 at a time; no text or vectors), looks the page UUIDs up in `meta_records` in all
libraries, and walks each page row up `(parent_id, parent_library)` within its own library
(batched, max depth 16) until it reaches the document's id. A page UUID match alone proves
nothing: only chains that reach the document count. Distinct start pages are the evidence
unit (several chunks on one page count once).

| Evidence | Report | Library |
|---|---|---|
| 2+ distinct pages reach the document, all in one library | `page_evidence.confidence: high` | that library (`library_from: page_ancestry`), replacing a different stored library |
| exactly one such page | `low` | the same |
| chains reach the document in several libraries (mirrored page UUIDs, or different pages in different libraries) | `ambiguous` | a stored library among them, else the first of them in `--library-priority` (`page_priority`), else `unresolved: page_evidence_ambiguous` |
| a `--library-map` / `--library-override` library the chains do not reach | | the explicit library; `page_evidence_disagrees: true` for review |
| no chunks, no valid start page, no page in the mirror, or no chain reaches the document | `no_chunks` / `none` | the stored library, else rule 5 |

Each entry's `page_evidence` lists chunks read (`truncated` beyond 1000), distinct valid
start pages, invalid or missing `start_page_id` values, pages not in the mirror, verified
pages per library, the statuses of chains that did not reach the document
(`other_document`, `cross_library`, `broken`, `cycle`, `too_deep`) and up to three sample
paths (UUIDs only). Failure modes: a store without `start_page_id` gives `none`; a mirror
missing one library's page rows makes the other library look unique (two libraries with
their own, differently identified pages are separate digitizations; the text came from the
one whose pages match).

**Update rule.** `library` and `public` always follow the selected row, so a document's
access matches its record in the source library (this can make a document public or
private; the report's `changed_properties.public` counts them). `title` is composed from the
row and its ancestors in the same library (periodical, volume, issue; see
[DATABASE.md](DATABASE.md#document-metadata-from-the-kramerius-mirror)). Other empty
properties are filled; replacing a differing value needs `--overwrite`, otherwise the change
is `held`. Values are never cleared (`stale` lists stored values the source row lacks). Only
declared properties are written, in their declared type; the schema changes only through
`--add-library-property`, which adds a text `library` (whole-value tokenization) so the
source library is stored. Applying requires it. `in_library` is reported only: the mirror
sets it on rows added or updated since the column was introduced, so `false` may just mean
"not reprocessed".

**Apply rule.** `--apply REPORT --confirm-endpoint HOST:PORT` refuses to run unless the
endpoint and collection equal the report's, the declared types are unchanged and include
`library`, and, without `--accept-incomplete`, the report has no unresolved documents. Per
document it writes only if the stored library and every changed property still equal the
report's old values, then reads the values back. The check and the write are not atomic, so
apply while nothing else edits document metadata. Running it again skips finished
documents. Exit code 1: nothing was eligible, or an eligible document was not written or
not verified (listed with the reason).

#### Local check on a copy of the development snapshot

Never run this against the only copy of `local_data/weaviate_semant_test/`, a shared
database or production. `make test-integration` does not use `local_data/`.

1. **Copy the snapshot offline.** Stop the development Weaviate (`docker stop
   semant-weaviate-dev`) so the files are consistent, check free space (the snapshot is
   ~110 MB; Weaviate turns read-only above `DISK_USE_READONLY_PERCENTAGE` of its disk),
   and copy it to an empty directory, e.g. `$COPY`. Some files are owned by the container's
   root user, so copy (and optionally checksum) through a container:

   ```bash
   mkdir "$COPY"
   docker run --rm --entrypoint sh \
     --mount type=bind,source="$(pwd)/local_data/weaviate_semant_test",target=/src,readonly \
     --mount type=bind,source="$COPY",target=/dst \
     cr.weaviate.io/semitechnologies/weaviate:1.34.4 -c 'cp -a /src/. /dst/'
   ```

   Restart the development Weaviate (section 3), then start the copy as a second instance
   with the section 3 command, changing only the name, ports and mount source:
   `--name semant-weaviate-metadata-test -p 127.0.0.1:18080:8080 -p 127.0.0.1:15051:50051
   --mount type=bind,source="$COPY",target=/var/lib/weaviate`. Check
   `curl localhost:18080/v1/.well-known/ready`, `/v1/schema/Documents` and the object counts.

2. **Point the command at the copy and the mirror.** In `semant_demo_backend/`:

   ```bash
   export WEAVIATE_HOST=localhost WEAVIATE_REST_PORT=18080 WEAVIATE_GRPC_PORT=15051
   ../.venv/bin/pip install "psycopg[binary]"     # driver, not an app dependency
   export KRAMERIUS_METADATA_DSN="postgresql+psycopg://librarymetadata_all@127.0.0.1:5888/librarymetadata_all"
   ```

   The DSN assumes an SSH tunnel to the mirror on port 5888 that you are authorized to
   use; keep passwords out of the command line and the repository. The command only reads
   the mirror.

3. **Read-only inventory.** `python -m semant_demo.maintenance.metadata_sync --report
   r1.json --infer-library-from-pages --library-priority LIB,LIB,...
   --infer-library-from-mirror --distrust-stored mzk --inferred inferred.csv --overwrite`
   (add `--limit N` / `--document-ids FILE` to narrow it). Check `counts`:
   `mirror_libraries` (none / one / several), `page_evidence`, `library_from`,
   `library_replaced`, `unresolved` kinds, `changed_properties` (especially `public` and
   `title`) and `held_properties`, and sample `changes` and `page_evidence` per library.

4. **Sample libraries.** Check a sample of `inferred.csv` per method (especially `low` and
   `page_priority`/`mirror_priority`); put corrections in an override file.

5. **Declare `library` on the copy:** `--add-library-property --confirm-endpoint localhost:18080`.

6. **Report for applying:** the step 3 options (plus `--library-override corrections.csv`)
   with `--report r2.json`. Sample replacements (`old` -> `new`) and review the unresolved
   list.

7. **Apply to the copy:** `--apply r2.json --confirm-endpoint localhost:18080
   [--accept-incomplete]`. Check `eligible`, `applied`, `verified`, `not_applied`, `failed`.

8. **Read back** through the application (`DocumentRepository.read` / `read_chunks`, a
   search with a `yearIssued` filter, the `library` of hits), then run step 7 again
   (expect `already_applied`) and a fresh report (expect `eligible: 0` apart from
   documents edited meanwhile).

9. **Clean up.** `docker stop semant-weaviate-metadata-test`; delete `$COPY` when done.
   Confirm the development snapshot was not modified (counts, no `library` property).

#### Results of the local check (2026-10-10)

Copy of the 500-document snapshot (3,260 chunks in 32 documents) and the real mirror:
237 documents have mirror rows in one library, 263 in several. Page evidence: 468
documents have no chunks; 23 got a library from their pages (20 `high`, 3 `low`; of the 263
with several libraries, 4 resolved to `mzk`, where both libraries hold the same number of
pages but only `mzk`'s page UUIDs match the chunks), and 9 are `ambiguous` (the same page
UUIDs reach the document in two libraries). All 14 single-library documents with chunks got
the same library from their pages as their single mirror row.

With the example priority `nkp,mzk` and `--infer-library-from-mirror` (2.2 s for the 500):
23 `page_ancestry`, 9 `page_priority`, 218 `mirror_unique`, 249 `mirror_priority`, 1
unresolved (`eod` + `knav`, neither in the list). The order matters: with `mzk,nkp`, 215
documents get `mzk` instead of `nkp`. `--overwrite` changes 360
titles, mostly issue numbers becoming full titles ("284" -> "Tagesbote. 76. 284"; "Právo
lidu. 183" -> "Právo lidu: časopis hájící zájmy… . 20. 183"). `mzk` issue rows without a
title or part number give only the periodical title ("Národní listy. 241" -> "Národní
listy"). 21 documents become non-public (the selected row's `public` is `false`), none
become public. Applying wrote and verified 499/499; applying again and a fresh report found
nothing to do; a stored library planted wrong was replaced from `high` page evidence and
verified. Details are on PR #258.

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
  membership, manual/automatic/rejected annotations and chunk tag references, Czech
  diacritics, a combining mark and a non-BMP character). The collections are created once
  per run and are dropped and recreated only when their configuration no longer matches
  (e.g. a test dropped one or auto-schema added a property); dropping and recreating them
  for every test was the main cost of the suite and could stall ~20 s in Weaviate. A
  missing or unowned store is an error, never a skip.
- `make test-e2e` builds the frontend into `semant_demo_frontend/dist/e2e` and starts
  `python -m tests.e2e_server` (from `semant_demo_backend`): the same seeded corpus, a
  temporary SQLite database with the corpus users, the built frontend on the same origin,
  and fake embedding/Topicer providers on the next port. All AI provider URLs point at the
  fakes and no API keys are set; unfaked provider routes answer 501.

To iterate on browser tests, run the profile yourself and let Playwright reuse it:

```bash
(cd semant_demo_frontend && QUASAR_DIST_DIR=dist/e2e BACKEND_URL=http://127.0.0.1:8765 npx quasar build)
scripts/with-test-weaviate.sh sh -c 'cd semant_demo_backend && ../.venv/bin/python -m tests.e2e_server --static ../semant_demo_frontend/dist/e2e'
# in another terminal:
cd semant_demo_frontend && E2E_REUSE_SERVER=1 npx playwright test
```

The profile serves at `http://127.0.0.1:8765`; log in with a corpus user, e.g. `owner` /
`owner-password-1`.

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