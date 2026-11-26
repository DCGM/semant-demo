"""Offline metrics, aggregation and reports of the search relevance benchmark (#728)."""
import csv
import json
import math

import pytest

from semant_demo.benchmarks.search_relevance import metrics as m
from semant_demo.benchmarks.search_relevance.analysis import (FAILED, MISSING, SCORED, aggregate, latency, query_grades,
                                                              score)
from semant_demo.benchmarks.search_relevance.contracts import ContractError, write_dataset, write_run
from semant_demo.benchmarks.search_relevance.report import (COMPARE_SECTIONS, REPORT_SECTIONS, build_report, load,
                                                            main, unjudged_counts)
from tests import search_benchmark_fixture as fixture

L3 = math.log2(3)


# ---- metrics ------------------------------------------------------------------------------

def test_dcg_uses_graded_gains_and_a_log_discount():
    assert m.dcg([2, 1]) == pytest.approx(3 + 1 / L3)
    assert m.dcg([]) == 0


def test_ndcg_is_against_the_ideal_ranking_of_all_qrels_of_the_intent():
    grades = {"a": 2, "b": 1, "c": 0}
    assert m.ndcg(["b", "a"], grades) == pytest.approx((1 + 3 / L3) / (3 + 1 / L3))
    assert m.ndcg(["a", "b"], grades) == pytest.approx(1.0)
    # "b" was never retrieved but is relevant: the ideal still holds it.
    assert m.ndcg(["a"], {"a": 2, "b": 2}) == pytest.approx(3 / (3 + 3 / L3))


def test_ndcg_edge_cases():
    assert m.ndcg([], {"a": 2}) == 0.0
    assert m.ndcg(["a"], {"a": 0}) is None  # no relevant qrel
    assert m.ndcg(["a"], {}) is None
    assert m.ndcg(["x", "a"], {"a": 2}) == pytest.approx(1 / L3)  # unjudged x counts as not relevant
    assert m.ndcg([f"x{i}" for i in range(10)] + ["a"], {"a": 2}) == 0.0  # below k


def test_precision_counts_empty_slots_as_misses():
    grades = {"a": 2, "b": 1, "c": 0}
    assert m.precision(["a"], grades) == pytest.approx(0.1)
    assert m.precision(["a", "b", "c", "x"], grades) == pytest.approx(0.2)
    assert m.precision(["a", "b", "c", "x"], grades, minimum=2) == pytest.approx(0.1)
    assert m.precision([], grades) == 0.0
    assert m.precision(["a"], {"a": 0}) is None
    assert m.precision(["b"], {"b": 1}, minimum=2) is None


def test_hit_of_known_source_chunks():
    ranked = [f"c{i}" for i in range(12)]
    assert m.hit(ranked, ["c9"]) == 1.0
    assert m.hit(ranked, ["c10"]) == 0.0
    assert m.hit(ranked, ["c10", "c0"]) == 1.0
    assert m.hit(ranked, []) is None
    assert m.hit([], ["c0"]) == 0.0


def test_recall_over_the_judged_relevant_chunks():
    grades = {"a": 2, "b": 1, "c": 0, "d": 2}
    ranked = ["c", "a"] + [f"x{i}" for i in range(20)] + ["b"]
    assert m.recall(ranked, grades, 20) == pytest.approx(1 / 3)
    assert m.recall(ranked, grades, 50) == pytest.approx(2 / 3)
    assert m.recall(ranked, {"c": 0}, 20) is None
    assert m.recall([], grades, 20) == 0.0


def test_unjudged_rate_and_condensed_ranking():
    grades = {"a": 2, "c": 0}
    assert m.unjudged_rate(["x", "a"], grades) == pytest.approx(0.5)
    assert m.unjudged_rate([], grades) is None
    assert m.unjudged_rate(["a", "c"] + [f"x{i}" for i in range(20)], grades) == pytest.approx(0.8)
    assert m.condensed(["x", "a", "y", "c"], grades) == ["a", "c"]


