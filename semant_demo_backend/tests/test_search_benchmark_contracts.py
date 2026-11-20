"""The file contract of the search relevance benchmark (#712): datasets and runs."""
import json

import pytest

from semant_demo.benchmarks.search_relevance.contracts import (
    ContractError, Hit, Qrel, Query, RunConfiguration, RunResult, load_dataset, load_run, sha256_file, write_dataset,
    write_run)
from tests import search_benchmark_fixture as fixture


@pytest.fixture
def dataset(tmp_path):
    return fixture.build_dataset(tmp_path / "dataset")


@pytest.fixture
def run(tmp_path, dataset):
    return fixture.build_run(tmp_path / "run", dataset)


def test_the_fixture_dataset_round_trips_with_counts_and_hashes(dataset):
    loaded = load_dataset(dataset.directory)
    assert loaded.manifest == dataset.manifest
    counts = loaded.manifest.counts
    assert (counts["chunks"], counts["intents"], counts["queries"], counts["qrels"]) == (9, 3, 9, 10)
    assert counts["chunks_ces"] == counts["chunks_eng"] == counts["chunks_deu"] == 3
    assert {name: entry.records for name, entry in loaded.manifest.files.items()} == {
        "corpus.jsonl": 9, "intents.jsonl": 3, "queries.jsonl": 9, "qrels.jsonl": 10}
    assert loaded.grades()["fire-lhota"][fixture.chunk_id(7)] == 1
    assert not [q for q in loaded.qrels if q.intent_id == "fire-lhota" and q.chunk_id == fixture.chunk_id(7)][0].consistent


def test_the_fixture_run_round_trips_against_its_dataset(dataset, run):
    loaded = load_run(run.directory, dataset)
    rankings = loaded.rankings()
    assert set(rankings) == {"bm25", "vector"} and len(rankings["bm25"]) == 9
    assert "school-council.eng" not in rankings["vector"]  # the failed search
    assert loaded.manifest.counts == {"results": 18, "failed": 1}
    assert loaded.manifest.dataset == dataset.ref()


def test_a_changed_file_or_a_missing_manifest_is_refused(dataset):
    path = dataset.directory / "queries.jsonl"
    path.write_text(path.read_text().replace("Lhota", "Lhotě"))
    with pytest.raises(ContractError, match="queries.jsonl: changed since its manifest"):
        load_dataset(dataset.directory)
    (dataset.directory / "manifest.json").unlink()
    with pytest.raises(ContractError, match="no manifest.json"):
        load_dataset(dataset.directory)


def test_a_record_with_an_unknown_field_or_a_bad_value_names_its_line(tmp_path, dataset):
    path = dataset.directory / "corpus.jsonl"
    lines = path.read_text().splitlines()
    record = json.loads(lines[1])
    record["colour"] = "red"
    lines[1] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n")
    manifest = json.loads((dataset.directory / "manifest.json").read_text())
    manifest["files"]["corpus.jsonl"]["sha256"] = sha256_file(path)
    (dataset.directory / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ContractError, match=r"corpus.jsonl:2: colour: Extra inputs are not permitted"):
        load_dataset(dataset.directory)
    with pytest.raises(ValueError):
        Query(query_id="q", intent_id="i", language="cs", text="x")  # two-letter code


