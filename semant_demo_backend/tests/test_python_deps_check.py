"""The Python dependency preflight, scripts/check_python_deps.py (#673).

The script is copied into a temporary checkout with its own lock and run with this test
interpreter, so "installed" is whatever this environment has; nothing is installed.
"""
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_python_deps.py"
PYTEST = f"pytest=={metadata.version('pytest')}"


def run(script):
    return subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=60)


@pytest.fixture
def checkout(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "semant_demo_backend").mkdir()
    shutil.copy(SCRIPT, tmp_path / "scripts")

    def with_lock(text):
        (tmp_path / "semant_demo_backend" / "requirements-dev.lock").write_text(text)
        return tmp_path / "scripts" / SCRIPT.name

    with_lock.root = tmp_path
    return with_lock


def test_this_environment_matches_the_real_lock():
    result = run(SCRIPT)

    assert result.returncode == 0, result.stderr


def test_a_matching_environment_passes_quietly(checkout):
    result = run(checkout(f"{PYTEST} \\\n    --hash=sha256:00\n    # via -r requirements-dev.txt\n"))

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_missing_and_differently_versioned_packages_are_named(checkout):
    result = run(checkout(f"no-such-package-673==1.0 \\\n    --hash=sha256:00\npytest==0.0.1\n"))

    assert result.returncode == 1
    assert "no-such-package-673==1.0 is missing" in result.stderr
    assert f"pytest is {metadata.version('pytest')}, locked 0.0.1" in result.stderr
    assert "requirements-dev.lock" in result.stderr


def test_names_match_regardless_of_case_and_separators(checkout):
    result = run(checkout(f"{PYTEST.upper()}\nTyping.Extensions=={metadata.version('typing-extensions')}\n"))

    assert result.returncode == 0, result.stderr


def test_pins_for_another_platform_are_ignored(checkout):
    result = run(checkout('no-such-package-673==1.0 ; sys_platform == "no-such-platform"\n'))

    assert result.returncode == 0, result.stderr


def test_another_checkouts_environment_gets_explicit_pip_commands(checkout):
    result = run(checkout("no-such-package-673==1.0\n"))

    assert "PYTHON override" in result.stderr
    assert f" -m pip install -r {checkout.root}" in result.stderr


def test_the_checkouts_own_venv_is_repaired_with_make_setup(checkout):
    (checkout.root / ".venv").symlink_to(sys.prefix)

    result = run(checkout("no-such-package-673==1.0\n"))

    assert "Repair: make setup" in result.stderr
