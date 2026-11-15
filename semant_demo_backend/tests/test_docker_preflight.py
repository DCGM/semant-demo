"""Docker preflight of the Weaviate launchers, scripts/docker-preflight.sh (#674).

No Docker: `docker` is a stub that records its calls and behaves as STUB_DOCKER says (daemon
down, permission denied, hung, image missing with a blocked or working registry). The
launchers are run far enough to show that a failed preflight stops them before anything is
started, built or tested.
"""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = ROOT / "scripts" / "docker-preflight.sh"
CANONICAL = "cr.weaviate.io/semitechnologies/weaviate:1.40.1"

DOCKER_STUB = r"""#!/bin/sh
echo "docker $*" >>"$CALLS"
case "$STUB_DOCKER:$1" in
  down:*) echo "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?" >&2; exit 1 ;;
  denied:*) echo "permission denied while trying to connect to the Docker daemon socket" >&2; exit 1 ;;
  hung:*) exec sleep 30 ;;
esac
case "$STUB_DOCKER:$*" in
  blocked:"image inspect"*|pulls:"image inspect"*|pull-hangs:"image inspect"*) exit 1 ;;
  blocked:pull*) echo "Error response from daemon: Get \"https://cr.weaviate.io/v2/\": blocked by policy" >&2; exit 1 ;;
  pull-hangs:pull*) exec sleep 30 ;;
esac
exit 0
"""


