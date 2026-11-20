"""The search benchmark store's pure parts (#726): ownership decisions, the token file, the
container's arguments, document templates and the embedding cache, search options. Against a
real Weaviate: ``integration/test_search_benchmark_store.py``."""
import json
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from weaviate.classes.query import HybridFusion

from semant_demo.adapters.weaviate.search import ChunkSearchRepository
from semant_demo.benchmarks.search_relevance import container, schema
from semant_demo.benchmarks.search_relevance.embeddings import BatchEmbeddings
from semant_demo.benchmarks.search_relevance.search import BenchmarkChunkSearch
from semant_demo.benchmarks.search_relevance.embedding_cache import (
    EmbeddingCache, TemplateError, check_template, input_hash, render, valid_embedding)
from semant_demo.benchmarks.search_relevance.store import (
    StoreNotOwned, bm25_properties, claim_decision, hit_score, read_or_create_token, token_sha256)
from semant_demo.benchmarks.search_relevance.store_api import StoreSpec
from semant_demo.config import Config
from semant_demo.features.search.schemas import ChunkQuery, SearchType

# ---- ownership ----------------------------------------------------------------------------

TOKEN = token_sha256("mine")


def test_an_instance_without_collections_is_claimed():
    assert claim_decision(set(), None, TOKEN) == "claim"


def test_an_instance_with_the_marker_and_token_is_owned():
    assert claim_decision({schema.MARKER, "Chunks"}, TOKEN, TOKEN) == "owned"


@pytest.mark.parametrize("owner", [None, token_sha256("theirs")])
def test_a_marker_without_the_token_is_refused(owner):
    with pytest.raises(StoreNotOwned, match="another benchmark store"):
        claim_decision({schema.MARKER}, owner, TOKEN)


def test_data_without_the_marker_is_refused_also_beside_tolerated_collections():
    with pytest.raises(StoreNotOwned, match="Chunks"):
        claim_decision({"Chunks", "Documents"}, None, TOKEN)
    with pytest.raises(StoreNotOwned, match="Chunks"):
        claim_decision({"SemantTestStoreMarker", "Chunks"}, None, TOKEN, tolerated={"SemantTestStoreMarker"})
    with pytest.raises(StoreNotOwned, match="SemantTestStoreMarker"):
        claim_decision({"SemantTestStoreMarker"}, None, TOKEN)
    assert claim_decision({"SemantTestStoreMarker"}, None, TOKEN, tolerated={"SemantTestStoreMarker"}) == "claim"


def test_the_token_file_is_created_private_and_then_reused(tmp_path):
    path = tmp_path / "config" / "token"
    token = read_or_create_token(path)

    assert len(token) == 64 and path.stat().st_mode & 0o777 == 0o600
    assert read_or_create_token(path) == token
    path.write_text("")
    with pytest.raises(StoreNotOwned, match="empty"):
        read_or_create_token(path)


# ---- container ----------------------------------------------------------------------------

SPEC = StoreSpec(name="bench", weaviate_image="weaviate:1.40.1")


def test_a_new_container_publishes_loopback_ports_and_mounts_the_labelled_volume():
    args = container.run_arguments(SPEC, 18080, 15051)

    assert args[:3] == ["docker", "run", "-d"]
    assert "127.0.0.1:18080:8080" in args and "127.0.0.1:15051:50051" in args
    assert "type=volume,source=bench-data,target=/var/lib/weaviate" in args
    assert "org.semant.purpose=search-benchmark" in args
    assert "weaviate:1.40.1" in args


def inspected(labels=None, image="weaviate:1.40.1", host_ip="127.0.0.1", rest="18080", running=True) -> dict:
    return {"Config": {"Labels": {"org.semant.purpose": "search-benchmark"} if labels is None else labels,
                       "Image": image},
            "HostConfig": {"PortBindings": {"8080/tcp": [{"HostIp": host_ip, "HostPort": rest}],
                                            "50051/tcp": [{"HostIp": host_ip, "HostPort": "15051"}]}},
            "State": {"Running": running}}


def test_an_existing_benchmark_container_is_reused_on_its_ports():
    assert container.check_existing(SPEC, inspected()) == container.Endpoint("127.0.0.1", 18080, 15051)


