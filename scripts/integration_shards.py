"""Split the real-Weaviate integration suite into CI shards and prove nothing is lost (#683).

Stdlib only; run with the backend interpreter (``plan`` collects with its pytest):

    python scripts/integration_shards.py plan --shard 1 --total 2 --out DIR
    python scripts/integration_shards.py check DIR             # after pytest wrote DIR/junit.xml
    python scripts/integration_shards.py verify DIR [DIR ...]  # one DIR per shard
    python scripts/integration_shards.py durations JUNIT [JUNIT ...]

``plan`` collects ``pytest -m integration`` (the inventory ``make test-integration`` runs),
groups it by test file and assigns whole files to shards by measured wall time from
``tests/integration/shard_durations.json``. A file without a measurement, e.g. a new one,
is still assigned, weighted by its test count times the mean measured time per test, so
nothing depends on a hand-maintained list. Every shard computes the same partition and
records it with the full inventory in DIR/plan.json; DIR/files.txt lists its files.

``check`` compares the shard's JUnit report with its plan. ``verify`` (the required
"Integration tests" gate) requires shards 1..N to be present with identical inventories,
disjoint plans whose union is the inventory, and JUnit reports that executed exactly the
planned tests. ``durations`` rewrites the measurements from JUnit reports of a full run.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "semant_demo_backend"
DURATIONS = BACKEND / "tests" / "integration" / "shard_durations.json"
COLLECT = ["-m", "pytest", "--collect-only", "-q", "-m", "integration", "-p", "no:cacheprovider"]


class ShardError(Exception):
    pass


def collect(python: str = sys.executable) -> list[str]:
    """Node ids of ``pytest -m integration``, collected in the backend directory."""
    result = subprocess.run([python, *COLLECT], cwd=BACKEND, capture_output=True, text=True)
    if result.returncode != 0:
        raise ShardError(f"pytest collection failed (exit {result.returncode}):\n{result.stdout}{result.stderr}")
    nodeids = [line.strip() for line in result.stdout.splitlines() if "::" in line]
    if not nodeids:
        raise ShardError("pytest collected no integration tests")
    return nodeids


def file_of(nodeid: str) -> str:
    return nodeid.split("::", 1)[0]


def load_durations(path: Path = DURATIONS) -> dict[str, float]:
    if not path.exists():
        return {}
    return {name: float(seconds) for name, seconds in json.loads(path.read_text())["files"].items()}


def weights(counts: dict[str, int], durations: dict[str, float]) -> dict[str, float]:
    """Measured seconds per file; unmeasured files count their tests at the mean rate."""
    measured = {name: durations[name] for name in counts if name in durations}
    measured_tests = sum(counts[name] for name in measured)
    per_test = sum(measured.values()) / measured_tests if measured_tests else 1.0
    return {name: measured.get(name, counts[name] * per_test) for name in counts}


def partition(file_weights: dict[str, float], total: int) -> list[list[str]]:
    """Longest-processing-time-first assignment; deterministic for equal inputs."""
    if total < 1:
        raise ShardError("the shard total must be at least 1")
    if len(file_weights) < total:
        raise ShardError(f"{len(file_weights)} test files cannot fill {total} shards")
    shards: list[list[str]] = [[] for _ in range(total)]
    loads = [0.0] * total
    for name in sorted(file_weights, key=lambda n: (-file_weights[n], n)):
        target = min(range(total), key=lambda i: (loads[i], i))
        shards[target].append(name)
        loads[target] += file_weights[name]
    return [sorted(files) for files in shards]


def plan(shard: int, total: int, nodeids: list[str], durations: dict[str, float]) -> dict:
    if not 1 <= shard <= total:
        raise ShardError(f"shard {shard} is not in 1..{total}")
    duplicates = sorted(n for n, c in Counter(nodeids).items() if c > 1)
    if duplicates:
        raise ShardError(f"pytest collected duplicate node ids: {duplicates[:5]}")
    counts = Counter(file_of(n) for n in nodeids)
    file_weights = weights(counts, durations)
    shards = partition(file_weights, total)
    files = set(shards[shard - 1])
    return {
        "shard": shard,
        "total": total,
        "inventory": nodeids,
        "files": shards[shard - 1],
        "nodeids": [n for n in nodeids if file_of(n) in files],
        "estimates": [round(sum(file_weights[f] for f in s), 1) for s in shards],
        "unmeasured": sorted(f for f in counts if f not in durations),
    }


def junit_key(nodeid: str) -> tuple[str, str]:
    """The (classname, name) pytest's JUnit report gives a node id (``mangle_test_address``)."""
    path, bracket, params = nodeid.partition("[")
    names = path.split("::")
    names[0] = re.sub(r"\.py$", "", names[0].replace("/", "."))
    names[-1] += bracket + params
    return ".".join(names[:-1]), names[-1]


def read_junit(path: Path) -> list[dict]:
    if not path.exists():
        raise ShardError(f"missing JUnit report {path}")
    cases = []
    for case in ET.parse(path).getroot().iter("testcase"):
        outcome = "passed"
        for tag in ("failure", "error", "skipped"):
            if case.find(tag) is not None:
                outcome = {"failure": "failed", "error": "error", "skipped": "skipped"}[tag]
                break
        cases.append({"key": (case.get("classname", ""), case.get("name", "")),
                      "time": float(case.get("time") or 0), "outcome": outcome})
    return cases


