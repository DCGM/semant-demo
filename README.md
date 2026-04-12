# semANT — Demo Application

**Quezio** (working name: semANT demo) is a web application for semantic exploration of digitised Czech cultural-heritage texts. It combines full-text, vector and hybrid search over a Weaviate database with LLM-powered summarisation, Retrieval-Augmented Generation (RAG), and AI-assisted text tagging.

> **Project ID:** DH23P03OVV060 (NAKI III programme)
> **Consortium:** Brno University of Technology · Moravian Library · Masaryk University

## Key Features

| Feature | Description |
|---|---|
| **Hybrid search** | BM25 + vector (HNSW) with configurable alpha; metadata & tag filters |
| **Summarisation** | Per-result titles, per-result summaries and overall query summary via configurable LLM |
| **RAG chat** | Multi-turn question answering with source citations; little/pipeline variants: `rag_generator`, `adaptive_rag`, `adaptive_rag_og`, `incremental_rag`, `agentic_rag` (recommended: incremental variant) |
| **Tagging** | Manual & LLM-assisted tag propagation across document collections |
| **User collections** | Group chunks into named collections per user |

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
│   ├── docker-compose.yaml        # Container definitions for the full stack
│   ├── Dockerfile                 # Multi-stage build for backend & embedding service
│   ├── update.sh                  # Helper script to run docker compose with .env
│   ├── .env.example               # Environment variables template
│   └── README.md                  # Deployment instructions
├── embedding_service/             # Gemma embedding microservice (FastAPI, port 8001)
├── semant_demo_backend/           # main API server (FastAPI, port 8000)
│   ├── semant_demo/
│   │   ├── main.py                # FastAPI app, startup, core endpoints
│   │   ├── config.py              # env-based configuration (Config singleton)
│   │   ├── schemas.py             # Pydantic models + SQLAlchemy Task model
│   │   ├── gemma_embedding.py     # HTTP client to embedding_service
│   │   ├── ollama_proxy.py        # round-robin Ollama client
│   │   ├── configs/               # YAML configs (summariser prompts)
│   │   ├── llm_api/               # async LLM abstraction (OpenAI, Ollama)
│   │   ├── rag/                   # RAG implementations + YAML configs
│   │   ├── routes/                # FastAPI routers (rag, tags, collections)
│   │   ├── summarization/         # search-result summariser (Jinja2 templates)
│   │   ├── tagging/               # LLM-based tag propagation logic
│   │   ├── weaviate_utils/        # Weaviate abstraction layer (CRUD operations per collection)
│   │   │   ├── weaviate_abstraction.py  # Main abstraction class organizing all collections
│   │   │   ├── document.py        # Document collection operations
│   │   │   ├── text_chunk.py      # TextChunk collection operations
│   │   │   ├── tag.py             # Tag collection operations
│   │   │   ├── span.py            # Span collection operations
│   │   │   ├── user_collection.py # UserCollection (user-defined grouping) operations
│   │   │   └── helpers.py         # Shared utility functions
│   │   └── utils/                 # Jinja2 template helpers
│   └── tests/                     # unit tests (llm_api, summarization, utils)
├── semant_demo_frontend/          # Vue/Quasar SPA
│   └── src/
│       ├── pages/                 # SearchPage, RagPage, TagManagementPage, …
│       ├── stores/                # Pinia stores (user, collections)
│       ├── models.ts              # TypeScript interfaces mirroring backend schemas
│       └── boot/axios.ts          # Axios instance & base URL config
└── weaviate_utils/                # DB bootstrap & inspection scripts
    ├── docker-compose.yml         # Weaviate container definition
    ├── db_insert_jsonl.py         # bulk-insert documents + chunks from JSONL
    ├── inspect_chunks.py          # CLI to dump chunks
    └── inspect_documents.py       # CLI to dump documents
