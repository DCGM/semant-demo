"""Opt-in timing of integration-fixture phases (#686).

Disabled unless ``SEMANT_FIXTURE_PROFILE`` names an output file, e.g.::

    SEMANT_FIXTURE_PROFILE=/tmp/profile.json make test-integration

``phase(name)`` then records the wall time of each fixture step per test. Names are
dotted; a dotted name's time is part of its parent's (``reset`` includes
``reset.delete_objects``). The integration conftest adds pytest's setup/call/teardown
durations, prints a ranking at the end of the run and writes every record to the file.
"""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path

ENV = "SEMANT_FIXTURE_PROFILE"

_path = os.environ.get(ENV)
_records: list[dict] = []
_test = {"id": ""}


def enabled() -> bool:
    return bool(_path)


@contextmanager
def phase(name: str):
    if not _path:
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        _records.append({"test": _test["id"], "phase": name, "seconds": time.perf_counter() - start})


def start_test(nodeid: str) -> None:
    _test["id"] = nodeid


def record(nodeid: str, name: str, seconds: float) -> None:
    if _path:
        _records.append({"test": nodeid, "phase": name, "seconds": seconds})


def ranking() -> list[tuple[str, int, float]]:
    """(phase, occurrences, total seconds), largest total first."""
    count: dict[str, int] = defaultdict(int)
    total: dict[str, float] = defaultdict(float)
    for r in _records:
        count[r["phase"]] += 1
        total[r["phase"]] += r["seconds"]
    return sorted(((p, count[p], total[p]) for p in total), key=lambda row: -row[2])


def write() -> Path | None:
    if not _path:
        return None
    path = Path(_path)
    path.write_text(json.dumps({"records": _records}, indent=0) + "\n")
    return path


def report_lines() -> list[str]:
    rows = ranking()
    lines = [f"{'phase':<40} {'count':>6} {'total s':>9} {'mean ms':>9}"]
    lines += [f"{p:<40} {n:>6} {t:>9.1f} {1000 * t / n:>9.1f}" for p, n, t in rows]
    return lines
