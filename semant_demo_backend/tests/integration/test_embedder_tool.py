"""The offline embedder (data_tools/embedder, #192) against the test-owned Weaviate.

The real pipeline and ``VLLMEmbedder`` run; the OpenAI-compatible endpoint is the fake
provider (``/openai/v1/embeddings``: ``second_embedding`` of each input). Covers named
vector creation, preservation of what objects already hold, resumability, write
failures, refused collections, the guarded test collection and querying a filled vector
through Search (#217), and the selection by ``haveVector`` (#816): only the records whose
list lacks the vector's name are read in full, the name is added with the vector, and a
record already storing the vector gets only the name. The seeded chunks list both of their
vectors, as the deployed chunks do since #805. Collections other than the application's
are named ``EmbedderToolTest*`` and deleted after each test.
"""
import asyncio
import json
import socket
import sys
from pathlib import Path

import httpx
import pytest
import yaml
from httpx import ASGITransport
from openai import AsyncOpenAI
from weaviate.classes.config import Configure, DataType, Property, Tokenization
from weaviate.classes.query import QueryReference

from semant_demo.adapters.weaviate.search import ChunkSearchRepository
from semant_demo.adapters.weaviate.spans import SpanRepository
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.bootstrap import load_search_vectors
from semant_demo.config import Config
from semant_demo.features.search import service
from semant_demo.features.search.schemas import SearchRequest
from semant_demo.features.search.service import SearchBackends
from semant_demo.maintenance import chunk_ingest
from tests.fake_providers import create_fake_provider_app
from tests.fakes import SECOND_VECTOR, second_embedding

sys.path.insert(0, str(Path(__file__).parents[3] / "data_tools" / "embedder"))
from semantembedder.db import HAVE_VECTOR, create_test_collection  # noqa: E402
from semantembedder.pipeline import EmbeddingPipeline  # noqa: E402

pytestmark = pytest.mark.integration

TEST_COLLECTION = "EmbedderToolTest"
TOOL_VECTOR = "tool_vector"
CHUNK_REFS = ["document", "userCollection"]
SEEDED_VECTORS = ["default", SECOND_VECTOR]
HAVE_VECTOR_PROPERTY = Property(name=HAVE_VECTOR, data_type=DataType.TEXT_ARRAY, tokenization=Tokenization.FIELD,
                                index_filterable=True, index_searchable=False)


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
        # One PATCH of the named vector and haveVector: the other properties, references and vectors are
        # unchanged, and the name is added to the listed ones.
        assert old["properties"][HAVE_VECTOR] == SEEDED_VECTORS
        assert new["properties"].pop(HAVE_VECTOR) == [*SEEDED_VECTORS, TOOL_VECTOR]
        old["properties"].pop(HAVE_VECTOR)
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
    spans = SpanRepository(tool_store, names)
    backends = SearchBackends(ChunkSearchRepository(tool_store, names), UserCollectionRepository(tool_store, names, spans),
                              vectors)
    target = corpus.chunks["gazette_1"]
    queries = {"tool": f"{target['title']}: {target['text']}", "original": target["text"]}
    for vector, query in queries.items():
        for search_type in ("vector", "hybrid"):
            response = await service.retrieve(backends, None, SearchRequest(
                query=query, type=search_type, vector=vector, limit=3))
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


async def test_records_with_an_empty_input_beyond_max_excluded_are_read_with_the_cursor(
        tool_store, make_pipeline, embed_calls):
    # Empty inputs stay selected and are left out by id; past max_excluded the run reads the rest with
    # the cursor and still embeds every other record exactly once.
    await create_test_collection(tool_store, collection_name=TEST_COLLECTION)
    collection = tool_store.collections.get(TEST_COLLECTION)
    for i in range(4):
        await collection.data.insert({"title": f"empty {i}", "text": "", "language": "ces"})

    stats = await make_pipeline(max_excluded=2).run_async()

    assert (stats.selected, stats.embedded, stats.empty) == (14, 10, 4) and stats.scanned == 14
    assert sum(len(c) for c in embed_calls) == 10   # every record embedded once
    vectors = await tool_vectors(tool_store)
    assert sum(v is not None for v in vectors.values()) == 10
    again = await make_pipeline().run_async()       # within max_excluded: no cursor
    assert (again.selected, again.embedded, again.empty, again.scanned) == (4, 0, 4, 0)


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


