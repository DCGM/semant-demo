"""The database benchmark tool (#374) without a store: profiles and their safety limits, the
load loop, statistics, input sampling, id hashing, disk attribution, log signals, ARC counters
and the reports."""
import asyncio
import json
import random
import time
from types import SimpleNamespace
from uuid import UUID

import pydantic
import pytest

from semant_demo.maintenance.db_benchmark import inventory, report, resources
from semant_demo.maintenance.db_benchmark.cli import REFUSED, main
from semant_demo.maintenance.db_benchmark.profile import Profile, Scenario, available_profiles, load_profile
from semant_demo.maintenance.db_benchmark.runner import Pacer, percentile, run_point
from semant_demo.maintenance.db_benchmark.workload import (
    IdHasher, _pick_vector, _sample_matching_ids, short_hash, terms)

UNREACHABLE = ["--host", "203.0.113.1"]


@pytest.mark.parametrize("name", available_profiles())
def test_shipped_profiles_load_and_are_production_safe(name):
    profile = load_profile(name)
    assert profile.violations() == []
    assert max(profile.concurrency) <= 10


def test_baseline_covers_the_application_read_paths():
    profile = load_profile("baseline")
    assert profile.concurrency == [1, 5, 10]
    kinds = {s.kind for s in profile.scenarios}
    assert {"search", "direct", "context", "document_view", "aggregate", "self_recall", "mixed"} <= kinds
    assert {s.filter for s in profile.scenarios} >= {"year_range", "language", "document_type", "tag", "user_collection"}


def test_violations_name_each_exceeded_limit():
    profile = Profile(name="x", concurrency=[1, 50], max_qps=100, requests_per_point=1000, timeout=120,
                      scenarios=[Scenario(name="s", kind="search", mode="text")])
    problems = " ".join(profile.violations())
    for word in ("concurrency 50", "max_qps", "requests_per_point", "timeout"):
        assert word in problems


@pytest.mark.parametrize("scenarios, message", [
    ([Scenario(name="a", kind="search")], "needs a mode"),
    ([Scenario(name="a", kind="direct", mode="text", filter="tag")], "take no filter"),
    ([Scenario(name="a", kind="mixed", of=["missing"])], "'of'"),
    ([Scenario(name="a", kind="aggregate"), Scenario(name="a", kind="aggregate")], "unique"),
])
def test_invalid_profiles_are_rejected(scenarios, message):
    with pytest.raises(ValueError, match=message):
        Profile(name="x", scenarios=scenarios).check()


@pytest.mark.parametrize("field, value", [
    ("max_qps", 0), ("max_qps", -1), ("requests_per_point", 0), ("max_seconds_per_point", 0),
    ("max_seconds_per_point", -5), ("timeout", 0), ("warmup_requests", -1), ("concurrency", []),
    ("concurrency", [0]), ("concurrency", [1, -2]), ("pause_between_points", -1),
])
def test_non_positive_limits_are_invalid(field, value):
    # A zero rate would otherwise disable pacing while passing the "<= limit" checks.
    data = load_profile("smoke").model_dump()
    data[field] = value
    with pytest.raises(pydantic.ValidationError):
        Profile.model_validate(data)


@pytest.mark.parametrize("scenario", [
    {"concurrency": []}, {"concurrency": [0]}, {"limit": 0}, {"context_chunks": 0}, {"alpha": 1.5},
])
def test_invalid_scenario_values_are_rejected(scenario):
    with pytest.raises(pydantic.ValidationError):
        Scenario(name="a", kind="search", mode="hybrid", **scenario)


def test_heavy_profile_is_refused_before_connecting(tmp_path, capsys):
    path = tmp_path / "heavy.yaml"
    path.write_text("name: heavy\nconcurrency: [50]\nscenarios:\n  - {name: a, kind: aggregate}\n")
    # An unreachable endpoint: the refusal must come first.
    assert main(["run", "--profile", str(path), *UNREACHABLE]) == REFUSED
    assert "--allow-heavy" in capsys.readouterr().err


@pytest.mark.parametrize("override", [
    ["--max-qps", "0"], ["--max-qps", "-3"], ["--requests", "0"], ["--max-seconds", "0"], ["--timeout", "0"],
    ["--concurrency", "0"], ["--concurrency", "1,x"], ["--scenarios", "no_such_scenario"], ["--scenarios", ","],
])
def test_invalid_overrides_are_refused_before_connecting(override, capsys):
    assert main(["run", "--profile", "baseline", *override, *UNREACHABLE]) == REFUSED
    assert "Refused" in capsys.readouterr().err


