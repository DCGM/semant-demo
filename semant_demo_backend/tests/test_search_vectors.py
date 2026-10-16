"""Search vectors (#217): configuration, embedders, the vectors endpoint and RAG retrieval.

Selection inside search is covered in test_search_service.py; the real multi-vector
collection in integration/test_search.py.
"""
import json
from pathlib import Path

import httpx
import pytest
import yaml
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from semant_demo.adapters.embeddings.gemma import GemmaEmbeddings
from semant_demo.adapters.embeddings.openai_compatible import OpenAICompatibleEmbeddings
from semant_demo.bootstrap import create_embedder, load_search_vectors
from semant_demo.config import SCRIPT_PATH, Config
from semant_demo.core.errors import InvalidRequestError
from semant_demo.features.rag import service as rag_service
from semant_demo.features.rag.registry import BaseRag, RagRegistry
from semant_demo.features.rag.schemas import RagRequest, RagRequestMain, RagResponse, RagSearch
from semant_demo.features.search.schemas import SearchRequest
from semant_demo.features.search.vectors import EmbeddingSettings, SearchVectorsSettings, load_search_vectors_settings
from semant_demo.main import create_app
from tests.app_support import make_test_config, offline_weaviate
from tests.test_search_service import FakeChunks, FakeEmbeddings, backends

QWEN = {"id": "qwen3", "name": "Qwen3", "target_vector": "Qwen3_Embedding_0_6B",
        "embedding": {"provider": "openai", "base_url": "http://embedder.invalid/v1", "model": "Qwen/Qwen3-Embedding-0.6B",
                      "query_prefix": "Query: ", "dimensions": 256}}
GEMMA = {"id": "gemma", "name": "Gemma", "description": "original", "target_vector": "default",
         "embedding": {"provider": "embedding_service"}}


def settings(**overrides) -> dict:
    return {"default": "gemma", "vectors": [GEMMA, QWEN], **overrides}


#################
# Configuration #
#################

def test_the_shipped_configuration_keeps_the_original_vector_as_default():
    vectors = load_search_vectors(Config(environ={"EMBEDDING_SERVICE_HOST": "embedding.invalid"}))

    default = vectors.resolve(None)
    assert (default.target_vector, type(default.embedder)) == ("default", GemmaEmbeddings)
    assert default.embedder.base_url == "http://embedding.invalid:8001"
    assert vectors.describe().model_dump() == {"default_vector": default.id, "vectors": [
        {"id": default.id, "name": default.name, "description": default.description}]}


def test_a_configuration_file_is_found_through_the_setting(tmp_path):
    path = tmp_path / "vectors.yaml"
    path.write_text(yaml.safe_dump(settings(default="qwen3")))

    vectors = load_search_vectors(Config(environ={"SEARCH_VECTORS_CONFIG": str(path)}))

    assert vectors.default == "qwen3" and vectors.resolve(None).target_vector == "Qwen3_Embedding_0_6B"
    assert [v.id for v in vectors.describe().vectors] == ["gemma", "qwen3"]
    assert load_search_vectors_settings(path) == SearchVectorsSettings.model_validate(settings(default="qwen3"))


@pytest.mark.parametrize("change", [
    {"default": "missing"},
    {"vectors": []},
    {"vectors": [GEMMA, {**QWEN, "id": "gemma"}]},
    {"vectors": [GEMMA, {**QWEN, "id": "has space"}]},
    {"vectors": [GEMMA, {**QWEN, "target_vector": ""}]},
    # Weaviate builds GraphQL names from the vector name; `-` breaks GraphQL for the whole instance.
    {"vectors": [GEMMA, {**QWEN, "target_vector": "Qwen3-Embedding-0-6B"}]},
    {"vectors": [GEMMA, {**QWEN, "target_vector": "3vector"}]},
    {"vectors": [GEMMA, {**QWEN, "unknown": 1}]},
    {"vectors": [GEMMA, {**QWEN, "embedding": {"provider": "openai", "base_url": "http://x.invalid/v1"}}]},
    {"vectors": [GEMMA, {**QWEN, "embedding": {"provider": "openai", "model": "m"}}]},
    {"vectors": [GEMMA, {**QWEN, "embedding": {"provider": "other", "model": "m"}}]},
    {"vectors": [{**GEMMA, "embedding": {"provider": "embedding_service", "model": "m"}}]},
    {"vectors": [{**GEMMA, "embedding": {"provider": "embedding_service", "query_prefix": "q: "}}]},
])
def test_invalid_configurations_are_rejected(change):
    with pytest.raises(ValidationError):
        SearchVectorsSettings.model_validate(settings(**change))