@pytest.mark.parametrize("declared", [None, Property(name=HAVE_VECTOR, data_type=DataType.TEXT_ARRAY)],
                         ids=["missing", "word-tokenized"])
async def test_a_collection_without_the_expected_have_vector_is_refused_before_any_change(
        tool_store, make_pipeline, embed_calls, declared):
    # Without the declared list a write would let Weaviate's auto-schema create it otherwise (#816).
    name = f"{TEST_COLLECTION}NoList"
    await tool_store.collections.create(name, properties=[Property(name="text", data_type=DataType.TEXT),
                                                          *([declared] if declared else [])],
                                        vector_config=Configure.Vectors.self_provided(name="default"))
    await tool_store.collections.get(name).data.insert({"text": "nečíst"})

    with pytest.raises(ValueError, match=HAVE_VECTOR):
        await make_pipeline(collection=name).run_async()
    stats = await make_pipeline(collection=name).check_async()
    assert HAVE_VECTOR in stats.refused and (stats.selected, stats.scanned) == (0, 0)
    config = await tool_store.collections.get(name).config.get()
    assert set(config.vector_config) == {"default"} and embed_calls == []
    assert [p.name for p in config.properties] == ["text", *([HAVE_VECTOR] if declared else [])]


def unused_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_an_unreachable_grpc_port_stops_a_run_before_any_change(tool_store, make_pipeline, embed_calls):
    # The client skips its start-up checks (no version lookup on pypi.org, #798), so the run reads
    # one object over gRPC before it creates the vector.
    await create_test_collection(tool_store, collection_name=TEST_COLLECTION)
    port = unused_port()

    with pytest.raises(ConnectionError, match=f"gRPC at .*:{port}"):
        await make_pipeline(weaviate_grpc_port=port).run_async()
    with pytest.raises(ConnectionError, match=f"gRPC at .*:{port}"):
        await make_pipeline(weaviate_grpc_port=port).check_async()
    assert set((await tool_store.collections.get(TEST_COLLECTION).config.get()).vector_config) == {"default"}
    assert embed_calls == []


async def test_the_test_collection_is_replaced_only_when_forced(tool_store):
    await create_test_collection(tool_store, collection_name=TEST_COLLECTION)
    collection = tool_store.collections.get(TEST_COLLECTION)
    await collection.data.insert({"title": "kept", "text": "added after creation", "language": "ces"})

    with pytest.raises(ValueError, match="already exists"):
        await create_test_collection(tool_store, collection_name=TEST_COLLECTION)
    assert (await collection.aggregate.over_all(total_count=True)).total_count == 11

    await create_test_collection(tool_store, replace=True, collection_name=TEST_COLLECTION)
    assert (await collection.aggregate.over_all(total_count=True)).total_count == 10


@pytest.mark.parametrize("name", ["Qwen3-Embedding-0-6B", "3vector", ""])
async def test_a_vector_name_graphql_cannot_use_is_refused_before_any_write(tool_store, make_pipeline, name):
    # Weaviate 1.34 and 1.40 accept such a named vector but can then build no GraphQL schema (#385).
    await create_test_collection(tool_store, collection_name=TEST_COLLECTION)

    with pytest.raises(Exception, match="vector_name"):
        make_pipeline(vector_name=name)
    assert set((await tool_store.collections.get(TEST_COLLECTION).config.get()).vector_config) == {"default"}


##############
# Check mode #
##############

async def test_a_check_counts_what_a_run_would_embed_and_changes_nothing(tool_store, make_pipeline, embed_calls,
                                                                         monkeypatch):
    await create_test_collection(tool_store, collection_name=TEST_COLLECTION)
    collection = tool_store.collections.get(TEST_COLLECTION)
    await collection.data.insert({"title": "empty", "text": "", "language": "ces"})

    # Before the first run the vector does not exist: the check neither creates it nor reads vectors.
    stats = await make_pipeline().check_async()
    assert (stats.selected, stats.missing, stats.already_stored, stats.empty, stats.scanned) == (11, 10, 0, 1, 0)
    assert set((await collection.config.get()).vector_config) == {"default"}
    # Each page read is left out of the next query; beyond max_excluded the rest is read with the cursor,
    # whose records are not kept (it reads none twice): two pages of 3, not all 11 ids.
    kept = []
    scan = EmbeddingPipeline._scan

    def spy(self, collection, excluded, *args):
        kept.append(excluded)
        return scan(self, collection, excluded, *args)
    monkeypatch.setattr(EmbeddingPipeline, "_scan", spy)
    stats = await make_pipeline(max_excluded=4).check_async()
    assert (stats.selected, stats.missing, stats.already_stored, stats.empty, stats.scanned) == (11, 10, 0, 1, 11)
    assert [len(e) for e in kept] == [6]
    monkeypatch.undo()

    await make_pipeline(max_records=4).run_async()
    filled = await tool_vectors(tool_store)
    calls = len(embed_calls)

    # The four embedded records list the name now and are not read. The empty one stays selected.
    stats = await make_pipeline().check_async()
    assert (stats.selected, stats.missing, stats.already_stored, stats.empty, stats.scanned) == (7, 6, 0, 1, 0)
    assert stats.embedded == 0 and len(embed_calls) == calls     # no embedding requests
    assert await tool_vectors(tool_store) == filled               # no writes


