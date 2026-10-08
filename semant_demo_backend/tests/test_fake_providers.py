"""The fake providers speak the protocol the real backend clients expect."""
import pytest
from httpx import ASGITransport, AsyncClient

from semant_demo.adapters.topicer.client import TopicerClient, TopicerTag
from tests.corpus import load_corpus
from tests.fake_providers import FAKE_REASON, create_fake_provider_app
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

    proposals = await topicer.propose_for_text(
        chunk_id=chunk["id"], text=chunk["text"], tags=[topicer_tag(corpus.tags["person"])])

    assert [(p["span_start"], p["span_end"], p["tag"]["id"], p["reason"]) for p in proposals] == [
        (51, 60, corpus.tags["person"]["id"], FAKE_REASON)]
    assert chunk["text"][51:60] == "Jan Novák"


async def test_db_stream_covers_collection_chunks_of_document(topicer):
    corpus = load_corpus()

    events = [event async for event in topicer.propose_for_db_stream(
        tag=topicer_tag(corpus.tags["person"]),
        collection_id=corpus.collections["chronicles"]["id"],
        document_id=corpus.documents["chronicle"]["id"],
    )]

    assert [e["id"] for e in events] == [corpus.chunks["chronicle_1"]["id"], corpus.chunks["chronicle_2"]["id"]]
    assert all(len(e["tag_span_proposals"]) == 1 for e in events)


async def test_embeddings_are_deterministic(fake_client):
    response = await fake_client.post("/embed_query", json={"query": "Lhota"})

    assert response.json()["embedding"] == fake_embedding("Lhota")
    assert len(fake_embedding("Lhota")) == FAKE_EMBEDDING_DIM


async def test_unfaked_provider_routes_fail_visibly(fake_client):
    response = await fake_client.post("/v1/chat/completions", json={})

    assert response.status_code == 501
