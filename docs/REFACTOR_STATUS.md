# Refactor status

Last updated: 2026-10-07

## Current state

- Integration branch: `197-refactor---base`
- Current issue: #199 — Establish reliable fast checks and make CI blocking
- Completed refactor issues: #198 (bootstrap and configuration; manually verified
  against local Weaviate)
- Current stage: R0

## Development environment

- Local realistic database snapshot is available under `local_data/`.
- Local Weaviate runs from `local_data/weaviate_semant_test`.
- Local SQLite state is `local_data/tasks.db`.
- Shared server databases are not used for normal refactor development.
- The SQL database is configurable through `SQL_DB_URL` (#198). The
  `semant_demo_backend/tasks.db` symlink still works with the default URL.
- #200 will establish deterministic test-owned integration fixtures.

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

## Known problems affecting later steps

- `WeaviateAbstraction.create` calls `exit(-1)` when Weaviate is reachable but not ready,
  which terminates the server process from inside a request. Unchanged here; address in #202.
- Auth test modules still use module-scoped clients with order-dependent tests
  (register, then login). Independent per-test fixtures belong to #199.
