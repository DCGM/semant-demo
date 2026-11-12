"""The public read-only MCP endpoint (#635, docs/MCP.md): Streamable HTTP at ``/mcp``.

Five read-only tools over the **public corpus**, anonymously: passage and document search,
document metadata, a passage in its context and the passages of a page. Each tool is a thin
adapter of a feature service (``features/search/service``, ``features/documents/service`` and
``pages``) called as an anonymous user, on the application's own repositories and embedders; no
other search, permission or storage logic lives here. Nothing here writes, calls an LLM or reads
user collections, tags or annotations: the inputs cannot name them (unknown arguments are
rejected, ``_forbid_extra_arguments``).

The endpoint is part of the FastAPI application (``mount``) and its session manager runs in the
application's lifespan (``serve``); it is stateless (every request stands alone, JSON answers),
so it needs no session store and leaves room for per-request OAuth later. Requests are bounded
(body size, tool timeout, concurrent searches); errors are fixed, safe messages, never exception
text of storage or providers (``_safe_errors``).
"""
import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from time import perf_counter
from typing import Annotated, Any, TypeVar
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.tools import Tool
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field, ValidationError
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from semant_demo.adapters.filesystem.page_assets import PageAssetStore
from semant_demo.adapters.weaviate.criteria import UnavailableFilter
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.config import MAX_QUERY_RESULTS, Config
from semant_demo.core.errors import InvalidRequestError, NotFoundError
from semant_demo.features.documents import pages as page_service
from semant_demo.features.documents import service as document_service
from semant_demo.features.documents.criteria import (
    MAX_TEXT_QUERY_LENGTH, ChunkFilters, ChunkVocabulary, DocumentFilters, SearchCriteria)
from semant_demo.features.documents.schemas import Document, DocumentChunk
from semant_demo.features.search import service as search_service
from semant_demo.features.search.filters import chunk_vocabulary, load_search_filters_config
from semant_demo.features.search.schemas import (
    DocumentSearchRequest, PassageSearchRequest, SearchFiltersResponse, SearchType)
from semant_demo.features.search.service import DocumentLimits, SearchBackends
from semant_demo.mcp.schemas import (
    MAX_PASSAGE_CHARS, Criteria, DocumentHitResult, DocumentMetadata, DocumentRef, DocumentSearchResult,
    PageText, Passage, PassageContext, PassageHit, PassageSearchResult)

logger = logging.getLogger(__name__)

PATH = "/mcp"
MAX_RESULTS = 25
"""Most hits, documents or passages one tool call returns."""
MAX_CONTEXT_SIDE = 10
MAX_PAGE_INDEX = 100_000
MAX_REQUEST_BODY_BYTES = 64 * 1024
LOOPBACK_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*", "127.0.0.1", "localhost", "[::1]"]
LOOPBACK_ORIGINS = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*",
                    "http://127.0.0.1", "http://localhost", "http://[::1]"]

DIGITAL_LIBRARY_CODES = frozenset({
    'mzk', 'nkp', 'knav', 'svkhk', 'ntk', 'svkul', 'kfbz', 'kkp', 'svkkl', 'mlp', 'nlk', 'uzei',
    'cbvk', 'kkkv', 'kvkli', 'vkol', 'svkos', 'svkpk', 'kkvhb', 'mkct', 'cuni', 'cuni_lf1',
    'cuni_fsv', 'vse', 'vsup', 'mjh', 'nm', 'npmk', 'zmp', 'upm', 'zcm', 'hmt', 'nacr', 'nfa',
    'lmda', 'dsmo', 'vugtk', 'd', 'nulk', 'cdk', 'idu', 'cro', 'cvti', 'snk', 'eod',
})
"""The library codes digitalniknihovna.cz serves: the frontend's verified list
(``semant_demo_frontend/src/features/documents/originalSource.ts``, #255; a test keeps them equal)."""
SOURCE_VIEWER = "https://www.digitalniknihovna.cz"

