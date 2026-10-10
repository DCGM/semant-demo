"""Deployments build and configure one exact commit, not the branch tip at deploy time (#233).

A deploy run can be queued while the branch moves on. The deploy files (Dockerfile, Compose,
.env template) and the application source cloned by the Dockerfile must both come from the
commit that run is deploying.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci-cd.yml"
DOCKERFILE = REPO_ROOT / "deploy" / "Dockerfile"

DEPLOY_JOBS = {
    "deploy-production": "${{ github.sha }}",
    "deploy-test-main": "${{ github.sha }}",
    "deploy-test-pr": "${{ github.event.pull_request.head.sha }}",
}


def _job(name):
    return yaml.safe_load(WORKFLOW.read_text())["jobs"][name]


def _step(job, name):
    return next(step for step in job["steps"] if step.get("name") == name)


@pytest.mark.parametrize("name", DEPLOY_JOBS)
def test_deploy_job_uses_one_pinned_commit(name):
    job = _job(name)
    assert job["env"]["DEPLOY_COMMIT"] == DEPLOY_JOBS[name]

    checkouts = [s for s in job["steps"] if s.get("uses", "").startswith("actions/checkout@")]
    assert [s["with"]["ref"] for s in checkouts] == ["${{ env.DEPLOY_COMMIT }}"]

    copy = _step(job, "Update deploy files" if name != "deploy-production" else "Update deploy/ files")["run"]
    assert "git clone" not in copy and "--branch" not in copy
    assert 'if [ "$HEAD" != "$DEPLOY_COMMIT" ]' in copy

    env_file = _step(job, "Create .env")["run"]
    assert 's|^COMMIT=.*|COMMIT=${DEPLOY_COMMIT}|' in env_file


@pytest.mark.parametrize("compose", ["docker-compose.app.yaml", "docker-compose.app-test.yml"])
def test_compose_passes_commit_to_the_build(compose):
    service = yaml.safe_load((REPO_ROOT / "deploy" / compose).read_text())["services"]["app"]
    assert "COMMIT=${COMMIT:-}" in service["build"]["args"]


def _dockerfile_clone_script(dest):
    """The git stage's clone command, with its fixed /tmp/repo destination replaced."""
    text = DOCKERFILE.read_text()
    match = re.search(r'^RUN (if \[ -n "\$\{COMMIT\}" \].*?^\s*fi)$', text, re.M | re.S)
    assert match, "clone RUN step not found in deploy/Dockerfile"
    return match.group(1).replace("\\\n", "\n").replace("/tmp/repo", str(dest))


def _git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def git_env(monkeypatch, tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    for key, value in {
        "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
    }.items():
        monkeypatch.setenv(key, value)


def test_dockerfile_builds_pinned_commit_after_branch_moved(git_env, tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    _git("init", "-q", "-b", "main", cwd=origin)
    # GitHub serves any reachable commit by SHA; a local repository must opt in.
    _git("config", "uploadpack.allowReachableSHA1InWant", "true", cwd=origin)
    (origin / "version").write_text("tested\n")
    _git("add", "version", cwd=origin)
    _git("commit", "-q", "-m", "tested", cwd=origin)
    tested = _git("rev-parse", "HEAD", cwd=origin)
    # Another push lands while the deploy run for `tested` is queued.
    (origin / "version").write_text("newer\n")
    _git("commit", "-q", "-am", "newer", cwd=origin)

    def build(dest, commit):
        env = {**os.environ, "REPO": f"file://{origin}", "BRANCH": "main", "COMMIT": commit}
        return subprocess.run(["sh", "-c", _dockerfile_clone_script(dest)], env=env, capture_output=True, text=True)

    pinned = build(tmp_path / "pinned", tested)
    assert pinned.returncode == 0, pinned.stderr
    assert _git("rev-parse", "HEAD", cwd=tmp_path / "pinned") == tested
    assert (tmp_path / "pinned" / "version").read_text() == "tested\n"

    # Without COMMIT (manual builds) the branch tip is built, as before.
    tip = build(tmp_path / "tip", "")
    assert tip.returncode == 0, tip.stderr
    assert (tmp_path / "tip" / "version").read_text() == "newer\n"

    # A commit that cannot be fetched fails the build instead of falling back to the tip.
    missing = build(tmp_path / "missing", "0" * 40)
    assert missing.returncode != 0