def test_query_metrics_in_both_variants():
    found = m.query_metrics(["x", "a", "y"], {"a": 2, "b": 1}, ["a"])
    assert set(found) == set(m.METRICS)
    ideal = 3 + 1 / L3
    assert found["ndcg@10"] == pytest.approx((3 / L3) / ideal)
    assert found["ndcg@10_condensed"] == pytest.approx(3 / ideal)
    assert found["p@10"] == found["p@10_condensed"] == pytest.approx(0.1)
    assert found["hit@10"] == 1.0 and found["recall@20"] == pytest.approx(0.5)
    assert found["unjudged@10"] == pytest.approx(2 / 3)
    nothing = m.query_metrics([], {"a": 0}, [])
    assert nothing["ndcg@10"] is None and nothing["p@10"] is None and nothing["hit@10"] is None
    assert nothing["unjudged@10"] is None


def test_percentile_ignores_missing_values():
    assert m.percentile([1.0, None, 3.0], 50) == 2.0
    assert m.percentile([None], 95) is None


def test_clustered_mean_resamples_whole_clusters_deterministically():
    values = [("i1", 1.0), ("i1", 1.0), ("i1", 1.0), ("i2", 0.0), ("i3", None)]
    first = m.clustered_mean(values, seed=1, samples=500)
    assert first == m.clustered_mean(values, seed=1, samples=500)
    assert first["mean"] == pytest.approx(0.75) and first["n"] == 4 and first["clusters"] == 2
    # Resampling whole intents, a mean is 1 (i1 twice), 0 (i2 twice) or 0.75 (both): nothing else.
    assert first["low"] in (0.0, 0.75, 1.0) and first["high"] in (0.0, 0.75, 1.0)
    assert first["low"] <= first["mean"] <= first["high"]
    single = m.clustered_mean([("i1", 0.5), ("i1", 0.7)])
    assert single["mean"] == pytest.approx(0.6) and single["low"] is None and single["high"] is None
    assert m.clustered_mean([("i1", None)])["mean"] is None


def test_bootstrap_seed_is_stable_across_processes():
    assert m.stable_seed(728, "bm25", "overall") == m.stable_seed(728, "bm25", "overall")
    assert m.stable_seed(728, "bm25") != m.stable_seed(728, "vector")


# ---- aggregation over the fixture -----------------------------------------------------------

@pytest.fixture
def dataset(tmp_path):
    return fixture.build_dataset(tmp_path / "dataset")


@pytest.fixture
def run(tmp_path, dataset):
    return fixture.build_run(tmp_path / "runs" / "fixture-run", dataset)


def test_rows_score_every_query_and_count_failed_searches(dataset, run):
    configs, rows = score(dataset, [run])
    assert [c.label for c in configs] == ["bm25", "vector"] and len(rows) == 18
    failed = [r for r in rows if r.status == FAILED]
    assert [(r.configuration, r.query_id, r.error) for r in failed] == [("vector", "school-council.eng", "ConnectError")]
    fire = next(r for r in rows if r.configuration == "bm25" and r.query_id == "fire-lhota.eng")
    # BM25 returns the three English chunks; chunk 4 (grade 2) first, 5 and 6 unjudged.
    assert fire.metrics["ndcg@10"] == pytest.approx(3 / (3 + 3 / L3 + 1 / 2))
    assert fire.metrics["unjudged@10"] == pytest.approx(2 / 3)
    assert fire.slices["language pair"] == "eng→ces" and fire.slices["language match"] == "cross language"
    assert fire.slices["source ocr_quality"] == "poor" and fire.slices["source title"] == "with title"


