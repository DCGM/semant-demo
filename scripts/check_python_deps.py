"""Fail fast when a Python environment does not match the backend development lock (#673).

Run with the interpreter to check (stdlib only, so it works in a broken environment):

    .venv/bin/python scripts/check_python_deps.py

Compares every ``name==version`` pin of semant_demo_backend/requirements-dev.lock with the
installed distributions and checks that the backend package itself is installed. It does
not resolve or install anything. An environment shared with another checkout (``PYTHON=``
override) passes as long as it has the locked versions.
"""

from __future__ import annotations

import re
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "semant_demo_backend" / "requirements-dev.lock"
PROJECT = "semantdemobackend"
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)\s*(?:;([^\\]*))?")


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def applies(marker: str | None) -> bool:
    if not marker or not marker.strip():
        return True
    try:
        from packaging.markers import Marker
    except ImportError:  # cannot evaluate it; do not report a possibly irrelevant pin
        return False
    return Marker(marker).evaluate()


def same_version(installed: str, locked: str) -> bool:
    if installed == locked:
        return True
    try:
        from packaging.version import Version
    except ImportError:
        return False
    try:
        return Version(installed) == Version(locked)
    except ValueError:
        return False


def locked_pins(text: str) -> dict[str, str]:
    pins = {}
    for line in text.splitlines():
        match = PIN.match(line)
        if match and applies(match.group(3)):
            pins[normalize(match.group(1))] = match.group(2)
    return pins


def problems(pins: dict[str, str], installed: dict[str, str]) -> list[str]:
    found = []
    for name, version in sorted(pins.items()):
        have = installed.get(name)
        if have is None:
            found.append(f"{name}=={version} is missing")
        elif not same_version(have, version):
            found.append(f"{name} is {have}, locked {version}")
    if PROJECT not in installed:
        found.append(f"the backend package ({PROJECT}) is not installed")
    return found


def installed_versions() -> dict[str, str]:
    versions = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if name:
            versions.setdefault(normalize(name), dist.version)
    return versions


def main() -> int:
    found = problems(locked_pins(LOCK.read_text(encoding="utf-8")), installed_versions())
    if not found:
        return 0
    shown = found[:10] + ([f"... and {len(found) - 10} more"] if len(found) > 10 else [])
    lock = LOCK.relative_to(ROOT)
    python = sys.executable
    print(f"Python environment {sys.prefix} ({python}) does not match {lock}:", file=sys.stderr)
    for line in shown:
        print(f"  - {line}", file=sys.stderr)
    default = (ROOT / ".venv").resolve()
    if Path(sys.prefix).resolve() == default:
        print("Repair: make setup", file=sys.stderr)
    else:
        print(
            "This is not this checkout's .venv (PYTHON override?). Repair that environment, or "
            "run make setup here and drop the override:\n"
            f"  {python} -m pip install -r {LOCK}\n"
            f"  {python} -m pip install --no-deps -e {LOCK.parent}",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
