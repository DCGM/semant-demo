"""The public MCP endpoint (#635) on the seeded test store, through a real MCP client.

Its answers match what the REST API (the Search and document pages) returns for the same request:
the same passages and documents in the same order, the same counts; context and page reads
follow document order and its boundaries, with canonical stored text, while search hits have
display text. Query embedding uses the application's configured vector (served by the fake
embedding provider). The calls change nothing in the store and contact no LLM provider.
The fixture corpus: tests/integration/test_search.py.
"""
from uuid import UUID, uuid4

import httpx
import pytest
import yaml
from asgi_lifespan import LifespanManager

from semant_demo.bootstrap import load_search_vectors
from semant_demo.config import Config
from semant_demo.main import create_app
from tests.app_support import make_test_config
from tests.fake_providers import create_fake_provider_app
from tests.integration.conftest import RecordingTransport
from tests.mcp_support import BASE_URL, error_text, mcp_session, structured
from tests.test_mcp import NoNetwork

pytestmark = pytest.mark.integration

ALL_WORDS = "Novák Požár Prahy rodinu Slavia trh"
APP_COLLECTIONS = ("chunks_collection_name", "document_collection_name", "tag_collection_name",
                   "user_collection_name", "span_collection_name", "annotation_collection_name")


@pytest.fixture
async def llm():
    return NoNetwork()


@pytest.fixture
async def mcp_app(tmp_path, store_endpoint, seeded_store, llm):
    """The application on the seeded store with the MCP endpoint enabled (no users needed)."""
    app = create_app(make_test_config(tmp_path, MCP_ENABLED="true", **store_endpoint.app_environ()),
                     llm_transport=llm)
    async with LifespanManager(app):
        yield app
    assert llm.requests == []


@pytest.fixture
def embedding_calls(mcp_app, tmp_path, corpus) -> list[str]:
    """The application's default search vector, embedded by the fake embedding service; the called paths."""
    path = tmp_path / "search_vectors.yaml"
    path.write_text(yaml.safe_dump({"default": "gemma", "vectors": [
        {"id": "gemma", "name": "Gemma", "target_vector": "default",
         "embedding": {"provider": "embedding_service", "base_url": "http://fake"}}]}))
    calls: list[str] = []
    transport = RecordingTransport(httpx.ASGITransport(app=create_fake_provider_app(corpus)), calls)
    mcp_app.state.resources.search_vectors = load_search_vectors(
        Config(environ={"SEARCH_VECTORS_CONFIG": str(path)}), transport)
    return calls


@pytest.fixture
def call(mcp_app):
    async def call_tool(tool: str, arguments: dict):
        async with mcp_session(mcp_app) as session:
            return await session.call_tool(tool, arguments)
    return call_tool


@pytest.fixture
def rest(mcp_app):
    async def post(path: str, body: dict) -> dict:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mcp_app), base_url=BASE_URL) as http:
            response = await http.post(path, json=body)
        assert response.status_code == 200, response.text
        return response.json()
    return post


@pytest.fixture
def key_of(corpus):
    by_id = {c["id"]: key for key, c in corpus.chunks.items()}
    return lambda chunk_id: by_id[chunk_id]


@pytest.mark.parametrize("mode", ["text", "hybrid", "vector"])
@pytest.mark.parametrize("filters", [
    {},
    {"document_filters": {"year_min": 1900}},
    {"chunk_filters": {"classifications": {"communicative_mode": ["narration", "interaction"]}}},
])
async def test_passage_search_matches_the_search_page(call, rest, embedding_calls, mode, filters):
    answer = structured(await call("search_passages", {"query": ALL_WORDS, "mode": mode, "limit": 5, **filters}))
    page = await rest("/api/search/passages", {
        "criteria": {"text_query": ALL_WORDS, **filters}, "type": mode, "limit": 5})

    assert [h["passage"]["chunk_id"] for h in answer["hits"]] == [i["id"] for i in page["items"]]
    assert [h["passage"]["text"] for h in answer["hits"]] == [i["text"] for i in page["items"]]
    assert answer["hits"], "the query matches passages"
    assert (answer["ranked_count"], answer["bounded"], answer["total_count"], answer["retrieval_limit"]) == (
        len(page["ranked_ids"]), page["bounded"], page["total_count"], page["retrieval_limit"])
    assert answer["criteria"] == {k: page["criteria"][k] for k in ("document_filters", "chunk_filters")}
    assert [h["document"]["document_id"] for h in answer["hits"]] == [i["document"] for i in page["items"]]
    # Vector and hybrid search embed the query with the configured vector, text search does not.
    assert (len(embedding_calls) > 0) is (mode != "text")
    assert all(path == "/embed_query" for path in embedding_calls)


