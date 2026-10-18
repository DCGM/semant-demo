"""Every backend-owned AI route admits its operation against the caller's daily allowance
(#398), through the application with fake providers and fake stores.

AI-only routes answer a refusal with the structured 429 before any provider request,
also for nested (agentic) RAG; Search keeps its results and skips only the optional
titles and summaries, with a quota warning. Admitted operations are settled with all
their calls, also streamed span chat.
"""
import json
import sqlite3
from types import SimpleNamespace
from uuid import UUID

import pytest
import yaml
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from semant_demo.features.documents.schemas import DocumentStats
from semant_demo.features.quota import service
from semant_demo.features.quota.principal import GUEST_COOKIE, guest_principal
from semant_demo.features.quota.schemas import QuotaExhaustedResponse
from semant_demo.features.quota.service import QuotaPrincipal
from semant_demo.features.search.service import SUMMARY_QUOTA_WARNING
from semant_demo.main import create_app
from semant_demo.routes.dependencies import get_annotation_store, get_documents, get_search_backends, \
    get_topicer, get_user_collections
from tests.app_support import make_test_config, offline_weaviate
from tests.auth_support import auth_headers, register
from tests.corpus import load_corpus
from tests.fake_providers import create_fake_provider_app
from tests.test_llm.test_features import AGENT_PARAMS, hit
from tests.test_llm.test_gateway import CountingTransport
from tests.test_quota.test_ledger import call
from tests.test_search_service import backends as search_backends
from tests.test_span_chat import COLLECTION as SPAN_COLLECTION, FakeStore, span
from tests.test_summarization import test_document_service as documents
from tests import test_suggestions as suggestion_fakes

PASSWORD = "StrongPassw0rd!"
SEARCH_RESPONSE = {"results": [], "search_request": {"query": "Novák", "tag_uuids": [], "positive": False,
                                                    "automatic": False}, "time_spent": 0.1, "search_log": []}
GUEST_ROUTES = {
    "rag": ("/api/rag", {"rag_id": "agent", "rag_request": {"question": "Kdo byl Novák?", "rag_search": {}}}),
    "explain": ("/api/rag/explain", {"rag_id": "adaptive", "selected_text": "Novák", "full_answer": "Novák [doc1]",
                                     "sources": [hit("Jan Novák byl kronikář.").model_dump(mode="json")]}),
    "question": ("/api/question", {"question_text": "Kdo byl Novák?", "search_response": SEARCH_RESPONSE}),
    "summarize": ("/api/summarize/results", SEARCH_RESPONSE),
}


class Ai:
    def __init__(self, app, provider: CountingTransport, db):
        self.app = app
        self.provider = provider
        self.db = db
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    @property
    def resources(self):
        return self.app.state.resources

    async def guest(self) -> QuotaPrincipal:
        response = await self.client.get("/api/quota")
        return guest_principal(response.cookies[GUEST_COOKIE])

    async def account(self, email: str = "a@example.com") -> tuple[QuotaPrincipal, dict]:
        assert (await register(self.client, email=email, password=PASSWORD)).status_code == 201
        headers = await auth_headers(self.client, email, PASSWORD)
        user_id = (await self.client.get("/api/users/me", headers=headers)).json()["id"]
        return QuotaPrincipal(kind="account", id=user_id), headers

    async def exhaust(self, principal: QuotaPrincipal) -> None:
        ledger, policy = self.resources.quota_ledger, self.resources.quota_policy
        operation = await service.admit(ledger, policy, principal, "test", 0)
        await service.settle(ledger, operation, [call(policy.daily_limit(principal) / 1e6)])

    async def status(self, headers=None) -> dict:
        return (await self.client.get("/api/quota", headers=headers)).json()

    def rows(self, sql: str) -> list[tuple]:
        with sqlite3.connect(self.db) as connection:
            return connection.execute(sql).fetchall()