async def test_the_check_exit_code_says_whether_records_are_left(tool_store, make_pipeline, tmp_path, monkeypatch,
                                                                 capsys):
    from semantembedder.__main__ import main
    await create_test_collection(tool_store, collection_name=TEST_COLLECTION)

    def check_cli(**settings) -> int:
        make_pipeline(**settings)
        config = max(tmp_path.glob("embedder-*.yaml"), key=lambda p: int(p.stem.split("-")[1]))
        monkeypatch.setattr(sys, "argv", ["semantembedder", str(config), "--check"])
        with pytest.raises(SystemExit) as exit_:
            main()
        return exit_.value.code

    assert await asyncio.to_thread(check_cli) == 1
    assert "10 a run would embed" in capsys.readouterr().out
    await make_pipeline().run_async()
    assert await asyncio.to_thread(check_cli) == 0
    assert await asyncio.to_thread(check_cli, collection=f"{TEST_COLLECTION}Missing") == 2
    assert "does not exist" in capsys.readouterr().err


async def test_a_check_fails_when_the_run_would_be_refused_even_with_nothing_to_embed(tool_store, make_pipeline,
                                                                                      tmp_path, monkeypatch, capsys):
    from semantembedder.__main__ import main
    # A run refuses a missing vector with create_vector disabled before reading anything, so the check
    # must not report "nothing left" (exit 0) for an empty collection or 1 for a populated one, and it
    # returns at once (#642): the answer is known before the scan.
    await tool_store.collections.create(f"{TEST_COLLECTION}Empty",
                                        properties=[Property(name="text", data_type=DataType.TEXT),
                                                    HAVE_VECTOR_PROPERTY],
                                        vector_config=Configure.Vectors.self_provided(name="default"))
    await create_test_collection(tool_store, collection_name=TEST_COLLECTION)

    def no_select(*args, **kwargs):
        raise AssertionError("a refused check must not read the records")
    monkeypatch.setattr(EmbeddingPipeline, "_select", no_select)

    def check_cli(**settings) -> int:
        make_pipeline(create_vector=False, **settings)
        config = max(tmp_path.glob("embedder-*.yaml"), key=lambda p: int(p.stem.split("-")[1]))
        monkeypatch.setattr(sys, "argv", ["semantembedder", str(config), "--check"])
        with pytest.raises(SystemExit) as exit_:
            main()
        return exit_.value.code

    for collection in (f"{TEST_COLLECTION}Empty", TEST_COLLECTION):
        stats = await make_pipeline(create_vector=False, collection=collection).check_async()
        assert (stats.selected, stats.missing) == (0, 0) and "create_vector is disabled" in stats.refused
    for collection in (f"{TEST_COLLECTION}Empty", TEST_COLLECTION):
        assert await asyncio.to_thread(check_cli, collection=collection) == 2
        assert "A run would be refused" in capsys.readouterr().err
    with pytest.raises(ValueError, match="create_vector is disabled"):
        await make_pipeline(create_vector=False, collection=f"{TEST_COLLECTION}Empty").run_async()
    assert set((await tool_store.collections.get(TEST_COLLECTION).config.get()).vector_config) == {"default"}


##########################
# Selection by haveVector #
##########################

async def listed(client, collection) -> dict[str, list[str] | None]:
    res = await client.collections.get(collection).query.fetch_objects(limit=200, return_properties=[HAVE_VECTOR])
    return {str(o.uuid): o.properties.get(HAVE_VECTOR) for o in res.objects}