INSTRUCTIONS = """\
semANT searches a corpus of historical documents (mostly Czech, digitized by Czech libraries \
and OCR'd). Tools return retrieval results and source text only; you do the reasoning. Search \
first (search_passages for passages, search_documents for documents), then open a passage in \
context (get_passage_context), a document's metadata (get_document) or a page's passages \
(get_document_page). Cite document_id and chunk_id with the title, year and source_url or \
semant_url. Search hits hold display-normalized text; context and page reads hold the canonical \
stored OCR text, which may contain recognition errors. Only the public corpus is available."""

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


@dataclass(frozen=True)
class Corpus:
    """What the tools read: the running application's repositories and search vectors."""
    documents: DocumentRepository
    backends: SearchBackends
    pages: PageAssetStore


def application_corpus(app: FastAPI) -> Callable[[], Corpus | None]:
    """The corpus of ``app`` while its lifespan runs (None otherwise)."""
    def corpus() -> Corpus | None:
        resources = app.state.resources
        weaviate = resources.weaviate if resources is not None else None
        if weaviate is None:
            return None
        return Corpus(
            documents=weaviate.documents,
            backends=SearchBackends(chunks=weaviate.search, collections=weaviate.user_collections, tags=weaviate.tags,
                                    vectors=resources.search_vectors),
            pages=PageAssetStore(app.state.config.PAGE_ASSETS_DIR or None))
    return corpus


#########
# Links #
#########

def source_url(document: Document, page_id: UUID | None = None) -> str | None:
    """The original digitized document in its digital library (#255), at ``page_id`` when given;
    None for a library the viewer does not serve (no link rather than a guessed one)."""
    library = (document.library or "").strip().lower()
    if library not in DIGITAL_LIBRARY_CODES:
        return None
    url = f"{SOURCE_VIEWER}/{library}/view/uuid:{document.id}"
    return f"{url}?page=uuid:{page_id}" if page_id is not None else url


def semant_url(base: str | None, document_id: UUID, chunk_id: UUID | None = None) -> str | None:
    """semANT's public document view (``/documents/:documentId``, hash routing, #545) at a passage."""
    if not base:
        return None
    url = f"{base}/#/documents/{document_id}"
    return f"{url}?chunk={chunk_id}" if chunk_id is not None else url


