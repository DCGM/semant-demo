"""The public read-only MCP endpoint (#635) with the feature services replaced by fakes.

Through a real MCP client over the ASGI application: routing and its default, the exact tool
list, argument bounds and the refusal of unsupported scope, the mapping of service answers to the
tools' projections (display vs canonical text, counts, links), safe errors and timeouts, the
transport's Origin/Host checks, and that no LLM provider is contacted. Parity with the services on
a real store: ``tests/integration/test_mcp.py``.
"""
import asyncio
import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from asgi_lifespan import LifespanManager

from semant_demo.config import Config
from semant_demo.core.errors import NotFoundError
from semant_demo.features.documents import pages as page_service
from semant_demo.features.documents import service as document_service
from semant_demo.features.documents.criteria import SearchCriteria
from semant_demo.features.documents.schemas import (
    Document, DocumentChunk, DocumentChunkWindow, DocumentPage, DocumentPages, PageChunks)
from semant_demo.features.search import service as search_service
from semant_demo.features.search.schemas import (
    DocumentHit, DocumentRetrieval, DocumentSearchResponse, PassageSearchResponse, RankedDocument,
    SearchResultChunk, SearchType)
from semant_demo.main import create_app
from semant_demo.mcp import server as mcp_server
from semant_demo.mcp.schemas import MAX_PASSAGE_CHARS
from tests.app_support import make_test_config, offline_weaviate
from tests.mcp_support import BASE_URL, error_text, mcp_session, structured

TOOLS = {"search_passages", "search_documents", "get_document", "get_passage_context", "get_document_page"}
DOC_ID = UUID("5e3a0000-0000-4000-8000-00000000d001")
PAGE_ID = UUID("5e3a0000-0000-4000-8000-0000000d1f01")
INITIALIZE = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}}
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


class NoNetwork(httpx.AsyncBaseTransport):
    """LLM provider transport that records and refuses every request."""

    def __init__(self):
        self.requests: list[str] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        raise httpx.ConnectError("no LLM call expected")


@asynccontextmanager
async def started_app(tmp_path, **overrides):
    llm = NoNetwork()
    app = create_app(make_test_config(tmp_path, **{"MCP_ENABLED": "true", **overrides}),
                     weaviate_connector=offline_weaviate, llm_transport=llm)
    async with LifespanManager(app):
        yield app
    assert llm.requests == []


@pytest.fixture
async def app(tmp_path):
    async with started_app(tmp_path) as app:
        yield app


@pytest.fixture
def call(app):
    """Calls a tool in a session of its own (the server is stateless); an async fixture holding
    the client's task group would be closed in another task."""
    async def call_tool(tool: str, arguments: dict):
        async with mcp_session(app) as session:
            return await session.call_tool(tool, arguments)
    return call_tool


def document(**fields) -> Document:
    return Document(**{"id": DOC_ID, "title": "Kronika obce Lhota", "author": ["Jan Kronikář"], "yearIssued": 1851,
                       "language": "ces", "library": "mzk", **fields})


def chunk(text: str = "Roku 1848 při-\njel hejtman.", order: int = 0, **fields) -> DocumentChunk:
    return DocumentChunk(**{"id": uuid4(), "text": text, "start_page_id": PAGE_ID, "from_page": 1, "to_page": 2,
                            "document": DOC_ID, "order": order, "language": "ces", **fields})


def hit(text: str = "Roku 1848 přijel hejtman.", **fields) -> SearchResultChunk:
    return SearchResultChunk(**chunk(text).model_dump(), document_object=document(**fields))


def record(monkeypatch, module, name, answer):
    """Replace ``module.name`` by a fake returning ``answer`` (or raising it); the recorded calls."""
    calls = []

    async def fake(*args, **kwargs):
        calls.append(args)
        if isinstance(answer, BaseException):
            raise answer
        return answer(*args) if callable(answer) else answer
    monkeypatch.setattr(module, name, fake)
    return calls


###########
# Routing #
###########

def test_disabled_by_default():
    assert Config(environ={}).MCP_ENABLED is False


