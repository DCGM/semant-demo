"""Complete requests of the LLM features through the real gateway and LangChain models,
against fake HTTP providers: the RAG pipelines (incl. agent tool subcalls), the question
endpoint and search summaries. Also: RAG configurations choose only permitted tiers, and
feature limits bound each feature's calls and operations (#397)."""
import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from semant_demo.adapters.llm.gateway import LlmGateway, ProviderSettings, limit_provider_sdk_logs
from semant_demo.adapters.llm.models import ModelCatalog
from semant_demo.adapters.llm.usage import LlmInputTooLarge, LlmOperationLimitExceeded
from semant_demo.config import SCRIPT_PATH, Config
from semant_demo.features.documents.schemas import Document
from semant_demo.features.rag import service as rag_service
from semant_demo.features.rag.schemas import ExplainRequest, RagRequest, RagRequestMain, RagResponse, RagSearch
from semant_demo.features.search.schemas import SearchRequest, SearchResponse, SearchResultChunk
from semant_demo.main import create_app
from semant_demo.features.summarization.templated import load_summarizer
from semant_demo.routes.dependencies import get_llm, get_rag_registry, get_search_backends
from semant_demo.features.rag.registry import BaseRag, RagRegistry, rag_factory, rag_load_single_config
from tests.app_support import make_test_config, offline_weaviate, write_offline_llm_catalog
from tests.corpus import load_corpus
from tests.fake_providers import create_fake_provider_app
from tests.fakes import FakeLlm
from tests.test_llm.test_gateway import RecordingMetrics

QUESTION = "Kdo byl Jan Novák?"
PASSAGES = ["Jan Novák byl kronikář obce Lhota.", "Novák psal kroniku v letech 1890 až 1910."]


@pytest.fixture
def metrics():
    return RecordingMetrics()


@pytest.fixture
def llm(tmp_path, metrics) -> LlmGateway:
    """The deployed tier catalog, with every provider served by the fake."""
    catalog = ModelCatalog.load(write_offline_llm_catalog(tmp_path / "llm_models.yaml"))
    settings = ProviderSettings(openai_api_key="test-key", openai_base_url="http://fake/openai/v1",
                                ollama_base_url="http://fake/ollama")
    return LlmGateway(catalog, settings, metrics, http_transport=ASGITransport(app=create_fake_provider_app(load_corpus())))


def search_request(**fields) -> SearchRequest:
    return SearchRequest(**{"query": "Novák", "tag_uuids": [], "positive": False, "automatic": False, **fields})


def hit(text: str) -> SearchResultChunk:
    doc = uuid4()
    return SearchResultChunk(id=uuid4(), title="Kronika", text=text, start_page_id=uuid4(), from_page=1, to_page=1,
                             order=0, language="ces", document=doc, document_object=Document(id=doc, library="mzk"))


class FakeRetriever:
    def __init__(self):
        self.requests: list[SearchRequest] = []

    async def __call__(self, request: SearchRequest) -> SearchResponse:
        self.requests.append(request)
        return SearchResponse(results=[hit(t) for t in PASSAGES], search_request=request, time_spent=0.0,
                              search_log=[])


def rag_config(tmp_path: Path, class_name: str, **params) -> Path:
    path = tmp_path / f"{class_name}.yaml"
    path.write_text(yaml.safe_dump({"id": class_name, "name": class_name, "description": "test",
                                    "class_name": class_name, "params": {"search_type": "hybrid", **params}}))
    return path


def load_rag(tmp_path, llm, class_name, **params):
    loaded = rag_load_single_config(Config(environ={}), str(rag_config(tmp_path, class_name, **params)), llm)
    assert loaded is not None
    return loaded[2]


def rag_calls(metrics):
    return [(c["attributes"]["feature"], c["attributes"]["tier"], c["attributes"]["usage_source"], c["outcome"])
            for c in metrics.calls]


# ── RAG ────────────────────────────────────────────────────────────────────

async def test_basic_rag_answers_from_retrieved_passages(tmp_path, llm, metrics):
    rag = load_rag(tmp_path, llm, "RagGenerator", tier="small")
    retrieve = FakeRetriever()

    response = await rag.rag_request(RagRequest(question=QUESTION, rag_search=RagSearch()), retrieve)

    # The passages go to the system prompt, which the fake ignores; the question is the user turn.
    assert response.rag_answer == "Fake summary without passages."
    assert [r.query for r in retrieve.requests] == [QUESTION]
    assert [s.text for s in response.sources] == PASSAGES
    assert rag_calls(metrics) == [("rag", "small", "provider", "success")]


