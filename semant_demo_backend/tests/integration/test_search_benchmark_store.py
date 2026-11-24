"""The search benchmark's store (#726, #727) against the run's throwaway Weaviate.

The instance belongs to the test run (``tests/weaviate_store.claim_store``) and already holds the
tests' marker; each test first drops every other collection, so the benchmark store sees an
instance holding only that marker, which it is told to tolerate when claiming. Embeddings come
from the fake providers (``/openai/v1/embeddings``, 8-dimensional) through an injected transport.
"""
import json
import shutil
import subprocess
import uuid
from dataclasses import replace

import httpx
import pytest
from weaviate.classes.config import DataType, Property
from weaviate.classes.query import QueryReference

from semant_demo.benchmarks.search_relevance import schema
from semant_demo.benchmarks.search_relevance.contracts import RunConfiguration, VectorSpec, write_dataset
from semant_demo.benchmarks.search_relevance.store import (
    StoreDatasetMismatch, StoreNotOwned, StoreVectorMismatch, open_store)
from semant_demo.benchmarks.search_relevance.store_api import EmbeddingEndpoint, StoreSpec
from tests import search_benchmark_fixture as fixture
from tests.corpus import load_corpus
from tests.fake_providers import create_fake_provider_app
from tests.weaviate_store import MARKER_COLLECTION, claim_store

pytestmark = pytest.mark.integration

ENDPOINT = EmbeddingEndpoint(base_url="http://fake-provider/openai/v1", batch_size=4, concurrency=2)
VECTOR = VectorSpec(id="fake-small", model="fake-small", target_vector="fake_small")


async def _drop_all_but_the_tests_marker(client, token):
    await claim_store(client, token)  # the run owns the instance
    for name in (await client.collections.list_all(simple=True)):
        if name != MARKER_COLLECTION:
            await client.collections.delete(name)


@pytest.fixture
async def instance(weaviate_client, store_token):
    await _drop_all_but_the_tests_marker(weaviate_client, store_token)
    yield weaviate_client
    await _drop_all_but_the_tests_marker(weaviate_client, store_token)


class CountingTransport(httpx.AsyncBaseTransport):
    """The fake providers, counting embedding requests and texts; ``fail`` answers ``status``
    (500) for a request with an input containing it."""

    def __init__(self, fail: str | None = None, status: int = 500):
        self.inner = httpx.ASGITransport(app=create_fake_provider_app(load_corpus()))
        self.requests = 0
        self.texts: list[str] = []
        self.fail, self.status = fail, status

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests += 1
        self.texts.extend(body["input"])
        if self.fail and any(self.fail in text for text in body["input"]):
            return httpx.Response(self.status, request=request)
        return await self.inner.handle_async_request(request)


@pytest.fixture
def spec(store_endpoint, tmp_path):
    return StoreSpec(host=store_endpoint.host, rest_port=store_endpoint.rest_port,
                     grpc_port=store_endpoint.grpc_port, token_file=tmp_path / "token")


@pytest.fixture
def dataset(tmp_path):
    return fixture.build_dataset(tmp_path / "dataset")


async def _open(spec, transport=None):
    store = await open_store(spec, embedding_transport=transport or CountingTransport(),
                             tolerated_collections={MARKER_COLLECTION})
    store.retry_delay = 0.0
    return store


async def test_an_empty_instance_is_claimed_and_reopened_with_its_token_only(instance, spec, tmp_path):
    store = await _open(spec)
    await store.close()
    assert (spec.token_file.stat().st_mode & 0o777) == 0o600
    names = set(await instance.collections.list_all(simple=True))
    assert {schema.MARKER, "Chunks", "Documents", "UserCollection"} <= names
    marker = await instance.collections.get(schema.MARKER).query.fetch_objects()
    assert spec.token_file.read_text().strip() not in str([o.properties for o in marker.objects])

    store = await _open(spec)  # the same token: reused
    await store.close()
    with pytest.raises(StoreNotOwned, match="another benchmark store"):
        await _open(replace(spec, token_file=tmp_path / "other-token"))


