# MCP endpoint (public corpus, read-only)

semANT can serve a remote [Model Context Protocol](https://modelcontextprotocol.io) endpoint so a
user's own AI client (Claude, ChatGPT, Gemini or another MCP-capable tool) can search the
historical documents and read their text and bibliographic data. The client's model does any
summarizing or reasoning; semANT returns retrieval results and source text and makes **no LLM
calls** for it. First stage of [#138](https://github.com/DCGM/semant-demo/issues/138),
implemented in [#635](https://github.com/DCGM/semant-demo/issues/635).

Only the **public corpus** is available: the scope that semANT already serves without login
([ADR 0007](adr/0007-access-and-collaboration.md)). It includes no user collections (shared or
not), tags, annotations, AI generation or writes, and needs no account.

## Endpoint and configuration

- **URL:** `https://<host>/mcp` (local: `http://127.0.0.1:8000/mcp`). Streamable HTTP,
  stateless, JSON answers (MCP SDK `mcp` 1.30, protocol 2025-11-25 and the versions it
  negotiates). It is a route of the backend application (`semant_demo/mcp/`) and shares its
  startup and shutdown; it is registered before the static frontend mount, so the frontend
  and `/api` are unaffected. Traefik routes the host to the app; a separate router for `/mcp`
  only adds the rate limit below. The REST API and its OpenAPI schema do not change.
- **Off by default.** `MCP_ENABLED=true` enables it. While disabled, `/mcp` is 404.

| Variable | Default | Description |
|---|---|---|
| `MCP_ENABLED` | `false` | Serve `/mcp` |
| `MCP_ALLOWED_HOSTS` | empty | Host header values accepted besides loopback and the host of `ALLOWED_ORIGIN` (comma-separated; `host:*` for any port). Others get 421 (DNS rebinding protection) |
| `MCP_ALLOWED_ORIGINS` | empty | Origin header values accepted besides loopback (`http://localhost:*`, e.g. MCP Inspector) and `ALLOWED_ORIGIN`. Requests without Origin (server-side clients) are accepted; others get 403 |
| `MCP_TOOL_TIMEOUT_SECONDS` | `30` | Most time one tool call may take, including waiting for a search slot |
| `MCP_MAX_CONCURRENT_SEARCHES` | `4` | Most `search_*` calls running at once (per backend process); others wait |

`ALLOWED_ORIGIN` (the frontend's origin) also gives the semANT links in answers; set it to the
public `https://` origin. A deployment behind the proxy needs only `MCP_ENABLED=true` in its
`.env` when the public host equals `ALLOWED_ORIGIN`'s host, as in `deploy/.env*.example`.

## Tools

All five are read-only (`readOnlyHint`, `idempotentHint`), with typed input and output
schemas; undeclared arguments (e.g. `user_collection_id`, `collection_id`, `tag_uuids`) are
rejected, never ignored. Each calls the same service as the corresponding REST endpoint
(as an anonymous user), so filtering and ranking match the Search and document pages.

| Tool | Arguments | Answer | Service (REST equivalent) |
|---|---|---|---|
| `search_passages` | `query` (required, ≤ 1000 chars), `document_filters`, `chunk_filters`, `mode` (`hybrid` default, `text`, `vector`), `vector`, `alpha` (0–1, 0.5), `limit` (10, ≤ 25) | Ranked passages (display text) with their documents; `ranked_count`, `retrieval_limit`, `bounded`, `total_count`, normalized `criteria` | `search.service.search_passages` (`POST /api/search/passages`) |
| `search_documents` | optional `query`; the same filters and retrieval options; `limit` (10, ≤ 25); `offset` (filter-only browsing; must be 0 with a query) | Documents with `match` and best passage; `order`, `eligible_count`, `total_count`, `ranked_count`, `bounded`, `next_offset` | `search.service.search_documents` (`POST /api/search/documents`) |
| `get_document` | `document_id` | Bibliographic metadata (null when unavailable), `chunk_count`, `page_count` (null without page scans), links | `documents.service.read_document` (`GET /api/document/{id}`) |
| `get_passage_context` | `document_id`, `chunk_id`, `before`/`after` (2, ≤ 10) | The passage and its neighbours in document order (canonical text), `has_before`/`has_after`, `total_chunks`, document | `documents.service.read_chunk_window` (`…/chunks/{id}/window`) |
| `get_document_page` | `document_id`, `page` (zero-based page-list index, not the printed label), `limit` (20, ≤ 25) | Passages whose stored page range covers the page (canonical text), `has_more`, `page_label`, `page_scans_available` | `documents.pages.read_page_chunks` (`…/chunks/by_page`) |

Filters are semANT's search criteria ([ARCHITECTURE.md](ARCHITECTURE.md#search-criteria-featuresdocumentscriteriapy-adaptersweaviatecriteriapy)):
`document_filters` (`year_min`, `year_max`, `title_contains`, `libraries`, `languages`) apply
to the document's bibliographic metadata; `chunk_filters` (`languages`, `classifications`:
classification → values, as configured in `SEARCH_FILTERS_CONFIG`) must hold on the returned
passage itself in `search_passages`, and per filter on some passage of the document in
`search_documents`. Example:

```json
{"query": "požár obce", "document_filters": {"year_min": 1800, "year_max": 1900},
 "chunk_filters": {"languages": ["ces"]}, "mode": "hybrid", "limit": 5}
```

### Counts and limits

- Passage search ranks up to `SEARCH_PASSAGES_LIMIT` (1000) passages once and returns the first
  `limit`; `bounded: true` means more passages match and `total_count` is then null. Vector and
  hybrid search match every passage that passes the filters, so they are normally bounded.
  No relevance score is reported: the ranking has none.
- Document search with a query returns only the start of its ranking (no offset paging of a
  hybrid ranking). `eligible_count` is the number of documents the filters admit, an upper bound,
  not the number of query matches; `total_count` is that number only when no limit cut the
  ranking. Without a query, `offset`/`next_offset` page through the first 10 000 documents.
- A passage's text is cut at 6000 characters (`text_truncated`). Requests are at most 64 KiB.
- `get_document_page` is not a page transcription: stored page ranges are coarse, so passages
  may begin before or continue after the page, and the text is OCR output. A page index past the
  document's page list is refused; a document without page scans has `page_scans_available:
  false` and only the passages' ranges locate the page.

### Text and citations

- **Search hits carry display text** (hyphenated line breaks joined, other line breaks as
  spaces, `text_form: "display"`); **context and page reads carry the canonical stored text**
  (`text_form: "canonical"`), the text semANT's annotation offsets refer to.
- Every passage has stable `document_id` and `chunk_id`, its `order` in the document and its
  zero-based `from_page`/`to_page`; documents have title, authors, year and library.
- `source_url` links to the original digitized document on digitalniknihovna.cz (at the
  passage's first page, or the requested page), built as the frontend does
  (`originalSource.ts`, #255) and only for the library codes that viewer is verified to serve;
  otherwise it is null. `semant_url` is semANT's public document view at the passage
  (`<ALLOWED_ORIGIN>/#/documents/<document_id>?chunk=<chunk_id>`).

### Errors

Failed calls return an MCP tool error (`isError: true`) whose text starts with a kind:
`invalid_input` (arguments, unknown vector or chunk filter value, offset with a query, page past
the page list), `unavailable_filter` (a filter this corpus database cannot answer),
`not_found` (unknown document or a chunk of another document), `timeout` and `unavailable`
(storage or embedding failures). Messages never contain exception text of storage or providers.

## Security and operations

- Anonymous and stateless: no cookies, sessions or service identity are used, so per-user OAuth
  can be added later without changing the tools. Nothing writes; the only external call besides
  Weaviate is the configured query embedding of `hybrid`/`vector` searches.
- Host and Origin are validated by the MCP SDK's transport security (above); HTTPS is terminated
  by the reverse proxy. Timeouts and the search concurrency limit protect the store and the
  embedding service. Traefik limits `/mcp` per client IP to an average of 60 requests per
  minute with bursts of 30 and answers 429 above it; the rest of the host is not limited
  ([DEPLOYMENT.md](DEPLOYMENT.md#production-considerations)).
- Each call logs one `MCP tool call completed` record with `mcp.tool`, `mcp.outcome`,
  `mcp.duration_ms`, `mcp.limit` and `mcp.results.count`, never queries or text
  ([OBSERVABILITY.md](OBSERVABILITY.md#add-a-log-field)); failures log the exception class.

## Smoke tests

Locally, on the seeded development application (fake providers, page scans):

```bash
MCP_ENABLED=true make dev-backend                 # terminal 1
.venv/bin/python scripts/mcp_smoke.py              # terminal 2: all five tools, official MCP client
npx @modelcontextprotocol/inspector                # optional UI: Streamable HTTP, http://127.0.0.1:8000/mcp
```

On a deployed instance with `MCP_ENABLED=true`: `.venv/bin/python scripts/mcp_smoke.py
https://<host>/mcp <query>`, then add `https://<host>/mcp` as a custom (remote) connector in a
client, e.g. Claude's *Settings → Connectors → Add custom connector*, with no authentication,
and ask it to search the corpus.

Verified for #635: the MCP Python SDK client (automated tests and `scripts/mcp_smoke.py`
against the local application over HTTP). MCP Inspector and commercial clients over a public
HTTPS endpoint were not yet tested; do not assume support for a client until it has been.

Automated tests: `tests/test_mcp.py` (fast, mocked services) and `tests/integration/test_mcp.py`
(seeded test Weaviate: parity with the REST search, document order, display vs canonical text,
no side effects).

## Not included (future phases of #138)

OAuth/login and user-scoped reads, user collections, tag vocabularies, annotations and their
writes or review, RAG answers, summaries, question answering, chat or any other LLM use, MCP
resources and prompts, uploads or reindexing.