async def test_basic_rag_with_history_meters_the_rephrasing_call_too(tmp_path, llm, metrics):
    rag = load_rag(tmp_path, llm, "RagGenerator")
    request = RagRequest(question=QUESTION, rag_search=RagSearch(),
                         history=[{"role": "user", "content": "Kronika Lhoty"},
                                  {"role": "assistant", "content": "Kronika existuje."}])

    await rag.rag_request(request, FakeRetriever())

    assert rag_calls(metrics) == [("rag", "medium", "provider", "success")] * 2   # the rag default tier


async def test_incremental_rag_graph_completes_with_every_node_metered(tmp_path, llm, metrics):
    rag = load_rag(tmp_path, llm, "IncrementalAdaptiveRagGenerator", tier="medium", web_search_enabled=False,
                   max_retries=1)

    response = await rag.rag_request(RagRequest(question=QUESTION, rag_search=RagSearch()), FakeRetriever())

    assert response.rag_answer
    assert len(metrics.calls) >= 3
    assert {call[:3] for call in rag_calls(metrics)} == {("rag", "medium", "provider")}


async def test_agentic_rag_meters_the_agent_and_its_tool_subcalls(tmp_path, llm, metrics):
    prompts = {name: f"{name} prompt" for name in (
        "assess_retrieval_quality_prompt", "expand_query_prompt", "decompose_question_prompt",
        "synthesize_evidence_prompt")}
    rag = load_rag(tmp_path, llm, "xmartiAgentRag", alpha=0.5, chunk_limit=5, agent_iterations=5,
                   prompts={"system_prompt_template": "Agent ({remaining_iterations} steps).", **prompts})
    retrieve = FakeRetriever()

    response = await rag.rag_request(RagRequest(question=QUESTION, rag_search=RagSearch()), retrieve)

    # The fake agent searches, has the synthesize_evidence tool summarize, then answers with it.
    assert [r.query for r in retrieve.requests] == [QUESTION]
    assert response.rag_answer == "Fake summary of 2 passage(s); last [doc2]."
    assert [s.text for s in response.sources] == PASSAGES
    # agent → tool call, agent → tool call (+ synthesize subcall), agent → answer
    assert rag_calls(metrics) == [("rag", "medium", "provider", "success")] * 4



@pytest.mark.parametrize("class_name, params", [
    ("RagGenerator", {}),
    ("IncrementalAdaptiveRagGenerator", {"tier": "medium", "web_search_enabled": False, "max_retries": 1}),
])
async def test_rag_pipelines_retrieve_with_the_retriever_of_each_request(tmp_path, llm, class_name, params):
    # The retriever carries per-request choices (the search vector, #217); a shared pipeline
    # instance must not keep the first request's one.
    rag = load_rag(tmp_path, llm, class_name, **params)
    first, second = FakeRetriever(), FakeRetriever()

    await rag.rag_request(RagRequest(question=QUESTION, rag_search=RagSearch()), first)
    calls = len(first.requests)
    await rag.rag_request(RagRequest(question=QUESTION, rag_search=RagSearch()), second)

    assert calls > 0 and len(first.requests) == calls and second.requests

@pytest.mark.parametrize(("params", "reason"), [
    ({"model_type": "OPENAI", "model_name": "gpt-4o"}, "retired model params"),
    ({"api_key": "sk-..."}, "retired model params"),
    ({"tier": "tiny"}, "tier the rag feature may not use"),
    ({"tier": "openai/gpt-5.1"}, "not a tier"),
])
def test_rag_configurations_cannot_choose_a_model_or_unpermitted_tier(tmp_path, llm, params, reason):
    assert rag_load_single_config(Config(environ={}), str(rag_config(tmp_path, "RagGenerator", **params)), llm) is None


def test_agentic_rag_needs_a_tool_calling_tier(tmp_path, llm):
    path = rag_config(tmp_path, "xmartiAgentRag", tier="small", prompts={})

    assert rag_load_single_config(Config(environ={}), str(path), llm) is None


@pytest.mark.parametrize("configs", ["demo_configs", "configs"])
def test_shipped_rag_configurations_load_with_their_tiers(llm, configs):
    directory = SCRIPT_PATH / "configs" / "rag" / configs
    registry = rag_factory(Config(environ={}), str(directory), llm)

    # Every shipped configuration names an existing class and a permitted tier.
    assert set(registry.instances) == {yaml.safe_load(p.read_text())["id"] for p in directory.glob("*.yaml")}


# ── question endpoint ──────────────────────────────────────────────────────

def question_body(question: str, search_response: SearchResponse) -> dict:
    return {"question_text": question, "search_response": search_response.model_dump(mode="json")}


