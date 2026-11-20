"""The search benchmark runner (#727) against a fake benchmark store, on the synthetic fixture."""
import asyncio
import hashlib
import json
import time
from pathlib import Path

import pytest
import yaml

from semant_demo.benchmarks.search_relevance import runner
from semant_demo.benchmarks.search_relevance.contracts import ContractError, load_run
from semant_demo.benchmarks.search_relevance.runner_config import (
    ConfigError, RunnerConfig, expand, load_config, select, select_queries)
from semant_demo.benchmarks.search_relevance.store_api import LoadReport, SearchOutcome, VectorReport
from tests import search_benchmark_fixture as fixture

BACKEND = Path(__file__).resolve().parents[1]
EXAMPLE = BACKEND / "semant_demo/configs/search_benchmark/runner.example.yaml"
PREFIX = "Instruct: find passages\nQuery:"


class Interrupted(BaseException):
    """Stands for Ctrl-C or a killed process: not a search failure."""


class FakeStore:
    """A ``BenchmarkStore`` whose rankings are a deterministic function of the configuration and
    the query; it can fail chosen searches, simulate latency and be interrupted."""

    def __init__(self, dataset=None, *, fail=lambda configuration_id, text: False, latency=0.0, interrupt_after=None,
                 extra_hits=()):
        self.fail, self.latency, self.interrupt_after, self.extra_hits = fail, latency, interrupt_after, extra_hits
        self.dataset = dataset
        self.calls: list[tuple[str, str]] = []
        self.vectors: list = []
        self.searchers: dict[str, object] = {}
        self.in_flight = self.max_in_flight = 0
        self.closed = False

    async def load(self, dataset):
        self.dataset = dataset
        return LoadReport(dataset_id=dataset.manifest.dataset_id, version=dataset.manifest.version,
                          chunks_written=len(dataset.corpus))

    async def ensure_vector(self, spec, endpoint, cache_dir):
        self.vectors.append((spec, endpoint, cache_dir))
        return VectorReport(vector=spec.target_vector, embedded=len(self.dataset.corpus))

    def searcher(self, configuration, endpoint):
        self.searchers[configuration.configuration_id] = endpoint

        async def search(text):
            if self.interrupt_after is not None and len(self.calls) >= self.interrupt_after:
                raise Interrupted()
            self.calls.append((configuration.configuration_id, text))
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            try:
                await asyncio.sleep(self.latency)
            finally:
                self.in_flight -= 1
            if self.fail(configuration.configuration_id, text):
                raise ConnectionError(f"cannot search {text}")  # the text must not reach the run
            ranked = sorted(self.dataset.corpus, key=lambda c: hashlib.sha256(
                f"{configuration.configuration_id}|{text}|{c}".encode()).hexdigest())
            hits = [(c, 1.0 / (r + 1)) for r, c in enumerate(ranked)]
            return SearchOutcome(hits=hits[:1] + hits + list(self.extra_hits),  # a repeated chunk is dropped
                                 embed_ms=None if configuration.mode == "text" else 4.0, search_ms=2.0)
        return search

    async def describe(self):
        return {"weaviate": "fake-1.40", "dataset": self.dataset.manifest.dataset_id}

    async def close(self):
        self.closed = True


def opener(store):
    async def open_store(spec):
        store.spec = spec
        return store
    return open_store


@pytest.fixture
def dataset(tmp_path):
    return fixture.build_dataset(tmp_path / "dataset")


def base_config(**changes):
    config = {
        "dataset": "dataset", "runs_dir": "runs", "cache_dir": "cache",
        "store": {"name": "test-benchmark-store", "token_file": "token"},
        "endpoints": {"fake": {"base_url": "http://embedder.invalid/v1", "api_key_env": "FAKE_EMBEDDING_KEY"}},
        "vectors": {"fake": {"model": "fake-small", "target_vector": "fake_small",
                             "query_prefixes": {"instruct": PREFIX, "none": ""}}},
        "bm25_properties": {"titles": {"text": 1.0, "title": 2.0}},
        "depth": 4,
        "grid": {"modes": ["text", "vector", "hybrid"], "alphas": [0.5], "fusions": ["ranked"],
                 "query_prefixes": {"fake": ["instruct"]}},
        "budget": {"concurrency": 2},
    }
    config.update(changes)
    return config


