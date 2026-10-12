"""Complete requests of the LLM features through the real gateway and LangChain models,
against fake HTTP providers: the RAG pipelines (incl. agent tool subcalls), the question
endpoint and search summaries. Also: RAG configurations choose only permitted tiers."""
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from semant_demo.adapters.llm.gateway import LlmGateway, ProviderSettings
from semant_demo.adapters.llm.models import ModelCatalog
from semant_demo.config import SCRIPT_PATH, Config
from semant_demo.features.documents.schemas import Document
from semant_demo.features.rag.schemas import RagRequest, RagSearch
from semant_demo.features.search.schemas import SearchRequest, SearchResponse, SearchResultChunk
from semant_demo.main import create_app
from semant_demo.rag.rag_factory import rag_factory, rag_load_single_config
from tests.app_support import make_test_config, offline_weaviate, write_offline_llm_catalog
from tests.corpus import load_corpus
from tests.fake_providers import create_fake_provider_app
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

    assert rag_calls(metrics) == [("rag", "large", "provider", "success")] * 2   # the rag default tier


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
    assert rag_calls(metrics) == [("rag", "large", "provider", "success")] * 4


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
    directory = SCRIPT_PATH / "rag" / "rag_configs" / configs
    registry = rag_factory(Config(environ={}), str(directory), llm)

    loadable = {yaml.safe_load(p.read_text())["id"] for p in directory.glob("*.yaml")
                if yaml.safe_load(p.read_text())["class_name"] in {"RagGenerator", "IncrementalAdaptiveRagGenerator",
                                                                   "xmartiAgentRag"}}
    assert set(registry.instances) == loadable


# ── question endpoint ──────────────────────────────────────────────────────

async def test_question_endpoint_answers_with_the_question_tier(tmp_path, metrics):
    fake = create_fake_provider_app(load_corpus())
    config = make_test_config(tmp_path, OPENAI_API_KEY="test-key", OPENAI_API_URL="http://fake/openai/v1")
    app = create_app(config, weaviate_connector=offline_weaviate, llm_transport=ASGITransport(app=fake))
    request = search_request()
    body = SearchResponse(results=[hit(t) for t in PASSAGES], search_request=request, time_spent=0.5, search_log=[])

    async with app.router.lifespan_context(app):
        app.state.resources.llm.recorder.metrics = metrics
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(f"/api/question/{QUESTION}", json=body.model_dump(mode="json"))

    assert response.status_code == 200
    # The fake answers the last user turn, which is the question.
    assert response.json() == {"summary": "Fake summary without passages.", "time_spent": 0.5}
    [call] = metrics.calls
    assert call["attributes"] == {"feature": "question", "tier": "medium", "provider": "openai",
                                  "model": "openai/gpt-4.1-mini", "usage_source": "provider"}


async def test_question_without_a_provider_key_is_a_bad_gateway(tmp_path):
    app = create_app(make_test_config(tmp_path, OPENAI_API_KEY=""), weaviate_connector=offline_weaviate)
    body = SearchResponse(results=[], search_request=search_request(query="q"), time_spent=0.0, search_log=[])

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/question/q", json=body.model_dump(mode="json"))

    assert response.status_code == 502
    assert response.json()["detail"] == "OPENAI_API_KEY is not configured on the server"


def test_clients_cannot_name_a_summary_model(tmp_path):
    schema = create_app(make_test_config(tmp_path)).openapi()["components"]["schemas"]

    for name in ("SearchRequest", "SummaryRequestBase"):
        if name in schema:
            assert not [p for p in schema[name]["properties"] if p.endswith("_model")]
    # A stale client sending one is ignored, not honoured.
    assert "search_title_model" not in search_request(search_title_model="evil").model_dump()