async def test_an_instance_with_data_but_no_marker_is_refused(instance, spec):
    await instance.collections.create("Chunks", properties=[Property(name="text", data_type=DataType.TEXT)])

    with pytest.raises(StoreNotOwned, match="did not create.*Chunks"):
        await _open(spec)
    assert not await instance.collections.exists(schema.MARKER)


async def test_the_tests_marker_alone_makes_an_instance_non_empty_without_tolerating_it(instance, spec):
    with pytest.raises(StoreNotOwned, match=MARKER_COLLECTION):
        await open_store(spec)
    assert not await instance.collections.exists(schema.MARKER)


async def test_writes_are_refused_once_the_marker_is_gone(instance, spec, dataset):
    store = await _open(spec)
    try:
        await instance.collections.delete(schema.MARKER)
        with pytest.raises(StoreNotOwned, match="no .* marker"):
            await store.load(dataset)
    finally:
        await store.close()


async def test_a_dataset_is_loaded_once_with_its_ids_and_another_one_is_refused(instance, spec, dataset, tmp_path):
    store = await _open(spec)
    try:
        report = await store.load(dataset)
        assert (report.chunks_written, report.documents_written, report.already_loaded) == (9, 3, False)
        again = await store.load(dataset)
        assert (again.chunks_written, again.documents_written, again.already_loaded) == (0, 0, True)

        chunks = instance.collections.get("Chunks")
        stored = await chunks.query.fetch_object_by_id(fixture.chunk_id(4), return_references=[
            QueryReference(link_on="document", return_properties=["title"])])
        assert stored.properties["text"] == dataset.corpus[fixture.chunk_id(4)].text
        assert stored.properties["language"] == "eng" and stored.properties["yearIssued"] == 1901
        assert stored.properties["documentPublic"] is True  # anonymous search selects it (#793)
        assert stored.references["document"].objects[0].uuid == fixture.document_id(2)

        # The same corpus under another manifest (the generator's corpus-only dataset, then the
        # final one) is the same load; another version or another corpus is refused.
        same_corpus = write_dataset(tmp_path / "final", {**fixture.MANIFEST, "description": "final"},
                                    fixture.corpus(), fixture.INTENTS, fixture.queries(), fixture.qrels())
        assert same_corpus.manifest_sha256() != dataset.manifest_sha256()
        assert (await store.load(same_corpus)).already_loaded
        other = write_dataset(tmp_path / "other", {**fixture.MANIFEST, "version": "v1"}, fixture.corpus(),
                              fixture.INTENTS, fixture.queries(), fixture.qrels())
        with pytest.raises(StoreDatasetMismatch, match="holds dataset fixture v0"):
            await store.load(other)
        changed = fixture.corpus()
        changed[0] = changed[0].model_copy(update={"text": "Changed text."})
        recorpused = write_dataset(tmp_path / "changed", fixture.MANIFEST, changed, fixture.INTENTS,
                                   fixture.queries(), fixture.qrels())
        with pytest.raises(StoreDatasetMismatch, match="corpus"):
            await store.load(recorpused)
    finally:
        await store.close()