async def test_document_filters_restrict_passages(call, key_of):
    answer = structured(await call("search_passages", {"query": ALL_WORDS, "mode": "text", "limit": 25,
                                                       "document_filters": {"year_max": 1900}}))

    assert {key_of(h["passage"]["chunk_id"]) for h in answer["hits"]} == {"chronicle_1", "chronicle_2", "chronicle_3"}
    assert {h["document"]["year"] for h in answer["hits"]} == {1851}
    assert (answer["bounded"], answer["total_count"]) == (False, 3)


async def test_documents_by_filters_are_paged_by_offset(call, rest, corpus):
    first = structured(await call("search_documents", {"limit": 2}))
    second = structured(await call("search_documents", {"limit": 2, "offset": first["next_offset"]}))
    page = await rest("/api/search/documents", {"criteria": {}, "limit": 3})

    listed = [h["document"]["document_id"] for h in first["hits"] + second["hits"]]
    assert listed == [i["document"]["id"] for i in page["items"]]
    # Oldest first, the document without a year last.
    assert listed == [corpus.documents[k]["id"] for k in ("chronicle", "letters", "gazette")]
    assert [h["rank"] for h in first["hits"] + second["hits"]] == [1, 2, 3]
    assert (first["next_offset"], second["next_offset"]) == (2, None)
    assert first["eligible_count"] == first["total_count"] == 3 and first["bounded"] is False
    assert first["order"] == "year_asc" and first["ranked_count"] is None


@pytest.mark.parametrize("mode", ["text", "hybrid"])
async def test_documents_for_a_text_query_match_the_search_page(call, rest, embedding_calls, mode):
    answer = structured(await call("search_documents", {"query": "Novák Praha", "mode": mode, "limit": 3}))
    page = await rest("/api/search/documents", {"criteria": {"text_query": "Novák Praha"}, "type": mode, "limit": 3})

    assert [h["document"]["document_id"] for h in answer["hits"]] == [i["document"]["id"] for i in page["items"]]
    assert [h["match"] for h in answer["hits"]] == [i["match"] for i in page["items"]]
    assert [(h["best_passage"] or {}).get("chunk_id") for h in answer["hits"]] == [
        (i.get("chunk") or {}).get("id") for i in page["items"]]
    assert (answer["eligible_count"], answer["total_count"], answer["ranked_count"], answer["bounded"]) == (
        page["eligible_count"], page["total_count"], len(page["ranked"]), page["bounded"])
    assert answer["hits"] and answer["order"] == "metadata_then_text"


async def test_document_metadata(call, corpus):
    letters = corpus.documents["letters"]

    answer = structured(await call("get_document", {"document_id": letters["id"]}))

    assert (answer["document_id"], answer["title"], answer["year"]) == (
        letters["id"], letters["properties"]["title"], 1902)
    assert answer["authors"] == ["Karel Pisatel", "Marie Pisatelová"]
    assert (answer["chunk_count"], answer["page_count"]) == (2, None)  # no page scans in the test store
    assert answer["library"] is None and answer["source_url"] is None  # no library code: no link


async def test_passage_context_in_document_order(call, corpus):
    chronicle = corpus.documents["chronicle"]["id"]
    ids = [corpus.chunks[k]["id"] for k in ("chronicle_1", "chronicle_2", "chronicle_3")]

    middle = structured(await call("get_passage_context", {"document_id": chronicle, "chunk_id": ids[1],
                                                           "before": 1, "after": 1}))
    start = structured(await call("get_passage_context", {"document_id": chronicle, "chunk_id": ids[0],
                                                          "before": 2, "after": 1}))
    anchor_only = structured(await call("get_passage_context", {"document_id": chronicle, "chunk_id": ids[1],
                                                                "before": 0, "after": 0}))

    assert [p["chunk_id"] for p in middle["passages"]] == ids
    assert (middle["has_before"], middle["has_after"], middle["total_chunks"]) == (False, False, 3)
    assert [p["chunk_id"] for p in start["passages"]] == ids[:2]
    assert (start["has_before"], start["has_after"]) == (False, True)
    assert [p["chunk_id"] for p in anchor_only["passages"]] == [ids[1]]
    assert (anchor_only["has_before"], anchor_only["has_after"]) == (True, True)
    assert middle["document"]["title"] == corpus.documents["chronicle"]["properties"]["title"]
    assert {p["document_id"] for p in middle["passages"]} == {chronicle}