async def test_question_endpoint_answers_with_the_question_tier(tmp_path, metrics):
    fake = create_fake_provider_app(load_corpus())
    config = make_test_config(tmp_path, OPENAI_API_KEY="test-key", OPENAI_API_URL="http://fake/openai/v1")
    app = create_app(config, weaviate_connector=offline_weaviate, llm_transport=ASGITransport(app=fake))
    request = search_request()
    body = SearchResponse(results=[hit(t) for t in PASSAGES], search_request=request, time_spent=0.5, search_log=[])

    async with app.router.lifespan_context(app):
        app.state.resources.llm.recorder.metrics = metrics
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/question", json=question_body(QUESTION, body))

    assert response.status_code == 200
    # The fake answers the last user turn, which is the question.
    assert response.json() == {"summary": "Fake summary without passages.", "time_spent": 0.5}
    [call] = metrics.calls
    assert call["attributes"] == {"feature": "question", "tier": "small", "provider": "openai",
                                  "model": "anthropic/claude-haiku-5.5", "usage_source": "provider",
                                  "cost_source": "price"}


async def test_question_without_a_provider_key_is_a_bad_gateway(tmp_path):
    app = create_app(make_test_config(tmp_path, OPENAI_API_KEY=""), weaviate_connector=offline_weaviate)
    body = SearchResponse(results=[], search_request=search_request(query="q"), time_spent=0.0, search_log=[])

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/question", json=question_body("q", body))

    assert response.status_code == 502
    assert response.json()["detail"] == "OPENAI_API_KEY is not configured on the server"


async def test_question_provider_failure_returns_a_fixed_error_without_content(tmp_path, caplog):
    secret = "sk-SECRET-MARKER-7f3a"

    def failing(messages):
        raise RuntimeError(f"401 at http://provider/v1?key={secret}: {messages[1]['content']}")

    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    app.dependency_overrides[get_llm] = lambda: FakeLlm(failing)
    body = SearchResponse(results=[hit(t) for t in PASSAGES], search_request=search_request(), time_spent=0.5,
                          search_log=[])

    with caplog.at_level(logging.DEBUG):
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/question", json=question_body(QUESTION, body))

    assert response.status_code == 502
    assert response.json() == {"detail": "The language model could not answer the question."}
    for leaked in (secret, "kronikář", "Novák"):
        assert leaked not in response.text and leaked not in caplog.text


@pytest.mark.parametrize("path, body, status", [
    ("/api/question", lambda results: {"question_text": "", "search_response": results}, 422),
    ("/api/question", lambda results: {"question_text": QUESTION}, 422),
    # The question is no longer accepted in the URL.
    (f"/api/question/{QUESTION}", lambda results: results, 404),
], ids=["empty-question", "no-search-response", "legacy-path"])
async def test_invalid_question_requests_never_reach_the_model(tmp_path, path, body, status):
    calls = []
    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    app.dependency_overrides[get_llm] = lambda: FakeLlm(lambda messages: calls.append(messages) or "answer")
    results = SearchResponse(results=[], search_request=search_request(), time_spent=0.0, search_log=[])

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(path, json=body(results.model_dump(mode="json")))

    assert response.status_code == status
    assert calls == []


def test_clients_cannot_name_a_summary_model(tmp_path):
    schema = create_app(make_test_config(tmp_path)).openapi()["components"]["schemas"]

    for name in ("SearchRequest", "SummaryRequestBase"):
        if name in schema:
            assert not [p for p in schema[name]["properties"] if p.endswith("_model")]
    # A stale client sending one is ignored, not honoured.
    assert "search_title_model" not in search_request(search_title_model="evil").model_dump()


@pytest.mark.parametrize(("class_name", "params"), [
    ("RagGenerator", {}),
    ("IncrementalAdaptiveRagGenerator", {"tier": "medium", "web_search_enabled": False, "max_retries": 1}),
    ("xmartiAgentRag", {"alpha": 0.5, "chunk_limit": 5, "agent_iterations": 5, "prompts": {
        "system_prompt_template": "Agent ({remaining_iterations} steps).",
        **{name: name for name in ("assess_retrieval_quality_prompt", "expand_query_prompt",
                                   "decompose_question_prompt", "synthesize_evidence_prompt")}}}),
])
async def test_rag_pipelines_neither_print_nor_log_questions_passages_or_answers(tmp_path, llm, class_name, params,
                                                                              caplog, capsys):
    # As deployed with LOG_LEVEL=DEBUG; provider SDK loggers included.
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.NOTSET, logger="openai")
    limit_provider_sdk_logs()
    rag = load_rag(tmp_path, llm, class_name, **params)
    request = RagRequest(question=QUESTION, rag_search=RagSearch(),
                         history=[{"role": "user", "content": "Kronika Lhoty"},
                                  {"role": "assistant", "content": "Kronika existuje."}])

    response = await rag.rag_request(request, FakeRetriever())

    logged = caplog.text + capsys.readouterr().out
    for content in ("Novák", "Lhot", "Kronika", response.rag_answer):
        assert content not in logged