async def test_vectors_are_embedded_once_and_then_come_from_the_cache(instance, store_token, spec, dataset,
                                                                      tmp_path):
    cache = tmp_path / "cache"
    transport = CountingTransport()
    store = await _open(spec, transport)
    try:
        await store.load(dataset)
        report = await store.ensure_vector(VECTOR, ENDPOINT, cache)
        assert (report.embedded, report.from_cache, report.written, report.failed) == (9, 0, 9, {})
        assert transport.requests == 3  # batches of 4
        assert sorted(transport.texts) == sorted(c.text for c in dataset.corpus.values())

        again = await store.ensure_vector(VECTOR, ENDPOINT, cache)  # every chunk has the vector
        assert (again.embedded, again.from_cache, again.written) == (0, 0, 0) and transport.requests == 3

        with pytest.raises(StoreVectorMismatch, match="holds fake-small"):
            await store.ensure_vector(VECTOR.model_copy(update={"document_template": "{title}: {text}"}),
                                      ENDPOINT, cache)
    finally:
        await store.close()

    # A recreated store gets the same vectors from the cache, without embedding anything.
    await _drop_all_but_the_tests_marker(instance, store_token)
    transport = CountingTransport()
    store = await _open(spec, transport)
    try:
        await store.load(dataset)
        report = await store.ensure_vector(VECTOR, ENDPOINT, cache)
        assert (report.embedded, report.from_cache, report.written) == (0, 9, 9) and transport.requests == 0
        stored = await instance.collections.get("Chunks").query.fetch_object_by_id(
            fixture.chunk_id(1), include_vector=["fake_small"])
        assert len(stored.vector["fake_small"]) == 8
    finally:
        await store.close()


async def test_failed_embeddings_leave_their_chunks_without_a_vector(instance, spec, dataset, tmp_path):
    transport = CountingTransport(fail="Lhota")
    store = await _open(spec, transport)
    try:
        await store.load(dataset)
        report = await store.ensure_vector(VECTOR, replace(ENDPOINT, batch_size=1), tmp_path / "cache")
        # Chunks 1, 4 and 7 mention Lhota; each was tried four times.
        assert (report.embedded, report.written, report.failed) == (6, 6, {"HTTP500": 3})
        assert transport.requests == 6 + 3 * 4
        stored = await instance.collections.get("Chunks").query.fetch_object_by_id(
            fixture.chunk_id(1), include_vector=["fake_small"])
        assert not stored.vector.get("fake_small")

        transport.fail = None
        retried = await store.ensure_vector(VECTOR, replace(ENDPOINT, batch_size=1), tmp_path / "cache")
        assert (retried.embedded, retried.from_cache, retried.written, retried.failed) == (3, 0, 3, {})
    finally:
        await store.close()


async def test_a_text_refused_by_the_model_does_not_cost_its_batch_their_embeddings(instance, spec, dataset,
                                                                                    tmp_path):
    """A server refuses a whole request for one text (e.g. over the model's length, HTTP 400):
    the batch is resent one text at a time, so only the refused texts stay without a vector."""
    transport = CountingTransport(fail="Lhota", status=400)
    store = await _open(spec, transport)
    try:
        await store.load(dataset)
        report = await store.ensure_vector(VECTOR, ENDPOINT, tmp_path / "cache")  # batches of 4
        assert (report.embedded, report.written, report.failed) == (6, 6, {"HTTP400": 3})
    finally:
        await store.close()


@pytest.fixture
async def searchable(instance, spec, dataset, tmp_path):
    store = await _open(spec)
    await store.load(dataset)
    await store.ensure_vector(VECTOR, ENDPOINT, tmp_path / "cache")
    try:
        yield store
    finally:
        await store.close()


def configuration(mode, **fields):
    vector = None if mode == "text" else VECTOR
    return RunConfiguration(configuration_id=f"c-{mode}", mode=mode, vector=vector, **fields)


async def test_text_search_ranks_the_matching_chunks_with_scores(searchable):
    outcome = await searchable.searcher(configuration("text"), None)("Lhota")

    assert {hit for hit, _ in outcome.hits} == {fixture.chunk_id(1), fixture.chunk_id(4), fixture.chunk_id(7)}
    scores = [score for _, score in outcome.hits]
    assert all(s is not None for s in scores) and scores == sorted(scores, reverse=True)
    assert outcome.embed_ms is None and outcome.search_ms > 0


async def test_bm25_properties_and_boosts_choose_what_is_searched(searchable):
    by_title = await searchable.searcher(configuration("text", properties={"title": 2.5}), None)("Title 5")
    assert by_title.hits[0][0] == fixture.chunk_id(5)
    assert len(by_title.hits) == 6  # every chunk with a title matches "title"

    text_only = await searchable.searcher(configuration("text", properties={"text": 1.0}), None)("Title 5")
    assert text_only.hits == []


