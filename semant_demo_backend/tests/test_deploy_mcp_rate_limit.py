"""Deployed instances rate-limit the public MCP endpoint per client IP at the proxy (#635)."""
import pytest
import yaml

from tests.test_deploy_commit import REPO_ROOT

DEPLOY = REPO_ROOT / "deploy"
COMPOSE = [("docker-compose.app.yaml", "semant-demo", "${DOMAIN}"),
           ("docker-compose.app-test.yml", "${TEST_ROUTER_NAME}", "${TEST_SUBDOMAIN}")]


def _labels(compose: str) -> dict[str, str]:
    labels = yaml.safe_load((DEPLOY / compose).read_text())["services"]["app"]["labels"]
    return dict(label.split("=", 1) for label in labels)


@pytest.mark.parametrize(("compose", "name", "host"), COMPOSE)
def test_mcp_router_takes_only_mcp_paths_through_the_rate_limit(compose, name, host):
    labels = _labels(compose)
    mcp = f"traefik.http.routers.{name}-mcp"
    middleware = f"traefik.http.middlewares.{name}-mcp-ratelimit.ratelimit"

    assert labels[f"{mcp}.rule"] == f"Host(`{host}`) && PathPrefix(`/mcp`)"
    assert labels[f"{mcp}.entrypoints"] == "websecure"
    assert labels[f"{mcp}.middlewares"] == f"{name}-mcp-ratelimit"
    assert (labels[f"{middleware}.average"], labels[f"{middleware}.period"], labels[f"{middleware}.burst"]) == \
        ("60", "1m", "30")
    # No sourceCriterion: Traefik terminates TLS itself, so the remote address is the client.
    assert not any(key.startswith(f"{middleware}.sourcecriterion") for key in labels)


@pytest.mark.parametrize(("compose", "name", "host"), COMPOSE)
def test_both_routers_reach_the_one_app_service_and_the_host_router_is_unlimited(compose, name, host):
    labels = _labels(compose)

    # With two routers, each names the service explicitly.
    assert labels[f"traefik.http.routers.{name}.service"] == name
    assert labels[f"traefik.http.routers.{name}-mcp.service"] == name
    assert labels[f"traefik.http.routers.{name}.rule"] == f"Host(`{host}`)"
    assert f"traefik.http.routers.{name}.middlewares" not in labels