async def test_an_invalid_configuration_stops_the_application_from_starting(tmp_path):
    path = tmp_path / "vectors.yaml"
    path.write_text(yaml.safe_dump(settings(default="missing")))
    app = create_app(make_test_config(tmp_path, SEARCH_VECTORS_CONFIG=str(path)), weaviate_connector=offline_weaviate)

    with pytest.raises(ValidationError):
        async with LifespanManager(app):
            pass


def test_an_unknown_selection_is_an_invalid_request():
    vectors = load_search_vectors(Config(environ={}))

    with pytest.raises(InvalidRequestError, match="Unknown search vector: nope"):
        vectors.resolve("nope")


def test_the_qwen_configuration_matches_the_embedding_service_and_the_backfill():
    """configs/search_vectors_qwen.yaml (#385) queries what the compose file serves and the backfill writes."""
    root = Path(__file__).parents[2]
    settings = load_search_vectors_settings(SCRIPT_PATH / "configs" / "search_vectors_qwen.yaml")
    compose = yaml.safe_load((root / "deploy" / "docker-compose.embedder.yml").read_text())
    backfill = yaml.safe_load((root / "data_tools" / "embedder" / "config.qwen.yaml").read_text())

    [vector] = settings.vectors
    service, = compose["services"].values()
    args = dict((*arg.removeprefix("--").split("=", 1), "")[:2] for arg in service["command"])
    assert settings.default == vector.id and vector.embedding.provider == "openai"
    assert vector.embedding.base_url == f"http://{service['hostname']}:{args['port']}/v1"
    assert vector.embedding.model == args["served-model-name"] == backfill["embedder"]["config"]["model_name"]
    assert vector.target_vector == backfill["vector_name"]
    assert vector.embedding.dimensions is None and backfill["embedder"]["config"]["dimensions"] is None
    assert backfill["embedder"]["config"]["input_template"] == "{{ text }}" and vector.embedding.document_prefix == ""
    assert vector.embedding.query_prefix.startswith("Instruct: ") and vector.embedding.query_prefix.endswith("\nQuery:")


#############
# Embedders #
#############

def test_each_provider_gets_its_client():
    config = Config(environ={"EMBEDDING_SERVICE_HOST": "embedding.invalid", "EMBEDDING_API_KEY": "secret"})

    service = create_embedder(EmbeddingSettings(provider="embedding_service"), config)
    elsewhere = create_embedder(EmbeddingSettings(provider="embedding_service", base_url="http://other.invalid:1"),
                                config)
    openai = create_embedder(EmbeddingSettings.model_validate(QWEN["embedding"]), config)

    assert (type(service), service.base_url, elsewhere.base_url) == (
        GemmaEmbeddings, "http://embedding.invalid:8001", "http://other.invalid:1")
    assert type(openai) is OpenAICompatibleEmbeddings
    assert (openai.base_url, openai.model, openai.api_key, openai.query_prefix, openai.dimensions) == (
        "http://embedder.invalid/v1", "Qwen/Qwen3-Embedding-0.6B", "secret", "Query: ", 256)


def recording_transport(requests: list[httpx.Request]) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"object": "list", "data": [{"index": 0, "embedding": [0.5, 0.25]}]})
    return httpx.MockTransport(handle)


