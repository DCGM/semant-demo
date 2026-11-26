"""The search benchmark end to end (#712): the generator (#726) builds a dataset, pooling in the
real benchmark store; the runner (#727) searches it in the same store; the reports (#728) are
rendered from the saved run. Models and embeddings are the fake providers; the store is the
test run's throwaway Weaviate (tolerating the tests' own marker)."""
import json
from collections import Counter

import httpx
import pytest
import yaml

from semant_demo.adapters.llm.gateway import LlmGateway, ProviderSettings
from semant_demo.benchmarks.search_relevance import runner
from semant_demo.benchmarks.search_relevance.config import GeneratorConfig, load_config as load_generator_config
from semant_demo.benchmarks.search_relevance.contracts import load_dataset, load_run
from semant_demo.benchmarks.search_relevance.llm import UsageTotals
from semant_demo.benchmarks.search_relevance.pipeline import Generator, Resources
from semant_demo.benchmarks.search_relevance.report import build_report, load
from semant_demo.benchmarks.search_relevance.runner_config import load_config as load_runner_config
from semant_demo.benchmarks.search_relevance.store import open_store
from tests.corpus import load_corpus
from tests.fake_providers import create_fake_provider_app
from tests.test_search_benchmark_generator import FakeSource, catalog, source_chunks
from tests.weaviate_store import MARKER_COLLECTION, claim_store

pytestmark = pytest.mark.integration

VECTOR = {"model": "fake-small", "target_vector": "fake_small"}


async def _drop_all_but_the_tests_marker(client, token):
    await claim_store(client, token)  # the run owns the instance
    for name in await client.collections.list_all(simple=True):
        if name != MARKER_COLLECTION:
            await client.collections.delete(name)


@pytest.fixture
async def instance(weaviate_client, store_token):
    await _drop_all_but_the_tests_marker(weaviate_client, store_token)
    yield weaviate_client
    await _drop_all_but_the_tests_marker(weaviate_client, store_token)


@pytest.fixture
def providers():
    return httpx.ASGITransport(app=create_fake_provider_app(load_corpus()))


def store_opener(providers):
    async def opener(spec):
        store = await open_store(spec, embedding_transport=providers, tolerated_collections={MARKER_COLLECTION})
        store.retry_delay = 0.0
        return store
    return opener


def generator_config(store_endpoint, tmp_path) -> dict:
    store = {"name": "e2e", "host": store_endpoint.host, "rest_port": store_endpoint.rest_port,
             "grpc_port": store_endpoint.grpc_port, "token_file": str(tmp_path / "token")}
    return {
        "dataset_id": "e2e", "version": "v0", "models": catalog(),
        "sample": {"per_language": 6, "max_per_document": 2, "min_chars": 20, "context_fraction": 0},
        "intents": {"count": 6, "styles": {"keywords": 1, "question": 1}},
        "judge": {"per_language_fraction": 0.5},
        "pooling": {"methods": [
            {"id": "bm25", "mode": "text", "depth": 5},
            {"id": "vector", "mode": "vector", "depth": 5, "vector": {"id": "fake-small", **VECTOR},
             "endpoint": {"base_url": "http://fake/openai/v1"}}],
            "max_candidates_per_intent": 8, "store": store},
    }


def runner_config(store_endpoint, tmp_path, dataset_dir) -> dict:
    return {
        "dataset": str(dataset_dir), "runs_dir": str(tmp_path / "runs"), "cache_dir": str(tmp_path / "cache"),
        "store": {"name": "e2e", "host": store_endpoint.host, "rest_port": store_endpoint.rest_port,
                  "grpc_port": store_endpoint.grpc_port, "token_file": str(tmp_path / "token")},
        "endpoints": {"fake": {"base_url": "http://fake/openai/v1"}},
        "vectors": {"fake": {**VECTOR, "query_prefixes": {"plain": "", "instruct": "Query: "}}},
        "depth": 10,
        "grid": {"modes": ["text", "vector", "hybrid"], "alphas": [0.5], "fusions": ["relativeScore", "ranked"],
                 "query_prefixes": {"fake": ["plain", "instruct"]}},
        "budget": {"concurrency": 2},
    }