@pytest.mark.parametrize("changes, message", [
    ({"labels": {}}, "without the label"),
    ({"image": "weaviate:1.34.0"}, "runs weaviate:1.34.0"),
    ({"host_ip": "0.0.0.0"}, "beyond loopback"),
])
def test_another_container_of_the_name_is_refused(changes, message):
    with pytest.raises(container.ContainerError, match=message):
        container.check_existing(SPEC, inspected(**changes))


def test_an_existing_container_on_other_ports_than_the_spec_is_refused():
    with pytest.raises(container.ContainerError, match="REST on 18080, not 9999"):
        container.check_existing(StoreSpec(name="bench", weaviate_image="weaviate:1.40.1", rest_port=9999),
                                 inspected())


def test_free_ports_are_loopback_ports():
    assert 0 < container.free_port() < 65536


# ---- document embeddings ------------------------------------------------------------------

def test_templates_use_the_chunk_text_and_title():
    check_template("{title}\n{text}")
    assert render("{title}: {text}", "Body", "Head") == "Head: Body"
    assert render("{title}: {text}", "Body", None) == ": Body"


@pytest.mark.parametrize("template", ["{title}", "{text} {document}", "{} {text}", "{text", "{0}"])
def test_templates_with_other_fields_or_without_the_text_are_refused(template):
    with pytest.raises(TemplateError):
        check_template(template)


def test_embeddings_must_be_finite_numbers_of_the_dimensions():
    assert valid_embedding([0.5, 1], 2) and valid_embedding([0.5], None)
    assert not valid_embedding([], None)
    assert not valid_embedding([0.5], 2)
    assert not valid_embedding([float("nan")], None)
    assert not valid_embedding([True], None)
    assert not valid_embedding("0.5", None)


def test_the_cache_keeps_embeddings_per_model_template_and_dimensions(tmp_path):
    cache = EmbeddingCache(tmp_path, "m", "{text}", None)
    key = input_hash("Body")
    cache.put_many({key: [0.5, 0.25]})

    again = EmbeddingCache(tmp_path, "m", "{text}", None)
    assert again.get(key) == [0.5, 0.25] and len(again) == 1
    assert EmbeddingCache(tmp_path, "other", "{text}", None).get(key) is None
    assert EmbeddingCache(tmp_path, "m", "{title} {text}", None).get(key) is None
    assert EmbeddingCache(tmp_path, "m", "{text}", 2).get(key) is None
    assert json.loads((tmp_path / f"{cache.namespace}.json").read_text()) == {
        "model": "m", "dimensions": None, "document_template": "{text}"}


def test_a_line_cut_off_by_an_interrupted_write_is_ignored_and_not_continued(tmp_path):
    cache = EmbeddingCache(tmp_path, "m", "{text}", None)
    cache.put_many({"a": [1.0]})
    with cache.path.open("a") as f:
        f.write('{"sha256": "b", "embed')

    reread = EmbeddingCache(tmp_path, "m", "{text}", None)
    assert reread.get("a") == [1.0] and reread.get("b") is None
    reread.put_many({"c": [2.0]})
    assert EmbeddingCache(tmp_path, "m", "{text}", None).get("c") == [2.0]


# ---- search options -----------------------------------------------------------------------

def test_bm25_properties_carry_their_boosts():
    assert bm25_properties(None) is None
    assert bm25_properties({"text": 1.0, "title": 2.5, "language": 2}) == ["text", "title^2.5", "language^2"]


def test_scores_are_weaviate_scores_or_the_cosine_similarity():
    assert hit_score(SearchType.text, (0.75, 0.25)) == 0.75
    assert hit_score(SearchType.hybrid, (0.75, 0.25)) == 0.75
    assert hit_score(SearchType.vector, (0.0, 0.1)) == pytest.approx(0.9)
    assert hit_score(SearchType.vector, (None, None)) is None
    assert hit_score(SearchType.text, None) is None  # not recorded


class RecordingQuery:
    def __init__(self, objects=()):
        self.calls = []
        self.objects = list(objects)

    async def _record(self, kind, kwargs):
        self.calls.append((kind, kwargs))
        return SimpleNamespace(objects=self.objects)

    async def bm25(self, **kwargs):
        return await self._record("bm25", kwargs)

    async def near_vector(self, **kwargs):
        return await self._record("near_vector", kwargs)

    async def hybrid(self, **kwargs):
        return await self._record("hybrid", kwargs)


def recording_client(query: RecordingQuery):
    collection = SimpleNamespace(query=query)
    return SimpleNamespace(collections=SimpleNamespace(get=lambda name: collection))