def public_base_url(config: Config) -> str | None:
    """Where semANT's frontend is served: ``ALLOWED_ORIGIN``, when it is an http(s) origin."""
    parts = urlsplit(config.ALLOWED_ORIGIN.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


###############
# Projections #
###############

def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def document_ref(document: Document, base: str | None) -> DocumentRef:
    return DocumentRef(
        document_id=document.id, title=document.title, subtitle=document.subtitle, authors=document.author or [],
        year=document.yearIssued, language=document.language, library=document.library,
        source_url=source_url(document), semant_url=semant_url(base, document.id))


def document_metadata(document: Document, base: str | None, chunk_count: int, page_count: int | None,
                      ) -> DocumentMetadata:
    return DocumentMetadata(
        **document_ref(document, base).model_dump(),
        date_issued=document.dateIssued.date().isoformat() if document.dateIssued else None,
        publisher=document.publisher, place_of_publication=document.placeOfPublication or document.placeTerm,
        part_number=_text(document.partNumber), part_name=document.partName, series_name=document.seriesName,
        series_number=document.seriesNumber, edition=document.edition, document_type=document.documentType,
        genre=document.genre, keywords=document.keywords or [], editors=document.editors or [],
        translators=document.translators or [], illustrators=document.illustrators or [],
        description=document.description, chunk_count=chunk_count, page_count=page_count)


def passage(chunk: DocumentChunk, document: Document, base: str | None, text_form: str) -> Passage:
    return Passage(
        chunk_id=chunk.id, document_id=chunk.document, order=chunk.order, from_page=chunk.from_page,
        to_page=chunk.to_page, start_page_id=chunk.start_page_id, language=chunk.language,
        text=chunk.text[:MAX_PASSAGE_CHARS], text_form=text_form, text_truncated=len(chunk.text) > MAX_PASSAGE_CHARS,
        source_url=source_url(document, chunk.start_page_id), semant_url=semant_url(base, chunk.document, chunk.id))


##########
# Errors #
##########

class _Timeout(Exception):
    pass


def _validation_message(error: ValidationError) -> str:
    return "; ".join(
        (".".join(str(part) for part in e["loc"]) + ": " if e["loc"] else "") + e["msg"] for e in error.errors())


def _tool_error(exc: BaseException, timeout: float) -> tuple[str, ToolError]:
    """The outcome label and the safe client error of a failed call. Messages of the application's
    own validation and lookup errors are written for clients (as in the REST API); anything else
    is reported by kind only."""
    if isinstance(exc, ValidationError):
        return "invalid_input", ToolError(f"invalid_input: {_validation_message(exc)}")
    if isinstance(exc, InvalidRequestError):
        return "invalid_input", ToolError(f"invalid_input: {exc}")
    if isinstance(exc, UnavailableFilter):
        return "invalid_input", ToolError(f"unavailable_filter: {exc}")
    if isinstance(exc, NotFoundError):
        return "not_found", ToolError(f"not_found: {exc}")
    if isinstance(exc, _Timeout):
        return "timeout", ToolError(
            f"timeout: The call did not finish within {timeout:g} seconds; the server may be busy. "
            "Try again later or narrow the query.")
    return "unavailable", ToolError("unavailable: The corpus service is temporarily unavailable. Try again later.")


T = TypeVar("T")


class _Calls:
    """Runs one tool call: the corpus, bounds, safe errors and a content-free log record."""

    def __init__(self, config: Config, corpus: Callable[[], Corpus | None]):
        self.corpus = corpus
        self.timeout = config.MCP_TOOL_TIMEOUT_SECONDS
        self.searches = asyncio.Semaphore(config.MCP_MAX_CONCURRENT_SEARCHES)

    async def run(self, tool: str, work: Callable[[Corpus], Awaitable[T]], *, limit: int | None = None,
                  search: bool = False) -> T:
        started = perf_counter()
        outcome, count = "success", None
        try:
            corpus = self.corpus()
            if corpus is None:
                raise RuntimeError("application not started")
            try:
                async with asyncio.timeout(self.timeout):
                    if search:
                        # Waiting for a free search slot counts towards the timeout.
                        async with self.searches:
                            result = await work(corpus)
                    else:
                        result = await work(corpus)
            except TimeoutError:
                raise _Timeout() from None
            count = _result_count(result)
            return result
        except Exception as exc:
            outcome, error = _tool_error(exc, self.timeout)
            if outcome == "unavailable":
                logger.error("MCP tool call failed: %s", type(exc).__qualname__, extra={"mcp.tool": tool})
            raise error from None
        finally:
            extra = {"mcp.tool": tool, "mcp.outcome": outcome,
                     "mcp.duration_ms": round((perf_counter() - started) * 1000, 2)}
            if limit is not None:
                extra["mcp.limit"] = limit
            if count is not None:
                extra["mcp.results.count"] = count
            logger.info("MCP tool call completed", extra=extra)


def _result_count(result: Any) -> int:
    for name in ("hits", "passages"):
        if hasattr(result, name):
            return len(getattr(result, name))
    return 1


#########
# Tools #
#########

Query = Annotated[str, Field(min_length=1, max_length=MAX_TEXT_QUERY_LENGTH,
                             description="Free-text query (keywords or a natural-language description).")]
DocumentFiltersArg = Annotated[DocumentFilters | None, Field(
    description="Bibliographic filters on the document: publication years (inclusive), title words, source "
                "library codes, document languages. Different filters AND, values of one filter OR.")]
ChunkFiltersArg = Annotated[ChunkFilters | None, Field(
    description="Filters on passages: passage languages and configured classifications (classification -> "
                "accepted values).")]
Mode = Annotated[SearchType, Field(
    description="hybrid (default): keywords and meaning; text: keywords (BM25) only; vector: meaning only.")]
VectorArg = Annotated[str | None, Field(max_length=100, description="Configured search vector id; default if omitted.")]
Alpha = Annotated[float, Field(ge=0, le=1, description="Hybrid weighting: 0 keywords only, 1 meaning only.")]
Limit = Annotated[int, Field(ge=1, le=MAX_RESULTS, description=f"Results to return (at most {MAX_RESULTS}).")]
DocumentId = Annotated[UUID, Field(description="document_id from a search result.")]


def build_server(config: Config, corpus: Callable[[], Corpus | None]) -> FastMCP:
    """The MCP server with exactly the five public read-only tools; ``corpus`` gives the
    application's repositories for each call (None while the application is not started)."""
    calls = _Calls(config, corpus)
    base = public_base_url(config)
    filter_definitions: SearchFiltersResponse = load_search_filters_config(config.SEARCH_FILTERS_CONFIG)
    vocabulary: ChunkVocabulary = chunk_vocabulary(filter_definitions)
    document_limits = DocumentLimits(browse=MAX_QUERY_RESULTS, metadata=config.SEARCH_DOCUMENTS_METADATA_LIMIT,
                                     chunks=config.SEARCH_DOCUMENTS_CHUNK_LIMIT)

    async def search_passages(query: Query, document_filters: DocumentFiltersArg = None,
                              chunk_filters: ChunkFiltersArg = None, mode: Mode = SearchType.hybrid,
                              vector: VectorArg = None, alpha: Alpha = 0.5, limit: Limit = 10,
                              ) -> PassageSearchResult:
        """Find the passages of public corpus documents that best match a text query, in rank order.

        Chunk filters must hold on the returned passage itself; document filters on its document.
        Each hit has the passage (display-normalized text), its document and citation links. No
        relevance scores: hits are ranked. ``bounded`` tells whether more passages match than were
        ranked; ``total_count`` is known only when not bounded."""
        async def work(c: Corpus) -> PassageSearchResult:
            request = PassageSearchRequest(
                criteria=SearchCriteria(text_query=query, document_filters=document_filters or DocumentFilters(),
                                        chunk_filters=chunk_filters or ChunkFilters()),
                limit=limit, type=mode, hybrid_search_alpha=alpha, vector=vector)
            response = await search_service.search_passages(c.backends, None, request, filter_definitions,
                                                            config.SEARCH_PASSAGES_LIMIT)
            return PassageSearchResult(
                query=response.criteria.text_query or "", mode=mode, vector=response.vector,
                criteria=Criteria(document_filters=response.criteria.document_filters,
                                  chunk_filters=response.criteria.chunk_filters),
                hits=[PassageHit(rank=i + 1, passage=passage(item, item.document_object, base, "display"),
                                 document=document_ref(item.document_object, base))
                      for i, item in enumerate(response.items)],
                ranked_count=len(response.ranked_ids), retrieval_limit=response.retrieval_limit,
                bounded=response.bounded, total_count=response.total_count)
        return await calls.run("search_passages", work, limit=limit, search=True)

    async def search_documents(query: Annotated[str | None, Field(
                                   max_length=MAX_TEXT_QUERY_LENGTH,
                                   description="Free-text query; omit (or leave blank) to browse the documents the "
                                               "filters admit, by publication year.")] = None,
                               document_filters: DocumentFiltersArg = None, chunk_filters: Annotated[
                                   ChunkFilters | None, Field(
                                       description="Passage filters, per filter: some passage of the document has "
                                                   "one of the values (different filters may be met by different "
                                                   "passages).")] = None,
                               mode: Mode = SearchType.hybrid, vector: VectorArg = None, alpha: Alpha = 0.5,
                               limit: Limit = 10, offset: Annotated[int, Field(
                                   ge=0, le=MAX_QUERY_RESULTS,
                                   description="Filter-only browsing: documents to skip (next_offset of the "
                                               "previous page). Must be 0 with a query.")] = 0,
                               ) -> DocumentSearchResult:
        """Find public corpus documents: ranked for a text query, or every document the filters admit
        (browsing, oldest first) without one.

        With a query, documents whose bibliographic metadata holds every query word come first, then
        the others by their best-matching passage (included as evidence, display text); only the first
        page of that ranking is available (offset must be 0). Without a query, page with offset.
        ``eligible_count`` counts the documents the filters admit; it is not the number of query
        matches. ``bounded`` tells whether a retrieval limit cut the result."""
        async def work(c: Corpus) -> DocumentSearchResult:
            criteria = SearchCriteria(text_query=query, document_filters=document_filters or DocumentFilters(),
                                      chunk_filters=chunk_filters or ChunkFilters())
            if criteria.text_query is not None and offset:
                raise InvalidRequestError(
                    "offset must be 0 with a query: a text query's ranking is returned from its start only.")
            if criteria.text_query is None:
                c.backends.vectors.resolve(vector)  # an unknown vector is refused, not ignored
            request = DocumentSearchRequest(criteria=criteria, limit=limit, offset=offset, type=mode,
                                            hybrid_search_alpha=alpha, vector=vector)
            response = await search_service.search_documents(c.documents, c.backends, None, request, vocabulary,
                                                             document_limits)
            return DocumentSearchResult(
                query=response.criteria.text_query, order=response.order,
                mode=response.retrieval.type if response.retrieval else None,
                vector=response.retrieval.vector if response.retrieval else None,
                criteria=Criteria(document_filters=response.criteria.document_filters,
                                  chunk_filters=response.criteria.chunk_filters),
                hits=[DocumentHitResult(
                    rank=response.offset + i + 1, document=document_ref(hit.document, base), match=hit.match,
                    best_passage=passage(hit.chunk, hit.document, base, "display") if hit.chunk else None)
                    for i, hit in enumerate(response.items)],
                offset=response.offset, next_offset=response.next_offset, eligible_count=response.eligible_count,
                total_count=response.total_count,
                ranked_count=len(response.ranked) if response.ranked is not None else None,
                bounded=response.bounded)
        return await calls.run("search_documents", work, limit=limit, search=True)

    async def get_document(document_id: DocumentId) -> DocumentMetadata:
        """Bibliographic metadata of a public corpus document, with its source identifiers and links,
        its number of passages and of pages (null without page scans). Unavailable fields are null."""
        async def work(c: Corpus) -> DocumentMetadata:
            document = await document_service.read_document(c.documents, document_id)
            chunk_count, pages = await asyncio.gather(
                document_service.count_chunks(c.documents, document_id),
                page_service.read_pages(c.documents, c.pages, document_id))
            return document_metadata(document, base, chunk_count, len(pages.pages) if pages.available else None)
        return await calls.run("get_document", work)

    async def get_passage_context(document_id: DocumentId,
                                  chunk_id: Annotated[UUID, Field(description="chunk_id of a passage of the document.")],
                                  before: Annotated[int, Field(ge=0, le=MAX_CONTEXT_SIDE,
                                                               description="Passages to read before it.")] = 2,
                                  after: Annotated[int, Field(ge=0, le=MAX_CONTEXT_SIDE,
                                                              description="Passages to read after it.")] = 2,
                                  ) -> PassageContext:
        """A passage with up to ``before``/``after`` neighbouring passages, in document order, as
        canonical stored text, with the document's metadata. ``has_before``/``has_after`` tell whether
        the document continues; call again from the first or last passage to read further."""
        async def work(c: Corpus) -> PassageContext:
            window = await document_service.read_chunk_window(c.documents, document_id, chunk_id, before, after)
            return PassageContext(
                document=document_ref(window.document, base), anchor_chunk_id=window.anchor_chunk_id,
                passages=[passage(chunk, window.document, base, "canonical") for chunk in window.chunks],
                has_before=window.has_before, has_after=window.has_after, total_chunks=window.total_chunks)
        return await calls.run("get_passage_context", work, limit=before + after + 1)

    async def get_document_page(document_id: DocumentId,
                                page: Annotated[int, Field(ge=0, le=MAX_PAGE_INDEX, description=(
                                    "Zero-based page index in the document's page list (from_page/to_page of "
                                    "passages), not the printed page label."))],
                                limit: Annotated[int, Field(ge=1, le=MAX_RESULTS, description=(
                                    f"Passages to return (at most {MAX_RESULTS}).")) ] = 20,
                                ) -> PageText:
        """The passages whose stored page range covers one page, in document order (canonical stored
        text), and whether more do (``has_more``). Not a verified page transcription: page ranges are
        coarse, so passages may begin before or continue after the page."""
        async def work(c: Corpus) -> PageText:
            document = await document_service.read_document(c.documents, document_id)
            pages = await page_service.read_pages(c.documents, c.pages, document_id)
            entry = None
            if pages.available:
                if page >= len(pages.pages):
                    raise InvalidRequestError(
                        f"page must be below {len(pages.pages)}: the document has {len(pages.pages)} pages.")
                entry = next((p for p in pages.pages if p.order == page), None)
            chunks = await page_service.read_page_chunks(c.documents, document_id, page, limit)
            return PageText(
                document=document_ref(document, base), page=page, page_label=entry.label if entry else None,
                page_scans_available=pages.available,
                source_url=source_url(document, entry.page_id) if entry else None,
                passages=[passage(chunk, document, base, "canonical") for chunk in chunks.chunks],
                has_more=chunks.has_more)
        return await calls.run("get_document_page", work, limit=limit)

    tools = [_forbid_extra_arguments(Tool.from_function(fn, title=title, annotations=READ_ONLY))
             for fn, title in ((search_passages, "Search passages"), (search_documents, "Search documents"),
                               (get_document, "Get document"), (get_passage_context, "Get passage context"),
                               (get_document_page, "Get document page"))]
    return FastMCP(
        name="semANT", instructions=INSTRUCTIONS, tools=tools, log_level=config.LOG_LEVEL,
        streamable_http_path=PATH, stateless_http=True, json_response=True,
        max_request_body_size=MAX_REQUEST_BODY_BYTES,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True, allowed_hosts=allowed_hosts(config),
            allowed_origins=allowed_origins(config)))


