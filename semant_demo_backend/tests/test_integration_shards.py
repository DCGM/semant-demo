"""CI integration sharding, scripts/integration_shards.py (#683).

The partition must cover the real ``pytest -m integration`` inventory exactly once, new
files included, and the gate's verification must catch lost, duplicated or missing shards.
"""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("integration_shards", ROOT / "scripts" / "integration_shards.py")
shards = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shards)

NODEIDS = [
    "tests/integration/test_a.py::test_one",
    "tests/integration/test_a.py::TestCase::test_two[x-1]",
    "tests/integration/test_b.py::test_three",
    "tests/integration/test_c.py::test_four[a::b]",
    "tests/integration/test_c.py::test_five",
    "tests/integration/test_new.py::test_six",
]
DURATIONS = {"tests/integration/test_a.py": 30.0, "tests/integration/test_b.py": 50.0,
             "tests/integration/test_c.py": 20.0, "tests/integration/test_gone.py": 99.0}


def junit(path: Path, nodeids, outcome=None):
    cases = []
    for nodeid in nodeids:
        classname, name = shards.junit_key(nodeid)
        child = f"<{outcome} message='x'/>" if outcome else ""
        cases.append(f'<testcase classname="{classname}" name="{name}" time="1.5">{child}</testcase>')
    path.write_text(f'<testsuites><testsuite name="pytest">{"".join(cases)}</testsuite></testsuites>')


def write_shard(directory: Path, data, executed=None):
    directory.mkdir(parents=True)
    (directory / "plan.json").write_text(json.dumps(data))
    junit(directory / "junit.xml", data["nodeids"] if executed is None else executed)
    return directory


def test_plans_partition_the_inventory_once_including_unmeasured_files():
    plans = [shards.plan(i, 2, NODEIDS, DURATIONS) for i in (1, 2)]

    assigned = [n for p in plans for n in p["nodeids"]]
    assert sorted(assigned) == sorted(NODEIDS)
    assert all(p["files"] for p in plans)
    assert plans[0]["unmeasured"] == ["tests/integration/test_new.py"]
    # The new file weighs its one test at the measured mean (100 s / 5 tests).
    assert sorted(plans[0]["estimates"]) == [50.0, 70.0]


def test_partition_balances_by_time_not_count_and_is_deterministic():
    weights = {"big.py": 100.0, "m1.py": 40.0, "m2.py": 35.0, "s1.py": 20.0, "s2.py": 5.0}

    result = shards.partition(weights, 2)

    assert result == [["big.py"], ["m1.py", "m2.py", "s1.py", "s2.py"]]
    assert shards.partition(dict(reversed(weights.items())), 2) == result


def test_without_measurements_files_are_weighted_by_test_count():
    assert shards.weights({"a.py": 3, "b.py": 1}, {}) == {"a.py": 3.0, "b.py": 1.0}


@pytest.mark.parametrize("shard,total", [(0, 2), (3, 2)])
def test_out_of_range_shard_is_refused(shard, total):
    with pytest.raises(shards.ShardError):
        shards.plan(shard, total, NODEIDS, DURATIONS)


def test_more_shards_than_files_is_refused_rather_than_running_an_empty_selection():
    # pytest given no file arguments would run the whole suite in that shard.
    with pytest.raises(shards.ShardError):
        shards.partition({"a.py": 1.0}, 2)


def test_junit_keys_match_pytest_mangling():
    assert shards.junit_key("tests/integration/test_a.py::TestCase::test_two[x-1]") == (
        "tests.integration.test_a.TestCase", "test_two[x-1]")
    assert shards.junit_key("tests/integration/test_c.py::test_four[a::b]") == (
        "tests.integration.test_c", "test_four[a::b]")


def test_verify_accepts_complete_shards(tmp_path):
    dirs = [write_shard(tmp_path / str(i), shards.plan(i, 2, NODEIDS, DURATIONS)) for i in (1, 2)]

    rows, problems = shards.verify(dirs)

    assert problems == []
    assert len(rows) == 2


def test_verify_reports_a_missing_shard(tmp_path):
    only = write_shard(tmp_path / "1", shards.plan(1, 2, NODEIDS, DURATIONS))

    _, problems = shards.verify([only, tmp_path / "absent"])

    assert any("missing shard plan" in p for p in problems)
    assert any("missing shard(s): [2]" in p for p in problems)
    assert shards.verify([])[1] == ["no shard results"]


def test_verify_reports_tests_not_executed_or_executed_twice(tmp_path):
    one, two = (shards.plan(i, 2, NODEIDS, DURATIONS) for i in (1, 2))
    dirs = [write_shard(tmp_path / "1", one, executed=one["nodeids"][1:]),
            write_shard(tmp_path / "2", two, executed=two["nodeids"] + two["nodeids"][:1])]

    _, problems = shards.verify(dirs)

    assert any("shard 1/2: 1 test(s) not executed" in p for p in problems)
    assert any("shard 2/2: 1 test(s) not planned" in p for p in problems)
    assert any("shard 2/2: 1 test(s) reported more than once" in p for p in problems)


def test_verify_reports_plans_that_overlap_or_disagree(tmp_path):
    one = shards.plan(1, 2, NODEIDS, DURATIONS)
    two = shards.plan(2, 2, NODEIDS, DURATIONS)
    overlapping = dict(two, nodeids=two["nodeids"] + one["nodeids"][:1])
    other_inventory = dict(two, inventory=NODEIDS[:-1])

    _, overlap = shards.verify([write_shard(tmp_path / "a1", one), write_shard(tmp_path / "a2", overlapping)])
    _, differ = shards.verify([write_shard(tmp_path / "b1", one), write_shard(tmp_path / "b2", other_inventory)])

    assert any("assigned twice" in p for p in overlap)
    assert any("different integration inventories" in p for p in differ)


def test_check_counts_outcomes(tmp_path, capsys):
    data = shards.plan(1, 2, NODEIDS, DURATIONS)
    directory = write_shard(tmp_path / "1", data)
    junit(directory / "junit.xml", data["nodeids"], outcome="failure")

    # A failing test is the pytest step's verdict; check only compares plan and report.
    assert shards.main(["check", str(directory)]) == 0
    row = next(line for line in capsys.readouterr().out.splitlines() if line.startswith("| 1/2"))
    assert row.split("|")[6].strip() == str(len(data["nodeids"]))


def test_real_inventory_is_partitioned_with_committed_durations():
    nodeids = shards.collect()
    durations = shards.load_durations()
    plans = [shards.plan(i, 2, nodeids, durations) for i in (1, 2)]

    assert sorted(n for p in plans for n in p["nodeids"]) == sorted(nodeids)
    assert not set(plans[0]["files"]) & set(plans[1]["files"])