async def test_a_run_reads_only_the_records_lacking_the_name_and_lists_a_stored_vector_without_embedding(
        tool_store, collection_names, corpus, make_pipeline, embed_calls):
    chunks_name = collection_names.chunks_collection_name
    chunks = tool_store.collections.get(chunks_name)
    before = await snapshot_chunks(tool_store, collection_names)

    # The fake provider's embeddings have SECOND_VECTOR's dimension, so that is the vector filled here.
    # Every seeded chunk lists it: nothing is selected, read or written.
    stats = await make_pipeline(collection=chunks_name, vector_name=SECOND_VECTOR, create_vector=False).run_async()
    assert (stats.selected, stats.embedded, stats.already_stored, stats.scanned) == (0, 0, 0, 0)
    assert await snapshot_chunks(tool_store, collection_names) == before

    # Chunks storing the vector without listing it (empty, null and another name) get only the name.
    ids = [corpus.chunks[key]["id"] for key in ("letters_1", "letters_2", "gazette_1")]
    for chunk_id, value in zip(ids, ([], None, ["default"])):
        await chunks.data.update(uuid=chunk_id, properties={HAVE_VECTOR: value})
    check = await make_pipeline(collection=chunks_name, vector_name=SECOND_VECTOR, create_vector=False).check_async()
    assert (check.selected, check.missing, check.already_stored, check.scanned) == (3, 0, 3, 0)
    stats = await make_pipeline(collection=chunks_name, vector_name=SECOND_VECTOR, create_vector=False).run_async()
    assert (stats.selected, stats.embedded, stats.already_stored, stats.scanned) == (3, 0, 3, 0)
    assert embed_calls == []
    lists = await listed(tool_store, chunks_name)
    assert [lists[str(i)] for i in ids] == [[SECOND_VECTOR], [SECOND_VECTOR], ["default", SECOND_VECTOR]]
    after = await snapshot_chunks(tool_store, collection_names)
    for chunk_id, old in before.items():
        new = after[chunk_id]
        new["properties"].pop(HAVE_VECTOR), old["properties"].pop(HAVE_VECTOR)
        assert new == old       # the vectors, other properties and references are kept


async def test_a_chunk_inserted_by_chunk_ingest_is_selected_and_embedded(tool_store, collection_names, corpus,
                                                                       make_pipeline, embed_calls, tmp_path):
    # chunk_ingest writes no haveVector (#816): an absent list is selected like an empty one.
    document = "5e3a0000-0000-4000-8000-0000000d8161"
    texts = ["Nový dokument, první úsek.", "Druhý úsek nového dokumentu."]
    path = tmp_path / "new.jsonl"
    path.write_text("".join(json.dumps({"id": f"5e3a0000-0000-4000-8000-0000000c816{i}", "document": document,
                                        "order": i, "text": text, "language": "ces"}, ensure_ascii=False) + "\n"
                            for i, text in enumerate(texts)), encoding="utf-8")
    result = await chunk_ingest.run(tool_store, collection_names, [path], checkpoint=tmp_path / "ingest.json",
                                    endpoint="test", write_=True, backup={"offline_backup": "test"},
                                    progress=lambda *_: None)
    assert chunk_ingest.exit_code(result) == 0 and result["counts"]["chunks_inserted"] == 2
    chunks_name = collection_names.chunks_collection_name
    new_ids = {f"5e3a0000-0000-4000-8000-0000000c816{i}" for i in range(2)}
    assert {i: v for i, v in (await listed(tool_store, chunks_name)).items() if i in new_ids} == dict.fromkeys(new_ids)

    stats = await make_pipeline(collection=chunks_name, vector_name=SECOND_VECTOR, create_vector=False).run_async()

    assert (stats.selected, stats.embedded, stats.already_stored, stats.scanned) == (2, 2, 0, 0)
    assert sorted(t for call in embed_calls for t in call) == sorted(texts)
    lists = await listed(tool_store, chunks_name)
    assert all(lists[i] == [SECOND_VECTOR] for i in new_ids)
    assert all(lists[c["id"]] == SEEDED_VECTORS for c in corpus.chunks.values())
    vectors = await tool_store.collections.get(chunks_name).query.fetch_objects(
        limit=200, include_vector=[SECOND_VECTOR], return_properties=[])
    stored = {str(o.uuid): o.vector[SECOND_VECTOR] for o in vectors.objects if str(o.uuid) in new_ids}
    for i, text in enumerate(texts):
        assert stored[f"5e3a0000-0000-4000-8000-0000000c816{i}"] == pytest.approx(second_embedding(text))