def compare(planned: list[str], cases: list[dict]) -> list[str]:
    """Problems with a shard's JUnit report: planned tests missing, extra or run twice."""
    expected = Counter(junit_key(n) for n in planned)
    executed = Counter(case["key"] for case in cases)
    problems = []
    for label, keys in (("not executed", expected - executed), ("not planned", executed - expected)):
        if keys:
            shown = ", ".join("::".join(k) for k in sorted(keys)[:10])
            problems.append(f"{sum(keys.values())} test(s) {label}: {shown}")
    repeated = sorted(k for k, c in executed.items() if c > 1)
    if repeated:
        problems.append(f"{len(repeated)} test(s) reported more than once: "
                        + ", ".join("::".join(k) for k in repeated[:10]))
    return problems


def shard_row(data: dict, cases: list[dict]) -> str:
    outcomes = Counter(case["outcome"] for case in cases)
    seconds = sum(case["time"] for case in cases)
    return (f"| {data['shard']}/{data['total']} | {len(data['files'])} | {len(data['nodeids'])} | "
            f"{len(cases)} | {outcomes['passed']} | {outcomes['failed'] + outcomes['error']} | "
            f"{outcomes['skipped']} | {seconds / 60:.1f} | {data['estimates'][data['shard'] - 1] / 60:.1f} |")


HEADER = ("| Shard | Files | Planned | Reported | Passed | Failed | Skipped | Test min | Estimated min |\n"
          "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")


def load_shard(directory: Path) -> tuple[dict, list[dict]]:
    plan_path = directory / "plan.json"
    if not plan_path.exists():
        raise ShardError(f"missing shard plan {plan_path}")
    return json.loads(plan_path.read_text()), read_junit(directory / "junit.xml")


def verify(directories: list[Path]) -> tuple[list[str], list[str]]:
    """(markdown rows, problems) for the complete set of shard results."""
    rows, problems, shards = [], [], {}
    for directory in directories:
        try:
            data, cases = load_shard(directory)
        except ShardError as exc:
            problems.append(str(exc))
            continue
        if data["shard"] in shards:
            problems.append(f"shard {data['shard']} reported twice")
        shards[data["shard"]] = data
        rows.append(shard_row(data, cases))
        problems += [f"shard {data['shard']}/{data['total']}: {p}" for p in compare(data["nodeids"], cases)]
    if not shards:
        return rows, problems + ["no shard results"]
    totals = {data["total"] for data in shards.values()}
    if len(totals) != 1:
        problems.append(f"shards disagree on the shard total: {sorted(totals)}")
    missing = sorted(set(range(1, max(totals) + 1)) - set(shards))
    if missing:
        problems.append(f"missing shard(s): {missing}")
    inventories = {tuple(data["inventory"]) for data in shards.values()}
    if len(inventories) != 1:
        problems.append("shards collected different integration inventories")
    inventory = Counter(next(iter(inventories)))
    assigned = Counter(n for data in shards.values() for n in data["nodeids"])
    if not missing and assigned != inventory:
        lost, twice = inventory - assigned, assigned - inventory
        problems.append(f"plans do not partition the inventory: {sum(lost.values())} unassigned, "
                        f"{sum(twice.values())} assigned twice")
    return sorted(rows), problems


def summary(title: str, rows: list[str], problems: list[str], unmeasured: list[str]) -> str:
    lines = [f"### {title}", "", HEADER, *rows, ""]
    if unmeasured:
        lines.append(f"Unmeasured test files, weighted by test count: {', '.join(unmeasured)}. "
                     "Refresh `tests/integration/shard_durations.json` (see docs/DEVELOPMENT.md).")
        lines.append("")
    lines += [f"- :x: {p}" for p in problems] or ["Every planned test was reported exactly once."]
    return "\n".join(lines) + "\n"


def measure(junits: list[Path]) -> dict[str, float]:
    """Per-file wall time (setup + call + teardown) from JUnit reports of the suite."""
    seconds: Counter[str] = Counter()
    for junit in junits:
        for case in read_junit(junit):
            seconds[file_for_classname(case["key"][0])] += case["time"]
    return {name: round(value, 1) for name, value in sorted(seconds.items())}


def file_for_classname(classname: str) -> str:
    parts = classname.split(".")
    for end in range(len(parts), 0, -1):
        candidate = "/".join(parts[:end]) + ".py"
        if (BACKEND / candidate).is_file():
            return candidate
    raise ShardError(f"no test file for JUnit classname {classname!r}")


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
    d.add_argument("junits", type=Path, nargs="+")
    d.add_argument("--out", type=Path, default=DURATIONS)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            data = plan(args.shard, args.total, collect(), load_durations())
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / "plan.json").write_text(json.dumps(data, indent=1) + "\n")
            (args.out / "files.txt").write_text("\n".join(data["files"]) + "\n")
            print(f"Shard {args.shard}/{args.total}: {len(data['files'])} files, {len(data['nodeids'])} "
                  f"of {len(data['inventory'])} tests; estimated minutes per shard: "
                  + ", ".join(f"{s / 60:.1f}" for s in data["estimates"]))
            for name in data["unmeasured"]:
                print(f"unmeasured (weighted by test count): {name}")
            return 0
        if args.command == "check":
            data, cases = load_shard(args.directory)
            problems = compare(data["nodeids"], cases)
            print(summary(f"Integration shard {data['shard']}/{data['total']}", [shard_row(data, cases)],
                          problems, data["unmeasured"]))
            return 1 if problems else 0
        if args.command == "verify":
            rows, problems = verify(args.directories)
            print(summary("Integration shards", rows, problems, []))
            return 1 if problems else 0
        measured = measure(args.junits)
        args.out.write_text(json.dumps({
            "comment": "Per-file integration wall time in seconds for CI sharding; "
                       "regenerate with scripts/integration_shards.py durations (#683).",
            "files": measured}, indent=1) + "\n")
        print(f"wrote {len(measured)} files to {args.out}")
        return 0
    except ShardError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