async def test_generate_run_and_report_on_a_real_benchmark_store(instance, store_endpoint, providers, tmp_path):
    # 1. The generator: sample (a fake source with ces/eng/deu chunks), intents and translations by
    #    the fake model, pooling in the real store, judging, writing the dataset.
    path = tmp_path / "generator.yaml"
    path.write_text(yaml.safe_dump(generator_config(store_endpoint, tmp_path)), encoding="utf-8")
    config, data, sha = load_generator_config(path)
    assert isinstance(config, GeneratorConfig)
    usage = UsageTotals()
    llm = LlmGateway(config.catalog(), ProviderSettings(ollama_base_url="http://fake/ollama", max_retries=0), usage,
                     http_transport=providers)
    source = FakeSource(source_chunks())

    async def open_source():
        return source
    generator = Generator(config, data, sha, tmp_path / "work", tmp_path / "dataset",
                          Resources(llm=llm, usage=usage, source=open_source, open_store=store_opener(providers)))
    assert await generator.run() == ["sample", "intents", "translate", "pool", "judge", "write"]

    dataset = load_dataset(tmp_path / "dataset")
    assert Counter(c.language for c in dataset.corpus.values()) == {"ces": 6, "eng": 6, "deu": 6}
    assert Counter(q.language for q in dataset.queries.values()) == {"ces": 6, "eng": 6, "deu": 6}
    methods = Counter(m for qrel in dataset.qrels for m in qrel.pooled_by)
    assert methods["source"] == len(dataset.intents) and methods["bm25"] and methods["vector"]
    assert dataset.manifest.store_schema["schema_version"] == "search-benchmark-store/2"
    recorded = json.dumps(dataset.manifest.model_dump(mode="json"))
    assert "127.0.0.1" not in recorded and "fake/" not in recorded and str(tmp_path) not in recorded

    # 2. The runner: the same store holds the corpus already (the final dataset has the
    #    generator's corpus) and the pooling vector, which the runner's vector shares.
    run_path = tmp_path / "runner.yaml"
    run_path.write_text(yaml.safe_dump(runner_config(store_endpoint, tmp_path, tmp_path / "dataset")),
                        encoding="utf-8")
    runner_settings, run_sha = load_runner_config(run_path)
    plan = runner.make_plan(runner_settings, config_path=run_path, config_sha256=run_sha)
    run = await runner.execute(plan, tmp_path / "runs" / "e2e", "e2e", store_opener(providers),
                               log=lambda line: None)
    assert load_run(run.directory, dataset).manifest == run.manifest
    environment = run.manifest.environment
    recorded = json.dumps(run.manifest.model_dump(mode="json"))
    assert "127.0.0.1" not in recorded and "fake/" not in recorded and str(tmp_path / "token") not in recorded
    assert environment["load"]["already_loaded"] is True  # loaded by the generator's pooling
    assert environment["vectors"]["fake"]["embedded"] == 0  # every chunk has the pooling vector
    configurations = [c.configuration_id for c in run.manifest.configurations]
    assert len(configurations) == 1 + 2 + 4  # text; vector per prefix; hybrid per fusion and prefix
    assert run.manifest.counts["failed"] == 0
    assert run.manifest.counts["results"] == len(configurations) * len(dataset.queries)
    by_query = {(r.configuration_id, r.query_id): r for r in run.results}
    text = by_query["text", next(iter(dataset.queries))]
    assert text.hits and all(h.score is not None for h in text.hits) and text.embed_ms is None

    # 3. The reports: offline, from the saved files.
    loaded_dataset, runs = load(tmp_path / "dataset", [run.directory])
    summary = build_report(loaded_dataset, runs, tmp_path / "report", samples=200)
    report = (tmp_path / "report" / "report.md").read_text()
    assert "## Overall" in report or "Overall" in report
    assert summary and (tmp_path / "report" / "summary.csv").exists()
    assert any((tmp_path / "report" / "plots").glob("*.png"))
