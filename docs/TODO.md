# TODO — Technical Debt & Recommended Improvements

## Critical / High Priority

### 1. Eliminate duplicated global state across route files
**Files:** `main.py`, `tag_routes.py`, `user_collection_routes.py`, `rag_routes.py`

Each route module independently creates its own `global_engine`, `global_async_session_maker`, `global_searcher`, and `openai_client`. This means multiple Weaviate connections and SQLAlchemy engines exist simultaneously, wasting resources and risking inconsistency.

**Fix:** Create a shared dependency-injection module (e.g. `dependencies.py`) that provides singleton instances via FastAPI's `Depends()`. All route files should import from this single source.

### 2. Remove duplicate imports
Multiple files contain repeated imports (e.g. `tag_routes.py` imports `openai`, `logging`, `schemas`, `config`, `WeaviateSearch`, `asyncio` twice). This causes no runtime error but hurts readability and indicates copy-paste patterns.

**Fix:** Clean up import blocks in all route files.

### 3. Add authentication and user management
User identity is currently just a free-text string passed from the frontend. There is no authentication, session management, or access control.

**Fix:** Implement proper auth (e.g. OAuth2 / JWT) and associate user collections and tags with authenticated users.

### 4. Replace in-process asyncio tasks with a proper task queue
Tagging jobs run as `asyncio.create_task()` inside the FastAPI process. If the server restarts, all running tasks are lost. There is no retry logic and no way to distribute work across multiple workers.

**Fix:** Use Celery + Redis/RabbitMQ (there's already a `celery_tagging.py` stub) or a similar job queue. This also enables horizontal scaling.

### 5. Pin dependency versions
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
`boot/axios.ts` falls back to `http://pcvaskom.fit.vutbr.cz:8024/api` if `BACKEND_URL` is not set. This is a development-machine-specific URL.

**Fix:** Default to `http://localhost:8000/api` or make the fallback a build-time configuration.

### 11. Improve Weaviate search module size
`weaviate_search.py` is ~1500 lines covering search, tag CRUD, collection CRUD, tag propagation, and chunk filtering. 

**Fix:** Split into focused modules: `search.py`, `tag_repository.py`, `collection_repository.py`.

### 12. SQLite not suitable for production
SQLite with `aiosqlite` works for development but has concurrency limitations under real load. Also the DB file (`tasks.db`) is created relative to the working directory.

**Fix:** Support PostgreSQL via env config for production. Make the DB path configurable.

---

## Low Priority / Nice to Have

### 13. Add frontend linting and type checking to CI
`package.json` has ESLint configured but `"test"` script is a no-op. TypeScript strict mode is not enforced.

**Fix:** Add `tsc --noEmit` and `eslint` to CI pipeline.

### 14. Add request/response logging middleware
No structured request logging exists. Debugging production issues requires manual log reading.

**Fix:** Add FastAPI middleware that logs request method, path, status code, and latency.

### 15. Configuration validation on startup
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
No `/health` or `/ready` endpoint exists. Container orchestrators (Kubernetes, Docker Compose health checks) cannot verify service status.

**Fix:** Add `GET /health` that checks Weaviate connectivity and embedding service availability.

---

## Code Smells to Address

| Location | Issue |
|---|---|
| `schemas.py` — `ExtractedMeradata` | Typo in class name (should be `ExtractedMetadata`); `min_date` field declared twice |
| `tag_routes.py` | `global_engine` created in both `main.py` startup and `tag_routes.py` dependency |
| `routes.ts` | `/tag/` route references `TaggingPage.vue` which does not exist in the repository |
| `package.json` | Package name is `image-search-frontend`, description says "Semantic image search" — both outdated |
| `ollama_proxy.py` | Typo: `"genereting"` → `"generating"` |
| `config.py` | `GEMMA_URL` is hardcoded to `http://localhost:8001`, not configurable via env var |
| `config.py` | `MODEL_NAME` (default `clip-ViT-L-14`) and `USE_TRANSLATOR` env vars appear unused in the codebase |
| `weaviate_search.py` | Contains `# TODO remove` on `add_or_get_tag` |
| `rag_generator.py` | `RagGenerator` and `AdaptiveRagGenerator` share ~40 identical lines of model init code |
| `prompt_templates.py` | `"Strict"` template: missing comma after `"{content}"` causes `"Do not output..."` lines to be silently concatenated after the content placeholder via Python implicit string concatenation, instead of appearing as instructions before it |
| `db_insert_jsonl.py` | Hardcoded `limit=1000` in inspection scripts — may miss data in larger collections |
