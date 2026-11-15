"""Which CI results gate which deployment (#213, #689, #687).

PR previews are for manual testing only: they start alongside the tests and never wait for
them, only for the change classification, which omits them for documentation-only PRs.
Production and test-main deploy only after every required check and the gate pass.
"""
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci-cd.yml"
JOBS = yaml.safe_load(WORKFLOW.read_text())["jobs"]
REQUIRED = {"test-backend", "test-frontend", "test-integration", "test-browser", "api-client-drift", "python-locks"}
SAME_REPO = "github.event.pull_request.head.repo.full_name == github.repository"


def test_pr_preview_does_not_wait_for_tests_and_stays_internal():
    job = JOBS["deploy-test-pr"]

    assert job["needs"] == ["classify"]
    # A failed classification still deploys the preview.
    assert "!cancelled()" in job["if"]
    assert SAME_REPO in job["if"]
    assert "github.event.action != 'closed'" in job["if"]
    assert job["runs-on"] == ["self-hosted", "semant-server"]


def test_production_and_test_main_wait_for_every_required_check():
    for name in ("deploy-production", "deploy-test-main"):
        assert set(JOBS[name]["needs"]) == REQUIRED | {"ci-result"}, name
        assert "always()" not in JOBS[name]["if"], name
