"""The fake providers speak the protocol the real backend clients expect."""
import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from semant_demo.adapters.topicer.client import TopicerClient, TopicerTag
from semant_demo.config import Config
from semant_demo.features.documents.schemas import DocumentChunk
from semant_demo.adapters.llm.gateway import LlmGateway, ProviderSettings
from semant_demo.adapters.llm.models import ModelCatalog
from semant_demo.features.summarization.templated import load_summarizer
from tests.app_support import write_offline_llm_catalog
from tests.corpus import load_corpus
from tests.fake_providers import (
    FAKE_REASON, FAKE_TOPICER_CALL_COST_USD, FAKE_TOPICER_CONFIGS, create_fake_provider_app,
)
from tests.fakes import FAKE_EMBEDDING_DIM, fake_embedding


@pytest.fixture
def fake_app():
    return create_fake_provider_app(load_corpus())


@pytest.fixture
async def fake_client(fake_app):
    async with AsyncClient(transport=ASGITransport(app=fake_app), base_url="http://fake") as client:
        yield client


@pytest.fixture
def topicer(fake_app):
    return TopicerClient("http://fake", FAKE_TOPICER_CONFIGS[0], 5.0, transport=ASGITransport(app=fake_app))


def topicer_tag(tag):
    return TopicerTag(id=tag["id"], name=tag["name"], definition=tag["definition"], examples=tag["examples"])


async def test_text_proposals_mark_tag_examples(topicer):
    corpus = load_corpus()
    chunk = corpus.chunks["chronicle_2"]

    answer = await topicer.propose_for_text(
        chunk_id=chunk["id"], text=chunk["text"], tags=[topicer_tag(corpus.tags["person"])])

    assert [(p["span_start"], p["span_end"], p["tag"]["id"], p["reason"]) for p in answer.proposals] == [
        (51, 60, corpus.tags["person"]["id"], FAKE_REASON)]
    assert chunk["text"][51:60] == "Jan Novák"
    assert [c.cost_usd for c in answer.usage.calls] == [FAKE_TOPICER_CALL_COST_USD]


async def test_text_answers_are_paced_one_by_one_when_delayed():
    # The browser tests rely on it to act while a suggestion run is under way.
    corpus = load_corpus()
    chunk = corpus.chunks["chronicle_1"]
    topicer = TopicerClient("http://fake", FAKE_TOPICER_CONFIGS[0], 5.0,
                            transport=ASGITransport(app=create_fake_provider_app(corpus, stream_delay=0.2)))
    loop = asyncio.get_running_loop()
    started = loop.time()

    async def answered_after() -> float:
        await topicer.propose_for_text(chunk_id=chunk["id"], text=chunk["text"],
                                       tags=[topicer_tag(corpus.tags["person"])])
        return loop.time() - started

    first, second = sorted(await asyncio.gather(answered_after(), answered_after()))

    assert second - first >= 0.15 and second >= 0.2


async def test_configs_are_listed_and_an_unknown_one_is_refused(topicer, fake_client):
    assert await topicer.list_configs() == list(FAKE_TOPICER_CONFIGS)

    response = await fake_client.post("/v1/tags/propose/texts", params={"config_name": "unknown"},
                                      json={"text_chunk": {"id": "c", "text": "x"}, "tags": []})

    assert response.status_code == 404


async def test_embeddings_are_deterministic(fake_client):
    response = await fake_client.post("/embed_query", json={"query": "Lhota"})

    assert response.json()["embedding"] == fake_embedding("Lhota")
    assert len(fake_embedding("Lhota")) == FAKE_EMBEDDING_DIM


async def test_chunk_title_requests_get_a_distinct_deterministic_title(fake_client):
    def request(excerpt: str) -> dict:
        return {"model": "fake", "stream": False, "messages": [
            {"role": "system", "content": "Respond only with the title."},
            {"role": "user", "content": f"Original Document Title:\nKronika\n\nExcerpt Text:\n{excerpt}"}]}

    first = await fake_client.post("/ollama/api/chat", json=request("Požár v roce 1850 zničil obec."))
    second = await fake_client.post("/openai/v1/chat/completions", json=request("Café Slavia hostila setkání."))

    assert first.json()["message"]["content"] == "Požár v roce 1850"
    assert second.json()["choices"][0]["message"]["content"] == "Café Slavia hostila setkání."


async def test_unfaked_provider_routes_fail_visibly(fake_client):
    response = await fake_client.post("/v1/chat/completions", json={})

    assert response.status_code == 501
    # The OpenAI client retries a 5xx after this instead of its random backoff (#853).
    assert response.headers["retry-after-ms"] == "1"


async def test_configured_openrouter_chat_summarizes_the_passages_it_was_sent(fake_app, tmp_path):
    # The real summarizer and tier (configured as deployed), talking to the fake over ASGI.
    llm = LlmGateway(ModelCatalog.load(write_offline_llm_catalog(tmp_path / "llm_models.yaml")),
                     ProviderSettings(openai_api_key="test-key", openai_base_url="http://fake/openai/v1"),
                     http_transport=ASGITransport(app=fake_app))
    summarizer = load_summarizer(Config(environ={}).SEARCH_SUMMARIZER_CONFIG, llm)
    corpus = load_corpus()
    chunks = [
        DocumentChunk(id=c["id"], text=c["text"], start_page_id=c["id"], from_page=1, to_page=1,
                  end_paragraph=False, document=corpus.documents["chronicle"]["id"], order=c["order"])
        for c in (corpus.chunks["chronicle_1"], corpus.chunks["chronicle_2"])
    ]

    summary = await summarizer.gen_results_summary("Novák", chunks)

    assert summary == "Fake summary of 2 passage(s); last [doc2]."