def write_config(tmp_path, data, name="experiment.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def plan_for(tmp_path, dataset, data, only=None):
    path = write_config(tmp_path, data)
    config, sha = load_config(path)
    return runner.make_plan(config, config_path=path, config_sha256=sha, only=only, dataset=dataset)


def run(plan, tmp_path, store, run_id="r1", **kwargs):
    return asyncio.run(runner.execute(plan, tmp_path / "runs" / run_id, run_id, opener(store),
                                      log=lambda line: None, **kwargs))


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("FAKE_EMBEDDING_KEY", "not-a-real-key")


# ---- configuration ------------------------------------------------------------------------

def test_the_grid_expands_to_stable_readable_ids(tmp_path):
    config, _ = load_config(write_config(tmp_path, base_config(grid={
        "modes": ["text", "vector", "hybrid"], "alphas": [0.25, 0.5, 0.50], "fusions": ["relativeScore", "ranked"],
        "properties": ["default", "titles"]})))
    configurations = {c.configuration_id: c for c in expand(config)}
    assert list(configurations)[:4] == ["text", "text.b-titles", "vector.fake.p-instruct", "vector.fake.p-none"]
    assert len(configurations) == 2 + 2 + 2 * 2 * 2 * 2  # 0.5 and 0.50 are one alpha
    hybrid = configurations["hybrid.fake.a0.5.ranked.p-instruct.b-titles"]
    assert (hybrid.alpha, hybrid.fusion, hybrid.properties, hybrid.depth) == (0.5, "ranked", {"text": 1.0, "title": 2.0}, 4)
    assert hybrid.vector.query_prefix == PREFIX and hybrid.vector.target_vector == "fake_small"
    assert configurations["vector.fake.p-none"].vector.query_prefix == ""
    assert configurations["text"].properties is None and configurations["vector.fake.p-none"].properties is None
    # Growing the grid never renames a configuration.
    smaller, _ = load_config(write_config(tmp_path, base_config(grid={"modes": ["hybrid"], "alphas": [0.5],
                                                                      "fusions": ["ranked"]}), "small.yaml"))
    assert {c.configuration_id: c for c in expand(smaller)}.items() <= configurations.items()


def test_explicit_configurations_join_the_grid_once(tmp_path):
    explicit = [{"configuration_id": "hybrid.fake.a0.5.ranked.p-instruct", "mode": "hybrid", "alpha": 0.5,
                 "fusion": "ranked", "vector": "fake", "query_prefix": "instruct"},
                {"configuration_id": "shallow-bm25", "mode": "text", "properties": "titles", "depth": 2}]
    config, _ = load_config(write_config(tmp_path, base_config(configurations=explicit)))
    ids = [c.configuration_id for c in expand(config)]
    assert ids == ["text", "vector.fake.p-instruct", "hybrid.fake.a0.5.ranked.p-instruct", "shallow-bm25"]
    assert select(expand(config), ["shallow-bm25", "text"])[0].configuration_id == "text"
    with pytest.raises(ConfigError, match="unknown configurations: nope"):
        select(expand(config), ["nope"])


@pytest.mark.parametrize(("change", "message"), [
    ({"endpoints": {"fake": {"base_url": "http://x", "api_key": "secret"}}}, "Extra inputs"),
    ({"endpoints": {"fake": {"base_url": "http://x", "api_key_env": "sk-123 secret"}}}, "pattern"),
    ({"endpoints": {}}, "vector fake has no endpoint"),
    ({"grid": {"modes": ["vector"], "vectors": ["other"]}}, "unknown vector other"),
    ({"grid": {"modes": ["hybrid"], "alphas": [1.5]}}, "between 0 and 1"),
    ({"grid": {"modes": ["vector"], "query_prefixes": {"fake": ["missing"]}}}, "no query prefix missing"),
    ({"grid": {"modes": ["text"], "properties": ["missing"]}}, "unknown BM25 property set"),
    ({"bm25_properties": {"default": {"text": 1.0}}}, "leave it null"),
    ({"bm25_properties": {"zero": {"text": 0}}}, "positive boosts"),
    ({"vectors": {"fake": {"model": "a", "target_vector": "t"}, "other": {"model": "b", "target_vector": "t"}}},
     "share the target vector"),
    ({"vectors": {"fake": {"model": "a", "target_vector": "t", "document_template": "no text"}}}, "{text}"),
    ({"vectors": {"fa.ke": {"model": "a", "target_vector": "t"}}}, "names are"),
    ({"grid": None}, "neither a grid nor configurations"),
    ({"filters": {"year": 1900}}, "Extra inputs"),  # metadata filtering is not benchmarked
    ({"configurations": [{"configuration_id": "text", "mode": "text", "depth": 9}]}, "defined twice"),
    ({"configurations": [{"configuration_id": "bm25-again", "mode": "text"}]}, "have the same settings"),
    ({"configurations": [{"configuration_id": "v", "mode": "vector", "vector": "fake"}]}, "several query prefixes"),
    ({"configurations": [{"configuration_id": "h", "mode": "hybrid", "vector": "fake", "query_prefix": "none"}]},
     "needs alpha"),
])
def test_bad_configurations_are_refused(tmp_path, change, message):
    with pytest.raises(ConfigError, match=message):
        config, _ = load_config(write_config(tmp_path, base_config(**change)))
        expand(config)


def test_the_example_config_is_valid():
    config, _ = load_config(EXAMPLE)
    ids = [c.configuration_id for c in expand(config)]
    assert len(ids) == len(set(ids)) and "hybrid.qwen.a0.5.ranked.p-instruct" in ids
    assert config.dataset.is_absolute() and all(e.api_key_env is None for e in config.endpoints.values())


# ---- budget -------------------------------------------------------------------------------

def test_the_budget_selects_a_deterministic_subset(dataset):
    def ids(**budget):
        return [q.query_id for q in select_queries(dataset, RunnerConfig.model_validate(
            {"dataset": "d", "grid": {"modes": ["text"]}, "budget": budget}).budget)]

    assert len(ids()) == 9
    assert ids(languages=["ces", "deu"]) == [q for q in ids() if not q.endswith(".eng")]
    sampled = ids(max_intents=2, seed=3)
    assert sampled == ids(max_intents=2, seed=3) and len(sampled) == 6  # whole intents: every translation
    assert len({q.split(".")[0] for q in sampled}) == 2
    assert {tuple(ids(max_intents=1, seed=s)) for s in range(10)} != {tuple(ids(max_intents=1, seed=0))}
    assert ids(intents=["fire-lhota"], languages=["eng"]) == ["fire-lhota.eng"]
    capped = ids(max_queries=4, seed=1)
    assert capped == ids(max_queries=4, seed=1) and len(capped) == 4 and capped == sorted(capped)
    with pytest.raises(ConfigError, match="not in the dataset: nope"):
        ids(intents=["nope"])
    with pytest.raises(ConfigError, match="without queries in the dataset: fra"):
        ids(languages=["fra"])


# ---- running ------------------------------------------------------------------------------

def test_a_run_on_the_fixture_is_a_valid_run(tmp_path, dataset):
    plan = plan_for(tmp_path, dataset, base_config())
    store = FakeStore()
    result = run(plan, tmp_path, store)
    loaded = load_run(tmp_path / "runs" / "r1", dataset)
    assert loaded.manifest == result.manifest
    assert [c.configuration_id for c in loaded.manifest.configurations] == [
        "text", "vector.fake.p-instruct", "hybrid.fake.a0.5.ranked.p-instruct"]
    assert loaded.manifest.counts == {"results": 27, "failed": 0, "configurations": 3}
    assert all(len(r.hits) == 4 for r in loaded.results)  # truncated to the depth, the repeated chunk dropped
    vector = {r.query_id: r for r in loaded.results if r.configuration_id == "vector.fake.p-instruct"}
    assert vector["fire-lhota.ces"].embed_ms == 4.0 and vector["fire-lhota.ces"].search_ms == 2.0
    assert all(r.embed_ms is None for r in loaded.results if r.configuration_id == "text")
    # One document vector, without the query prefix; endpoints only for vector searches.
    assert len(store.vectors) == 1
    spec, endpoint, cache_dir = store.vectors[0]
    assert (spec.id, spec.query_prefix, spec.target_vector, cache_dir) == ("fake", "", "fake_small", tmp_path / "cache")
    assert store.searchers["text"] is None and store.searchers["vector.fake.p-instruct"] == endpoint
    assert store.spec.name == "test-benchmark-store" and store.closed
    environment = loaded.manifest.environment
    assert environment["config"]["sha256"] == hashlib.sha256((tmp_path / "experiment.yaml").read_bytes()).hexdigest()
    assert environment["store"] == {"weaviate": "fake-1.40", "dataset": "fixture"}
    assert environment["embedding_endpoints"]["fake"]["api_key_env"] == "FAKE_EMBEDDING_KEY"
    assert "revision" in environment["git"] and environment["host"] and environment["finished"] >= environment["started"]
    assert environment["budget"]["concurrency"] == 2 and environment["sessions"] == []
    assert "not-a-real-key" not in (tmp_path / "runs/r1/manifest.json").read_text()
    assert not (tmp_path / "runs/r1" / runner.PARTIAL_RESULTS).exists()
    assert not (tmp_path / "runs/r1" / runner.PARTIAL_STATE).exists()


def test_failed_searches_are_recorded_by_class_without_text(tmp_path, dataset):
    plan = plan_for(tmp_path, dataset, base_config())
    store = FakeStore(fail=lambda configuration_id, text: configuration_id == "vector.fake.p-instruct"
                      and "Lhot" in text)
    loaded = run(plan, tmp_path, store)
    failed = [r for r in loaded.results if r.error]
    assert {(r.query_id, r.error) for r in failed} == {("fire-lhota.ces", "ConnectionError"),
                                                       ("fire-lhota.eng", "ConnectionError"),
                                                       ("fire-lhota.deu", "ConnectionError")}
    assert all(not r.hits for r in failed) and loaded.manifest.counts["failed"] == 3
    assert "Lhot" not in (tmp_path / "runs/r1/results.jsonl").read_text(encoding="utf-8")


def test_hits_outside_the_dataset_are_an_error(tmp_path, dataset):
    from uuid import UUID
    plan = plan_for(tmp_path, dataset, base_config(depth=50))
    loaded = run(plan, tmp_path, FakeStore(extra_hits=[(UUID(int=7), 0.1)]))
    assert {r.error for r in loaded.results} == {"ChunkOutsideDataset"}


def test_an_interrupted_run_resumes_without_repeating_searches(tmp_path, dataset):
    plan = plan_for(tmp_path, dataset, base_config(budget={"concurrency": 1}))
    first = FakeStore(interrupt_after=10)
    with pytest.raises(Interrupted):
        run(plan, tmp_path, first)
    directory = tmp_path / "runs/r1"
    assert not (directory / "manifest.json").exists() and first.closed
    assert len((directory / runner.PARTIAL_RESULTS).read_text().splitlines()) == 10
    with (directory / runner.PARTIAL_RESULTS).open("a") as f:
        f.write('{"configuration_id": "text", "que')  # the process died mid-line
    second = FakeStore()
    loaded = run(plan, tmp_path, second)
    assert len(second.calls) == 27 - 10
    assert not set(first.calls) & set(second.calls)
    assert loaded.manifest.counts["results"] == 27 and load_run(directory, dataset)
    # Nothing left to do: the store is not even opened.
    third = FakeStore()
    run(plan, tmp_path, third)
    assert third.calls == [] and not hasattr(third, "spec")


def test_configurations_are_added_to_an_existing_run(tmp_path, dataset):
    small = base_config(grid={"modes": ["text"]})
    run(plan_for(tmp_path, dataset, small), tmp_path, FakeStore())
    before = load_run(tmp_path / "runs/r1", dataset)
    store = FakeStore()
    loaded = run(plan_for(tmp_path, dataset, base_config()), tmp_path, store)
    assert {c for c, _ in store.calls} == {"vector.fake.p-instruct", "hybrid.fake.a0.5.ranked.p-instruct"}
    assert loaded.manifest.counts["results"] == 27 and loaded.manifest.created == before.manifest.created
    kept = {(r.configuration_id, r.query_id): r for r in loaded.results}
    assert all(kept[(r.configuration_id, r.query_id)] == r for r in before.results)
    sessions = loaded.manifest.environment["sessions"]
    assert len(sessions) == 1 and sessions[0]["configurations_run"] == ["text"]
    # --configurations runs a subset; it adds only that one.
    store = FakeStore()
    data = base_config(configurations=[{"configuration_id": "extra", "mode": "text", "properties": "titles"}])
    loaded = run(plan_for(tmp_path, dataset, data, only=["extra"]), tmp_path, store)
    assert {c for c, _ in store.calls} == {"extra"} and loaded.manifest.counts["results"] == 36


def test_changed_configurations_and_other_datasets_are_refused(tmp_path, dataset):
    run(plan_for(tmp_path, dataset, base_config()), tmp_path, FakeStore())
    with pytest.raises(runner.RunnerError, match="text ran with other settings"):
        run(plan_for(tmp_path, dataset, base_config(depth=3)), tmp_path, FakeStore())
    other = fixture.write_dataset(tmp_path / "other", {**fixture.MANIFEST, "version": "v9"}, fixture.corpus(),
                                  fixture.INTENTS, fixture.queries(), fixture.qrels())
    with pytest.raises(ContractError, match="not fixture v9"):
        run(plan_for(tmp_path, other, base_config()), tmp_path, FakeStore())
    # Unfinished results of another dataset are refused too.
    store = FakeStore(interrupt_after=2)
    with pytest.raises(Interrupted):
        run(plan_for(tmp_path, dataset, base_config()), tmp_path, store, run_id="r2")
    with pytest.raises(runner.RunnerError, match="another dataset"):
        run(plan_for(tmp_path, other, base_config()), tmp_path, FakeStore(), run_id="r2")


def test_failed_searches_are_retried_on_request(tmp_path, dataset):
    plan = plan_for(tmp_path, dataset, base_config(grid={"modes": ["text"]}))
    run(plan, tmp_path, FakeStore(fail=lambda configuration_id, text: "Lhot" in text))
    store = FakeStore()
    run(plan, tmp_path, store)
    assert store.calls == []
    loaded = run(plan, tmp_path, store, retry_failed=True)
    assert len(store.calls) == 3 and loaded.manifest.counts["failed"] == 0


def test_a_missing_key_stops_the_run_before_the_store(tmp_path, dataset, monkeypatch):
    monkeypatch.delenv("FAKE_EMBEDDING_KEY")
    store = FakeStore()
    with pytest.raises(runner.RunnerError, match="FAKE_EMBEDDING_KEY"):
        run(plan_for(tmp_path, dataset, base_config()), tmp_path, store)
    assert not hasattr(store, "spec")


def test_concurrency_is_bounded(tmp_path, dataset):
    store = FakeStore(latency=0.01)
    run(plan_for(tmp_path, dataset, base_config(budget={"concurrency": 3})), tmp_path, store)
    assert store.max_in_flight == 3 and len(store.calls) == 27


def test_the_rate_limit_spaces_searches(tmp_path, dataset):
    data = base_config(grid={"modes": ["text"]}, budget={"concurrency": 4, "max_qps": 100})
    started = time.monotonic()
    run(plan_for(tmp_path, dataset, data), tmp_path, FakeStore())
    assert time.monotonic() - started >= 8 / 100  # nine searches, at most 100 a second


def test_the_rate_limiter_reserves_distinct_slots():
    waits = []

    async def sleep(seconds):
        waits.append(seconds)

    limiter = runner.RateLimiter(4, clock=lambda: 10.0, sleep=sleep)

    async def all_of_them():
        await asyncio.gather(*(limiter.wait() for _ in range(4)))
    asyncio.run(all_of_them())
    assert sorted(waits) == [0.25, 0.5, 0.75]  # the first starts at once, the others a quarter second apart
    assert runner.RateLimiter(None).interval == 0


# ---- command line -------------------------------------------------------------------------

def never_open(spec):
    raise AssertionError("a dry run must not open a store")


def test_a_dry_run_prints_the_plan_and_touches_nothing(tmp_path, dataset):
    path = write_config(tmp_path, base_config(budget={"languages": ["ces", "eng"]}))
    lines = []
    assert runner.main(["run", "--config", str(path), "--dry-run"], open_store=never_open, out=lines.append) == 0
    text = "\n".join(lines)
    assert "6 queries selected of 9 (ces 3, eng 3), 3 intents" in text
    assert "hybrid.fake.a0.5.ranked.p-instruct: hybrid vector=fake alpha=0.5 fusion=ranked" in text
    assert "18 searches to do" in text and not (tmp_path / "runs").exists()


def test_the_command_line_runs_and_lists(tmp_path, dataset):
    path = write_config(tmp_path, base_config())
    lines = []
    assert runner.main(["list-configurations", "--config", str(path)], out=lines.append) == 0
    assert [line.split("\t")[0] for line in lines] == ["text", "vector.fake.p-instruct",
                                                        "hybrid.fake.a0.5.ranked.p-instruct"]
    store = FakeStore()
    assert runner.main(["run", "--config", str(path), "--out", str(tmp_path / "elsewhere"), "--configurations",
                        "text"], open_store=opener(store), out=lines.append) == 0
    loaded = load_run(tmp_path / "elsewhere" / "experiment", dataset)  # the run id defaults to the config's name
    assert [c.configuration_id for c in loaded.manifest.configurations] == ["text"]
    assert runner.main(["run", "--config", str(path), "--run-id", "bad id"], open_store=never_open) == runner.REFUSED
    assert runner.main(["run", "--config", str(path), "--configurations", "nope"],
                       open_store=never_open) == runner.REFUSED


def test_the_partial_state_names_the_dataset(tmp_path, dataset):
    store = FakeStore(interrupt_after=1)
    with pytest.raises(Interrupted):
        run(plan_for(tmp_path, dataset, base_config()), tmp_path, store)
    state = json.loads((tmp_path / "runs/r1" / runner.PARTIAL_STATE).read_text())
    assert state["dataset"]["manifest_sha256"] == dataset.manifest_sha256()
    assert [c["configuration_id"] for c in state["configurations"]][0] == "text"