def test_aggregates_leave_failed_searches_out_of_the_means(dataset, run):
    configs, rows = score(dataset, [run])
    aggregates = aggregate(configs, rows, samples=200)
    overall = {e["configuration"]: e for e in aggregates if e["slice"] == "overall"}
    assert (overall["vector"]["scored"], overall["vector"]["failed"], overall["vector"]["intents"]) == (8, 1, 3)
    assert overall["vector"]["metrics"]["ndcg@10"]["n"] == 8
    assert overall["vector"]["metrics"]["ndcg@10"]["mean"] == pytest.approx(1.0)
    bm25 = [r.metrics["ndcg@10"] for r in rows if r.configuration == "bm25"]
    assert overall["bm25"]["metrics"]["ndcg@10"]["mean"] == pytest.approx(sum(bm25) / 9)
    pairs = {e["group"] for e in aggregates if e["configuration"] == "bm25" and e["slice"] == "language pair"}
    assert len(pairs) == 9
    cell = next(e for e in aggregates if e["configuration"] == "vector" and e["group"] == "eng→deu")
    assert (cell["scored"], cell["failed"], cell["metrics"]["ndcg@10"]["mean"]) == (0, 1, None)
    assert aggregate(configs, rows, samples=200) == aggregates  # deterministic


def test_inconsistent_intents_can_be_left_out(dataset, run):
    _, rows = score(dataset, [run], exclude_inconsistent=True)
    assert len(rows) == 12 and not [r for r in rows if r.intent_id == "fire-lhota"]


def test_latency_percentiles_per_configuration(dataset, run):
    configs, rows = score(dataset, [run])
    times = {t["configuration"]: t for t in latency(configs, rows)}
    assert times["bm25"]["embed_ms_p50"] is None and times["bm25"]["search_ms_p95"] == 2.0
    assert times["vector"]["embed_ms_p50"] == 5.0 and times["vector"]["total_ms_p95"] == 8.0
    assert times["vector"]["searches"] == 8


def test_a_query_missing_from_a_run_is_counted(tmp_path, dataset, run):
    results = [r for r in run.results if r.query_id != "railway-vienna.deu"]
    partial = write_run(tmp_path / "partial", {**run.manifest.model_dump(exclude={"files", "counts"}),
                                               "run_id": "partial"}, results, dataset)
    _, rows = score(dataset, [partial])
    assert {(r.configuration, r.status) for r in rows if r.query_id == "railway-vienna.deu"} == {
        ("bm25", MISSING), ("vector", MISSING)}
    assert sum(r.status == SCORED for r in rows) == 15


# ---- commands -----------------------------------------------------------------------------