```

## Architecture Overview

```mermaid
flowchart LR
    subgraph Browser
        FE[Vue / Quasar SPA]
    end

    subgraph Backend ["Backend (FastAPI :8000)"]
        API[main.py endpoints]
        RAG[RAG engines]
        SUM[Summariser]
        TAG[Tagging worker]
        WA["WeaviateAbstraction<br/>(unified data layer)"]
    end

    EMB[Embedding Service :8001]
    WV[(Weaviate :8080)]
    SQL[(SQLite tasks.db)]
    LLM[Ollama / OpenAI / Gemini]

    FE -- REST --> API
    API --> RAG
    API --> SUM
    API --> TAG
    API -- embed query --> EMB
    API --> WA
    WA -- search/CRUD --> WV
    TAG -- status --> SQL
    RAG --> LLM
    SUM --> LLM
    TAG --> LLM
```

### Weaviate Abstraction Layer

The **WeaviateAbstraction** class provides a unified, object-oriented interface to Weaviate collections. Instead of direct client calls scattered across the codebase, all database operations flow through organized collection handlers:

- **Document**: document metadata and retrieval
- **TextChunk**: text passages with embeddings, metadata and search
- **Tag**: tagging definitions, CRUD, and search
- **Span**: tag span markers within chunks
- **UserCollection**: user-defined groupings of chunks (collections per user)
- **helpers**: shared utility functions (tag reference management, filtering, transforms) used across handlers

Each handler encapsulates:
- **Query construction** (filters, references, properties)
- **Error handling** (custom Weaviate exceptions)
- **Schema consistency** (CRUD operations always respect the schema)
- **Async/await patterns** (non-blocking database I/O)

**Collection names** are centrally managed via the `CollectionNames` schema (Pydantic model) and initialized from `config.py`, allowing handlers to reference collections by name without hardcoding. This makes collection names easily configurable across the application:
```python
# In schemas.py: CollectionNames defines the structure
class CollectionNames(BaseModel):
    chunks_collection_name: str
    tag_collection_name: str
    user_collection_name: str
    user_collection_link_name: str

# In config.py: CollectionNames values are initialized
self.collectionNames = CollectionNames(
    chunks_collection_name = "Chunks",
    tag_collection_name = "Tag",
    user_collection_name = "UserCollection",
    user_collection_link_name = "userCollection"
)

# In handlers: Access collection names consistently
collection = self.client.collections.get(self.collectionNames.chunks_collection_name)
```

**Usage example:**
```python
searcher = WeaviateAbstraction(client, collectionNames)  # initialized at startup

# Create a tag
tag_id = await searcher.tag.create(tagData)

# Search chunks
results = await searcher.textChunk.search(query, limit=10, filters=...)