@pytest.fixture
async def ai(tmp_path):
    provider = CountingTransport(ASGITransport(app=create_fake_provider_app(load_corpus())))
    config = make_test_config(tmp_path, OPENAI_API_KEY="test-key", OPENAI_API_URL="http://fake/openai/v1")
    (tmp_path / "rag_configs" / "agent.yaml").write_text(yaml.safe_dump({
        "id": "agent", "name": "Agent", "description": "test", "class_name": "xmartiAgentRag",
        "params": {"search_type": "hybrid", **AGENT_PARAMS}}))
    # Explains selections; the agent does not.
    (tmp_path / "rag_configs" / "adaptive.yaml").write_text(yaml.safe_dump({
        "id": "adaptive", "name": "Adaptive", "description": "test", "class_name": "IncrementalAdaptiveRagGenerator",
        "params": {"search_type": "hybrid", "tier": "medium", "web_search_enabled": False}}))
    app = create_app(config, weaviate_connector=offline_weaviate, llm_transport=provider)
    app.dependency_overrides[get_search_backends] = search_backends
    async with LifespanManager(app):
        ai = Ai(app, provider, tmp_path / "test.db")
        async with ai.client:
            yield ai


def assert_refused(response, principal: str) -> None:
    assert response.status_code == 429, response.text
    body = QuotaExhaustedResponse.model_validate(response.json())
    assert (body.code, body.principal) == ("llm_quota_exhausted", principal)
    assert int(response.headers["retry-after"]) > 0


@pytest.mark.parametrize("route", GUEST_ROUTES)
async def test_an_exhausted_guest_gets_a_429_without_a_provider_request(ai, route):
    path, body = GUEST_ROUTES[route]
    await ai.exhaust(await ai.guest())

    response = await ai.client.post(path, json=body)

    assert_refused(response, "guest")
    assert ai.provider.paths == []
    assert ai.rows("SELECT count(*) FROM llm_quota_operation") == [(1,)]  # only the exhausting one


async def test_an_agentic_rag_answer_settles_all_its_calls_as_one_operation(ai):
    await ai.guest()
    path, body = GUEST_ROUTES["rag"]

    response = await ai.client.post(path, json=body)

    assert response.status_code == 200, response.text
    calls = len(ai.provider.paths)
    assert calls >= 3  # the agent, its synthesis tool subcall and the final answer
    assert ai.rows("SELECT feature, status FROM llm_quota_operation") == [("rag", "settled")]
    assert ai.rows("SELECT count(*) FROM llm_quota_call") == [(calls,)]
    status = await ai.status()
    assert status["reserved_usd"] == 0 and status["charged_usd"] > 0


@pytest.mark.parametrize("route", ["explain", "question", "summarize"])
async def test_an_admitted_guest_operation_is_charged(ai, route):
    path, body = GUEST_ROUTES[route]
    await ai.guest()

    response = await ai.client.post(path, json=body)

    assert response.status_code == 200, response.text
    calls = len(ai.provider.paths)
    assert calls >= 1  # an explanation detects the answer's language first
    assert ai.rows("SELECT status FROM llm_quota_operation") == [("settled",)]
    assert ai.rows("SELECT count(*) FROM llm_quota_call") == [(calls,)]
    status = await ai.status()
    assert status["reserved_usd"] == 0 and status["charged_usd"] > 0