@pytest.mark.parametrize("change, message", [
    (lambda c, i, q, r: (c, i, q, r + [Qrel(intent_id="fire-lhota", chunk_id=fixture.chunk_id(99), grade=1,
                                            judge=fixture.JUDGE, pooled_by=("bm25",))]), "chunk not in the corpus"),
    (lambda c, i, q, r: (c, i, q, [x for x in r if x.chunk_id != fixture.chunk_id(6)]), "source chunks without a grade"),
    (lambda c, i, q, r: (c, i, q + [Query(query_id="x.ces", intent_id="nope", language="ces", text="x")], r),
     "unknown intent nope"),
    (lambda c, i, q, r: (c, i, q + q[:1], r), "duplicate query ids"),
    (lambda c, i, q, r: (c, i, q, r[:1] + [r[1].model_copy(update={"pooled_by": ("bm42",)})] + r[2:]),
     "unknown pooling methods bm42"),
    (lambda c, i, q, r: (c, i, q, r[:1] + [r[1].model_copy(update={"judge": "other"})] + r[2:]), "unknown judge other"),
    (lambda c, i, q, r: (c, i, q, r + r[:1]), "graded twice"),
    (lambda c, i, q, r: (c, i, [x for x in q if x.intent_id != "railway-vienna"], r), "intents without a query"),
])
def test_a_dataset_that_breaks_referential_integrity_is_not_written(tmp_path, change, message):
    corpus, intents, queries, qrels = change(fixture.corpus(), list(fixture.INTENTS), fixture.queries(), fixture.qrels())
    with pytest.raises(ContractError, match=message):
        write_dataset(tmp_path / "d", fixture.MANIFEST, corpus, intents, queries, qrels)
    assert not (tmp_path / "d").exists()


def test_a_failed_manifest_leaves_the_directory_without_one(dataset):
    with pytest.raises(ContractError, match="manifest.json"):
        write_dataset(dataset.directory, {**fixture.MANIFEST, "dataset_id": "has space"}, fixture.corpus(),
                      fixture.INTENTS, fixture.queries(), fixture.qrels())
    assert not (dataset.directory / "manifest.json").exists()


@pytest.mark.parametrize("configuration, message", [
    ({"configuration_id": "h", "mode": "hybrid", "vector": fixture.VECTOR}, "needs alpha"),
    ({"configuration_id": "v", "mode": "vector"}, "needs a vector"),
    ({"configuration_id": "t", "mode": "text", "alpha": 0.5}, "hybrid only"),
])
def test_a_configuration_must_be_consistent(configuration, message):
    with pytest.raises(ValueError, match=message):
        RunConfiguration.model_validate(configuration)


def test_a_result_ranks_each_chunk_once_and_a_failed_search_has_no_hits():
    hit = Hit(chunk_id=fixture.chunk_id(1))
    with pytest.raises(ValueError, match="ranked twice"):
        RunResult(configuration_id="c", query_id="q", hits=(hit, hit))
    with pytest.raises(ValueError, match="no hits"):
        RunResult(configuration_id="c", query_id="q", hits=(hit,), error="Timeout")


@pytest.mark.parametrize("result, message", [
    (RunResult(configuration_id="other", query_id="fire-lhota.ces"), "unknown configuration"),
    (RunResult(configuration_id="bm25", query_id="nope"), "unknown query"),
    (RunResult(configuration_id="bm25", query_id="fire-lhota.ces", hits=(Hit(chunk_id=fixture.chunk_id(99)),)),
     "not in the dataset"),
    (RunResult(configuration_id="bm25", query_id="fire-lhota.ces",
               hits=tuple(Hit(chunk_id=fixture.chunk_id(n)) for n in range(1, 7))), "6 hits, depth 5"),
])
def test_a_run_must_match_its_configurations_and_dataset(tmp_path, dataset, result, message):
    manifest = {"run_id": "r", "dataset": dataset.ref(), "configurations": fixture.CONFIGURATIONS}
    with pytest.raises(ContractError, match=message):
        write_run(tmp_path / "r", manifest, [result], dataset)


def test_a_run_of_another_dataset_version_or_a_changed_dataset_is_refused(tmp_path, dataset, run):
    other = write_dataset(tmp_path / "other", {**fixture.MANIFEST, "version": "v1"}, fixture.corpus(),
                          fixture.INTENTS, fixture.queries(), fixture.qrels())
    with pytest.raises(ContractError, match="not fixture v1"):
        load_run(run.directory, other)
    rewritten = write_dataset(dataset.directory, {**fixture.MANIFEST, "description": "changed"}, fixture.corpus(),
                              fixture.INTENTS, fixture.queries(), fixture.qrels())
    with pytest.raises(ContractError, match="manifest changed since the run"):
        load_run(run.directory, rewritten)
