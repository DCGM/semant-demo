"""Guards of the fast browser-test loop, scripts/e2e-dev.sh (#272).

No Docker, server or network: `npx` and `docker` are stubs that record calls, state lives in
a temporary E2E_DEV_STATE, and every case ends before the script would reach a server.
"""
import os
import signal
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "e2e-dev.sh"


@pytest.fixture
def loop(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    for tool in ("npx", "docker"):
        stub = bin_dir / tool
        stub.write_text(f'#!/bin/sh\necho "{tool} $*" >>"{calls}"\n')
        stub.chmod(0o755)
    state = tmp_path / "state"
    state.mkdir()
    base_env = {k: v for k, v in os.environ.items()
                if not k.startswith(("E2E_", "SEMANT_TEST_"))}
    base_env.update(PATH=f"{bin_dir}:{os.environ['PATH']}", E2E_DEV_STATE=str(state))

    def run(*args, **env):
        result = subprocess.run([str(SCRIPT), *args], env={**base_env, **env}, cwd=ROOT,
                                capture_output=True, text=True, timeout=60)
        result.calls = calls.read_text() if calls.exists() else ""
        return result

    run.state = state
    return run


@pytest.fixture
def running_session(loop):
    """A live process group recorded as a profile started on port 8790 (it serves nothing)."""
    sleeper = subprocess.Popen(["sleep", "60"], start_new_session=True)
    (loop.state / "server.pid").write_text(f"{sleeper.pid}\n")
    (loop.state / "server.port").write_text("8790\n")
    yield sleeper
    os.killpg(sleeper.pid, signal.SIGKILL)
    sleeper.wait()


@pytest.mark.parametrize("command", ["start", "restart"])
def test_start_refuses_an_inherited_external_weaviate(loop, command):
    result = loop(command, SEMANT_TEST_WEAVIATE_HOST="127.0.0.1")

    assert result.returncode == 1
    assert "SEMANT_TEST_WEAVIATE_HOST is set" in result.stderr
    assert result.calls == ""  # neither built nor started a container


@pytest.mark.parametrize("args", [[], ["--headed"], ["--project=chromium"], ["--project", "chromium"], ["smoke"]])
def test_test_without_a_selection_does_not_run_the_suite(loop, args):
    result = loop("test", *args)

    assert result.returncode == 1
    assert "select a spec path or --grep" in result.stderr
    assert result.calls == ""


@pytest.mark.parametrize("args", [
    ["--all"], ["--all", "--headed"], ["test/e2e/smoke.spec.ts"], ["--grep", "login"],
    ["--grep=login", "--headed"], ["test/e2e"],
])
def test_selected_or_all_runs_reach_the_server_check(loop, args):
    result = loop("test", *args)

    assert result.returncode == 1
    assert "not running" in result.stderr
    assert result.calls == ""


def test_test_refuses_a_missing_spec_file(loop):
    result = loop("test", "test/e2e/no-such.spec.ts")

    assert result.returncode == 1
    assert "no such spec file" in result.stderr


def test_a_build_is_current_only_for_the_port_it_was_built_for(loop):
    built = loop("rebuild", E2E_DEV_PORT="8790")
    assert built.returncode == 0, built.stderr
    assert "BACKEND_URL :8790" in built.stderr

    assert "frontend build: current for port 8790" in loop("status", E2E_DEV_PORT="8790").stdout
    assert "frontend build: stale for port 8775" in loop("status").stdout


def test_a_running_profile_keeps_its_port(loop, running_session):
    for command in (["test", "test/e2e/smoke.spec.ts"], ["capture"], ["rebuild"], ["start"]):
        result = loop(*command, E2E_DEV_PORT="8791")
        assert result.returncode == 1, command
        assert "the running profile uses port 8790, not E2E_DEV_PORT=8791" in result.stderr
    assert loop().calls == ""


def test_status_and_stop_work_before_anything_was_started(loop):
    status = loop("status")
    assert status.returncode == 0, status.stderr
    assert "not running" in status.stdout

    stop = loop("stop")
    assert stop.returncode == 0, stop.stderr
    assert stop.calls == ""