def test_pacer_needs_a_positive_rate():
    with pytest.raises(ValueError):
        Pacer(0)


def test_percentile_is_nearest_rank():
    values = [float(v) for v in range(1, 101)]
    assert (percentile(values, 0.5), percentile(values, 0.95), percentile(values, 0.99)) == (50, 95, 99)
    assert percentile([], 0.5) is None


async def test_run_point_counts_results_errors_and_timeouts():
    async def request(index):
        if index % 5 == 1:
            raise RuntimeError("boom")
        if index % 5 == 2:
            await asyncio.sleep(1)
        return [UUID(int=index)] if index % 5 else []

    point = await run_point(request, concurrency=3, requests=10, max_seconds=10, timeout=0.05, max_qps=1000,
                            keep_results=True)
    summary = point.summary()
    assert summary["requests"] == 10
    assert (summary["ok"], summary["timeouts"], summary["errors"]) == (6, 2, {"RuntimeError": 2, "timeout": 2})
    assert summary["hit_requests"] == 4  # indices 0 and 5 return no ids
    assert set(point.results) == {0, 3, 4, 5, 8, 9}
    assert all(len(h) == 12 for ids in point.results.values() for h in ids)


async def test_run_point_respects_rate_and_time_caps():
    async def request(index):
        return []

    start = time.monotonic()
    point = await run_point(request, concurrency=5, requests=6, max_seconds=10, timeout=1, max_qps=20)
    assert time.monotonic() - start >= 0.25  # 6 starts at most 20/s
    capped = await run_point(request, concurrency=2, requests=10_000, max_seconds=0.2, timeout=1, max_qps=50)
    assert capped.stopped_by == "time" and capped.requests < 20
    assert point.ok == 6


async def test_no_request_starts_after_the_time_cap():
    starts = []

    async def request(index):
        starts.append(time.monotonic())
        return []

    begin = time.monotonic()
    # Five workers reserve start slots 0, 0.5, 1.0, ... s; only those before 0.6 s may run.
    point = await run_point(request, concurrency=5, requests=100, max_seconds=0.6, timeout=1, max_qps=2)
    assert point.requests == 2 and point.stopped_by == "time"
    assert all(t - begin < 0.6 for t in starts)
    assert time.monotonic() - begin < 0.9  # workers do not sleep until slots past the cap


async def test_run_point_rejects_non_positive_limits():
    with pytest.raises(ValueError):
        await run_point(lambda i: None, concurrency=1, requests=1, max_seconds=0, timeout=1, max_qps=1)


def test_query_terms_are_the_longest_distinct_words():
    assert terms("Na Pražském hradě se konala slavnost, slavnost veliká.", 2) == "pražském slavnost"  # equal length: alphabetical
    assert terms("a b c", 2) == ""


def test_an_explicit_named_vector_is_never_substituted():
    assert _pick_vector({"b": [2.0], "a": [1.0]}, None) == ([1.0], "a")
    assert _pick_vector({"a": [1.0]}, "b") == (None, "b")
    assert _pick_vector([3.0], None) == ([3.0], "default")
    assert _pick_vector([3.0], "other") == (None, "other")


async def test_filter_values_are_sampled_only_when_they_match_chunks():
    ids = [UUID(int=i) for i in range(1, 11)]
    collection = SimpleNamespace(query=SimpleNamespace(
        fetch_objects=lambda **kw: _resolved(SimpleNamespace(objects=[SimpleNamespace(uuid=i) for i in ids]))))

    async def matches(candidate):
        return candidate.int % 3 == 0  # 3, 6 and 9

    found, checked = await _sample_matching_ids(collection, random.Random(1), 5, matches)
    assert sorted(found) == [UUID(int=3), UUID(int=6), UUID(int=9)] and checked == 10
    found, checked = await _sample_matching_ids(collection, random.Random(1), 1, matches)
    assert len(found) == 1 and checked < 10
    assert await _sample_matching_ids(collection, random.Random(1), 0, matches) == ([], 0)


async def _resolved(value):
    return value


