"""The offline embedder (data_tools/embedder, #192) against the test-owned Weaviate.

The real pipeline and ``VLLMEmbedder`` run; the OpenAI-compatible endpoint is the fake
provider (``/openai/v1/embeddings``: ``second_embedding`` of each input). Covers named
vector creation, preservation of what objects already hold, resumability, write
failures, refused collections, the guarded test collection and querying a filled vector
through Search (#217). Collections other than the application's are named
``EmbedderToolTest*`` and deleted after each test.
"""
import json
import sys
from pathlib import Path

import httpx
import pytest
import yaml
from httpx import ASGITransport
from openai import AsyncOpenAI
from weaviate.classes.config import Configure, DataType, Property
from weaviate.classes.query import QueryReference

from semant_demo.adapters.weaviate.search import ChunkSearchRepository
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.bootstrap import load_search_vectors
from semant_demo.config import Config
from semant_demo.features.search import service
from semant_demo.features.search.schemas import SearchRequest
from semant_demo.features.search.service import SearchBackends
from tests.fake_providers import create_fake_provider_app
from tests.fakes import SECOND_VECTOR, second_embedding

sys.path.insert(0, str(Path(__file__).parents[3] / "data_tools" / "embedder"))
from semantembedder.db import create_test_collection  # noqa: E402
from semantembedder.pipeline import EmbeddingPipeline  # noqa: E402

pytestmark = pytest.mark.integration

TEST_COLLECTION = "EmbedderToolTest"
TOOL_VECTOR = "tool_vector"
CHUNK_REFS = ["document", "userCollection", "positiveTag", "negativeTag", "automaticTag"]


@pytest.fixture
async def tool_store(seeded_store):
    """The owned, seeded store; collections named ``EmbedderToolTest*`` are deleted afterwards."""
    yield seeded_store
    for name in await seeded_store.collections.list_all(simple=True):
        if name.startswith(TEST_COLLECTION):
            await seeded_store.collections.delete(name)


@pytest.fixture
def fake_provider(corpus):
    return create_fake_provider_app(corpus)


@pytest.fixture
def embed_calls() -> list[list[str]]:
    """Inputs of every embedding request the pipelines sent, one list per request."""
    return []


@pytest.fixture
def make_pipeline(tmp_path, store_endpoint, fake_provider, embed_calls):
    """``make_pipeline(**settings)``: a pipeline on the test store whose embedder calls the fake."""
    count = 0

    def make(**settings) -> EmbeddingPipeline:
        nonlocal count
        count += 1
        config = {
            "weaviate_host": store_endpoint.host, "weaviate_port": store_endpoint.rest_port,
            "weaviate_grpc_port": store_endpoint.grpc_port, "weaviate_api_key": None, "weaviate_headers": None,
            "collection": TEST_COLLECTION, "vector_name": TOOL_VECTOR, "create_vector": True,
            "vector_index_type": "hnsw", "distance_metric": "cosine", "return_properties": None,
            "max_records": None, "scan_batch_size": 3, "embed_batch_size": 2, "max_concurrent_requests": 2,
            "max_concurrent_writes": 4, "max_retries": 1, "retry_delay": 0.0,
            "embedder": {"cls": "VLLMEmbedder", "config": {
                "base_url": "http://fake/openai/v1", "api_key": "test-key", "model_name": "fake-small",
                "input_template": settings.pop("input_template", "{{ text }}"), "dimensions": None,
                "truncate_prompt_tokens": None, "extra_body": None, "timeout": 10.0, "max_retries": 0}},
            **settings,
        }
        path = tmp_path / f"embedder-{count}.yaml"
        path.write_text(yaml.safe_dump(config))
        pipeline = EmbeddingPipeline.create(str(path))

        async def record(request: httpx.Request) -> None:
            embed_calls.append(json.loads(request.content)["input"])
        # The embedder's OpenAI client (created lazily otherwise), routed to the fake provider.
        pipeline.embedder._client = AsyncOpenAI(
            api_key="test-key", base_url="http://fake/openai/v1", max_retries=0,
            http_client=httpx.AsyncClient(transport=ASGITransport(app=fake_provider),
                                          event_hooks={"request": [record]}))
        return pipeline
    return make


async def tool_vectors(client, collection=TEST_COLLECTION) -> dict[str, list[float] | None]:
    res = await client.collections.get(collection).query.fetch_objects(limit=100, include_vector=[TOOL_VECTOR])
    return {str(o.uuid): (o.vector or {}).get(TOOL_VECTOR) for o in res.objects}


async def snapshot_chunks(client, names) -> dict:
    res = await client.collections.get(names.chunks_collection_name).query.fetch_objects(
        limit=100, include_vector=True, return_references=[QueryReference(link_on=r) for r in CHUNK_REFS])
    return {str(o.uuid): {
        "properties": dict(o.properties),
        "refs": {r: sorted(str(x.uuid) for x in o.references[r].objects) if o.references and r in o.references else []
                 for r in CHUNK_REFS},
        "vectors": dict(o.vector or {})} for o in res.objects}


##################################
# Application chunks and Search #
##################################