# ── bounded workloads (#397) ───────────────────────────────────────────────

AGENT_PARAMS = {"alpha": 0.5, "chunk_limit": 5, "agent_iterations": 5, "prompts": {
    "system_prompt_template": "Agent ({remaining_iterations} steps).",
    **{name: name for name in ("assess_retrieval_quality_prompt", "expand_query_prompt",
                               "decompose_question_prompt", "synthesize_evidence_prompt")}}}


def limited_catalog(tmp_path, feature: str, **limits) -> Path:
    path = write_offline_llm_catalog(tmp_path / "limited_llm_models.yaml")
    catalog = yaml.safe_load(path.read_text())
    catalog["features"][feature]["limits"].update(limits)
    path.write_text(yaml.safe_dump(catalog))
    return path


def limited_llm(tmp_path, metrics, feature: str, **limits) -> LlmGateway:
    settings = ProviderSettings(openai_api_key="test-key", openai_base_url="http://fake/openai/v1")
    return LlmGateway(ModelCatalog.load(limited_catalog(tmp_path, feature, **limits)), settings, metrics,
                      http_transport=ASGITransport(app=create_fake_provider_app(load_corpus())))


class RecordingRag(BaseRag):
    def __init__(self, llm=None, error: Exception | None = None):
        super().__init__(None, {}, llm)
        self.requests: list = []
        self.error = error

    async def rag_request(self, request, retrieve):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return RagResponse(rag_answer="ok", time_spent=0.0, response_id="r", sources=[])

    async def explain_selection(self, request):
        self.requests.append(request)
        return {"explanation": "ok"}


def rag_backends():
    return SimpleNamespace(vectors=SimpleNamespace(resolve=lambda vector: SimpleNamespace(id="default")))


def history(n: int) -> list[dict[str, str]]:
    return [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(n)]


async def test_an_agentic_rag_answer_is_capped_by_the_rag_call_limit(tmp_path, metrics):
    # The fake agent needs 4 calls (agent, agent, synthesize subcall, agent); allow 3.
    llm = limited_llm(tmp_path, metrics, "rag", max_calls=3)
    rag = load_rag(tmp_path, llm, "xmartiAgentRag", **AGENT_PARAMS)

    with llm.operation("rag"), pytest.raises(LlmOperationLimitExceeded):
        await rag.rag_request(RagRequest(question=QUESTION, rag_search=RagSearch()), FakeRetriever())

    assert len(metrics.calls) == 3


async def test_each_rag_answer_and_explanation_is_one_llm_operation():
    llm = FakeLlm()
    registry = RagRegistry(instances={"r": RecordingRag(llm)})

    await rag_service.answer(registry, rag_backends(), RagRequestMain(
        rag_id="r", rag_request=RagRequest(question=QUESTION, rag_search=RagSearch())))
    await rag_service.explain(registry, ExplainRequest(rag_id="r", selected_text="x", full_answer="x", sources=[]))

    assert llm.operations == ["rag", "rag"]


async def test_the_adaptive_rag_passes_a_server_refusal_on(tmp_path, metrics):
    llm = limited_llm(tmp_path, metrics, "rag", max_calls=1)
    rag = load_rag(tmp_path, llm, "IncrementalAdaptiveRagGenerator", tier="medium", web_search_enabled=False,
                   max_retries=1)

    with llm.operation("rag"), pytest.raises(LlmOperationLimitExceeded):
        await rag.rag_request(RagRequest(question=QUESTION, rag_search=RagSearch()), FakeRetriever())
    assert len(metrics.calls) == 1


class GatedChain:
    """Grading calls that stay in flight until cancelled; the call number ``refuse_at`` is refused."""

    def __init__(self, refuse_at: int):
        self.refuse_at, self.started, self.running, self.cancelled = refuse_at, 0, 0, 0

    async def ainvoke(self, inputs):
        self.started += 1
        if self.started == self.refuse_at:
            raise LlmOperationLimitExceeded("The request needs more language model calls than allowed.")
        self.running += 1
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        finally:
            self.running -= 1