async def test_a_new_guest_refused_for_a_large_reservation_keeps_its_cookie(tmp_path):
    config = make_test_config(tmp_path, LLM_QUOTA_GUEST_DAILY_USD="0.001")  # below the question's reservation
    app = create_app(config, weaviate_connector=offline_weaviate)
    path, body = GUEST_ROUTES["question"]

    async with LifespanManager(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        refused = await client.post(path, json=body)
        status = await client.get("/api/quota")

    assert_refused(refused, "guest")
    assert GUEST_COOKIE in refused.cookies
    # The client kept the cookie: the same guest, no new cookie.
    assert "set-cookie" not in status.headers and status.json()["used_usd"] == 0


def summaries_request(**fields) -> dict:
    return {"query": "Novák", "type": "text", "tag_uuids": [], "positive": False, "automatic": False,
            "search_title_generate": True, "search_summary_generate": True,
            "search_results_summary_generate": True, **fields}


async def test_search_keeps_its_results_and_warns_when_the_allowance_is_exhausted(ai):
    await ai.exhaust(await ai.guest())

    response = await ai.client.post("/api/search", json=summaries_request())

    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 1 and body["results"][0]["query_title"] is None
    assert body["results_summary"] is None
    assert body["quota_exhausted"]["code"] == "llm_quota_exhausted"
    [warning] = body["warnings"]
    assert warning.startswith(SUMMARY_QUOTA_WARNING + "Insufficient remaining daily AI allowance")
    assert ai.provider.paths == []


async def test_search_without_generation_neither_admits_nor_warns(ai):
    await ai.exhaust(await ai.guest())

    response = await ai.client.post("/api/search", json=summaries_request(
        search_title_generate=False, search_summary_generate=False, search_results_summary_generate=False))

    assert response.status_code == 200
    assert (response.json()["warnings"], response.json()["quota_exhausted"]) == ([], None)
    assert ai.rows("SELECT count(*) FROM llm_quota_operation") == [(1,)]


async def test_search_summaries_are_one_charged_operation(ai):
    await ai.guest()

    response = await ai.client.post("/api/search", json=summaries_request())

    assert response.status_code == 200 and response.json()["warnings"] == []
    assert len(ai.provider.paths) == 3  # a title, a result summary and the results summary
    assert ai.rows("SELECT feature, status FROM llm_quota_operation") == [("search_summary", "settled")]
    assert ai.rows("SELECT count(*) FROM llm_quota_call") == [(3,)]


def span_store(user_id: str) -> FakeStore:
    store = FakeStore(span(0, 3))

    async def access(collection_id):
        return UUID(user_id), set()

    store.collections = SimpleNamespace(read_access_record=access)
    return store


def discuss_body(store: FakeStore) -> dict:
    return {"collection_id": str(SPAN_COLLECTION), "span_id": store.span.id,
            "messages": [{"role": "user", "content": "Fits?"}]}


async def test_span_chat_is_refused_before_streaming_for_an_exhausted_account(ai):
    account, headers = await ai.account()
    store = span_store(account.id)
    ai.app.dependency_overrides[get_annotation_store] = lambda: store
    await ai.exhaust(account)

    response = await ai.client.post("/api/ai/discuss_span", json=discuss_body(store), headers=headers)

    assert_refused(response, "account")
    assert ai.provider.paths == [] and "span" not in store.reads


async def test_a_streamed_span_chat_reply_is_settled_before_it_ends(ai):
    account, headers = await ai.account()
    store = span_store(account.id)
    ai.app.dependency_overrides[get_annotation_store] = lambda: store

    response = await ai.client.post("/api/ai/discuss_span", json=discuss_body(store), headers=headers)

    events = [json.loads(line) for line in response.text.splitlines()]
    assert response.status_code == 200 and events[-1] == {"done": True} and len(events) > 2
    assert ai.rows("SELECT feature, status FROM llm_quota_operation") == [("span_chat", "settled")]
    assert ai.rows("SELECT outcome, cost_source FROM llm_quota_call") == [("success", "price")]
    status = await ai.status(headers)
    assert (status["principal"], status["reserved_usd"]) == ("account", 0) and status["charged_usd"] > 0


def summary_stores(user_id: str):
    class Collections(documents.FakeCollections):
        async def read_access_record(self, collection_id):
            return (UUID(user_id), set()) if collection_id == documents.COLLECTION else None

    return Collections(), documents.FakeDocuments([documents.chunk(0), documents.chunk(1)])


async def test_document_summary_admits_after_authorization(ai):
    account, headers = await ai.account()
    collections, chunks = summary_stores(account.id)
    ai.app.dependency_overrides[get_user_collections] = lambda: collections
    ai.app.dependency_overrides[get_documents] = lambda: chunks
    path = f"/api/user_collections/{documents.COLLECTION}/documents/{documents.DOCUMENT}/summary"

    summarized = await ai.client.post(path, json={}, headers=headers)
    other = await ai.client.post(f"/api/user_collections/{documents.COLLECTION}/documents/"
                                 f"{documents.OUTSIDE_DOCUMENT}/summary", json={}, headers=headers)
    await ai.exhaust(account)
    refused = await ai.client.post(path, json={}, headers=headers)

    assert summarized.status_code == 200, summarized.text
    assert other.status_code == 404
    assert_refused(refused, "account")
    assert len(ai.provider.paths) == 1
    # The summary and the exhausting operation; the denied request reserved nothing.
    assert ai.rows("SELECT feature FROM llm_quota_operation ORDER BY started_at") \
        == [("document_summary",), ("test",)]


def test_ai_routes_declare_the_429_and_search_does_not(tmp_path):
    paths = create_app(make_test_config(tmp_path)).openapi()["paths"]

    for path in ("/api/rag", "/api/rag/explain", "/api/question", "/api/summarize/{summary_type}",
                 "/api/ai/discuss_span", "/api/ai/suggest_spans/thorough", "/api/ai/suggest_spans/optimized",
                 "/api/ai/suggest_spans/selection",
                 "/api/user_collections/{collection_id}/documents/{document_id}/summary"):
        refused = paths[path]["post"]["responses"]["429"]
        assert refused["content"]["application/json"]["schema"]["$ref"].endswith("/QuotaExhaustedResponse")
        assert "Retry-After" in refused["headers"]
    assert "429" not in paths["/api/search"]["post"]["responses"]


def suggestion_world(user_id: str) -> suggestion_fakes.World:
    """One-chunk document in a collection owned by ``user_id``."""
    world = suggestion_fakes.World("Jan Novák")

    async def read_access_record(collection_id):
        return (UUID(user_id), set()) if collection_id == suggestion_fakes.COLLECTION else None

    world.read_access_record = read_access_record
    return world


def suggestion_bodies(world) -> dict[str, dict]:
    document = {"collection_id": str(suggestion_fakes.COLLECTION), "document_id": str(suggestion_fakes.DOCUMENT),
                "tag_ids": [str(suggestion_fakes.PERSON)]}
    selection = {**document, "chunk_ids": [str(world.chunks[0].id)], "selection_start": 0, "selection_end": 3}
    return {"thorough": document, "optimized": document, "selection": selection}


def use_suggestion_fakes(ai, world, provider) -> None:
    ai.app.dependency_overrides[get_annotation_store] = lambda: world.store()
    ai.app.dependency_overrides[get_topicer] = lambda: provider


@pytest.mark.parametrize("mode", ["thorough", "optimized", "selection"])
async def test_suggestions_are_refused_before_streaming_for_an_exhausted_account(ai, mode):
    account, headers = await ai.account()
    world = suggestion_world(account.id)
    provider = suggestion_fakes.FakeProvider(world)
    use_suggestion_fakes(ai, world, provider)
    await ai.exhaust(account)

    response = await ai.client.post(f"/api/ai/suggest_spans/{mode}", json=suggestion_bodies(world)[mode],
                                    headers=headers)

    assert_refused(response, "account")
    assert provider.calls == [] and world.log == []


async def test_suggestion_access_is_checked_before_admission(ai):
    account, headers = await ai.account()
    world = suggestion_world(str(suggestion_fakes.OTHER.id))  # someone else's collection
    provider = suggestion_fakes.FakeProvider(world)
    use_suggestion_fakes(ai, world, provider)

    response = await ai.client.post("/api/ai/suggest_spans/thorough", json=suggestion_bodies(world)["thorough"],
                                    headers=headers)

    assert response.status_code == 404
    assert ai.rows("SELECT count(*) FROM llm_quota_operation") == [(0,)]


async def test_a_suggestion_run_settles_each_chunk_on_the_account(ai):
    account, headers = await ai.account()
    world = suggestion_world(account.id)
    provider = suggestion_fakes.FakeProvider(world, {"Jan Novák": [suggestion_fakes.proposal(
        suggestion_fakes.PERSON, 0, 3)]})  # no reported usage: charged the reservation
    use_suggestion_fakes(ai, world, provider)

    response = await ai.client.post("/api/ai/suggest_spans/thorough", json=suggestion_bodies(world)["thorough"],
                                    headers=headers)

    end = json.loads(response.text.splitlines()[-1])
    assert (end["event"], end["outcome"], end["units_processed"], end["stop_reason"]) == ("end", "complete", 1, None)
    assert ai.rows("SELECT feature, status FROM llm_quota_operation") == [("topicer_thorough", "settled")]
    status = await ai.status(headers)
    assert (status["reserved_usd"], status["charged_usd"]) == (0, 0.005)


async def test_document_stats_carry_the_optimized_chunk_limit(ai):
    account, headers = await ai.account()
    collections, _ = summary_stores(account.id)

    async def read_document_stats(collection_id, document_id):
        return DocumentStats(document_id=str(document_id), collection_id=str(collection_id), chunks_in_collection=2,
                             total_chunks=3, annotations_count=0, distinct_tags_count=0)

    collections.read_document_stats = read_document_stats
    ai.app.dependency_overrides[get_user_collections] = lambda: collections

    response = await ai.client.get(f"/api/user_collections/{documents.COLLECTION}/documents/{documents.DOCUMENT}"
                                   "/stats", headers=headers)

    assert response.status_code == 200, response.text
    assert (response.json()["chunks_in_collection"], response.json()["ai_max_chunks_per_tag"]) == (2, 40)