@pytest.mark.parametrize("api_key, auth", [("", None), ("secret", "Bearer secret")])
async def test_openai_compatible_embeddings_send_the_model_prefixes_and_key(api_key, auth):
    requests: list[httpx.Request] = []
    embedder = OpenAICompatibleEmbeddings("http://embedder.invalid/v1/", "m", api_key=api_key, query_prefix="Q: ",
                                          document_prefix="D: ", dimensions=2, transport=recording_transport(requests))

    assert await embedder.embed_query("Novák") == [0.5, 0.25]
    assert await embedder.embed_document("Novák") == [0.5, 0.25]

    assert [str(r.url) for r in requests] == ["http://embedder.invalid/v1/embeddings"] * 2
    assert [json.loads(r.content) for r in requests] == [
        {"model": "m", "input": [text], "encoding_format": "float", "dimensions": 2} for text in ("Q: Novák", "D: Novák")]
    assert [r.headers.get("authorization") for r in requests] == [auth, auth]


async def test_openai_compatible_embedding_errors_propagate():
    embedder = OpenAICompatibleEmbeddings("http://embedder.invalid/v1", "m",
                                          transport=httpx.MockTransport(lambda r: httpx.Response(503)))

    with pytest.raises(httpx.HTTPStatusError):
        await embedder.embed_query("Novák")


############
# Endpoint #
############

async def test_vectors_endpoint_lists_the_configured_vectors_without_provider_details(tmp_path):
    path = tmp_path / "vectors.yaml"
    path.write_text(yaml.safe_dump(settings()))
    app = create_app(make_test_config(tmp_path, SEARCH_VECTORS_CONFIG=str(path)), weaviate_connector=offline_weaviate)

    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/search/vectors")

    assert response.status_code == 200
    assert response.json() == {"default_vector": "gemma", "vectors": [
        {"id": "gemma", "name": "Gemma", "description": "original"},
        {"id": "qwen3", "name": "Qwen3", "description": ""}]}


async def test_search_with_an_unknown_vector_is_a_bad_request(tmp_path):
    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    body = {"query": "Novák", "type": "hybrid", "tag_uuids": [], "positive": False, "automatic": False,
            "vector": "missing"}

    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/search", json=body)

    assert (response.status_code, response.json()) == (400, {"detail": "Unknown search vector: missing."})


#######
# RAG #
#######

class SearchingRag(BaseRag):
    """Retrieves twice (the second time as HyDE), like the multi-step pipelines."""

    def __init__(self):
        super().__init__(None, {})
        self.calls = 0

    async def rag_request(self, request: RagRequest, retrieve) -> RagResponse:
        self.calls += 1
        for is_hyde in (False, True):
            await retrieve(SearchRequest(query=request.question, type="hybrid", is_hyde=is_hyde, tag_uuids=[],
                                         positive=False, automatic=False))
        return RagResponse(rag_answer="answer", time_spent=0.0, response_id="r", sources=[])


def rag_registry(pipeline: BaseRag) -> RagRegistry:
    return RagRegistry(instances={"searching": pipeline})


def rag_request(**fields) -> RagRequestMain:
    return RagRequestMain(rag_id="searching", rag_request=RagRequest(question="Novák", rag_search=RagSearch()), **fields)


@pytest.mark.parametrize("selected, target", [(None, "default"), ("main", "default"), ("second", "second_target")])
async def test_rag_retrieves_with_the_selected_or_default_vector(selected, target):
    main, second, chunks = FakeEmbeddings(), FakeEmbeddings(10.0), FakeChunks()

    await rag_service.answer(rag_registry(SearchingRag()), backends(chunks, main, second), rag_request(vector=selected))

    assert [q.target_vector for q in chunks.queries] == [target, target]
    used, unused = (second, main) if selected == "second" else (main, second)
    assert used.calls == [("query", "Novák"), ("document", "Novák")] and unused.calls == []


async def test_rag_with_an_unknown_vector_is_refused_before_the_pipeline_runs():
    pipeline, chunks = SearchingRag(), FakeChunks()

    with pytest.raises(InvalidRequestError, match="Unknown search vector: missing"):
        await rag_service.answer(rag_registry(pipeline), backends(chunks), rag_request(vector="missing"))
    assert pipeline.calls == 0 and chunks.queries == []