async def test_the_depth_bounds_the_ranking(searchable):
    outcome = await searchable.searcher(configuration("text", properties={"title": 1}, depth=2), None)("Title")
    assert len(outcome.hits) == 2


async def test_vector_search_finds_a_chunk_by_its_own_text(searchable, dataset):
    text = dataset.corpus[fixture.chunk_id(6)].text
    outcome = await searchable.searcher(configuration("vector", depth=3), ENDPOINT)(text)

    assert outcome.hits[0][0] == fixture.chunk_id(6) and len(outcome.hits) == 3
    assert outcome.hits[0][1] == pytest.approx(1.0, abs=1e-5)
    assert outcome.embed_ms is not None and outcome.embed_ms > 0


@pytest.mark.parametrize("fusion", ["relativeScore", "ranked"])
async def test_hybrid_search_with_either_fusion(searchable, dataset, fusion):
    text = dataset.corpus[fixture.chunk_id(6)].text
    search = searchable.searcher(configuration("hybrid", alpha=0.5, fusion=fusion, depth=5), ENDPOINT)
    outcome = await search(text)

    assert outcome.hits[0][0] == fixture.chunk_id(6)
    assert all(score is not None for _, score in outcome.hits)
    assert outcome.embed_ms is not None


async def test_a_query_prefix_changes_the_query_embedding_only(searchable, dataset):
    text = dataset.corpus[fixture.chunk_id(6)].text
    prefixed = VECTOR.model_copy(update={"query_prefix": "Query: "})
    outcome = await searchable.searcher(
        RunConfiguration(configuration_id="p", mode="vector", vector=prefixed, depth=9), ENDPOINT)(text)

    assert len(outcome.hits) == 9
    assert outcome.hits[0][1] < 0.999  # "Query: <text>" is embedded, not the chunk's own text


async def test_describe_reports_the_schema_vectors_and_dataset(searchable, dataset):
    described = await searchable.describe()

    assert described["weaviate_version"].startswith("1.")
    assert described["schema_version"] == schema.SCHEMA_VERSION
    chunks = described["collections"]["Chunks"]
    text = next(p for p in chunks["properties"] if p["name"] == "text")
    assert (text["data_type"], text["tokenization"], text["index_searchable"]) == ("text", "word", True)
    page = next(p for p in chunks["properties"] if p["name"] == "start_page_id")
    assert page["index_searchable"] is True  # BM25 searches the same properties as the application's schema
    assert chunks["vectors"]["fake_small"]["distance"] == "cosine"
    assert chunks["bm25"]["k1"] > 0
    assert described["vectors"]["fake_small"]["model"] == "fake-small"
    assert described["dataset"] == {"dataset_id": "fixture", "version": "v0",
                                    "corpus_sha256": dataset.manifest.files["corpus.jsonl"].sha256,
                                    "chunks": 9, "documents": 3, "state": "loaded"}
    assert "instance" in described and "127.0.0.1" not in json.dumps(described)


def _docker_image_available(image: str) -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode == 0


@pytest.mark.skipif(not _docker_image_available(StoreSpec().weaviate_image),
                    reason="needs Docker with the Weaviate image already pulled (no download)")
async def test_without_a_host_the_store_starts_and_reuses_its_own_container(tmp_path, dataset):
    spec = StoreSpec(name=f"semant-search-benchmark-test-{uuid.uuid4().hex[:8]}", token_file=tmp_path / "token")
    try:
        store = await open_store(spec)
        try:
            await store.load(dataset)
        finally:
            await store.close()
        store = await open_store(spec)  # reused, with its data
        try:
            assert (await store.load(dataset)).already_loaded
        finally:
            await store.close()
    finally:
        subprocess.run(["docker", "rm", "-f", spec.name], capture_output=True)
        subprocess.run(["docker", "volume", "rm", f"{spec.name}-data"], capture_output=True)