def _forbid_extra_arguments(tool: Tool) -> Tool:
    """Reject arguments a tool does not declare (e.g. a ``user_collection_id``) rather than ignore them."""
    tool.parameters["additionalProperties"] = False
    model = tool.fn_metadata.arg_model
    tool.fn_metadata.arg_model = type(model.__name__, (model,), {"model_config": {**model.model_config,
                                                                                  "extra": "forbid"}})
    return tool


def allowed_origins(config: Config) -> list[str]:
    """Origin values the endpoint accepts: loopback, ``ALLOWED_ORIGIN`` and ``MCP_ALLOWED_ORIGINS``.
    Requests without an Origin (non-browser clients) are accepted."""
    base = public_base_url(config)
    return [*LOOPBACK_ORIGINS, *([base] if base else []), *config.MCP_ALLOWED_ORIGINS]


def allowed_hosts(config: Config) -> list[str]:
    """Host values the endpoint accepts (DNS rebinding protection): loopback, the host of
    ``ALLOWED_ORIGIN`` (the public host behind the reverse proxy) and ``MCP_ALLOWED_HOSTS``."""
    base = public_base_url(config)
    return [*LOOPBACK_HOSTS, *([urlsplit(base).netloc] if base else []), *config.MCP_ALLOWED_HOSTS]


#######################
# HTTP and lifecycle  #
#######################

class _Endpoint:
    """``/mcp`` of the application: the session manager of its running lifespan, else 503."""

    def __init__(self, app: FastAPI):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        manager = getattr(self.app.state, "mcp_session_manager", None)
        if manager is None:
            await JSONResponse({"detail": "Application is not started."}, status_code=503)(scope, receive, send)
            return
        await manager.handle_request(scope, receive, send)


def mount(app: FastAPI) -> None:
    """Route ``/mcp`` to the MCP endpoint; call before the catch-all static mount."""
    endpoint = _Endpoint(app)
    app.router.routes.append(Route(PATH, endpoint=endpoint))


@asynccontextmanager
async def serve(app: FastAPI) -> AsyncIterator[None]:
    """Run the MCP session manager for one application lifespan (a new server per lifespan, so the
    same application can be started again)."""
    server = build_server(app.state.config, application_corpus(app))
    server.streamable_http_app()  # creates the session manager
    async with server.session_manager.run():
        app.state.mcp_session_manager = server.session_manager
        try:
            yield
        finally:
            app.state.mcp_session_manager = None
