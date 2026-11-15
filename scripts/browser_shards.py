"""Split the Playwright browser suite into CI shards and prove nothing is lost (#685).

Stdlib only; ``plan`` needs the frontend's installed Playwright:

    python scripts/browser_shards.py plan --shard 1 --total 2 --out DIR
    python scripts/browser_shards.py check DIR             # after Playwright wrote DIR/report.json
    python scripts/browser_shards.py verify DIR [DIR ...]  # one DIR per shard
    python scripts/browser_shards.py durations REPORT [REPORT ...]

``plan`` lists the suite ``make test-e2e`` runs (``playwright test --list``) and assigns
whole spec files to shards by measured time from ``test/e2e/shard_durations.json``; an
unmeasured, e.g. new, file is weighted by its test count at the mean rate. Playwright's
own ``--shard`` cuts the alphabetical file list by test count, which measured 345 s and
168 s of test time for the two halves; whole files are kept because the specs run in
order on one worker against one seeded backend per shard.

``check`` compares the shard's JSON report with its plan. ``verify`` (the required
"Browser smoke tests" gate) requires shards 1..N with identical inventories, disjoint
plans covering the inventory and reports that executed exactly the planned tests.
``durations`` rewrites the measurements from the JSON reports of a complete run.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from integration_shards import ShardError, partition, weights  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "semant_demo_frontend"
TEST_DIR = FRONTEND / "test" / "e2e"
DURATIONS = TEST_DIR / "shard_durations.json"


def tests_in(report: dict) -> list[dict]:
    """One entry per (project, spec) in a Playwright JSON report, in report order."""
    found = []

    def walk(suite: dict, titles: list[str]) -> None:
        for spec in suite.get("specs", []):
            for test in spec["tests"]:
                found.append({
                    "key": f"{test['projectName']}:{spec['id']}",
                    "file": spec["file"],
                    "title": " › ".join([*titles, spec["title"]]),
                    "status": test["status"],
                    "results": test["results"],
                })
        for child in suite.get("suites", []):
            walk(child, [*titles, child["title"]])

    for top in report.get("suites", []):
        walk(top, [])
    return found


def collect() -> list[dict]:
    """The complete browser inventory as ``{key, file, title}``, without starting a server."""
    result = subprocess.run(["npx", "playwright", "test", "--list", "--reporter=json"],
                            cwd=FRONTEND, capture_output=True, text=True)
    if result.returncode != 0:
        raise ShardError(f"playwright --list failed (exit {result.returncode}):\n{result.stdout}{result.stderr}")
    report = json.loads(result.stdout)
    if report.get("errors"):
        raise ShardError(f"playwright reported load errors: {report['errors']}")
    inventory = [{k: t[k] for k in ("key", "file", "title")} for t in tests_in(report)]
    if not inventory:
        raise ShardError("playwright listed no browser tests")
    return inventory


def load_durations(path: Path = DURATIONS) -> dict[str, float]:
    if not path.exists():
        return {}
    return {name: float(seconds) for name, seconds in json.loads(path.read_text())["files"].items()}


def plan(shard: int, total: int, inventory: list[dict], durations: dict[str, float]) -> dict:
    if not 1 <= shard <= total:
        raise ShardError(f"shard {shard} is not in 1..{total}")
    duplicates = sorted(k for k, c in Counter(t["key"] for t in inventory).items() if c > 1)
    if duplicates:
        raise ShardError(f"playwright listed duplicate tests: {duplicates[:5]}")
    counts = Counter(t["file"] for t in inventory)
    file_weights = weights(counts, durations)
    shards = partition(file_weights, total)
    files = set(shards[shard - 1])
    return {
        "shard": shard,
        "total": total,
        "inventory": inventory,
        "files": shards[shard - 1],
        "tests": [t["key"] for t in inventory if t["file"] in files],
        "estimates": [round(sum(file_weights[f] for f in s), 1) for s in shards],
        "unmeasured": sorted(f for f in counts if f not in durations),
    }


def read_report(path: Path) -> tuple[list[dict], list[str]]:
    """(tests Playwright started, load/run errors) from a shard's JSON report."""
    if not path.exists():
        raise ShardError(f"missing Playwright report {path}")
    report = json.loads(path.read_text())
    errors = [(e.get("message") or str(e)).splitlines()[0] for e in report.get("errors", [])]
    return [t for t in tests_in(report) if t["results"]], errors


def compare(data: dict, executed: list[dict]) -> list[str]:
    """Problems with a shard's report: planned tests missing, extra or run twice."""
    titles = {t["key"]: f"{t['file']} › {t['title']}" for t in data["inventory"]}
    expected = Counter(data["tests"])
    reported = Counter(t["key"] for t in executed)
    problems = []
    for label, keys in (("not executed", expected - reported), ("not planned", reported - expected)):
        if keys:
            shown = ", ".join(titles.get(k, k) for k in sorted(keys)[:10])
            problems.append(f"{sum(keys.values())} test(s) {label}: {shown}")
    skipped = [t for t in executed if t["status"] == "skipped"]
    if skipped:
        problems.append(f"{len(skipped)} test(s) skipped: "
                        + ", ".join(titles.get(t["key"], t["key"]) for t in skipped[:10]))
    repeated = sorted(k for k, c in reported.items() if c > 1)
    if repeated:
        problems.append(f"{len(repeated)} test(s) reported more than once: "
                        + ", ".join(titles.get(k, k) for k in repeated[:10]))
    return problems