async def test_search_hits_are_display_text_and_context_is_canonical(call, seeded_store, collection_names, corpus):
    chunk_id = corpus.chunks["chronicle_1"]["id"]
    stored = "Roku 1848 přijel do Lhoty hejt-\nman Jan Novák a ubytoval\nse v hostinci."
    await seeded_store.collections.get(collection_names.chunks_collection_name).data.update(
        uuid=UUID(chunk_id), properties={"text": stored})

    found = structured(await call("search_passages", {"query": "ubytoval", "mode": "text"}))
    context = structured(await call("get_passage_context", {
        "document_id": corpus.documents["chronicle"]["id"], "chunk_id": chunk_id, "before": 0, "after": 0}))
    page = structured(await call("get_document_page", {"document_id": corpus.documents["chronicle"]["id"], "page": 1}))

    [hit] = found["hits"]
    assert (hit["passage"]["text"], hit["passage"]["text_form"]) == (
        "Roku 1848 přijel do Lhoty hejtman Jan Novák a ubytoval se v hostinci.", "display")
    assert [(p["text"], p["text_form"]) for p in context["passages"]] == [(stored, "canonical")]
    assert page["passages"][0]["text"] == stored


async def test_page_passages(call, corpus):
    chronicle = corpus.documents["chronicle"]["id"]
    ids = {k: corpus.chunks[k]["id"] for k in ("chronicle_1", "chronicle_2", "chronicle_3")}

    page_1 = structured(await call("get_document_page", {"document_id": chronicle, "page": 1}))
    truncated = structured(await call("get_document_page", {"document_id": chronicle, "page": 2, "limit": 1}))
    page_0 = structured(await call("get_document_page", {"document_id": chronicle, "page": 0}))

    assert [p["chunk_id"] for p in page_1["passages"]] == [ids["chronicle_1"], ids["chronicle_2"]]
    assert page_1["has_more"] is False
    assert ([p["chunk_id"] for p in truncated["passages"]], truncated["has_more"]) == ([ids["chronicle_2"]], True)
    # A page no passage covers; the test store has no page scans, so no page list bounds the index.
    assert (page_0["passages"], page_0["has_more"], page_0["page_scans_available"]) == ([], False, False)
    assert page_1["page_label"] is None and page_1["source_url"] is None


async def test_missing_data_and_invalid_filters(call, corpus):
    chronicle = corpus.documents["chronicle"]["id"]
    letters_chunk = corpus.chunks["letters_1"]["id"]
    unknown = str(uuid4())

    assert "not_found" in error_text(await call("get_document", {"document_id": unknown}))
    assert "not_found" in error_text(await call("get_document_page", {"document_id": unknown, "page": 0}))
    assert "not_found" in error_text(await call("get_passage_context", {"document_id": unknown, "chunk_id": unknown}))
    # A passage of another document is not found in this one.
    assert "not_found" in error_text(await call("get_passage_context", {
        "document_id": chronicle, "chunk_id": letters_chunk}))
    assert "invalid_input" in error_text(await call("search_passages", {
        "query": "Novák", "mode": "text", "chunk_filters": {"classifications": {"style": ["shouting"]}}}))
    assert "invalid_input" in error_text(await call("search_passages", {
        "query": "Novák", "mode": "text", "chunk_filters": {"classifications": {"no_such_class": ["x"]}}}))
    # The test store has no chunk-value summaries of its documents: refused, not answered with 0.
    assert "unavailable_filter" in error_text(await call("search_documents", {
        "chunk_filters": {"classifications": {"style": ["formal"]}}}))


async def test_calls_change_nothing(call, seeded_store, collection_names, corpus, embedding_calls):
    async def counts() -> dict[str, int]:
        result = {}
        for attribute in APP_COLLECTIONS:
            name = getattr(collection_names, attribute)
            collection = seeded_store.collections.get(name)
            if attribute == "annotation_collection_name":  # one tenant per collection
                tenants = await collection.tenants.get()
                result[name] = sum([(await collection.with_tenant(t).aggregate.over_all(total_count=True)).total_count
                                    for t in tenants])
            else:
                result[name] = (await collection.aggregate.over_all(total_count=True)).total_count
        return result
    chronicle = corpus.documents["chronicle"]["id"]
    before = await counts()

    for tool, arguments in [
        ("search_passages", {"query": ALL_WORDS}), ("search_passages", {"query": "Novák", "mode": "vector"}),
        ("search_documents", {"query": "Novák"}), ("search_documents", {}),
        ("get_document", {"document_id": chronicle}),
        ("get_passage_context", {"document_id": chronicle, "chunk_id": corpus.chunks["chronicle_2"]["id"]}),
        ("get_document_page", {"document_id": chronicle, "page": 1}),
    ]:
        structured(await call(tool, arguments))

    assert await counts() == before