QUERIES = [ChunkQuery(text="q", mode=SearchType.text, limit=3),
           ChunkQuery(text="q", mode=SearchType.vector, limit=3, vector=[1.0], target_vector="v"),
           ChunkQuery(text="q", mode=SearchType.hybrid, limit=3, alpha=0.5, vector=[1.0], target_vector="v")]
BENCHMARK_ONLY = {"return_metadata", "fusion_type", "query_properties"}


async def test_with_default_settings_the_benchmark_search_queries_as_the_application():
    # The guard of the subclass's dependency on ChunkSearchRepository._ranked: when the application
    # changes how it ranks (another argument, filter or call), this fails.
    names = Config(environ={}).collectionNames
    application, benchmark = RecordingQuery(), RecordingQuery()
    for query in QUERIES:
        await ChunkSearchRepository(recording_client(application), names).ranked_ids(query)
        await BenchmarkChunkSearch(recording_client(benchmark), names).ranked_ids(query)
    assert [kind for kind, _ in application.calls] == [kind for kind, _ in benchmark.calls]
    for (_, app_kwargs), (_, bench_kwargs) in zip(application.calls, benchmark.calls):
        assert set(bench_kwargs) - set(app_kwargs) <= BENCHMARK_ONLY
        assert {k: v for k, v in bench_kwargs.items() if k not in BENCHMARK_ONLY} == app_kwargs
        assert bench_kwargs.get("fusion_type") is None and bench_kwargs.get("query_properties") is None


async def test_the_benchmark_search_sets_fusion_and_bm25_properties_and_records_scores():
    hit = SimpleNamespace(uuid=UUID("5e3b0000-0000-4000-8000-000000000001"),
                          metadata=SimpleNamespace(score=1.5, distance=None))
    query = RecordingQuery([hit])
    search = BenchmarkChunkSearch(recording_client(query), Config(environ={}).collectionNames,
                                  fusion=HybridFusion.RANKED, query_properties=["text", "title^2"])
    assert await search.ranked_ids(QUERIES[0]) == [hit.uuid]
    await search.ranked_ids(QUERIES[2])
    [(_, bm25), (_, hybrid)] = query.calls
    assert bm25["query_properties"] == hybrid["query_properties"] == ["text", "title^2"]
    assert hybrid["fusion_type"] == HybridFusion.RANKED and bm25["return_metadata"] is not None
    assert search.scores == {hit.uuid: (1.5, None)}


def test_the_applications_search_has_no_benchmark_options():
    # The application's class stays as on main: the benchmark sets its options in its subclass.
    repository = ChunkSearchRepository(None, Config(environ={}).collectionNames)
    assert not hasattr(repository, "scores") and not hasattr(repository, "fusion")


class EmbeddingServer(httpx.AsyncBaseTransport):
    """An OpenAI-compatible ``/embeddings`` answering in reverse input order (with indexes)."""

    def __init__(self, count_offset: int = 0):
        self.bodies, self.headers, self.count_offset = [], [], count_offset

    async def handle_async_request(self, request):
        body = json.loads(request.content)
        self.bodies.append(body)
        self.headers.append(dict(request.headers))
        data = [{"index": i, "embedding": [float(len(text))]} for i, text in enumerate(body["input"])]
        data = list(reversed(data))[:len(data) + self.count_offset]
        return httpx.Response(200, json={"data": data}, request=request)


async def test_batch_embeddings_keep_the_input_order_and_send_the_model_settings():
    server = EmbeddingServer()
    client = BatchEmbeddings("http://e/v1/", "m", api_key="k", dimensions=8, transport=server)
    assert await client.embed_documents(["a", "bbb", "cc"]) == [[1.0], [3.0], [2.0]]
    assert server.bodies == [{"model": "m", "input": ["a", "bbb", "cc"], "encoding_format": "float", "dimensions": 8}]
    assert server.headers[0]["authorization"] == "Bearer k"
    assert await client.embed_documents([]) == [] and len(server.bodies) == 1


async def test_batch_embeddings_refuse_a_wrong_number_of_embeddings():
    client = BatchEmbeddings("http://e/v1", "m", transport=EmbeddingServer(count_offset=-1))
    with pytest.raises(ValueError, match="expected 2 embeddings, got 1"):
        await client.embed_documents(["a", "b"])