def shard_row(data: dict, executed: list[dict]) -> str:
    outcomes = Counter(t["status"] for t in executed)
    seconds = sum(r.get("duration", 0) for t in executed for r in t["results"]) / 1000
    return (f"| {data['shard']}/{data['total']} | {len(data['files'])} | {len(data['tests'])} | "
            f"{len(executed)} | {outcomes['expected']} | {outcomes['unexpected']} | {outcomes['flaky']} | "
            f"{outcomes['skipped']} | {seconds / 60:.1f} | {data['estimates'][data['shard'] - 1] / 60:.1f} |")


HEADER = ("| Shard | Files | Planned | Reported | Passed | Failed | Flaky | Skipped | Test min | Estimated min |\n"
          "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")


def load_shard(directory: Path) -> tuple[dict, list[dict], list[str]]:
    plan_path = directory / "plan.json"
    if not plan_path.exists():
        raise ShardError(f"missing shard plan {plan_path}")
    return (json.loads(plan_path.read_text()), *read_report(directory / "report.json"))


def verify(directories: list[Path]) -> tuple[list[str], list[str]]:
    """(markdown rows, problems) for the complete set of shard results."""
    rows, problems, shards = [], [], {}
    for directory in directories:
        try:
            data, executed, errors = load_shard(directory)
        except ShardError as exc:
            problems.append(str(exc))
            continue
        if data["shard"] in shards:
            problems.append(f"shard {data['shard']} reported twice")
        shards[data["shard"]] = data
        rows.append(shard_row(data, executed))
        label = f"shard {data['shard']}/{data['total']}"
        problems += [f"{label}: {p}" for p in compare(data, executed)]
        problems += [f"{label}: Playwright error: {e}" for e in errors]
    if not shards:
        return rows, problems + ["no shard results"]
    totals = {data["total"] for data in shards.values()}
    if len(totals) != 1:
        problems.append(f"shards disagree on the shard total: {sorted(totals)}")
    missing = sorted(set(range(1, max(totals) + 1)) - set(shards))
    if missing:
        problems.append(f"missing shard(s): {missing}")
    inventories = {json.dumps(data["inventory"], sort_keys=True) for data in shards.values()}
    if len(inventories) != 1:
        problems.append("shards listed different browser inventories")
    inventory = Counter(t["key"] for t in next(iter(shards.values()))["inventory"])
    assigned = Counter(k for data in shards.values() for k in data["tests"])
    if not missing and assigned != inventory:
        lost, twice = inventory - assigned, assigned - inventory
        problems.append(f"plans do not partition the inventory: {sum(lost.values())} unassigned, "
                        f"{sum(twice.values())} assigned twice")
    return sorted(rows), problems


def summary(title: str, rows: list[str], problems: list[str], unmeasured: list[str]) -> str:
    lines = [f"### {title}", "", HEADER, *rows, ""]
    if unmeasured:
        lines.append(f"Unmeasured spec files, weighted by test count: {', '.join(unmeasured)}. "
                     "Refresh `test/e2e/shard_durations.json` (see docs/DEVELOPMENT.md).")
        lines.append("")
    lines += [f"- :x: {p}" for p in problems] or ["Every planned test was reported exactly once."]
    return "\n".join(lines) + "\n"


def measure(reports: list[Path]) -> dict[str, float]:
    """Per-file test time (hooks and fixtures included) from the reports of a complete run."""
    seconds: Counter[str] = Counter()
    for report in reports:
        for test in read_report(report)[0]:
            seconds[test["file"]] += sum(r.get("duration", 0) for r in test["results"]) / 1000
    return {name: round(value, 1) for name, value in sorted(seconds.items())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("plan")
    p.add_argument("--shard", type=int, required=True)
    p.add_argument("--total", type=int, required=True)
    p.add_argument("--out", type=Path, required=True)
    c = commands.add_parser("check")
    c.add_argument("directory", type=Path)
    v = commands.add_parser("verify")
    v.add_argument("directories", type=Path, nargs="*")
    d = commands.add_parser("durations")
    d.add_argument("reports", type=Path, nargs="+")
    d.add_argument("--out", type=Path, default=DURATIONS)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            data = plan(args.shard, args.total, collect(), load_durations())
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / "plan.json").write_text(json.dumps(data, indent=1) + "\n")
            # Paths relative to the frontend, as the Playwright command line takes them.
            (args.out / "files.txt").write_text(
                "".join(f"{TEST_DIR.relative_to(FRONTEND) / name}\n" for name in data["files"]))
            print(f"Shard {args.shard}/{args.total}: {len(data['files'])} files, {len(data['tests'])} "
                  f"of {len(data['inventory'])} tests; estimated minutes per shard: "
                  + ", ".join(f"{s / 60:.1f}" for s in data["estimates"]))
            for name in data["unmeasured"]:
                print(f"unmeasured (weighted by test count): {name}")
            return 0
        if args.command == "check":
            data, executed, errors = load_shard(args.directory)
            problems = compare(data, executed) + [f"Playwright error: {e}" for e in errors]
            print(summary(f"Browser shard {data['shard']}/{data['total']}", [shard_row(data, executed)],
                          problems, data["unmeasured"]))
            return 1 if problems else 0
        if args.command == "verify":
            rows, problems = verify(args.directories)
            print(summary("Browser shards", rows, problems, []))
            return 1 if problems else 0
        measured = measure(args.reports)
        args.out.write_text(json.dumps({
            "comment": "Per-file Playwright test time in seconds for CI sharding; "
                       "regenerate with scripts/browser_shards.py durations (#685).",
            "files": measured}, indent=1) + "\n")
        print(f"wrote {len(measured)} files to {args.out}")
        return 0
    except ShardError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
