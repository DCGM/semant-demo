"""`make test-integration ARGS=...` passes quoted pytest arguments intact (#696).

No Docker or Weaviate: SEMANT_TEST_WEAVIATE_HOST makes scripts/with-test-weaviate.sh run its
command directly, and PYTHON is a stub that records the argv and working directory it gets.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

PYTHON_STUB = r"""#!/bin/sh
# deps-check-backend runs `$PYTHON scripts/check_python_deps.py`; accept it silently.
[ "$1" = "-m" ] || exit 0
pwd >"$RECORD"
for arg in "$@"; do printf '%s\n' "$arg" >>"$RECORD"; done
"""

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="needs make")


def _pytest_argv(tmp_path, args):
    stub = tmp_path / "python"
    stub.write_text(PYTHON_STUB)
    stub.chmod(0o755)
    record = tmp_path / "record"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SEMANT_", "MAKE"))}
    env.update(SEMANT_TEST_WEAVIATE_HOST="127.0.0.1", SEMANT_TEST_STORE_TOKEN="stub", RECORD=str(record))
    command = ["make", "--no-print-directory", "test-integration", f"PYTHON={stub}"]
    if args is not None:
        command.append(f"ARGS={args}")
    subprocess.run(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                   text=True, timeout=60, check=True)
    cwd, *argv = record.read_text().splitlines()
    assert Path(cwd) == ROOT / "semant_demo_backend"
    return argv


@pytest.mark.parametrize(("args", "expected"), [
    (None, []),
    ("tests/integration/test_annotations.py -k bulk", ["tests/integration/test_annotations.py", "-k", "bulk"]),
    ("tests/integration/test_access.py -k 'case_a or case_b'",
     ["tests/integration/test_access.py", "-k", "case_a or case_b"]),
    ("-k \"(a and not b) or c\" -x", ["-k", "(a and not b) or c", "-x"]),
])
def test_args_reach_pytest_intact(tmp_path, args, expected):
    assert _pytest_argv(tmp_path, args) == ["-m", "pytest", "-m", "integration", *expected]
