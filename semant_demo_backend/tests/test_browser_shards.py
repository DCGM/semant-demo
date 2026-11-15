"""CI browser-test sharding, scripts/browser_shards.py (#685).

The partition must cover the ``playwright test --list`` inventory exactly once, new spec
files included, and the gate's verification must catch lost, duplicated or missing shards.
"""
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("browser_shards", ROOT / "scripts" / "browser_shards.py")
shards = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shards)

SPECS = {"a.spec.ts": ["one", "two"], "b.spec.ts": ["three"], "c.spec.ts": ["four", "five"], "new.spec.ts": ["six"]}
DURATIONS = {"a.spec.ts": 30.0, "b.spec.ts": 50.0, "c.spec.ts": 20.0, "gone.spec.ts": 99.0}


def report(specs=SPECS, ran=True, statuses=None, duplicate=None):
    """A Playwright JSON report; ``ran=False`` is what ``--list`` prints."""
    suites = []
    for file, titles in specs.items():
        entries = []
        for title in titles + ([duplicate] if duplicate in titles else []):
            status = (statuses or {}).get(title, "expected") if ran else "skipped"
            results = [{"status": "passed", "duration": 1500}] if ran else []
            entries.append({"title": title, "id": f"id-{title}", "file": file,
                            "tests": [{"projectName": "chromium", "status": status, "results": results}]})
        # Specs inside a describe block, as Playwright nests them.
        suites.append({"title": file, "file": file, "specs": entries[:1],
                       "suites": [{"title": "group", "specs": entries[1:]}]})
    return {"suites": suites, "errors": [], "stats": {}}


INVENTORY = [{k: t[k] for k in ("key", "file", "title")} for t in shards.tests_in(report(ran=False))]


def write_shard(directory: Path, data, run=None):
    directory.mkdir(parents=True)
    (directory / "plan.json").write_text(json.dumps(data))
    executed = {f: t for f, t in SPECS.items() if f in data["files"]}
    (directory / "report.json").write_text(json.dumps(run if run is not None else report(executed)))
    return directory


def test_inventory_keys_tests_by_project_and_id_with_describe_titles():
    assert [t["key"] for t in INVENTORY] == [f"chromium:id-{t}" for t in ("one", "two", "three", "four", "five", "six")]
    assert INVENTORY[1]["title"] == "group › two"


def test_plans_partition_the_inventory_once_including_unmeasured_files():
    plans = [shards.plan(i, 2, INVENTORY, DURATIONS) for i in (1, 2)]

    assert sorted(k for p in plans for k in p["tests"]) == sorted(t["key"] for t in INVENTORY)
    assert all(p["files"] for p in plans)
    assert plans[0]["unmeasured"] == ["new.spec.ts"]
    # The new file weighs its one test at the measured mean (100 s / 5 tests).
    assert sorted(plans[0]["estimates"]) == [50.0, 70.0]


def test_more_shards_than_files_is_refused_rather_than_running_an_empty_selection():
    # Playwright given no file arguments would run the whole suite in that shard.
    with pytest.raises(shards.ShardError):
        shards.plan(1, 5, INVENTORY, DURATIONS)


def test_verify_accepts_complete_shards(tmp_path):
    dirs = [write_shard(tmp_path / str(i), shards.plan(i, 2, INVENTORY, DURATIONS)) for i in (1, 2)]

    rows, problems = shards.verify(dirs)

    assert problems == []
    assert len(rows) == 2


def test_verify_reports_a_missing_shard_or_report(tmp_path):
    one = write_shard(tmp_path / "1", shards.plan(1, 2, INVENTORY, DURATIONS))
    two = write_shard(tmp_path / "2", shards.plan(2, 2, INVENTORY, DURATIONS))
    (two / "report.json").unlink()  # e.g. the backend never started

    _, problems = shards.verify([one, two, tmp_path / "absent"])

    assert any("missing Playwright report" in p for p in problems)
    assert any("missing shard plan" in p for p in problems)
    assert any("missing shard(s): [2]" in p for p in problems)
    assert shards.verify([])[1] == ["no shard results"]


def test_verify_reports_tests_not_executed_or_executed_twice(tmp_path):
    one, two = (shards.plan(i, 2, INVENTORY, DURATIONS) for i in (1, 2))
    first_file = one["files"][0]
    partial = report({f: t for f, t in SPECS.items() if f in one["files"] and f != first_file})
    doubled = report({f: t for f, t in SPECS.items() if f in two["files"] + [first_file]},
                     duplicate=SPECS[two["files"][0]][0])

    _, problems = shards.verify([write_shard(tmp_path / "1", one, partial),
                                 write_shard(tmp_path / "2", two, doubled)])

    assert any(p.startswith("shard 1/2:") and "not executed" in p for p in problems)
    assert any(p.startswith("shard 2/2:") and "not planned" in p for p in problems)
    assert any(p.startswith("shard 2/2:") and "reported more than once" in p for p in problems)


def test_verify_reports_plans_that_overlap_or_disagree_and_playwright_errors(tmp_path):
    one = shards.plan(1, 2, INVENTORY, DURATIONS)
    two = shards.plan(2, 2, INVENTORY, DURATIONS)
    overlapping = dict(two, tests=two["tests"] + one["tests"][:1])
    other_inventory = dict(two, inventory=INVENTORY[:-1])
    failed_load = dict(report({}), errors=[{"message": "Error: cannot load spec\n  at x"}])

    _, overlap = shards.verify([write_shard(tmp_path / "a1", one), write_shard(tmp_path / "a2", overlapping)])
    _, differ = shards.verify([write_shard(tmp_path / "b1", one), write_shard(tmp_path / "b2", other_inventory)])
    _, errors = shards.verify([write_shard(tmp_path / "c1", one, failed_load)])

    assert any("assigned twice" in p for p in overlap)
    assert any("different browser inventories" in p for p in differ)
    assert "shard 1/2: Playwright error: Error: cannot load spec" in errors


def test_check_counts_outcomes(tmp_path, capsys):
    data = shards.plan(1, 2, INVENTORY, DURATIONS)
    titles = [t for f in data["files"] for t in SPECS[f]]
    run = report({f: SPECS[f] for f in data["files"]}, statuses={titles[0]: "unexpected"})
    directory = write_shard(tmp_path / "1", data, run)

    # A failing test is the Playwright step's verdict; check only compares plan and report.
    assert shards.main(["check", str(directory)]) == 0
    row = next(line for line in capsys.readouterr().out.splitlines() if line.startswith("| 1/2"))
    cells = [c.strip() for c in row.split("|")[1:-1]]
    assert cells[3:6] == [str(len(titles)), str(len(titles) - 1), "1"]


def test_durations_are_measured_per_file(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report()))

    assert shards.measure([path]) == {"a.spec.ts": 3.0, "b.spec.ts": 1.5, "c.spec.ts": 3.0, "new.spec.ts": 1.5}


def test_committed_durations_name_existing_spec_files():
    names = set(shards.load_durations())

    assert names
    assert names <= {p.name for p in shards.TEST_DIR.glob("*.spec.ts")}


def test_required_browser_check_gates_on_every_shard():
    jobs = yaml.safe_load((ROOT / ".github" / "workflows" / "ci-cd.yml").read_text())["jobs"]
    gate, shard = jobs["test-browser"], jobs["test-browser-shard"]

    assert gate["name"] == "Browser smoke tests"
    assert gate["needs"] == ["test-browser-shard"]
    assert gate["if"].startswith("always()")
    assert shard["strategy"]["fail-fast"] is False
    assert "matrix.shard" in shard["env"]["SEMANT_TEST_STORE_TOKEN"]