async def test_a_filled_vector_keeps_the_chunk_data_and_is_searchable(tool_store, collection_names, corpus, tmp_path,
                                                                     fake_provider, make_pipeline, embed_calls):
    names = collection_names
    before = await snapshot_chunks(tool_store, names)

    await make_pipeline(collection=names.chunks_collection_name, input_template="{{ title }}: {{ text }}").run_async()

    after = await snapshot_chunks(tool_store, names)
    config = await tool_store.collections.get(names.chunks_collection_name).config.get()
    assert set(config.vector_config) == {"default", SECOND_VECTOR, TOOL_VECTOR}
    assert config.vector_config[TOOL_VECTOR].vector_index_config.distance_metric.value == "cosine"
    assert after.keys() == before.keys()
    for chunk_id, old in before.items():
        new = after[chunk_id]
        # A PATCH of one named vector: properties, references and the other vectors are unchanged.
        assert new["properties"] == old["properties"] and new["refs"] == old["refs"]
        assert {k: v for k, v in new["vectors"].items() if k != TOOL_VECTOR} == old["vectors"]
        # A missing property renders as an empty string (letters_2 has no title).
        expected = second_embedding(f"{old['properties']['title'] or ''}: {old['properties']['text']}")
        assert new["vectors"][TOOL_VECTOR] == pytest.approx(expected)
    assert sorted(t for call in embed_calls for t in call) == sorted(
        f"{c['title'] or ''}: {c['text']}" for c in corpus.chunks.values())

    # Search (#217) queries the filled vector once it is configured; the original one still works.
    path = tmp_path / "search_vectors.yaml"
    path.write_text(yaml.safe_dump({"default": "original", "vectors": [
        {"id": "original", "name": "Original", "target_vector": "default",
         "embedding": {"provider": "embedding_service", "base_url": "http://fake"}},
        {"id": "tool", "name": "Tool", "target_vector": TOOL_VECTOR,
         "embedding": {"provider": "openai", "base_url": "http://fake/openai/v1", "model": "fake-small"}}]}))
    vectors = load_search_vectors(Config(environ={"SEARCH_VECTORS_CONFIG": str(path)}),
                                  ASGITransport(app=fake_provider))
    backends = SearchBackends(ChunkSearchRepository(tool_store, names), UserCollectionRepository(tool_store, names),
                              TagRepository(tool_store, names), vectors)
    target = corpus.chunks["gazette_1"]
    queries = {"tool": f"{target['title']}: {target['text']}", "original": target["text"]}
    for vector, query in queries.items():
        for search_type in ("vector", "hybrid"):
            response = await service.retrieve(backends, None, SearchRequest(
                query=query, type=search_type, vector=vector, limit=3, tag_uuids=[], positive=False, automatic=False))
            assert str(response.results[0].id) == target["id"], (vector, search_type)
            assert response.vector == vector


#######################################
# Resuming, failures, refused targets #
#######################################

async def test_an_interrupted_run_is_continued_by_the_next(tool_store, make_pipeline, embed_calls):
    await create_test_collection(tool_store, collection_name=TEST_COLLECTION)

    await make_pipeline(max_records=4).run_async()
    assert sum(v is not None for v in (await tool_vectors(tool_store)).values()) == 4
    await make_pipeline().run_async()
    filled = await tool_vectors(tool_store)
    calls_before_last_run = len(embed_calls)
    await make_pipeline().run_async()

    assert len(filled) == 10 and all(v is not None for v in filled.values())
    assert sum(len(c) for c in embed_calls) == 10   # every record embedded once
    assert len(embed_calls) == calls_before_last_run  # a complete collection makes no requests


async def test_a_failed_write_stops_the_run_and_keeps_the_written_vectors(tool_store, make_pipeline, fail_writes,
                                                                        monkeypatch):
    await create_test_collection(tool_store, collection_name=TEST_COLLECTION)
    failing = sorted(await tool_vectors(tool_store))[0]
    attempts = fail_writes("update", [failing])

    with pytest.raises(RuntimeError, match="injected write failure"):
        await make_pipeline().run_async()

    assert len(attempts) == 2                          # the first try and max_retries=1 retry
    assert (await tool_vectors(tool_store))[failing] is None
    monkeypatch.undo()                                  # the store accepts writes again
    await make_pipeline().run_async()
    assert all(v is not None for v in (await tool_vectors(tool_store)).values())


async def test_collections_the_tool_cannot_fill_are_refused(tool_store, make_pipeline):
    # The legacy unnamed vector can only be created through the deprecated argument.
    with pytest.warns(DeprecationWarning):
        await tool_store.collections.create(f"{TEST_COLLECTION}Legacy",
                                            properties=[Property(name="text", data_type=DataType.TEXT)],
                                            vectorizer_config=Configure.Vectorizer.none())
    await create_test_collection(tool_store, collection_name=TEST_COLLECTION)

    with pytest.raises(ValueError, match="does not exist"):
        await make_pipeline(collection=f"{TEST_COLLECTION}Missing").run_async()
    with pytest.raises(ValueError, match="legacy unnamed vector"):
        await make_pipeline(collection=f"{TEST_COLLECTION}Legacy").run_async()
    with pytest.raises(ValueError, match="create_vector is disabled"):
        await make_pipeline(create_vector=False).run_async()
    config = await tool_store.collections.get(TEST_COLLECTION).config.get()
    assert set(config.vector_config) == {"default"}


async def test_the_test_collection_is_replaced_only_when_forced(tool_store):
    await create_test_collection(tool_store, collection_name=TEST_COLLECTION)
    collection = tool_store.collections.get(TEST_COLLECTION)
    await collection.data.insert({"title": "kept", "text": "added after creation", "language": "ces"})

    with pytest.raises(ValueError, match="already exists"):
        await create_test_collection(tool_store, collection_name=TEST_COLLECTION)
    assert (await collection.aggregate.over_all(total_count=True)).total_count == 11

    await create_test_collection(tool_store, replace=True, collection_name=TEST_COLLECTION)
    assert (await collection.aggregate.over_all(total_count=True)).total_count == 10