def read_csv(path):
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_report_writes_markdown_tables_and_plots(tmp_path, dataset, run):
    out = tmp_path / "report"
    code = main(["report", "--dataset", str(dataset.directory), "--run", str(run.directory), "--out", str(out),
                 "--bootstrap", "200"])
    assert code == 0
    text = (out / "report.md").read_text(encoding="utf-8")
    for section in REPORT_SECTIONS:
        assert f"\n## {section}\n" in text
    assert "unjudged" in text and "ConnectError" not in text
    examples = (out / "examples.md").read_text(encoding="utf-8")
    assert "Relevant chunks it missed" in examples and str(fixture.chunk_id(1)) in examples
    assert "Dne 12. března vyhořela" in examples  # a corpus snippet in the examples
    assert "Relevant chunks it missed" not in text and "`examples.md`" in text
    # configurations by readable name (BM25 is the application's `text` mode), ids in the Configurations table
    assert "| BM25 | `bm25` |" in text
    # the vector configuration's failed search is explained, not a bare "failed"/"missing" column
    assert "| configuration | queries | search errors | not searched |" in text
    assert "| missing |" not in text and "| failed |" not in text
    doc = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert doc["settings"]["primary"] == "ndcg@10" and doc["inconsistent_intents"] == 1
    assert len(doc["queries"]) == 18
    summary = read_csv(out / "summary.csv")
    assert {r["configuration"] for r in summary} == {"bm25", "vector"}
    assert any(r["slice"] == "language pair" and r["group"] == "ces→deu" for r in summary)
    assert len(read_csv(out / "queries.csv")) == 18 and len(read_csv(out / "latency.csv")) == 2
    for name in ("ndcg_by_configuration", "language_matrix", "latency"):
        assert (out / "plots" / f"{name}.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert (out / "plots" / f"{name}.svg").read_text(encoding="utf-8").lstrip().startswith("<?xml")
        assert f"plots/{name}.png" in text


def test_report_explains_unjudged_effect_and_draws_no_conclusions(tmp_path, dataset, run):
    out = tmp_path / "report"
    assert main(["report", "--dataset", str(dataset.directory), "--run", str(run.directory), "--out", str(out),
                 "--bootstrap", "0"]) == 0
    text = (out / "report.md").read_text(encoding="utf-8")
    assert "## Conclusions\n\n_This report states measurements only; it draws no conclusions." in text
    assert "### Effect of unjudged results" in text and "Rank correlation (Spearman)" in text
    assert ("| configuration | top-10 results | without a grade | distinct ungraded pairs | nDCG@10 standard | rank "
            "| nDCG@10 condensed | rank |") in text
    assert "- Over all configurations: " in text and "graded pairs" in text


def test_unjudged_counts_count_results_without_a_qrel(dataset, run):
    configs, rows = score(dataset, [run], False)
    counts, missing, every = unjudged_counts(dataset, rows)
    grades_of = query_grades(dataset)
    for config in ("bm25", "vector"):
        mine = [r for r in rows if r.configuration == config]
        results = sum(len(r.ranked[:10]) for r in mine)
        ungraded = [(r.intent_id, c) for r in mine for c in r.ranked[:10]
                    if c not in grades_of(r.intent_id, r.query_language)]
        assert counts[config] == {"results": results, "unjudged": len(ungraded), "pairs": len(set(ungraded))}
    assert 0 < missing <= every


def test_report_is_deterministic(tmp_path, dataset, run):
    first = build_report(dataset, [run], tmp_path / "a", samples=300)
    second = build_report(dataset, [run], tmp_path / "b", samples=300)
    assert first == second
    assert (tmp_path / "a" / "report.md").read_text() == (tmp_path / "b" / "report.md").read_text()


def test_report_excluding_inconsistent_intents_says_so(tmp_path, dataset, run):
    doc = build_report(dataset, [run], tmp_path / "out", exclude_inconsistent=True, samples=100)
    assert doc["excluded_intents"] == 1 and len(doc["queries"]) == 12
    assert "Left out of this report: 1." in (tmp_path / "out" / "report.md").read_text()


def test_compare_two_configurations_of_two_runs(tmp_path, dataset, run):
    other = fixture.build_run(tmp_path / "runs" / "other", dataset)
    other = write_run(tmp_path / "runs" / "other", {**other.manifest.model_dump(exclude={"files", "counts"}),
                                                    "run_id": "other"}, other.results, dataset)
    out = tmp_path / "compare"
    code = main(["compare", "--dataset", str(dataset.directory), "--run", str(run.directory), "--run",
                 str(other.directory), "--a", "fixture-run/bm25", "--b", "other/vector", "--out", str(out),
                 "--bootstrap", "200"])
    assert code == 0
    text = (out / "comparison.md").read_text(encoding="utf-8")
    for section in COMPARE_SECTIONS:
        assert f"\n## {section}\n" in text
    doc = json.loads((out / "comparison.json").read_text(encoding="utf-8"))
    ndcg = next(e for e in doc["overall"] if e["metric"] == "ndcg@10")
    assert ndcg["n"] == 8 and ndcg["clusters"] == 3  # the failed vector search is not paired
    assert ndcg["delta"] == pytest.approx(ndcg["b"] - ndcg["a"]) and ndcg["low"] <= ndcg["delta"] <= ndcg["high"]
    rows = read_csv(out / "comparison.csv")
    assert {r["slice"] for r in rows} >= {"overall", "language pair", "language match", "style"}
    for name in ("delta_language_matrix", "delta_by_slice", "latency"):
        assert (out / "plots" / f"{name}.png").is_file() and (out / "plots" / f"{name}.svg").is_file()


def test_compare_refuses_unknown_or_identical_configurations(tmp_path, dataset, run, capsys):
    base = ["compare", "--dataset", str(dataset.directory), "--run", str(run.directory), "--out", str(tmp_path / "c")]
    assert main([*base, "--a", "bm25", "--b", "nope"]) == 2
    assert "unknown" in capsys.readouterr().err
    assert main([*base, "--a", "bm25", "--b", "bm25"]) == 2


def test_runs_of_another_dataset_are_refused(tmp_path, dataset):
    other = write_dataset(tmp_path / "other", {**fixture.MANIFEST, "version": "v1"}, fixture.corpus(),
                          fixture.INTENTS, fixture.queries(), fixture.qrels())
    foreign = fixture.build_run(tmp_path / "runs" / "foreign", other)
    with pytest.raises(ContractError, match="not fixture v0"):
        load(dataset.directory, [foreign.directory])
    assert main(["compare", "--dataset", str(dataset.directory), "--run", str(foreign.directory), "--a", "bm25",
                 "--b", "vector", "--out", str(tmp_path / "c")]) == 2


def test_a_query_uses_its_own_languages_grade_where_one_was_judged(dataset, run):
    # The fixture grades chunk 7 for "fire-lhota" 2 for Czech, 1 for English and German (grade 1);
    # the vector configuration ranks it among the intent's relevant chunks for every query.
    _, rows = score(dataset, [run])
    vector = {r.query_id: r for r in rows if r.configuration.endswith("vector") and r.status == SCORED}
    ces, eng = vector["fire-lhota.ces"], vector["fire-lhota.eng"]
    assert fixture.chunk_id(7) in ces.ranked and fixture.chunk_id(7) in eng.ranked
    assert ces.metrics["p2@10"] > eng.metrics["p2@10"]  # graded 2 only for the Czech query


def test_recall_is_not_shown_for_configurations_that_keep_fewer_chunks(dataset, run):
    _, rows = score(dataset, [run])  # the fixture's configurations keep 5 chunks
    scored = [r for r in rows if r.status == SCORED]
    assert scored and all(r.metrics["recall@20"] is None and r.metrics["recall@50"] is None for r in scored)
    assert all(r.metrics["ndcg@10"] is not None for r in scored if r.intent_id == "fire-lhota")


def test_the_examples_show_the_grades_the_query_was_scored_with(dataset, run, tmp_path):
    from semant_demo.benchmarks.search_relevance.analysis import query_grades
    from semant_demo.benchmarks.search_relevance.report import examples
    grades_of = query_grades(dataset)
    assert grades_of("fire-lhota", "ces")[fixture.chunk_id(7)] == 2  # its own language's grade
    assert grades_of("fire-lhota", "eng")[fixture.chunk_id(7)] == 1
    assert grades_of("railway-vienna", "ces") == dataset.grades()["railway-vienna"]  # no per-language grades
    _, rows = score(dataset, [run])
    vector = [r for r in rows if r.configuration.endswith("vector")]
    lines, found = examples(dataset, vector, vector[0].configuration, 3)
    fire = next(f for f in found if f["intent_id"] == "fire-lhota")
    assert fire["query_id"] == "fire-lhota.ces"
    # Chunk 7 is shown with its Czech grade (2), the one the Czech query was scored with, not the
    # intent's aggregate grade (1).
    assert f"| `{fixture.chunk_id(7)}` | deu | 2 |" in "\n".join(lines)


def test_the_summary_shows_the_best_configurations_in_a_table_not_every_one(dataset, run, monkeypatch):
    from semant_demo.benchmarks.search_relevance import report as report_module
    from semant_demo.benchmarks.search_relevance.analysis import aggregate as aggregate_rows
    configs, rows = score(dataset, [run])
    aggregates = aggregate_rows(configs, rows, samples=50)
    monkeypatch.setattr(report_module, "SUMMARY_TOP", 1)
    text = "\n".join(report_module.report_summary(dataset, configs, aggregates, inconsistent=1, excluded=False))
    assert "| # | configuration | nDCG@10 [95% CI] | same language | cross language | gap |" in text
    assert text.count("\n| 1 |") == 1 and "\n| 2 |" not in text  # only the top configuration
    assert "Lowest nDCG@10:" in text and "Order by" not in text
