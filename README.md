# semANT — Demo Application 

**Quezio** (working name: semANT demo) is a web application for semantic exploration of digitised Czech cultural-heritage texts. It combines full-text, vector and hybrid search over a Weaviate database with LLM-powered summarisation, Retrieval-Augmented Generation (RAG), and AI-assisted text tagging.

> **Project ID:** DH23P03OVV060 (NAKI III programme)
> **Consortium:** Brno University of Technology · Moravian Library · Masaryk University

## Key Features

| Feature | Description |
|---|---|
| **Hybrid search** | BM25 + vector (HNSW) with configurable alpha; metadata & tag filters |
| **Summarisation** | Per-result titles, per-result summaries and overall query summary via configurable LLM |
| **RAG chat** | Multi-turn question answering with source citations; pipeline variants: `rag_generator`, `adaptive_rag`, `adaptive_rag_og`, `incremental_rag`, `agentic_rag` (recommended: `incremental_rag`) |
| **Tagging** | Manual & LLM-assisted tag propagation across user collections |
| **Tag spans** | Character-level annotations of tags inside chunks (manual `pos`/`neg` and AI-suggested `auto` spans, the latter carrying `reason` + `confidence`) |
| **AI span suggestions** | Two NDJSON-streaming endpoints (thorough / optimised) backed by the external Topicer service |
| **Span discussion chat** | Streaming assistant chat around a single span using its tag, document metadata and surrounding chunk text |
| **User collections** | Group documents (and their chunks) into named collections per user |
| **App feedback** | In-app feedback form persisted server-side as JSONL |

## Technology Stack

| Layer | Technology |
|---|---|
| Database | Weaviate 1.30 (Docker) + SQLite (async, task tracking) |
| Embeddings | `BAAI/bge-multilingual-gemma2` via dedicated FastAPI service |
| Backend | Python 3.12 · FastAPI · LangChain / LangGraph · Ollama / OpenAI / Google Gemini |
| Frontend | Vue 3 · Quasar 2 · TypeScript · Pinia · Axios |

## Repository Structure

```
semant-demo/
├── docs/                          # project documentation (see below)
├── deploy/                        # Docker Compose stack management
│   ├── docker-compose.app.yaml    # Production app stack (backend + frontend)
│   ├── docker-compose.app-test.yml  # Test app stack (CI preview environments)
│   ├── docker-compose.database.yml  # Weaviate database (production)
│   ├── docker-compose.database-test.yml  # Weaviate database (test)
│   ├── docker-compose.embedder.yml  # GPU embedding service
│   ├── Dockerfile                 # Multi-stage build for backend + frontend
│   ├── Dockerfile.embedder        # Build for the embedding service
│   ├── update.sh                  # Helper script to run docker compose with .env
│   ├── .env.example               # Environment variables template (production)
│   ├── .env.test.example          # Environment variables template (test/CI)
│   └── README.md                  # Deployment instructions
├── embedding_service/             # Gemma embedding microservice (FastAPI, port 8001)
├── semant_demo_backend/           # main API server (FastAPI, port 8000)
│   ├── semant_demo/
│   │   ├── main.py                # create_app, routers, lifespan, error mapping
│   │   ├── bootstrap.py           # per-app resources: SQL engine, Weaviate repositories, providers
│   │   ├── config.py              # Config (read once from the environment or a mapping)
│   │   ├── core/                  # errors.py (NotFoundError, ...), outcomes.py (WriteResult)
│   │   ├── features/              # one package per feature: routes.py, service.py, schemas.py
│   │   │   ├── collections/       # collections, sharing, membership, access.py (rights checks)
│   │   │   ├── documents/         # public corpus reads, collection-scoped document reads
│   │   │   ├── annotations/       # tags, spans, offsets, AI suggestions, span chat
│   │   │   ├── search/            # search service, filters
│   │   │   ├── rag/               # RAG routes, service, registry (factory), pipelines/
│   │   │   ├── summarization/     # search-result summariser (Jinja2 templates), question
│   │   │   └── feedback/          # app feedback route and delivery
│   │   ├── adapters/              # concrete storage and provider clients
│   │   │   ├── weaviate/          # repositories (collections, documents, tags, spans,
│   │   │   │                      # chunk_tags, search), client, paging, writes
│   │   │   ├── sql/               # SQL Base, tables, user lookups, RAG feedback table
│   │   │   ├── embeddings/        # embedding service client
│   │   │   ├── topicer/           # Topicer span-proposal client
│   │   │   └── llm/               # LLM gateway: model tiers, LangChain models, usage
│   │   ├── routes/                # DI (dependencies.py), router registration, user search
│   │   ├── configs/               # YAML configs (LLM model tiers, summariser prompts, search
│   │   │                          # filters, rag/ RAG configurations)
│   │   ├── maintenance/           # chunk tag audit (explicit, reviewed cleanup)
│   │   ├── users/                 # FastAPI Users (auth model, manager, JWT)
│   │   └── utils/                 # Jinja2 template helpers
│   └── tests/                     # fast tests; integration/ (real Weaviate, `make test-integration`)
├── semant_demo_frontend/          # Vue/Quasar SPA
│   └── src/
│       ├── app/                   # app shell: main layout, right sidebar, session
│       │                          # scope, about/not-found pages
│       ├── features/              # feature-owned pages, components, stores,
│       │                          # composables and repository wrappers:
│       │                          # search, rag, user_collections, documents,
│       │                          # annotations, auth, feedback; the document
│       │                          # view is in features/documents/viewer/
│       ├── shared/api/            # API transport: backend URL, auth token, generated
│       │                          # client, NDJSON streams, errors, context guards
│       ├── shared/                # reusable UI pieces (ui/), notifications,
│       │                          # write outcomes, pagination, color picker
│       ├── router/                # routes and the sign-in guard
│       └── generated/             # OpenAPI-generated TS client (do not edit by hand)
└── weaviate_utils/                # DB bootstrap & inspection scripts
    ├── docker-compose.yml         # Weaviate container definition
    ├── build_db/                  # standalone schema + data bootstrap helpers
    ├── db_insert_jsonl.py         # bulk-insert documents + chunks from JSONL
    ├── inspect_*.py               # CLI tools to dump chunks, documents, etc.
    ├── delete_*.py                # CLI tools for cleaning collections
    └── migrate.py                 # schema-migration helpers
```