async def test_a_refused_grading_call_cancels_the_graders_still_in_flight(tmp_path, llm):
    rag = load_rag(tmp_path, llm, "IncrementalAdaptiveRagGenerator", tier="medium", web_search_enabled=False)
    chain = GatedChain(refuse_at=4)
    rag._create_chain = lambda model, prompt: chain
    documents = [hit(f"passage {i}") for i in range(8)]

    with pytest.raises(LlmOperationLimitExceeded):
        await rag.node_grade_context({"documents": documents, "retrieval_iteration_counter": 2,
                                      "question": QUESTION, "language": "ces"})

    # The other graders, started alongside the refused one, are cancelled and awaited, not left running.
    assert (chain.started, chain.running, chain.cancelled) == (8, 0, 7)


async def test_an_oversized_rag_input_is_refused_by_the_basic_rag(tmp_path, metrics):
    llm = limited_llm(tmp_path, metrics, "rag", max_input_tokens=50)
    rag = load_rag(tmp_path, llm, "RagGenerator", tier="small")

    with pytest.raises(LlmInputTooLarge):
        await rag.rag_request(RagRequest(question="Novák " * 300, rag_search=RagSearch()), FakeRetriever())
    assert metrics.calls == []


async def test_rag_answers_and_explanations_get_only_the_recent_history():
    pipeline = RecordingRag()
    registry = RagRegistry(instances={"r": pipeline})

    await rag_service.answer(registry, rag_backends(), RagRequestMain(
        rag_id="r", rag_request=RagRequest(question=QUESTION, rag_search=RagSearch(), history=history(7))),
        history_limit=4)
    await rag_service.explain(registry, ExplainRequest(rag_id="r", selected_text="x", full_answer="x",
                                                       history=history(7), sources=[]), history_limit=4)

    assert [[m.content for m in r.history] for r in pipeline.requests] == [["m3", "m4", "m5", "m6"]] * 2


@pytest.mark.parametrize(("error", "status"), [
    (LlmOperationLimitExceeded("The request needs more than the 20 language model calls allowed for it."), 503),
    (LlmInputTooLarge("The request is too large for the language model (about 24000 tokens are allowed)."), 413),
])
async def test_rag_routes_answer_a_server_refusal_with_its_status_and_message(tmp_path, error, status):
    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    app.dependency_overrides[get_rag_registry] = lambda: RagRegistry(instances={"r": RecordingRag(error=error)})
    app.dependency_overrides[get_search_backends] = rag_backends

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/rag", json={"rag_id": "r", "rag_request": {
                "question": QUESTION, "rag_search": {}}})

    assert (response.status_code, response.json()) == (status, {"detail": str(error)})


async def test_a_question_above_the_input_limit_is_refused_with_413(tmp_path, metrics):
    fake = create_fake_provider_app(load_corpus())
    config = make_test_config(tmp_path, OPENAI_API_KEY="test-key", OPENAI_API_URL="http://fake/openai/v1",
                              LLM_MODELS_CONFIG=str(limited_catalog(tmp_path, "question", max_input_tokens=30)))
    app = create_app(config, weaviate_connector=offline_weaviate, llm_transport=ASGITransport(app=fake))
    body = SearchResponse(results=[hit(t) for t in PASSAGES * 5], search_request=search_request(), time_spent=0.5,
                          search_log=[])

    async with app.router.lifespan_context(app):
        app.state.resources.llm.recorder.metrics = metrics
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/question", json=question_body(QUESTION, body))

    assert response.status_code == 413
    assert response.json() == {"detail": "The request is too large for the language model "
                                         "(about 30 tokens are allowed)."}
    assert metrics.calls == []


async def test_search_summaries_run_as_one_capped_operation_through_the_gateway(tmp_path, metrics, caplog):
    caplog.set_level(logging.INFO, logger="semant_demo.adapters.llm.usage")
    llm = limited_llm(tmp_path, metrics, "search_summary")
    summarizer = load_summarizer(str(SCRIPT_PATH / "configs" / "search_summarizer.yaml"), llm)
    response = SearchResponse(results=[hit(f"{PASSAGES[0]} {i}") for i in range(12)],
                              search_request=search_request(), time_spent=0.0, search_log=[])

    failures = await summarizer(search_request(), response)

    # 10 titles + 10 per-result summaries + the results summary, within max_calls (21).
    assert failures == ["results_limit"] and len(metrics.calls) == 21
    assert [r.query_title is not None for r in response.results] == [True] * 10 + [False] * 2
    [record] = [r for r in caplog.records if r.getMessage() == "LLM operation finished"]
    assert (record.__dict__["llm.operation.calls"], record.__dict__["llm.operation.max_calls"]) == (21, 21)
