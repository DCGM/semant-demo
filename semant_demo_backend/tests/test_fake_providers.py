"""The fake providers speak the protocol the real backend clients expect."""
import pytest
from httpx import ASGITransport, AsyncClient

from semant_demo.adapters.topicer.client import TopicerClient, TopicerStreamSummary, TopicerTag
from semant_demo.config import Config
from semant_demo.features.documents.schemas import DocumentChunk
from semant_demo.adapters.llm.gateway import LlmGateway, ProviderSettings
from semant_demo.adapters.llm.models import ModelCatalog
from semant_demo.features.summarization.templated import load_summarizer
from tests.app_support import write_offline_llm_catalog
from tests.corpus import load_corpus
from tests.fake_providers import FAKE_REASON, FAKE_TOPICER_CALL_COST_USD, create_fake_provider_app
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
    return TopicerClient("http://fake", "test", 5.0, transport=ASGITransport(app=fake_app))


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


async def test_db_stream_covers_collection_chunks_of_document(topicer):
    corpus = load_corpus()

    events = [event async for event in topicer.propose_for_db_stream(
        tag=topicer_tag(corpus.tags["person"]),
        collection_id=corpus.collections["chronicles"]["id"],
        document_id=corpus.documents["chronicle"]["id"],
    )]

    *chunks, summary = events
    assert [e["id"] for e in chunks] == [corpus.chunks["chronicle_1"]["id"], corpus.chunks["chronicle_2"]["id"]]
    assert all(len(e["tag_span_proposals"]) == 1 for e in chunks)
    assert isinstance(summary, TopicerStreamSummary)
    assert (summary.max_chunks, summary.processed_chunks, summary.limit_reached) == (40, 2, False)
    assert len(summary.usage.calls) == 2


async def test_db_stream_stops_at_max_chunks(fake_app):
    corpus = load_corpus()
    topicer = TopicerClient("http://fake", "test", 5.0, max_chunks_per_tag=1, transport=ASGITransport(app=fake_app))

    events = [event async for event in topicer.propose_for_db_stream(
        tag=topicer_tag(corpus.tags["person"]), collection_id=corpus.collections["chronicles"]["id"],
        document_id=corpus.documents["chronicle"]["id"])]

    chunk, summary = events
    assert chunk["id"] == corpus.chunks["chronicle_1"]["id"]
    assert (summary.processed_chunks, summary.limit_reached, summary.candidates_truncated) == (1, True, True)


async def test_embeddings_are_deterministic(fake_client):
    response = await fake_client.post("/embed_query", json={"query": "Lhota"})

    assert response.json()["embedding"] == fake_embedding("Lhota")
    assert len(fake_embedding("Lhota")) == FAKE_EMBEDDING_DIM


async def test_unfaked_provider_routes_fail_visibly(fake_client):
    response = await fake_client.post("/v1/chat/completions", json={})

    assert response.status_code == 501


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
