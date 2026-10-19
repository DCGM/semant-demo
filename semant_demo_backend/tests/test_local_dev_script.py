"""Guards of the local development launcher, scripts/local-dev.sh (#438).

No Docker, Weaviate or backend: `docker` and `curl` are stubs that record calls and answer
as configured, PYTHON is a stub recording which `tests.local_dev` commands would run.
"""
import os
import socket
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "local-dev.sh"
LABEL = "local-development"

DOCKER_STUB = r"""#!/bin/sh
echo "docker $*" >>"$CALLS"
case "$*" in
  "volume inspect --format"*) echo "$STUB_VOLUME_LABEL" ;;
  "volume inspect "*) [ -n "$STUB_VOLUME_LABEL" ] || exit 1 ;;
  "container inspect --format {{.State.Running}}"*) [ -n "$STUB_CONTAINER_LABEL" ] && echo true ;;
  "container inspect --format {{ index .Config.Labels"*) echo "$STUB_CONTAINER_LABEL" ;;
  "container inspect --format {{range"*) echo semant-local-weaviate ;;
  "container inspect "*) [ -n "$STUB_CONTAINER_LABEL" ] || exit 1 ;;
  "port "*" 8080/tcp") echo "$STUB_PORT" ;;
  "port "*" 50051/tcp") echo "$STUB_GRPC_PORT" ;;
esac
exit 0
"""


@pytest.fixture
def launcher(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    (bin_dir / "docker").write_text(DOCKER_STUB)
    (bin_dir / "curl").write_text("#!/bin/sh\nexit 0\n")
    python = tmp_path / "python"
    python.write_text(f'#!/bin/sh\necho "python $*" >>"{calls}"\n')
    for stub in (bin_dir / "docker", bin_dir / "curl", python):
        stub.chmod(0o755)
    # Free ports, so a service running on this machine is never mistaken for the stubs.
    ports = []
    for _ in range(3):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            ports.append(s.getsockname()[1])
    base_env = {k: v for k, v in os.environ.items() if not k.startswith(("SEMANT_DEV_", "CONFIRM"))}
    base_env.update(PATH=f"{bin_dir}:{os.environ['PATH']}", CALLS=str(calls), PYTHON=str(python),
                    SEMANT_DEV_WEAVIATE_REST_PORT=str(ports[0]), SEMANT_DEV_WEAVIATE_GRPC_PORT=str(ports[1]),
                    SEMANT_DEV_BACKEND_PORT=str(ports[2]),
                    STUB_VOLUME_LABEL=LABEL, STUB_CONTAINER_LABEL=LABEL, STUB_PORT=f"127.0.0.1:{ports[0]}",
                    STUB_GRPC_PORT=f"127.0.0.1:{ports[1]}")

    def run(*args, **env):
        result = subprocess.run([str(SCRIPT), *args], env={**base_env, **env}, cwd=ROOT, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=60)
        result.calls = calls.read_text() if calls.exists() else ""
        return result

    run.backend_port = ports[2]
    return run


def _changes(calls: str) -> list[str]:
    return [line for line in calls.splitlines()
            if line.split()[:2] in (["docker", "run"], ["docker", "start"], ["docker", "stop"], ["docker", "rm"])
            or line.startswith(("docker volume create", "docker volume rm"))]


def test_up_refuses_a_volume_without_the_development_label(launcher):
    result = launcher("up", STUB_VOLUME_LABEL="<no value>")

    assert result.returncode == 1
    assert "without the org.semant.purpose=local-development label" in result.stderr
    assert _changes(result.calls) == [] and "python" not in result.calls


def test_up_refuses_a_container_of_that_name_without_the_label(launcher):
    result = launcher("up", STUB_CONTAINER_LABEL="<no value>")

    assert result.returncode == 1
    assert "not touching it" in result.stderr
    assert _changes(result.calls) == [] and "python" not in result.calls


def test_up_initializes_through_the_owned_container(launcher):
    result = launcher("up")

    assert result.returncode == 0, result.stderr
    assert "python -m tests.local_dev init" in result.calls


def test_down_leaves_a_container_without_the_label(launcher):
    result = launcher("down", STUB_CONTAINER_LABEL="<no value>")

    assert result.returncode == 1
    assert _changes(result.calls) == []


@pytest.mark.parametrize("command", ["backend", "verify", "status"])
def test_commands_refuse_a_container_on_another_port(launcher, command):
    result = launcher(command, STUB_PORT="127.0.0.1:8080")

    assert result.returncode == 1
    assert "not 127.0.0.1:" in result.stderr
    assert "python" not in result.calls


@pytest.mark.parametrize("command", ["up", "backend", "verify", "reset"])
def test_commands_refuse_a_container_publishing_grpc_elsewhere(launcher, command):
    result = launcher(command, STUB_GRPC_PORT="127.0.0.1:50051", CONFIRM="yes")

    assert result.returncode == 1
    assert "publishes gRPC on '127.0.0.1:50051'" in result.stderr
    assert "python" not in result.calls and _changes(result.calls) == []


def test_reset_without_confirmation_and_terminal_only_shows_the_plan(launcher):
    result = launcher("reset")

    assert result.returncode == 1
    assert "CONFIRM=yes" in result.stderr
    assert "python -m tests.local_dev reset\n" in result.calls
    assert "reset --yes" not in result.calls


def test_a_confirmed_reset_runs_after_the_dry_run(launcher):
    result = launcher("reset", CONFIRM="yes")

    assert result.returncode == 0, result.stderr
    assert result.calls.index("tests.local_dev reset\n") < result.calls.index("tests.local_dev reset --yes")


def test_reset_refuses_while_a_backend_runs(launcher):
    with socket.socket() as server:
        server.bind(("127.0.0.1", launcher.backend_port))
        server.listen()

        result = launcher("reset", CONFIRM="yes")

    assert result.returncode == 1
    assert "stop make dev-backend" in result.stderr
    assert result.calls == ""