async def test_no_endpoint_unless_enabled(tmp_path):
    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    async with LifespanManager(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as http:
            response = await http.post("/mcp", json=INITIALIZE, headers=MCP_HEADERS)
            health = await http.get("/health")

    assert response.status_code == 404
    assert health.status_code == 200


async def test_the_endpoint_does_not_change_the_rest_api(tmp_path):
    disabled = create_app(make_test_config(tmp_path))
    enabled = create_app(make_test_config(tmp_path, MCP_ENABLED="true"))

    assert enabled.openapi() == disabled.openapi()


async def test_served_before_the_static_frontend(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html>frontend</html>")
    async with started_app(tmp_path, STATIC_PATH=str(static)) as app:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as http:
            frontend = await http.get("/")
            mcp = await http.post("/mcp", json=INITIALIZE, headers=MCP_HEADERS)

    assert "frontend" in frontend.text
    assert mcp.status_code == 200, mcp.text
    assert mcp.json()["result"]["serverInfo"]["name"] == "semANT"


async def test_the_application_can_be_started_again(tmp_path):
    app = create_app(make_test_config(tmp_path, MCP_ENABLED="true"), weaviate_connector=offline_weaviate)
    for _ in range(2):
        async with LifespanManager(app):
            async with mcp_session(app) as session:
                assert {t.name for t in (await session.list_tools()).tools} == TOOLS
    assert app.state.mcp_session_manager is None


#########
# Tools #
#########

async def test_exactly_the_five_read_only_tools(app):
    async with mcp_session(app) as session:
        tools = (await session.list_tools()).tools
        resources = (await session.list_resources()).resources
        prompts = (await session.list_prompts()).prompts

    assert {t.name for t in tools} == TOOLS
    for tool in tools:
        assert tool.description and tool.title
        assert tool.annotations.readOnlyHint is True and tool.annotations.destructiveHint is False
        assert tool.inputSchema["additionalProperties"] is False
        assert tool.outputSchema is not None
    # Nothing else is served: no resources or prompts.
    assert resources == [] and prompts == []


@pytest.mark.parametrize("tool, arguments", [
    ("search_passages", {"query": "hejtman"}),
    ("search_documents", {"query": "hejtman"}),
    ("search_documents", {}),
])
@pytest.mark.parametrize("scope", [{"user_collection_id": str(uuid4())}, {"collection_id": str(uuid4())},
                                   {"tag_uuids": [str(uuid4())]}, {"annotation_filters": {"tag": "x"}}])
async def test_collection_tag_and_annotation_scope_is_refused(call, monkeypatch, tool, arguments, scope):
    calls = record(monkeypatch, search_service, tool, RuntimeError("must not be called"))

    result = await call(tool, {**arguments, **scope})

    assert next(iter(scope)) in error_text(result)
    assert calls == []


@pytest.mark.parametrize("arguments, field", [
    ({"query": "x", "limit": 26}, "limit"),
    ({"query": "x", "limit": 0}, "limit"),
    ({"query": "x", "alpha": 1.5}, "alpha"),
    ({"query": ""}, "query"),
    ({"query": "x" * 1001}, "query"),
    ({"query": "x", "mode": "sql"}, "mode"),
    ({"query": "x", "document_filters": {"year_min": 1900, "year_max": 1800}}, "document_filters"),
    ({"query": "x", "document_filters": {"where": "1=1"}}, "document_filters"),
    ({"query": "x", "chunk_filters": {"languages": [""]}}, "chunk_filters"),
])
async def test_passage_search_arguments_are_bounded(call, monkeypatch, arguments, field):
    calls = record(monkeypatch, search_service, "search_passages", RuntimeError("must not be called"))

    result = await call("search_passages", arguments)

    assert result.isError and calls == []
    assert field in error_text(result) or "validation" in error_text(result).lower()


async def test_passage_search(call, monkeypatch, app):
    items = [hit(), hit("Druhý hejtman.", library="unknown-library")]
    response = PassageSearchResponse(
        ranked_ids=[i.id for i in items] + [uuid4()], items=items, read_count=2, retrieval_limit=1000, bounded=False,
        total_count=3, criteria=SearchCriteria(text_query="hejtman", document_filters={"year_min": 1800}),
        vector="default", time_spent=0.1)
    calls = record(monkeypatch, search_service, "search_passages", response)

    answer = structured(await call("search_passages", {
        "query": " hejtman ", "document_filters": {"year_min": 1800}, "chunk_filters": {"languages": ["ces"]},
        "mode": "vector", "alpha": 0.3, "limit": 2}))

    [(backends, user, request, _, retrieval_limit)] = calls
    assert user is None and request.user_collection_id is None  # anonymous, public corpus only
    assert (request.criteria.text_query, request.limit, request.type, request.hybrid_search_alpha) == (
        "hejtman", 2, SearchType.vector, 0.3)
    assert request.criteria.chunk_filters.languages == ["ces"]
    assert retrieval_limit == app.state.config.SEARCH_PASSAGES_LIMIT  # the Search page's ranking depth
    assert backends.vectors is app.state.resources.search_vectors  # the application's embedders
    assert (answer["ranked_count"], answer["bounded"], answer["total_count"], answer["vector"]) == (3, False, 3, "default")
    first, second = answer["hits"]
    assert [first["rank"], second["rank"]] == [1, 2]
    assert first["passage"]["text"] == "Roku 1848 přijel hejtman." and first["passage"]["text_form"] == "display"
    assert first["passage"]["chunk_id"] == str(items[0].id)
    assert first["document"]["title"] == "Kronika obce Lhota" and first["document"]["authors"] == ["Jan Kronikář"]
    assert first["passage"]["source_url"] == f"https://www.digitalniknihovna.cz/mzk/view/uuid:{DOC_ID}?page=uuid:{PAGE_ID}"
    assert first["passage"]["semant_url"] == f"http://localhost:9000/#/documents/{DOC_ID}?chunk={items[0].id}"
    # No link is guessed for a library the viewer does not serve.
    assert second["document"]["source_url"] is None and second["passage"]["source_url"] is None
    assert "score" not in str(answer)


async def test_long_passages_are_cut(call, monkeypatch):
    long = hit("a" * (MAX_PASSAGE_CHARS + 10))
    record(monkeypatch, search_service, "search_passages", PassageSearchResponse(
        ranked_ids=[long.id], items=[long], read_count=1, retrieval_limit=1000, bounded=True, total_count=None,
        criteria=SearchCriteria(text_query="a"), time_spent=0))

    answer = structured(await call("search_passages", {"query": "a"}))

    [only] = answer["hits"]
    assert len(only["passage"]["text"]) == MAX_PASSAGE_CHARS and only["passage"]["text_truncated"] is True
    assert (answer["bounded"], answer["total_count"]) == (True, None)


async def test_document_browsing_pages_by_offset(call, monkeypatch):
    response = DocumentSearchResponse(
        items=[DocumentHit(document=document())], offset=10, next_offset=11, total_count=12, eligible_count=12,
        retrieval_limit=10_000, bounded=False, order="year_asc", criteria=SearchCriteria(), time_spent=0)
    calls = record(monkeypatch, search_service, "search_documents", response)

    answer = structured(await call("search_documents", {"offset": 10, "limit": 1,
                                                                     "document_filters": {"languages": ["ces"]}}))

    [(_, _, user, request, _, limits)] = calls
    assert user is None and request.user_collection_id is None
    assert (request.offset, request.limit, request.criteria.text_query) == (10, 1, None)
    assert limits.browse == 10_000
    assert answer["hits"][0]["rank"] == 11 and answer["hits"][0]["match"] is None
    assert (answer["order"], answer["next_offset"], answer["eligible_count"], answer["total_count"],
            answer["ranked_count"], answer["mode"]) == ("year_asc", 11, 12, 12, None, None)


async def test_document_search_ranks_once(call, monkeypatch):
    evidence = hit()
    response = DocumentSearchResponse(
        items=[DocumentHit(document=document(), match="text", chunk=evidence)], offset=0, next_offset=None,
        total_count=None, eligible_count=40, retrieval_limit=3000, bounded=True, order="metadata_then_text",
        ranked=[RankedDocument(id=DOC_ID, match="text", chunk_id=evidence.id),
                RankedDocument(id=uuid4(), match="text")], read_count=1,
        retrieval=DocumentRetrieval(metadata_limit=1000, metadata_bounded=False, chunk_limit=2000, chunk_bounded=True,
                                    ranked_chunks=2000, type=SearchType.hybrid, vector="default"),
        criteria=SearchCriteria(text_query="hejtman"), time_spent=0)
    record(monkeypatch, search_service, "search_documents", response)

    answer = structured(await call("search_documents", {"query": "hejtman", "limit": 1}))

    [only] = answer["hits"]
    assert only["match"] == "text" and only["best_passage"]["chunk_id"] == str(evidence.id)
    assert only["best_passage"]["text_form"] == "display"
    # The eligible documents bound the matches; their number is unknown when the ranking was cut.
    assert (answer["eligible_count"], answer["total_count"], answer["ranked_count"], answer["bounded"]) == (
        40, None, 2, True)
    assert (answer["mode"], answer["vector"], answer["next_offset"]) == ("hybrid", "default", None)


async def test_a_ranked_document_search_cannot_be_paged(call, monkeypatch):
    calls = record(monkeypatch, search_service, "search_documents", RuntimeError("must not be called"))

    result = await call("search_documents", {"query": "hejtman", "offset": 10})

    assert error_text(result).endswith(
        "invalid_input: offset must be 0 with a query: a text query's ranking is returned from its start only.")
    assert calls == []


@pytest.mark.parametrize("tool, arguments", [("search_documents", {"vector": "nope"}),
                                             ("search_documents", {"query": "x", "vector": "nope"}),
                                             ("search_passages", {"query": "x", "vector": "nope"})])
async def test_an_unknown_vector_is_refused(call, tool, arguments):
    # The services resolve the vector before any read (the fake store would fail otherwise).
    result = await call(tool, arguments)

    assert "invalid_input: Unknown search vector: nope." in error_text(result)


async def test_document_metadata(call, monkeypatch):
    stored = document(dateIssued=datetime(1851, 5, 1), partNumber=2, publisher="Obec", keywords=["kronika"])
    record(monkeypatch, document_service, "read_document", stored)
    record(monkeypatch, document_service, "count_chunks", 3)
    record(monkeypatch, page_service, "read_pages", DocumentPages(document_id=DOC_ID, available=True, pages=[
        DocumentPage(page_id=PAGE_ID, order=0), DocumentPage(page_id=uuid4(), order=1)]))

    answer = structured(await call("get_document", {"document_id": str(DOC_ID)}))

    assert answer["document_id"] == str(DOC_ID) and answer["title"] == "Kronika obce Lhota"
    assert (answer["date_issued"], answer["part_number"], answer["publisher"], answer["keywords"]) == (
        "1851-05-01", "2", "Obec", ["kronika"])
    assert (answer["chunk_count"], answer["page_count"]) == (3, 2)
    # Unavailable fields are present and null.
    assert answer["series_name"] is None and answer["editors"] == []
    assert answer["source_url"] == f"https://www.digitalniknihovna.cz/mzk/view/uuid:{DOC_ID}"


async def test_passage_context_is_canonical_text(call, monkeypatch):
    before, anchor, after = chunk("Před-\nchozí", 0), chunk("Kotva", 1), chunk("Další", 2)
    calls = record(monkeypatch, document_service, "read_chunk_window", DocumentChunkWindow(
        document=document(), chunks=[before, anchor, after], anchor_chunk_id=anchor.id, has_before=False,
        has_after=True, total_chunks=9))

    answer = structured(await call("get_passage_context", {
        "document_id": str(DOC_ID), "chunk_id": str(anchor.id), "before": 1, "after": 1}))

    [(_, document_id, chunk_id, n_before, n_after)] = calls
    assert (document_id, chunk_id, n_before, n_after) == (DOC_ID, anchor.id, 1, 1)
    assert [p["text"] for p in answer["passages"]] == ["Před-\nchozí", "Kotva", "Další"]
    assert {p["text_form"] for p in answer["passages"]} == {"canonical"}
    assert [p["order"] for p in answer["passages"]] == [0, 1, 2]
    assert (answer["has_before"], answer["has_after"], answer["total_chunks"]) == (False, True, 9)
    assert answer["document"]["title"] == "Kronika obce Lhota"


@pytest.mark.parametrize("arguments", [{"before": 11}, {"after": 11}, {"before": -1}, {"chunk_id": "not-a-uuid"}])
async def test_passage_context_is_bounded(call, monkeypatch, arguments):
    calls = record(monkeypatch, document_service, "read_chunk_window", RuntimeError("must not be called"))

    result = await call("get_passage_context", {
        "document_id": str(DOC_ID), "chunk_id": str(uuid4()), **arguments})

    assert result.isError and calls == []


async def test_page_with_scans(call, monkeypatch):
    record(monkeypatch, document_service, "read_document", document())
    record(monkeypatch, page_service, "read_pages", DocumentPages(document_id=DOC_ID, available=True, pages=[
        DocumentPage(page_id=uuid4(), order=0, label="[1]"), DocumentPage(page_id=PAGE_ID, order=1, label="[2]")]))
    calls = record(monkeypatch, page_service, "read_page_chunks",
                   PageChunks(page=1, chunks=[chunk("Strana-\ndruhá")], has_more=True))

    answer = structured(await call("get_document_page", {
        "document_id": str(DOC_ID), "page": 1, "limit": 1}))

    [(_, document_id, page, limit)] = calls
    assert (document_id, page, limit) == (DOC_ID, 1, 1)
    assert (answer["page"], answer["page_label"], answer["page_scans_available"], answer["has_more"]) == (
        1, "[2]", True, True)
    assert answer["source_url"] == f"https://www.digitalniknihovna.cz/mzk/view/uuid:{DOC_ID}?page=uuid:{PAGE_ID}"
    assert [(p["text"], p["text_form"]) for p in answer["passages"]] == [("Strana-\ndruhá", "canonical")]


async def test_page_past_the_page_list_is_refused(call, monkeypatch):
    record(monkeypatch, document_service, "read_document", document())
    record(monkeypatch, page_service, "read_pages", DocumentPages(
        document_id=DOC_ID, available=True, pages=[DocumentPage(page_id=PAGE_ID, order=0)]))
    calls = record(monkeypatch, page_service, "read_page_chunks", RuntimeError("must not be called"))

    result = await call("get_document_page", {"document_id": str(DOC_ID), "page": 1})

    assert "invalid_input: page must be below 1: the document has 1 pages." in error_text(result)
    assert calls == []


async def test_page_of_a_text_only_document(call, monkeypatch):
    record(monkeypatch, document_service, "read_document", document(library=None))
    record(monkeypatch, page_service, "read_pages", DocumentPages(document_id=DOC_ID, available=False, pages=[]))
    record(monkeypatch, page_service, "read_page_chunks", PageChunks(page=7, chunks=[], has_more=False))

    answer = structured(await call("get_document_page", {"document_id": str(DOC_ID), "page": 7}))

    assert (answer["page_scans_available"], answer["page_label"], answer["source_url"]) == (False, None, None)
    assert (answer["passages"], answer["has_more"]) == ([], False)


@pytest.mark.parametrize("arguments", [{"page": -1}, {"page": 100_001}, {"page": 0, "limit": 26}])
async def test_page_arguments_are_bounded(call, monkeypatch, arguments):
    calls = record(monkeypatch, document_service, "read_document", RuntimeError("must not be called"))

    result = await call("get_document_page", {"document_id": str(DOC_ID), **arguments})

    assert result.isError and calls == []


##########
# Errors #
##########

async def test_not_found(call, monkeypatch):
    record(monkeypatch, document_service, "read_document", NotFoundError(f"Document with id {DOC_ID} not found"))

    result = await call("get_document", {"document_id": str(DOC_ID)})

    assert error_text(result).endswith(f"not_found: Document with id {DOC_ID} not found")


async def test_a_malformed_id_is_invalid_input(call):
    result = await call("get_document", {"document_id": "1 OR 1=1"})

    assert "document_id" in error_text(result)


async def test_dependency_failures_leak_nothing(call, monkeypatch, caplog):
    secret = "weaviate.internal:50051 token=abc Traceback"
    record(monkeypatch, search_service, "search_passages", ConnectionError(secret))

    result = await call("search_passages", {"query": "hejtman"})

    text = error_text(result)
    assert text.endswith("unavailable: The corpus service is temporarily unavailable. Try again later.")
    assert secret not in text and secret not in caplog.text
    assert "MCP tool call failed: ConnectionError" in caplog.text


async def test_tool_calls_time_out(tmp_path, monkeypatch):
    async def slow(*args):
        await asyncio.sleep(5)
    monkeypatch.setattr(search_service, "search_passages", slow)
    async with started_app(tmp_path, MCP_TOOL_TIMEOUT_SECONDS="0.05") as app:
        async with mcp_session(app) as session:
            result = await session.call_tool("search_passages", {"query": "hejtman"})

    assert "timeout: The call did not finish within 0.05 seconds" in error_text(result)


async def test_concurrent_searches_are_limited(tmp_path, monkeypatch):
    running, most = 0, 0

    async def search(*args):
        nonlocal running, most
        running += 1
        most = max(most, running)
        await asyncio.sleep(0.05)
        running -= 1
        raise NotFoundError("done")
    monkeypatch.setattr(search_service, "search_passages", search)
    async with started_app(tmp_path, MCP_MAX_CONCURRENT_SEARCHES="2") as app:
        async with mcp_session(app) as session:
            results = await asyncio.gather(*(session.call_tool("search_passages", {"query": "x"}) for _ in range(5)))

    assert all("not_found" in error_text(r) for r in results)
    assert most == 2


async def test_calls_are_logged_without_their_content(call, monkeypatch, caplog):
    record(monkeypatch, search_service, "search_passages", PassageSearchResponse(
        ranked_ids=[], items=[], read_count=0, retrieval_limit=1000, bounded=False, total_count=0,
        criteria=SearchCriteria(text_query="tajný dotaz"), time_spent=0))

    with caplog.at_level("INFO", logger="semant_demo.mcp.server"):
        structured(await call("search_passages", {"query": "tajný dotaz", "limit": 3}))

    [entry] = [r for r in caplog.records if r.getMessage() == "MCP tool call completed"]
    assert (entry.__dict__["mcp.tool"], entry.__dict__["mcp.outcome"], entry.__dict__["mcp.limit"],
            entry.__dict__["mcp.results.count"]) == ("search_passages", "success", 3, 0)
    assert "tajný dotaz" not in caplog.text


#############
# Transport #
#############

@pytest.mark.parametrize("headers, status", [
    ({}, 200),  # non-browser clients send no Origin
    ({"Origin": "http://localhost:6274"}, 200),  # MCP Inspector
    ({"Origin": "https://evil.example"}, 403),
    ({"Host": "evil.example"}, 421),
])
async def test_origin_and_host_are_checked(app, headers, status):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as http:
        response = await http.post("/mcp", json=INITIALIZE, headers={**MCP_HEADERS, **headers})

    assert response.status_code == status, response.text


async def test_the_public_host_and_configured_values_are_allowed(tmp_path):
    config = make_test_config(tmp_path, ALLOWED_ORIGIN="https://demo.semant.cz",
                              MCP_ALLOWED_HOSTS="mcp.example:443", MCP_ALLOWED_ORIGINS="https://claude.ai")

    assert {"demo.semant.cz", "mcp.example:443"} <= set(mcp_server.allowed_hosts(config))
    assert {"https://demo.semant.cz", "https://claude.ai"} <= set(mcp_server.allowed_origins(config))


async def test_oversized_requests_are_refused(app):
    body = {**INITIALIZE, "params": {**INITIALIZE["params"], "padding": "x" * (mcp_server.MAX_REQUEST_BODY_BYTES + 1)}}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as http:
        response = await http.post("/mcp", json=body, headers=MCP_HEADERS)

    assert response.status_code == 413


#########
# Links #
#########

def test_source_links_use_the_frontends_verified_libraries():
    source = (Path(__file__).parents[2] / "semant_demo_frontend/src/features/documents/originalSource.ts")
    listed = re.search(r"DIGITAL_LIBRARY_CODES[^\[]*\[(.*?)\]", source.read_text(), re.S).group(1)

    assert mcp_server.DIGITAL_LIBRARY_CODES == set(re.findall(r"'([^']+)'", listed))


def test_semant_links_need_an_http_origin(tmp_path):
    assert mcp_server.public_base_url(make_test_config(tmp_path, ALLOWED_ORIGIN="https://demo.semant.cz/")) == (
        "https://demo.semant.cz")
    assert mcp_server.public_base_url(make_test_config(tmp_path, ALLOWED_ORIGIN="*")) is None