@pytest.fixture
def env(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    stub = bin_dir / "docker"
    stub.write_text(DOCKER_STUB)
    stub.chmod(0o755)
    base = {k: v for k, v in os.environ.items()
            if not k.startswith(("SEMANT_", "E2E_", "DOCKER_"))}
    base.update(PATH=f"{bin_dir}:{os.environ['PATH']}", CALLS=str(calls), SEMANT_DOCKER_TIMEOUT="1",
                SEMANT_DOCKER_PULL_TIMEOUT="1")
    base["calls"] = calls
    base["bin"] = bin_dir
    return base


def _run(env, *command, **extra):
    env = dict(env)
    calls = env.pop("calls")
    env.pop("bin")
    env.update({k: str(v) for k, v in extra.items()})
    result = subprocess.run([str(c) for c in command], env=env, cwd=ROOT, stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, timeout=60)
    result.calls = calls.read_text() if calls.exists() else ""
    return result


def test_a_working_daemon_with_the_image_present_passes(env):
    result = _run(env, PREFLIGHT, "--image")

    assert result.returncode == 0, result.stderr
    assert f"docker image inspect {CANONICAL}" in result.calls
    assert "docker pull" not in result.calls


def test_a_missing_docker_command_is_named_with_what_works_without_it(env, tmp_path):
    no_docker = tmp_path / "no-docker"
    no_docker.mkdir()
    for tool in ("timeout", "sed"):
        (no_docker / tool).symlink_to(subprocess.check_output(["which", tool], text=True).strip())

    result = _run(env, "/bin/bash", PREFLIGHT, PATH=str(no_docker))

    assert result.returncode == 1
    assert "docker command is not installed" in result.stderr
    assert "make check" in result.stderr


@pytest.mark.parametrize("mode, cause", [
    ("down", "Start the daemon"),
    ("denied", "docker group"),
], ids=["not-running", "permission-denied"])
def test_an_unavailable_daemon_is_explained(env, mode, cause):
    result = _run(env, PREFLIGHT, "--image", STUB_DOCKER=mode)

    assert result.returncode == 1
    assert "the Docker daemon is not available" in result.stderr
    assert cause in result.stderr
    assert "docker image" not in result.calls and "docker pull" not in result.calls


def test_a_hung_daemon_times_out_with_a_diagnosis(env):
    result = _run(env, PREFLIGHT, STUB_DOCKER="hung")

    assert result.returncode == 1
    assert "did not answer within 1 s" in result.stderr


def test_a_blocked_registry_names_the_image_and_the_explicit_workarounds(env):
    result = _run(env, PREFLIGHT, "--image", STUB_DOCKER="blocked")

    assert result.returncode == 1
    assert f"could not pull {CANONICAL}" in result.stderr
    assert "The Docker daemon works" in result.stderr
    assert f"docker tag <that image> {CANONICAL}" in result.stderr
    assert "SEMANT_WEAVIATE_IMAGE=" in result.stderr


def test_a_stalled_pull_is_bounded(env):
    result = _run(env, PREFLIGHT, "--image", STUB_DOCKER="pull-hangs")

    assert result.returncode == 1
    assert "did not finish within 1 s" in result.stderr


def test_a_missing_image_is_pulled(env):
    result = _run(env, PREFLIGHT, "--image", STUB_DOCKER="pulls")

    assert result.returncode == 0, result.stderr
    assert f"docker pull {CANONICAL}" in result.calls


@pytest.mark.parametrize("image", [
    "mirror.example/semitechnologies/weaviate:latest",
    "mirror.example/semitechnologies/weaviate:1.40.0",
    "mirror.example:5000/semitechnologies/weaviate",
    "mirror.example/weaviate@sha256:" + "0" * 64,
])
def test_an_override_with_another_version_is_refused(env, image):
    result = _run(env, PREFLIGHT, "--image", SEMANT_WEAVIATE_IMAGE=image)

    assert result.returncode == 1
    assert "is not tagged :1.40.1" in result.stderr
    assert "docker image" not in result.calls and "docker pull" not in result.calls


@pytest.mark.parametrize("image", [
    "mirror.example:5000/semitechnologies/weaviate:1.40.1",
    "mirror.example/weaviate:1.40.1@sha256:" + "0" * 64,
])
def test_an_explicit_override_of_the_required_version_is_used(env, image):
    result = _run(env, PREFLIGHT, "--image", SEMANT_WEAVIATE_IMAGE=image)

    assert result.returncode == 0, result.stderr
    assert f"docker image inspect {image}" in result.calls


# The launchers stop at the preflight.

def test_the_test_store_launcher_stops_before_running_anything(env, tmp_path):
    marker = tmp_path / "ran"

    result = _run(env, ROOT / "scripts" / "with-test-weaviate.sh", "touch", marker, STUB_DOCKER="blocked")

    assert result.returncode == 1
    assert f"could not pull {CANONICAL}" in result.stderr
    assert "docker run" not in result.calls and not marker.exists()


def test_the_test_store_launcher_honours_its_older_override_under_the_version_rule(env, tmp_path):
    result = _run(env, ROOT / "scripts" / "with-test-weaviate.sh", "true",
                  SEMANT_TEST_WEAVIATE_IMAGE="mirror.example/weaviate:1.41.0")

    assert result.returncode == 1
    assert "SEMANT_TEST_WEAVIATE_IMAGE=mirror.example/weaviate:1.41.0 is not tagged" in result.stderr
    assert "docker run" not in result.calls


def test_an_external_test_store_needs_no_docker(env, tmp_path):
    marker = tmp_path / "ran"

    result = _run(env, ROOT / "scripts" / "with-test-weaviate.sh", "touch", marker,
                  STUB_DOCKER="down", SEMANT_TEST_WEAVIATE_HOST="127.0.0.1")

    assert result.returncode == 0, result.stderr
    assert result.calls == "" and marker.exists()


@pytest.mark.parametrize("command", ["up", "down", "status", "backend", "logs"])
def test_local_dev_commands_explain_a_stopped_daemon(env, tmp_path, command):
    python = tmp_path / "python"
    python.write_text(f'#!/bin/sh\necho "python $*" >>"{env["calls"]}"\nexit 0\n')
    python.chmod(0o755)

    result = _run(env, ROOT / "scripts" / "local-dev.sh", command, STUB_DOCKER="down", PYTHON=python)

    assert result.returncode == 1
    assert "the Docker daemon is not available" in result.stderr
    assert "Docker is required for the development Weaviate" in result.stderr
    assert "-m tests.local_dev" not in result.calls
    docker_calls = [line for line in result.calls.splitlines() if line.startswith("docker ")]
    assert docker_calls == ["docker version --format {{.Server.Version}}"]  # only the probe


def test_e2e_dev_start_stops_before_building(env, tmp_path):
    python = tmp_path / "python"
    python.write_text("#!/bin/sh\nexit 0\n")
    python.chmod(0o755)
    for tool in ("node", "npx"):
        stub = env["bin"] / tool
        stub.write_text(f'#!/bin/sh\necho "{tool} $*" >>"{env["calls"]}"\nexit 0\n')
        stub.chmod(0o755)

    result = _run(env, ROOT / "scripts" / "e2e-dev.sh", "start", STUB_DOCKER="blocked", PYTHON=python,
                  E2E_DEV_STATE=tmp_path / "state", E2E_DEV_PORT="8799")

    assert result.returncode == 1
    assert f"could not pull {CANONICAL}" in result.stderr
    assert "nothing was built or started" in result.stderr
    assert "npx" not in result.calls and "docker run" not in result.calls
