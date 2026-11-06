"""Deployed instances read the page asset store from a read-only host mount (#594)."""
import pytest
import yaml

from tests.test_deploy_commit import REPO_ROOT

DEPLOY = REPO_ROOT / "deploy"
MOUNT = {"type": "bind", "source": "${PAGE_ASSETS_PATH}", "target": "/app/page_assets", "read_only": True,
         "bind": {"create_host_path": False}}


def _env(name):
    return dict(line.split("=", 1) for line in (DEPLOY / name).read_text().splitlines()
                if line and not line.startswith("#"))


@pytest.mark.parametrize("compose, env, store", [
    ("docker-compose.app.yaml", ".env.example", "/mnt/zfs1/semant_demo_page_assets/production"),
    ("docker-compose.app-test.yml", ".env.test.example", "/mnt/zfs1/semant_demo_page_assets/test"),
])
def test_app_reads_its_page_asset_store_from_a_read_only_mount(compose, env, store):
    app = yaml.safe_load((DEPLOY / compose).read_text())["services"]["app"]

    assert app["environment"]["PAGE_ASSETS_DIR"] == MOUNT["target"]
    assert MOUNT in app["volumes"]
    assert _env(env)["PAGE_ASSETS_PATH"] == store