def test_id_hashes_are_keyed():
    key_a, key_b = IdHasher(b"a" * 32), IdHasher(b"b" * 32)
    value = UUID(int=7)
    assert key_a(value) != short_hash(value) and key_a(value) != key_b(value)
    assert key_a(value) == key_a.rekey(short_hash(value)) and len(key_a(value)) == 12
    assert key_a.key_id != key_b.key_id and "a" * 16 not in json.dumps(key_a.describe())
    with pytest.raises(ValueError):
        IdHasher(b"short")


def test_arcstats_value_is_the_data_column():
    text = ("9 1 0x01 147 39984 8724354308 15712861992255310\n"
            "name                            type data\n"
            "hits                            4    12652977794\n"
            "c_max                           4    100885237760\n"
            "size                            4    91932629864\n")
    arc = resources.parse_arcstats(text)
    assert (arc["size"], arc["c_max"]) == (91932629864, 100885237760)
    assert resources.parse_arcstats(None) == {}


def test_disk_use_is_attributed_to_collection_component_and_bucket():
    listing = "\n".join([
        "100 /var/lib/weaviate/chunks_test/abc/lsm/objects/segment-1.l3.s0.db",
        "50 /var/lib/weaviate/chunks_test/abc/lsm/objects/segment-2.l1.s0.db",
        "7 /var/lib/weaviate/chunks_test/abc/lsm/objects/segment-2.l1.s0.bloom",
        "30 /var/lib/weaviate/chunks_test/abc/lsm/vectors_compressed_default/segment-3.db",
        "20 /var/lib/weaviate/chunks_test/abc/vectors_default.hnsw.commitlog.d/1.condensed",
        "5 /var/lib/weaviate/schema.db",
        "garbage line",
    ])
    usage = inventory.scan_files(inventory.parse_files_list(listing))
    assert usage["total_bytes"] == 212
    assert usage["top_level"] == {"chunks_test": 207, "schema.db": 5}
    assert usage["components"]["chunks_test"] == {
        "lsm/objects": 157, "lsm/vectors_compressed_default": 30, "vectors_default.hnsw.commitlog.d": 20}
    assert usage["largest_bucket_segments"]["chunks_test"] == {"objects": [100, 50],
                                                               "vectors_compressed_default": [30]}


def test_log_signals_count_warnings_without_payloads():
    log = "\n".join([
        '{"level":"info","msg":"loading local db","time":"2026-01-01T00:00:00Z"}',
        '{"level":"warning","msg":"disk usage currently at 89.79%, threshold set to 50.00%","action":"read_disk_use","time":"t"}',
        '{"level":"warning","msg":"disk usage currently at 90.01%, threshold set to 50.00%","action":"read_disk_use","time":"t"}',
        '{"level":"error","msg":"x","query":"secret user text","time":"2026-01-02T00:00:00Z"}',
        "panic: runtime error",
    ])
    signals = inventory.log_signals(log)
    assert (signals["startups"], signals["panic_lines"], signals["lines"]) == (1, 1, 5)
    assert signals["signals"][0] == {"count": 2, "level": "warning", "action": "read_disk_use",
                                     "message": "disk usage currently at N%, threshold set to N%"}
    assert "secret" not in str(signals)


def _run_doc(p50: float, fingerprint: str = "f1", version: str = "1.34.4", results=None) -> dict:
    return {
        "kind": "run",
        "environment": {"created_at": "now", "git_commit": "abc", "tool_version": 1,
                        "target": {"endpoint": "localhost:8080", "weaviate_version": version, "chunks_class": "Chunks",
                                   "chunks_objects": 10, "chunks_vector_index": "hnsw"}},
        "profile": {"name": "baseline", "seed": 1, "max_qps": 20, "requests_per_point": 40,
                    "max_seconds_per_point": 20, "timeout": 30, "warmup_requests": 5},
        "profile_fingerprint": fingerprint, "allow_heavy": False,
        "inputs": {"sampled_chunks": 3, "query_set": "q", "notes": []},
        "resource_source": {"cgroup": None, "unavailable": "neither --container nor --cgroup given"},
        "scenarios": [
            {"name": "hybrid", "kind": "search", "layer": "adapter", "description": "d", "limit": 10,
             "results": results or {"a": ["1", "2"], "b": ["3", "4"]},
             "points": [{"concurrency": 1, "ok": 4, "hit_requests": 4, "error_count": 0, "timeouts": 0, "errors": {},
                         "throughput_rps": 2.0, "latency_ms": {"p50": p50, "p95": p50 * 2, "p99": None, "max": 9},
                         "resources": None}]},
            {"name": "aggregate", "kind": "aggregate", "layer": "adapter", "description": "", "limit": 10,
             "skipped": "no usable sampled inputs", "points": []},
        ],
    }