## Architecture Overview

```mermaid
flowchart LR
    subgraph Browser
        FE[Vue / Quasar SPA]
    end

    subgraph Backend ["Backend (FastAPI :8000)"]
        API["features/*/routes.py"]
        SVC["feature services<br/>(access checks, workflows)"]
        RAG[RAG engines]
        SUM[Summariser]
        AD["adapters/<br/>(weaviate, sql, providers)"]
    end

    EMB[Embedding Service :8001]
    WV[(Weaviate :8080)]
    SQL[(SQLite: users, RAG feedback)]
    LLM[Ollama / OpenAI / Gemini]
    TOP[Topicer]

    FE -- REST / NDJSON --> API
    API --> SVC
    SVC --> AD
    RAG --> SVC
    SVC --> SUM
    AD --> WV
    AD --> SQL
    AD --> EMB
    AD --> TOP
    AD --> LLM
    RAG --> LLM
    SUM --> LLM
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the current module map, access rules and
streaming behavior, and [docs/TARGET_ARCHITECTURE.md](docs/TARGET_ARCHITECTURE.md) for the
intended direction.

### Weaviate access

Weaviate is read and written only through plain repositories in
`semant_demo/adapters/weaviate/` (`UserCollectionRepository`, `DocumentRepository`,
`TagRepository`, `SpanRepository`, `ChunkTagRepository`, `ChunkSearchRepository`), built once per
application by `bootstrap.py` on one client. They take `UUID` ids, return application schemas,
return `None` for a missing object on single reads and raise `core.errors.NotFoundError` where an
operation needs one. Feature services call them after checking access; SDK filters and objects do
not leave `adapters/`.

**Collection names** are centrally managed via the `CollectionNames` model (`adapters/weaviate/names.py`) and
initialized in `config.py` (`Chunks`, `Tag`, `UserCollection`, `Documents`, `Span`, reference
names `userCollection` and `tagToUserCollection`); repositories receive them at construction.

## Quick Start

### Starting the Stack

```bash
cd deploy
./update.sh up -d --build
```
**Note:** Requires `.env` file configured in `deploy/` directory. 

### Stopping the Stack

```bash
cd deploy
./update.sh down
```

For detailed setup instructions, advanced options, and data management, see [deploy/README.md](deploy/README.md).

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| **Build arguments** | | |
| `REPO` | `https://github.com/DCGM/semant-demo.git` | Git repository to clone |
| `BRANCH` | `main` | Branch to build from |
| `BACKEND_URL` | `https://demo.semant.cz` | Public backend URL baked into the frontend bundle at build time |
| `DOMAIN` | `demo.semant.cz` | Domain name for the Traefik Host rule |
| **Weaviate** | | |
| `WEAVIATE_HOST` | `weaviate` | Weaviate hostname (in Docker Compose network) |
| `WEAVIATE_REST_PORT` | `8080` | Weaviate HTTP port |
| `WEAVIATE_GRPC_PORT` | `50051` | Weaviate gRPC port |
| **Embedding service** | | |
| `EMBEDDING_SERVICE_HOST` | `embedding-service` | Embedding service hostname (in Docker Compose network) |
| `EMBEDDING_SERVICE_PORT` | `8001` | Embedding service port |
| `GEMMA_MODEL` | `BAAI/bge-multilingual-gemma2` | HuggingFace embedding model name |
| `GPU_DEVICE` | `0` | GPU index visible to the container (`CUDA_VISIBLE_DEVICES`) |
| **Ollama** | | |
| `OLLAMA_URLS` | `http://localhost:11434` | Default endpoint of Ollama model tiers (only the first URL is used) |
| **OpenAI / OpenRouter** | | |
| `OPENAI_API_KEY` | _(empty)_ | OpenAI API key (works with both OpenAI and OpenRouter endpoints) |
| `OPENAI_API_URL` | `https://openrouter.ai/api/v1` | API endpoint URL ( https://api.openai.com/v1 for OpenAI, https://openrouter.ai/api/v1 for OpenRouter) |
| **Google** | | |
| `GOOGLE_API_KEY` | _(empty)_ | Google Gemini key |
| **Shared LLM** | | |
| `LLM_MODELS_CONFIG` | `configs/llm_models.yaml` | Model tier catalog: the provider and model of each tier (`tiny`/`small`/`medium`/`large`) and the tiers each feature may use. The only place models are chosen. |
| `RAG_CONFIGS_PATH` | `configs/rag/demo_configs` | Directory with RAG YAML configs |
| `SEARCH_SUMMARIZER_CONFIG` | `configs/search_summarizer.yaml` | Summariser config path |
| `LANGCHAIN_API_KEY` | _(empty)_ | LangChain/LangSmith tracing key (optional) |
| **Application** | | |
| `SQL_DB_PATH` | `/mnt/ssd2/semant_demo_app_data` | Directory for the SQLite `tasks.db` database with user accounts and RAG feedback (mounted into the container; the name is historical) |
| `ALLOWED_ORIGIN` | `https://demo.semant.cz` | CORS origin for frontend |
| `PORT` | `8000` | Backend listen port |
| `STATIC_PATH` | `./static` | Path to built frontend assets (production) |
| `JWT_SECRET` | _(placeholder)_ | JWT signing secret — **must be overridden in production** with a long random string |
| `JWT_LIFETIME_SECONDS` | `3600` | JWT token lifetime |
| **AI assistance** | | |
| `TOPICER_URL` | `http://semant.cz:8089` | Base URL of the external Topicer span-proposal service |
| `TOPICER_CONFIG_NAME` | `openai` | Name of the Topicer-side LLM config to use |
| `TOPICER_TIMEOUT` | `600.0` | HTTP timeout (seconds) for Topicer streaming calls |
| `SPAN_CHAT_TEMPERATURE` | `0.4` | Sampling temperature for the span discussion chat |
| `SPAN_CHAT_MAX_TOKENS` | `1024` | Max tokens generated per assistant reply |
| `SPAN_CHAT_CONTEXT_CHARS` | `1500` | Characters of neighbour-chunk text included around the span |
| `SPAN_CHAT_HISTORY_LIMIT` | `20` | Max chat-history messages forwarded to the LLM |

---

> **ℹ️ Models:** every backend LLM call uses a model tier from `LLM_MODELS_CONFIG`. Tiers with the `openai` provider use `OPENAI_API_KEY` and `OPENAI_API_URL` (`https://openrouter.ai/api/v1` for OpenRouter, the default, or the OpenAI endpoint; the catalog's model names must match the endpoint, e.g. `openai/gpt-4.1-mini` on OpenRouter). A tier whose provider has no key refuses calls without sending them.

## API Endpoints

The authoritative contract is the OpenAPI schema (`/docs` on a running backend,
`make api-generate` exports it and regenerates the frontend client). Login and resource
rights are checked per operation as described in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md);
public corpus reads, search without a collection, RAG and summaries work anonymously. The
`/api/ai/*` suggestion and span chat endpoints stream NDJSON.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/users/search` | Search users by username substring. |
| `POST` | `/api/tags` | Creates a tag in the collection, or returns the existing tag with the same fields. |
| `GET` | `/api/tags/{tag_uuid}` | Retrieve tag by its id |
| `DELETE` | `/api/tags/{tag_uuid}` | Deletes the tag with its annotations. |
| `PATCH` | `/api/tags/{tag_uuid}` | Updates a tag. |
| `GET` | `/api/user_collections` | Retrieves all collections for given user |
| `POST` | `/api/user_collections` | Creates user collection in weaviate db, or not if the same user collection already exists |
| `GET` | `/api/user_collections/{collection_id}` | Retrieves collection by its id |
| `PATCH` | `/api/user_collections/{collection_id}` | Updates collection name/description/color. |
| `DELETE` | `/api/user_collections/{collection_id}` | Deletes a collection with its tags and annotations. |
| `PATCH` | `/api/user_collections/{collection_id}/owner` | Reassigns ownership of a collection to a different user. |
| `POST` | `/api/user_collections/{collection_id}/share` | Shares a collection with another user. |
| `DELETE` | `/api/user_collections/{collection_id}/share/{user_id}` | Revokes a collection share. |
| `GET` | `/api/user_collections/{collection_id}/members` | Returns the users a collection is currently shared with. |
| `GET` | `/api/user_collections/{collection_id}/stats` | Collection statistics. |
| `GET` | `/api/user_collections/{collection_id}/tags` | Returns tags which belong to collection given by id |
| `POST` | `/api/user_collections/{collection_id}/chunks/{chunk_id}` | Connects chunk with user collection, and the chunk's document with the collection. |
| `DELETE` | `/api/user_collections/{collection_id}/chunks/{chunk_id}` | Removes a chunk from a user collection. |
| `GET` | `/api/user_collections/{collection_id}/documents` | Returns documents which belong to collection given by id |
| `GET` | `/api/user_collections/{collection_id}/documents/{document_id}` | Retrieves the document with all its chunks and marks whether each chunk belongs to the collection. |
| `POST` | `/api/user_collections/{collection_id}/documents/{document_id}` | Adds document to collection and also links all its chunks to that collection. |
| `DELETE` | `/api/user_collections/{collection_id}/documents/{document_id}` | Removes a document and its chunks from a collection. |
| `GET` | `/api/user_collections/{collection_id}/documents/{document_id}/stats` | Returns per-document statistics within the given collection: chunks in collection / total, annotation count, distinct tag count. |
| `GET` | `/api/user_collections/{collection_id}/documents/{document_id}/chunks` | Returns the document's chunks that belong to the collection, in order. |
| `GET` | `/api/user_collections/{collection_id}/documents/{document_id}/chunks/range` | Returns all chunks of a document (marked with collection membership) with order strictly greater than order_gt and/or strictly less than order_lt. |
| `GET` | `/api/user_collections/{collection_id}/documents/{document_id}/chunks/neighbour` | Returns the chunk immediately before (direction=prev) or after (direction=next) the given boundary_order within the document. |
| `GET` | `/api/rag/configurations` | Get Avalaible Rag Configurations |
| `POST` | `/api/rag` | Rag |
| `POST` | `/api/rag/explain` | Explain Selection |
| `POST` | `/api/rag/feedback` | Save Feedback |
| `POST` | `/api/v1/feedback` | Save App Feedback |
| `POST` | `/api/summarize/{summary_type}` | Summarize |
| `POST` | `/api/question/{question_text}` | Question |
| `GET` | `/api/document/{document_id}` | Retrieves document by its id |
| `GET` | `/api/documents/browse` | Browses the corpus with pagination, filtering and sorting options. |
| `GET` | `/api/documents/{document_id}/chunks/count` | Returns the total number of chunks in the given document (public corpus data). |
| `POST` | `/api/tag_spans` | Adds new TagSpan and the matching chunk tag reference. |
| `GET` | `/api/tag_spans` | Get stored TagSpans of a collection, optionally for one chunk. |
| `POST` | `/api/tag_spans/batch` | Get stored TagSpans of a collection for multiple chunk IDs in a single request. |
| `PATCH` | `/api/tag_spans/{span_id}` | Update TagSpan's information (start, end, tagId, ...), then re-derive the chunk tag references of its (chunk, tag) pair (and the new pair on a tag change), so saving again retries a failed chunk tag update. |
| `DELETE` | `/api/tag_spans/{span_id}` | Delete a TagSpan and the chunk tag reference no other span backs. |
| `POST` | `/api/tag_spans/bulk_update` | Apply the same :class:`PatchSpan` to many spans in one round-trip. |
| `POST` | `/api/tag_spans/in_document/delete` | Bulk-delete approved (``type == 'pos'``) spans for the given tag ids within a single (collection, document) scope. |
| `POST` | `/api/ai/suggest_spans/thorough` | Thorough AI span suggestion: every collection chunk in the document is sent to the LLM together with all selected tags. |
| `POST` | `/api/ai/suggest_spans/optimized` | Optimized AI span suggestion: per tag, the Topicer service uses vector similarity to pre-filter only the most relevant chunks before invoking the LLM. |
| `POST` | `/api/ai/suggest_spans/selection` | Run AI span suggestion on a single user-selected passage that may span multiple chunks of the collection. |
| `POST` | `/api/ai/auto_spans/delete` | Bulk-delete unresolved AI proposals (``type == 'auto'``) within a single (collection, document) for the given tag UUIDs. |
| `POST` | `/api/ai/discuss_span` | Stream an assistant reply discussing whether the given span fits its tag. |
| `GET` | `/api/search/filters` | Get Available Search Filters |
| `POST` | `/api/search` | Search |
| `POST` | `/api/auth/jwt/login` | Auth:Jwt.Login |
| `POST` | `/api/auth/jwt/logout` | Auth:Jwt.Logout |
| `POST` | `/api/auth/register` | Register:Register |
| `GET` | `/api/users/me` | Users:Current User |
| `PATCH` | `/api/users/me` | Users:Patch Current User |
| `GET` | `/api/users/{id}` | Users:User |
| `PATCH` | `/api/users/{id}` | Users:Patch User |
| `DELETE` | `/api/users/{id}` | Users:Delete User |
| `GET` | `/health` | Health |

## Testing

See [CONTRIBUTING.md](CONTRIBUTING.md#2-setup-and-commands). From the repository root:

```bash
make check             # offline: Ruff, fast pytest suite, ESLint, vue-tsc, Vitest, API client drift
make test-integration  # real-Weaviate tests in a throwaway container (Docker)
make test-e2e          # Playwright smoke suite with fake AI providers (Docker)
```

## Observability

The backend exports logs, traces, and metrics through OpenTelemetry when `OTEL_ENABLED=true`. Telemetry is initialized once in [`semant_demo_backend/semant_demo/opentelemetry.py`](semant_demo_backend/semant_demo/opentelemetry.py); `create_app()` in [`semant_demo_backend/semant_demo/main.py`](semant_demo_backend/semant_demo/main.py) installs it together with the request-logging and feature-metrics middleware.

Deployments are identified by `service.name=semant-demo-app` and one `DEPLOYMENT_ENVIRONMENT` value:

| Deployment | Environment value |
|---|---|
| Production | `production` |
| Persistent `main` test deployment | `test-main` |
| Pull-request preview | `test-pr-<number>` |

Telemetry is enabled for production, `test-main`, and pull-request preview deployments.

Grafana dashboards should filter by both `service_name="semant-demo-app"` and the selected `deployment_environment_name`; this prevents similarly named metrics from other projects in a shared metrics backend from being shown accidentally.

See [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md) for the complete signal inventory, environment rules, dashboard queries, Collector troubleshooting, and recipes for adding a metric, trace, or log safely.

## Further Documentation

| Document | Description |
|---|---|
| [docs/VISION.md](docs/VISION.md) | Project vision, goals and user personas |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Detailed architecture, RAG pipelines, data flow |
| [docs/DATABASE.md](docs/DATABASE.md) | Weaviate schema and the SQL tables (users, RAG feedback) |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production deployment and configuration guide |
| [docs/RIGHT_SIDEBAR.md](docs/RIGHT_SIDEBAR.md) | Frontend right sidebar and how to add page specific tools to it |
| [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md) | Telemetry architecture, dashboards, and guide for adding logs, traces, and metrics |
| [docs/TODO.md](docs/TODO.md) | Recommended improvements and known technical debt |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Local development databases and test store rules |
| [docs/TARGET_ARCHITECTURE.md](docs/TARGET_ARCHITECTURE.md), [docs/adr/](docs/adr/README.md) | Ongoing architecture principles and adopted decisions |
| [docs/archive/refactor-2026/](docs/archive/refactor-2026/README.md) | Historical architecture planning and delivery records |
| [CONTRIBUTING.md](CONTRIBUTING.md), [AGENTS.md](AGENTS.md) | `main`-based PR workflow, checks and agent instructions |

## Contribution Guidelines

`main` is the canonical development branch. Fetch the latest `origin/main`, create
a short-lived issue/topic branch **from `main`**, implement the focused change
with tests and documentation, and open a pull request **into `main`**.
Resolve newer `main` changes on your topic branch and wait for required
checks and review. Do not push directly to protected `main`.

See [CONTRIBUTING.md](CONTRIBUTING.md#6-branching-review-and-merge) for exact commands,
review requirements, and test selection; [AGENTS.md](AGENTS.md) adds rules for agents.
