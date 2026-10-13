"""Deployed instances keep in-app feedback on the host, not inside the container (#300)."""
from pathlib import PurePosixPath

import pytest
import yaml

from tests.test_deploy_commit import REPO_ROOT, _job

DEPLOY = REPO_ROOT / "deploy"
FEEDBACK_MOUNT = {"type": "bind", "source": "${SQL_DB_PATH}/feedback", "target": "/app/feedback",
                  "bind": {"create_host_path": False}}


def _env_value(template: str, name: str) -> str:
    [value] = [line.split("=", 1)[1] for line in (DEPLOY / template).read_text().splitlines()
               if line.startswith(f"{name}=")]
    return value


@pytest.mark.parametrize("template", [".env.example", ".env.test.example"])
def test_env_templates_put_the_feedback_log_in_the_mounted_directory(template):
    log_path = PurePosixPath(_env_value(template, "FEEDBACK_LOG_PATH"))

    assert log_path.parent == PurePosixPath(FEEDBACK_MOUNT["target"])


@pytest.mark.parametrize("compose", ["docker-compose.app.yaml", "docker-compose.app-test.yml"])
def test_app_compose_mounts_the_feedback_directory_from_the_instance_data(compose):
    volumes = yaml.safe_load((DEPLOY / compose).read_text())["services"]["app"]["volumes"]

    assert FEEDBACK_MOUNT in volumes


@pytest.mark.parametrize("name", ["deploy-production", "deploy-test-main", "deploy-test-pr"])
def test_deploy_job_creates_the_feedback_directory_before_starting(name):
    # create_host_path is false, so the directory must exist before `docker compose up`.
    steps = [step.get("run", "") for step in _job(name)["steps"]]
    created = next(i for i, run in enumerate(steps) if 'mkdir -p "$SQL_DB_PATH/feedback"' in run)
    started = next(i for i, run in enumerate(steps) if " up -d" in run)

    assert created < started
