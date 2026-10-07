# Refactor status

Last updated: 2026-10-07

## Current state

- Integration branch: `197-refactor---base`
- Current issue: #200 — Add isolated real-store and browser test infrastructure (in review)
- Completed refactor issues: #198 (bootstrap and configuration; manually verified
  against local Weaviate), #199 (fast checks and blocking CI, PR #211)
- Current stage: R0

## Development environment

- Local realistic database snapshot is available under `local_data/`.
- Local Weaviate runs from `local_data/weaviate_semant_test`.
- Local SQLite state is `local_data/tasks.db`.
- Shared server databases are not used for normal refactor development.
- The SQL database is configurable through `SQL_DB_URL` (#198). The
  `semant_demo_backend/tasks.db` symlink still works with the default URL.
- Automated real-store and browser tests use throwaway test-owned Weaviate instances,
  never `local_data/` (#200, see DEVELOPMENT.md section 11).

## #198 outcome

- `Config(environ=...)` reads settings once from an explicit mapping or the process
  environment. The duplicated Topicer block was removed; the values that were already
  effective (`http://topicer:8089`, `openai`, `600.0`) are unchanged. The unused
  `TOPICER_READ_WRITE_TIMEOUT` / `TOPICER_RW_TIMEOUT` setting was removed.
- `semant_demo.main.create_app(config)` builds an app; `semant_demo.main:app` is still the
  production entry point. `bootstrap.AppResources` owns the SQL engine, lazily connected
  Weaviate client, summarizer, and RAG registry for one lifespan and is closed at shutdown,
  also after a failed startup.
- The RAG registry, JWT secret, CORS/static settings, feedback, and summarizer routes now
  use the app's config instead of import-time globals.
- OpenAPI output is byte-identical to the pre-change export.
- Tests: `tests/test_config.py`, `tests/test_app/test_bootstrap.py`; auth tests build their
  own app with `tests/app_support.make_test_config` instead of patching globals and reloading.

## #199 outcome

- Root `Makefile` with `make setup`, `make check`, `make api-generate` (plus `check-backend`,
  `check-frontend`, `api-check`). CONTRIBUTING documents the underlying commands.
- Backend: test tools moved from `requirements.txt` to `requirements-dev.txt`; the full
  development set is pinned in `requirements-dev.lock` (versions taken from the existing
  `.venv`, no upgrades). Ruff 0.14.0 added. pytest registers `integration`/`live`/`benchmark`
  markers with `--strict-markers`; `tests/conftest.py` refuses network connections
  (including loopback) in unmarked tests. `tests/fakes.py` provides `FakeChatAPI`.
- Auth tests use a function-scoped `client` fixture (fresh app and SQLite per test) and
  create their own users; each test passes alone.
- Frontend: `npm test` runs Vitest (real composable and Quasar component tests in
  `test/unit`), `npm run typecheck` runs vue-tsc, Node pinned to 22 (`.nvmrc`, engines).
  TypeScript raised from 4.9 to 5.5 because zod 4 typings cannot be parsed by 4.9 (a
  deliberate compatibility upgrade; production build verified). `skipLibCheck` enabled.
  The duplicate `User`/`TagData` interfaces in `src/models.ts` (ESLint errors) were merged
  without changing the effective `TagData` type; the unused stale `User` variant was removed.
- Generated client: `scripts/api-client.sh` generates into an empty directory and diffs
  for drift. 92 stale files the generator no longer produces were removed; all other
  generated files were already identical to the current schema.
- CI: backend job is blocking (no `continue-on-error`), installs the lock, runs Ruff and
  fast tests; new frontend job (lint, type check, tests) and drift job (pinned generator
  image). Production and test-main deploys now require all three to succeed (previously
  `always()`, i.e. they deployed even after failed tests). PR preview deploys are unchanged.

## #200 outcome

- `make test-integration`: `scripts/with-test-weaviate.sh` starts a uniquely named Weaviate
  1.34.4 container with no volume on random loopback ports and a random per-run
  `SEMANT_TEST_STORE_TOKEN`, and removes it afterwards; pytest runs `-m integration`
  against it. Tests read only `SEMANT_TEST_*`, never the application's `WEAVIATE_*`.
- Ownership (`tests/weaviate_store.py`) is specific to the run: an empty instance is
  claimed with a marker holding the token, a marker with the same token is accepted, and
  anything else (unmarked data, or a marker from another run) is refused before any write.
  Verified by pointing the variables at the local development Weaviate: refused, its
  collections unchanged. Non-loopback hosts need `SEMANT_TEST_WEAVIATE_ALLOW_NONLOCAL=1`.
  Collection names cannot be prefixed per run (some are also used as reference names in
  filters), so the run's namespace is the whole throwaway instance.
- Fixture corpus `tests/fixtures/corpus.json` (single source for pytest and Playwright,
  validated on load): owner/annotator/outsider/admin, three collections (one shared, one
  of another user), a document in two collections with partial chunk membership,
  manual/automatic/rejected spans and positive/automatic/negative chunk tag references,
  Czech diacritics, a combining mark, a non-BMP character, missing metadata. The test
  schema (`create_app_schema`) mirrors the properties/references the backend uses in the
  deployed schema; unused metadata-enrichment properties are omitted.
- Integration tests (22): store isolation/cleanup, collection listing for owner/shared/
  unrelated/admin, stats, partial membership, document stats, span metadata, Unicode
  round trip, BM25 search scoped by collection and chunk tag, HTTP login for corpus users
  and document-view endpoints. They pin current behavior; no access checks exist yet (#201).
- `make test-e2e`: Playwright 1.63.0 (Chromium headless shell). The web server builds the
  frontend into `dist/e2e` (new `QUASAR_DIST_DIR` override in `quasar.config.js`) and starts
  `tests/e2e_server.py`: seeded store, temporary SQLite with corpus users, built SPA on the
  same origin, fake embedding/Topicer providers (`tests/fake_providers.py`; other provider
  routes answer 501, no API keys). Smoke tests: login persists across reload, shared user
  opens a shared document, approved annotations render at their offsets, switching
  collection shows no stale chunks/annotations. `aria-label="User menu"` was added to the
  account button so it has an accessible name.
- Fast tests added for the ownership rules and for the fakes speaking the real Topicer
  client protocol.
- CI: new blocking `Integration tests` job with a per-job Weaviate service container;
  production and test-main deploys also need it. The browser suite is not in CI yet (#212).

## Temporary exceptions

- **Process-wide `config` still read directly** by provider/adapter modules:
  `ai_assistance/span_chat.py`, `ai_assistance/topicer_client.py`, `gemma_embedding.py`,
  `search_filters.fetch_db_filter_stats` (default argument), and `rag/rag_runner_demo.py`.
  An app built with `create_app(other_config)` still uses the process-wide settings for
  these calls. `semant_demo.main:app` passes the same object, so production has one source.
  Remove when the embedding provider is injected (#205) and the AI assistance workflow is
  extracted (#207).
- **Weaviate is still connected lazily inside the first request** that needs it (now per
  app, guarded by a lock). Moving connection to bootstrap belongs to #202.

- **Vue type-check baseline** (`semant_demo_frontend/typecheck-baseline.json`, 60 errors).
  Several are real defects: `useTagging.ts` calls `DefaultApi` methods that no longer exist,
  `chunk_collection-store.ts` passes `userId` as fetch options, services import missing
  model exports. Remove entries as the owning features are migrated (#203–#209).
- **Ruff rule set limited** to `E9, F63, F7, F82`. The default rule set reports ~140 legacy
  findings (unused/star imports, comparisons). Python formatting and a Python type checker
  are not enforced yet.
- **`# noqa: F821`** on the undefined `e` in `add_chunk_to_collection`
  (`routes/user_collection_routes.py`); remove with the fix in #201.
- **Vitest 0.23.4** is pinned because it is the last release supporting Vite 2
  (`@quasar/app-vite` 1). Upgrade together with Quasar app-vite 2 / Vite 5.

## Known problems affecting later steps

- `WeaviateAbstraction.create` calls `exit(-1)` when Weaviate is reachable but not ready,
  which terminates the server process from inside a request. Unchanged here; address in #202.
- Required checks are a repository setting, not part of the workflow file. As of
  2026-10-07 the ruleset for `197-refactor---base` requires "Backend tests", "Frontend
  checks", "Generated API client drift" and "Integration tests" (strict, branch up to
  date). `main` has no required status checks yet; add the same four before the refactor
  is merged to `main`.
- PR preview deploys still run with production `OPENAI_API_KEY`/`JWT_SECRET` secrets on
  the self-hosted runner and still deploy after failed checks. Not changed in #200 (a
  deployment decision); tracked in #213.
- `WeaviateAbstraction.create` connects without `skip_init_checks`, so the weaviate client
  requests `https://pypi.org/pypi/weaviate-client/json` on every connection (also from
  integration/e2e test apps; failures are ignored by the client). The test-store client
  skips it. Decide when the connection moves to bootstrap (#202).
- `UserCollection.read_all_documents` calls `fetch_objects` without a limit, so it returns
  at most `QUERY_DEFAULTS_LIMIT` (25) documents per collection. Not covered by the corpus
  yet; add a document set exceeding a page with the pagination cases (#203).
- The corpus has no cross-chunk annotations or a document exceeding a chunk page; add
  them with the tests that need them (#204/#206 and pagination work).
