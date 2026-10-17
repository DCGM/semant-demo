"""``GET /api/quota``, the guest cookie and the 429 contract of an exhausted allowance."""
import pytest
from asgi_lifespan import LifespanManager
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from semant_demo.features.quota import service
from semant_demo.features.quota.schemas import QuotaExhaustedResponse
from semant_demo.features.quota.principal import GUEST_COOKIE, get_quota_principal, guest_principal
from semant_demo.main import create_app
from semant_demo.routes.dependencies import get_quota_ledger, get_quota_policy
from tests.app_support import make_test_config, offline_weaviate
from tests.auth_support import auth_headers, register
from tests.test_quota.test_ledger import call

QUOTA_URL = "/api/quota"
PASSWORD = "StrongPassw0rd!"


class App:
    def __init__(self, app):
        self.app = app

    @property
    def resources(self):
        return self.app.state.resources

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=self.app), base_url="http://test")

    async def spend(self, principal, usd: float) -> None:
        ledger, policy = self.resources.quota_ledger, self.resources.quota_policy
        await service.settle(ledger, await service.admit(ledger, policy, principal, "rag", 0), [call(usd)])


async def _start(tmp_path, **settings):
    app = create_app(make_test_config(tmp_path, **settings), weaviate_connector=offline_weaviate)

    # An AI operation as #398 will admit it: refused when nothing is left.
    @app.post("/api/test/ai-operation")
    async def ai_operation(principal=Depends(get_quota_principal), ledger=Depends(get_quota_ledger),
                           policy=Depends(get_quota_policy)):
        return {"operation_id": await service.admit(ledger, policy, principal, "rag", 0.01)}

    return app


@pytest.fixture
async def quota_app(tmp_path):
    app = await _start(tmp_path)
    async with LifespanManager(app):
        yield App(app)


def _guest_cookie(response) -> str:
    [header] = [h for h in response.headers.get_list("set-cookie") if h.startswith(f"{GUEST_COOKIE}=")]
    return header


async def test_a_guest_gets_a_cookie_and_the_guest_allowance(quota_app):
    async with quota_app.client() as client:
        response = await client.get(QUOTA_URL)

    assert response.status_code == 200
    header = _guest_cookie(response)
    assert "HttpOnly" in header and "Path=/api" in header and "SameSite=lax" in header
    assert "Max-Age=2592000" in header  # 30 days
    assert "Secure" not in header  # the test ALLOWED_ORIGIN is http://localhost:9000
    body = response.json()
    assert {k: body[k] for k in ("principal", "limit_usd", "used_usd", "remaining_usd", "near_limit", "exhausted")} \
        == {"principal": "guest", "limit_usd": 0.25, "used_usd": 0.0, "remaining_usd": 0.25,
            "near_limit": False, "exhausted": False}
    assert body["reset_at"].endswith(("+00:00", "Z")) and body["reset_at"][11:19] == "00:00:00"


async def test_the_guest_cookie_keeps_the_guest_usage(quota_app):
    async with quota_app.client() as client:
        token = _guest_cookie(await client.get(QUOTA_URL)).split(";")[0].split("=", 1)[1]
        await quota_app.spend(guest_principal(token), 0.21)

        response = await client.get(QUOTA_URL)  # the client sends the cookie back

    assert GUEST_COOKIE not in response.headers.get("set-cookie", "")
    body = response.json()
    assert (body["charged_usd"], body["near_limit"], body["exhausted"]) == (0.21, True, False)


async def test_a_cleared_or_forged_cookie_starts_a_new_guest(quota_app):
    async with quota_app.client() as client:
        token = _guest_cookie(await client.get(QUOTA_URL)).split(";")[0].split("=", 1)[1]
        await quota_app.spend(guest_principal(token), 0.10)

        for forged in (None, "not-a-server-token"):
            client.cookies.clear()
            if forged:
                client.cookies.set(GUEST_COOKIE, forged)
            response = await client.get(QUOTA_URL)
            assert _guest_cookie(response) and response.json()["used_usd"] == 0


async def test_an_account_has_its_own_allowance_and_logout_keeps_the_guest_usage(quota_app):
    async with quota_app.client() as client:
        token = _guest_cookie(await client.get(QUOTA_URL)).split(";")[0].split("=", 1)[1]
        await quota_app.spend(guest_principal(token), 0.10)
        assert (await register(client, email="a@example.com", password=PASSWORD)).status_code == 201
        headers = await auth_headers(client, "a@example.com", PASSWORD)

        # Signed in (the guest cookie is still sent): the account's allowance.
        account = await client.get(QUOTA_URL, headers=headers)
        assert {k: account.json()[k] for k in ("principal", "limit_usd", "used_usd")} == \
            {"principal": "account", "limit_usd": 1.0, "used_usd": 0.0}
        assert "set-cookie" not in account.headers

        # Signed out again: the guest's earlier usage is still there.
        guest = await client.get(QUOTA_URL)
        assert (guest.json()["principal"], guest.json()["used_usd"]) == ("guest", 0.1)


async def test_an_exhausted_allowance_refuses_new_operations_with_429(quota_app):
    async with quota_app.client() as client:
        token = _guest_cookie(await client.get(QUOTA_URL)).split(";")[0].split("=", 1)[1]
        assert (await client.post("/api/test/ai-operation")).status_code == 200
        await quota_app.spend(guest_principal(token), 0.25)

        refused = await client.post("/api/test/ai-operation")

    assert refused.status_code == 429
    body = QuotaExhaustedResponse.model_validate(refused.json()).model_dump(mode="json")
    assert (body["code"], body["principal"], body["limit_usd"]) == ("llm_quota_exhausted", "guest", 0.25)
    assert body["used_usd"] == pytest.approx(0.26) and "resets at" in body["detail"]
    assert body["reset_at"][11:19] == "00:00:00"
    assert 0 < int(refused.headers["retry-after"]) <= 24 * 60 * 60


@pytest.mark.parametrize("settings, secure", [
    ({"ALLOWED_ORIGIN": "https://demo.example"}, True),
    ({"ALLOWED_ORIGIN": "https://demo.example", "LLM_QUOTA_GUEST_COOKIE_SECURE": "false"}, False),
    ({"LLM_QUOTA_GUEST_COOKIE_SECURE": "true", "LLM_QUOTA_GUEST_COOKIE_DAYS": "7"}, True),
])
async def test_cookie_security_and_lifetime_follow_the_settings(tmp_path, settings, secure):
    app = await _start(tmp_path, **settings)
    async with LifespanManager(app), App(app).client() as client:
        header = _guest_cookie(await client.get(QUOTA_URL))

    assert ("Secure" in header) is secure
    assert f"Max-Age={int(settings.get('LLM_QUOTA_GUEST_COOKIE_DAYS', 30)) * 86400}" in header


@pytest.mark.parametrize("setting, value", [
    ("LLM_QUOTA_GUEST_DAILY_USD", "0"), ("LLM_QUOTA_ACCOUNT_DAILY_USD", "-1"), ("LLM_QUOTA_ACCOUNT_DAILY_USD", "inf"),
    ("LLM_QUOTA_NEAR_LIMIT_RATIO", "0"), ("LLM_QUOTA_NEAR_LIMIT_RATIO", "1.5"), ("LLM_QUOTA_GUEST_COOKIE_DAYS", "0"),
])
async def test_invalid_quota_settings_fail_startup(tmp_path, setting, value):
    app = await _start(tmp_path, **{setting: value})

    with pytest.raises(ValueError, match=setting):
        async with LifespanManager(app):
            pass