def test_run_report_lists_points_and_skipped_scenarios():
    text = report.run_markdown(_run_doc(10.0))
    assert "| hybrid | adapter | 1 | 4 | 4 | 0 | 0 | 10 | 20 |" in text
    assert "skipped: no usable sampled inputs" in text
    assert "not representative" not in text


def test_run_report_flags_scenarios_without_any_result():
    doc = _run_doc(1.0)
    doc["scenarios"][0]["points"][0]["hit_requests"] = 0
    assert "No request returned results in `hybrid`" in report.run_markdown(doc)


def test_summary_drops_per_query_hashes():
    summary = report.run_summary(_run_doc(10.0))
    assert summary["kind"] == "run_summary" and "results" not in summary["scenarios"][0]
    assert summary["scenarios"][0]["points"][0]["latency_ms"]["p50"] == 10.0


def test_sanitize_keys_version_1_hashes_and_drops_paths():
    doc = _run_doc(10.0)
    doc["inputs"]["query_set"] = "abcdefabcdef"
    doc["resource_source"] = {"cgroup": "/sys/fs/cgroup/system.slice/docker-0123.scope", "unavailable": None}
    hasher = IdHasher(b"k" * 32)
    clean = report.sanitize(doc, hasher)
    assert clean["scenarios"][0]["results"] == {hasher.rekey("a"): [hasher.rekey("1"), hasher.rekey("2")],
                                                hasher.rekey("b"): [hasher.rekey("3"), hasher.rekey("4")]}
    assert clean["inputs"]["query_set"] == hasher.rekey("abcdefabcdef")
    assert "docker-" not in json.dumps(clean) and clean["id_hashing"]["key_id"] == hasher.key_id
    assert doc["scenarios"][0]["results"]["a"] == ["1", "2"]  # the input is not changed
    assert report.sanitize(clean, hasher)["scenarios"][0]["results"] == clean["scenarios"][0]["results"]
    with pytest.raises(ValueError):
        report.sanitize(clean, IdHasher(b"x" * 32))
    # A converted version 1 run compares with a new run keyed with the same key.
    new = _run_doc(10.0, results={hasher.rekey("a"): [hasher.rekey("1"), hasher.rekey("9")]})
    new["id_hashing"] = hasher.describe()
    assert "0.5 (n=1)" in report.compare_markdown(clean, new)


def test_sanitize_inventory_drops_backup_ids_and_file_names():
    doc = {"kind": "inventory", "inventory": {
        "backups": [{"id": "full_2026-08-31_secret", "status": "SUCCESS", "size_gib": 1, "started": "2026-08-31"}],
        "disk": {"listed_via": "file list /home/someone/files.txt"}}}
    text = json.dumps(report.sanitize(doc, IdHasher(b"k" * 32)))
    assert "secret" not in text and "someone" not in text and "2026-08-31" in text


def test_compare_needs_the_same_hash_key_for_overlap():
    a, b = _run_doc(10.0), _run_doc(10.0)
    a["id_hashing"] = IdHasher(b"a" * 32).describe()
    b["id_hashing"] = IdHasher(b"b" * 32).describe()
    text = report.compare_markdown(a, b)
    assert "different keys" in text and "(n=" not in text


def test_compare_flags_setup_differences_and_reports_overlap():
    a = _run_doc(10.0)
    b = _run_doc(15.0, version="1.35.0", results={"a": ["1", "9"], "b": ["3", "4"]})
    text = report.compare_markdown(a, b)
    assert "Setup differs (Weaviate)" in text
    assert "+50%" in text
    assert "0.75 (n=2)" in text  # (1/2 + 2/2) / 2


def test_compare_warns_when_query_sets_differ():
    text = report.compare_markdown(_run_doc(10.0), _run_doc(10.0, fingerprint="f2"))
    assert "query sets differ" in text and "Setup differs (profile)" in text