# Manage user collections
collections = await searcher.userCollection.read(userId)
await searcher.userCollection.add_chunks(chunk_id, collection_id)
```

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
| `OLLAMA_URLS` | `http://localhost:11434` | Comma-separated Ollama endpoints |
| `OLLAMA_MODEL` | `gemma3:12b` | Ollama model |
| **OpenAI / OpenRouter** | | |
| `OPENAI_API_KEY` | _(empty)_ | OpenAI API key (works with both OpenAI and OpenRouter endpoints) |
| `OPENAI_API_URL` | `https://openrouter.ai/api/v1` | API endpoint URL ( https://api.openai.com/v1 for OpenAI, https://openrouter.ai/api/v1 for OpenRouter) |
| `OPENAI_MODEL` | `gpt-4o-mini` | Default OpenAI model |
| **Google** | | |
| `GOOGLE_API_KEY` | _(empty)_ | Google Gemini key |
| `GOOGLE_MODEL` | `gemini-2.5-pro` | Default Google model |
| **Shared LLM** | | |
| `RAG_CONFIGS_PATH` | `rag/rag_configs/configs` | Directory with RAG YAML configs |
| `SEARCH_SUMMARIZER_CONFIG` | `configs/search_summarizer.yaml` | Summariser config path |
| `MODEL_TEMPERATURE` | `0.0` | Default LLM temperature |
| `LANGCHAIN_API_KEY` | _(empty)_ | LangChain/LangSmith tracing key (optional) |
| **Application** | | |
| `ALLOWED_ORIGIN` | `https://demo.semant.cz` | CORS origin for frontend |
| `PORT` | `8000` | Backend listen port |
| `STATIC_PATH` | `./static` | Path to built frontend assets (production) |
| `JWT_SECRET` | _(placeholder)_ | JWT signing secret — **must be overridden in production** with a long random string |

---

> **ℹ️ Universal Configuration:** Methods using the OpenAI Python package use `OPENAI_API_KEY` and `OPENAI_API_URL`. Set `OPENAI_API_URL=https://openrouter.ai/api/v1` to use OpenRouter, or the OpenAI endpoint to use OpenAI directly. Seamless integration via `ChatOpenAI` in LangChain.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/auth/register` | Create a new account (email, password, username, name, institution) |
| `POST` | `/api/auth/jwt/login` | Login with email or username — returns `access_token` |
| `POST` | `/api/auth/jwt/logout` | Logout (client discards token) |
| `GET` | `/api/users/me` | Current user info (requires Bearer token) |
| `PATCH` | `/api/users/me` | Update current user (email / password / name / institution) |
| `POST` | `/api/search` | Hybrid/text/vector search with filters |
| `POST` | `/api/summarize/{type}` | Summarise search results (`results`) |
| `POST` | `/api/question/{text}` | Q&A over search results (OpenAI) |
| `GET`  | `/api/rag/configurations` | List available RAG configs |
| `POST` | `/api/rag` | RAG chat request |
| `POST` | `/api/rag/explain` | Explain selected text in RAG context |
| `POST` | `/api/tag` | Create a tag |
| `POST` | `/api/tag/task` | Start async LLM tagging job |
| `GET`  | `/api/tag/configs` | List available tagging configs |
| `GET`  | `/api/tag/tasks/info` | List all tagging tasks |
| `GET`  | `/api/tag/task/status/{id}` | Poll tagging task status |
| `DELETE` | `/api/tag/task/{id}` | Cancel a running tagging task |
| `GET`  | `/api/tags` | List all tags |
| `DELETE` | `/api/tags` | Delete tags entirely |
| `DELETE` | `/api/tags/automatic` | Remove automatic tag assignments |
| `PUT` | `/api/tag/approve` | Approve a tag assignment |
| `PUT` | `/api/tag/disapprove` | Reject a tag assignment |
| `POST` | `/api/tags/filter` | Filter chunks by tag UUIDs |
| `POST` | `/api/tag/textChunks` | Get chunks tagged with specific tags |
| `POST` | `/api/user_collection` | Create user collection |
| `GET`  | `/api/user_collection/all` | List collections for a user |
| `POST` | `/api/user_collection/chunks` | Add chunk to collection |
| `GET`  | `/api/user_collection/chunks` | List chunks in a collection |

## Testing

```bash
cd semant_demo_backend
python -m pytest tests/ -v
```

Tests cover the LLM API abstraction, Jinja2 template rendering and the summarisation pipeline. RAG factory loading is validated via test YAML configs under `rag/rag_configs/tests/`.

## Further Documentation

| Document | Description |
|---|---|
| [docs/VISION.md](docs/VISION.md) | Project vision, goals and user personas |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Detailed architecture, RAG pipelines, data flow |
| [docs/DATABASE.md](docs/DATABASE.md) | Weaviate schema and SQLite task model |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production deployment and configuration guide |
| [docs/TODO.md](docs/TODO.md) | Recommended improvements and known technical debt |

## Contribution Guidelines

1. Create an issue **and** a branch with the same name.
2. Issue should contain: descriptive title, short summary, technical checklist, verification steps.
3. Work on your branch; write notes/questions as issue comments.
4. Write or update unit tests.
5. Update relevant documentation; add/update diagrams where appropriate.
6. Merge `main` into your branch, resolve conflicts.
7. Open a pull request, assign a reviewer.
8. After approval, merge/rebase and delete the branch.
