# Start here: the semANT codebase

This guide is for new contributors. It shows how to explore the code and run tests without access to production data. Detailed setup, architecture and deployment instructions live in the linked guides.

## What runs where

- **Frontend:** Vue/Quasar code in `semant_demo_frontend/src/` displays Search, RAG chat, collections and annotations.
- **Backend:** FastAPI code in `semant_demo_backend/semant_demo/` authenticates requests, checks collection access and runs feature workflows.
- **Databases:** Weaviate stores corpus text, metadata, collections and annotations; SQLite stores user accounts and RAG feedback.
- **External services:** the embedding service, Topicer and configured LLM providers are required only for features that use them. They are replaced by fakes in automated browser tests.

See [ARCHITECTURE.md](ARCHITECTURE.md) for how the pieces connect and [DATABASE.md](DATABASE.md) for stored data.

## Choose your starting point

| I want to… | Read first |
|---|---|
| Understand what the application is for | [Vision](VISION.md) and the root [README](../README.md) |
| Choose or refine an issue | [Issue workflow](ISSUE_WORKFLOW.md): drafts, readiness and consultation |
| Change the UI or backend | [Contributing](../CONTRIBUTING.md), then the relevant feature directory below |
| Run the application with real development data | [Local development](DEVELOPMENT.md) |
| Understand deployment or environment settings | [Deployment guide](DEPLOYMENT.md) and [Compose operations](../deploy/README.md) |
| Inspect or repair data | [Data maintenance](DATA_MAINTENANCE.md) — read the safety rules first |
| Measure Weaviate size and query performance | [DB benchmark tool](DB_BENCHMARK.md) and the production audits [before](WEAVIATE_AUDIT_2026-10.md) and [after](WEAVIATE_AUDIT_2026-10-17.md) the Qwen migration |
| Find known limitations or proposed work | [Open issues](TODO.md) and [architecture decisions](adr/README.md) |

## Start with tests, not a database copy

You need **Python 3.12, Node.js 22, npm and Make**. Docker is needed for integration and browser tests; Java 11+ is needed only when regenerating the API client. From the repository root:

```bash
make setup   # installs Python and frontend dependencies; needs internet access
make check   # lint, type checks, fast tests and API-client check; runs offline
```

Neither command needs a corpus snapshot, a GPU, LLM credentials or running databases. To test real Weaviate behavior or browser interactions against **synthetic test data**, use `make test-integration` or `make test-e2e` (Docker required). The browser suite launches a temporary application with fake AI providers; see [testing the sample app](DEVELOPMENT.md#11-testing-versus-development-data) to inspect it interactively.

`local_data/` is not included in the repository. For manual development against a realistic corpus, obtain an **authorized, consistent development snapshot** of Weaviate and SQLite, then follow [DEVELOPMENT.md](DEVELOPMENT.md). Do not point local tooling at production or the shared server test database.

## Follow one feature: Search

1. The page is [`SearchPage.vue`](../semant_demo_frontend/src/features/search/SearchPage.vue). Navigation lives in [frontend routes](../semant_demo_frontend/src/router/routes.ts).
2. Requests use [`src/shared/api/`](../semant_demo_frontend/src/shared/api/index.ts) and the generated TypeScript API client. **Do not hand-edit** `src/generated/api/`.
3. [`main.py`](../semant_demo_backend/semant_demo/main.py) creates the FastAPI application. [`routes/__init__.py`](../semant_demo_backend/semant_demo/routes/__init__.py) registers [Search routes](../semant_demo_backend/semant_demo/features/search/routes.py).
4. [Search service](../semant_demo_backend/semant_demo/features/search/service.py) checks access and coordinates retrieval; the [Weaviate search adapter](../semant_demo_backend/semant_demo/adapters/weaviate/search.py) executes database queries.
5. Start testing with [`test_search_service.py`](../semant_demo_backend/tests/test_search_service.py). Integration tests live under [`tests/integration/`](../semant_demo_backend/tests/integration/); browser tests under [`test/e2e/`](../semant_demo_frontend/test/e2e/).

Other features follow the same pattern: backend `features/<feature>/`, frontend `src/features/<feature>/`, external clients in backend `adapters/`. Authentication lives in backend `users/`; dependency providers are in `routes/dependencies.py`.

## Before opening a PR

Start from current `main`, make one focused change, add a regression test for changed behavior and run the relevant checks. See [CONTRIBUTING.md](../CONTRIBUTING.md#6-branching-review-and-merge). Never run destructive database commands or use production secrets during ordinary development.
