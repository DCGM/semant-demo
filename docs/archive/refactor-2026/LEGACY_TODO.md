# TODO — Technical Debt & Recommended Improvements

> **Archived snapshot (2026-10-08).** The older backlog, including resolved and obsolete proposals; its unchecked items are not current commitments. Historical issue states and claims about branch protection are preserved as written; consult [active TODOs](../../TODO.md) and [contribution guidance](../../../CONTRIBUTING.md) for current instructions.

Status (2026-10-08, after the architecture refactor #198–#210): this list predates the
refactor. Items the refactor resolved are marked **Resolved**; the remaining ones are still
open. Current known problems are tracked in [REFACTOR_STATUS.md](REFACTOR_STATUS.md) and
GitHub issues.

## Critical / High Priority

### 2. Remove duplicate imports
**Resolved:** the old route modules are gone; Ruff enforces unused imports (F401) since #210.

Multiple files contain repeated imports (e.g. `tag_routes.py` imports `openai`, `logging`, `schemas`, `config`, `WeaviateSearch`, `asyncio` twice). This causes no runtime error but hurts readability and indicates copy-paste patterns.

**Fix:** Clean up import blocks in all route files.

### 3. Add authentication and user management
**Resolved:** FastAPI Users with JWT; collection access rules per ADR 0007 (#201, #203).

User identity is currently just a free-text string passed from the frontend. There is no authentication, session management, or access control.

**Fix:** Implement proper auth (e.g. OAuth2 / JWT) and associate user collections and tags with authenticated users.

### 4. Replace in-process asyncio tasks with a proper task queue
**Historical:** the background tagging jobs were removed. AI suggestions are request-scoped by decision (ADR 0003); no job queue is planned.

Tagging jobs run as `asyncio.create_task()` inside the FastAPI process. If the server restarts, all running tasks are lost. There is no retry logic and no way to distribute work across multiple workers.

**Fix:** Use Celery + Redis/RabbitMQ (there's already a `celery_tagging.py` stub) or a similar job queue. This also enables horizontal scaling.

### 5. Pin dependency versions
**Partly resolved:** the backend development set is pinned in `requirements-dev.lock` (#199); the runtime `requirements.txt` and the embedding service are not pinned.

`requirements.txt` for both backend and embedding service list packages without version pins. This makes builds non-reproducible and risks breakage on updates.

**Fix:** Add version pins or use a lockfile (`pip-compile`, `poetry.lock`).

---

## Medium Priority

### 6. Centralise LLM model creation
Both `RagGenerator` and `AdaptiveRagGenerator` contain identical `_create_model()` methods that switch on model_type (OLLAMA/OPENAI/GOOGLE).

**Fix:** Move to `BaseRag` or a factory function in `rag_factory.py`.

### 7. Standardise error handling in routes
Some endpoints return `{"created": false, "message": ...}` on errors instead of raising HTTP exceptions. Others raise `HTTPException`. The inconsistency makes it harder for the frontend to handle errors uniformly.

**Fix:** Use a consistent error strategy — either always raise HTTPException with appropriate status codes, or define a standard error response schema.

### 8. Add integration tests
**Resolved:** `make test-integration` (real Weaviate, #200) and `make test-e2e` (Playwright).

Current tests cover only the LLM API, template rendering and summarisation (with mocks). There are no integration tests for:
- Search pipeline (Weaviate queries)
- RAG end-to-end
- Tag CRUD and tagging task lifecycle
- User collection operations

**Fix:** Add integration tests using a test Weaviate instance (Docker) and test fixtures.

### 9. Add OpenAPI schema documentation
FastAPI auto-generates OpenAPI docs, but response models are not consistently declared (some endpoints have no `response_model`). Several route handlers have ambiguous return types.

**Fix:** Add `response_model` to all endpoints. Add `tags` grouping to routers for cleaner Swagger UI.

### 10. Frontend hardcoded backend URL
**Resolved:** one `BACKEND_URL` in `src/shared/api/config.ts`, no fallback host (#209).

`boot/axios.ts` falls back to `http://pcvaskom.fit.vutbr.cz:8024/api` if `BACKEND_URL` is not set. This is a development-machine-specific URL.

**Fix:** Default to `http://localhost:8000/api` or make the fallback a build-time configuration.

### 11. Improve Weaviate search module size
**Resolved:** one repository per concern in `adapters/weaviate/` (#202–#206).

`weaviate_search.py` is ~1500 lines covering search, tag CRUD, collection CRUD, tag propagation, and chunk filtering.

**Fix:** Split into focused modules: `search.py`, `tag_repository.py`, `collection_repository.py`.

### 12. SQLite not suitable for production
**Partly resolved:** the database is configurable through `SQL_DB_URL` (#198); PostgreSQL is not tested.

SQLite with `aiosqlite` works for development but has concurrency limitations under real load. Also the DB file (`tasks.db`) is created relative to the working directory.

**Fix:** Support PostgreSQL via env config for production. Make the DB path configurable.

---

## Low Priority / Nice to Have

### 13. Add frontend linting and type checking to CI
**Resolved:** ESLint, vue-tsc (empty baseline since #210) and Vitest run in CI (#199).

`package.json` has ESLint configured but `"test"` script is a no-op. TypeScript strict mode is not enforced.

**Fix:** Add `tsc --noEmit` and `eslint` to CI pipeline.

### 14. Add request/response logging middleware
No structured request logging exists. Debugging production issues requires manual log reading.

**Fix:** Add FastAPI middleware that logs request method, path, status code, and latency.

### 15. Configuration validation on startup
**Partly resolved:** startup fails when Weaviate is not ready (#202); provider keys are still checked at request time.

`Config.__init__` reads env vars but does not validate them. Missing required keys (like API keys for configured RAG) only fail at request time.

**Fix:** Add startup validation — e.g. check that Weaviate is reachable, Ollama is running, required API keys are set for the loaded RAG configs.

### 16. Docker Compose for full stack
Only Weaviate has a Docker Compose file. There is no way to bring up the entire stack (backend + frontend + embedding service + Weaviate) with a single command.

**Fix:** Create a root `docker-compose.yml` with all services, or add Dockerfiles to backend and embedding_service.

### 17. Add pagination to search and collection endpoints
Search uses a `limit` parameter but there is no offset/cursor-based pagination. Large collections cannot be browsed incrementally.

### 18. Prompt template management
RAG prompts are hardcoded in `adaptive_rag_prompts.py` while summarisation prompts are in YAML. Tagging prompts are in `prompt_templates.py`. Three different mechanisms for the same concept.

**Fix:** Unify prompt management — either all YAML/config-driven, or all in a shared prompt registry.

### 19. Frontend `package.json` metadata
Package name is `image-search-frontend` and description says "Semantic image search" — both are outdated from an earlier project.

**Fix:** Update to `semant-demo-frontend` / "semANT demo application".

### 20. Add health-check endpoints
**Partly resolved:** `GET /health` exists (liveness only, no dependency checks).

No `/health` or `/ready` endpoint exists. Container orchestrators (Kubernetes, Docker Compose health checks) cannot verify service status.

**Fix:** Add `GET /health` that checks Weaviate connectivity and embedding service availability.

### XX. Format the project's code consistently
Unreadable unstyled ununiform code.
Define formatter for BE and FE. FE should use Prettier. ESLint will then listen to Prettier rules and only report actual code issues. Add a package.json script for formatting whole frontend.

### XX. Use Pylance
Backend is full of typing errors.

---

## Code Smells to Address

| Location | Issue |
|---|---|
| `schemas.py` — `ExtractedMeradata` | Typo in class name (should be `ExtractedMetadata`) |
| `package.json` | Package name is `image-search-frontend`, description says "Semantic image search" — both outdated |
| `ollama_proxy.py` | Typo: `"genereting"` → `"generating"` |
| `rag_generator.py` | `RagGenerator` and `AdaptiveRagGenerator` share ~40 identical lines of model init code |
| `prompt_templates.py` | `"Strict"` template: missing comma after `"{content}"` causes `"Do not output..."` lines to be silently concatenated after the content placeholder via Python implicit string concatenation, instead of appearing as instructions before it |
| `db_insert_jsonl.py` | Hardcoded `limit=1000` in inspection scripts — may miss data in larger collections |
