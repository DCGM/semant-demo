"""Application creation, lifecycle and OpenAPI export without external services."""
import json
import socket
import sqlite3

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from semant_demo.bootstrap import AppResources
from semant_demo.main import create_app
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction
from tests.app_support import make_test_config

REGISTER_URL = "/api/auth/register"


@pytest.fixture
def no_external_connections(monkeypatch):
    """Fail any outgoing socket connection or Weaviate client creation."""
    attempts = []

    def refuse(self, address, *args, **kwargs):
        attempts.append(address)
        raise OSError(f"external connection attempted in test: {address!r}")

    async def refuse_weaviate(cls, config):
        attempts.append("weaviate")
        raise OSError("Weaviate connection attempted in test")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(WeaviateAbstraction, "create", classmethod(refuse_weaviate))
    return attempts


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _register(client: AsyncClient, email: str):
    return await client.post(REGISTER_URL, json={"email": email, "password": "StrongPassw0rd!"})


def _user_emails(db_path) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        return [row[0] for row in conn.execute('SELECT email FROM "user"')]


async def test_app_uses_injected_settings(tmp_path, no_external_connections):
    config = make_test_config(tmp_path, ALLOWED_ORIGIN="http://ui.test")
    app = create_app(config)

    async with LifespanManager(app), _client(app) as client:
        response = await _register(client, "a@example.com")
        preflight = await client.options(
            REGISTER_URL,
            headers={"Origin": "http://ui.test", "Access-Control-Request-Method": "POST"},
        )

    assert response.status_code == 201, response.text
    assert _user_emails(tmp_path / "test.db") == ["a@example.com"]
    assert preflight.headers["access-control-allow-origin"] == "http://ui.test"
    assert no_external_connections == []


async def test_lifecycle_can_run_repeatedly(tmp_path, no_external_connections):
    app = create_app(make_test_config(tmp_path))
    seen_resources = []

    for email in ("first@example.com", "second@example.com"):
        async with LifespanManager(app), _client(app) as client:
            seen_resources.append(app.state.resources)
            assert (await client.get("/health")).json() == {"status": "ok"}
            assert (await _register(client, email)).status_code == 201
        assert app.state.resources is None

    assert seen_resources[0] is not seen_resources[1]
    assert sorted(_user_emails(tmp_path / "test.db")) == ["first@example.com", "second@example.com"]
    assert no_external_connections == []


async def test_apps_with_different_settings_are_isolated(tmp_path, no_external_connections):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    app_a = create_app(make_test_config(tmp_path / "a"))
    app_b = create_app(make_test_config(tmp_path / "b"))

    async with LifespanManager(app_a), LifespanManager(app_b), _client(app_a) as a, _client(app_b) as b:
        assert (await _register(a, "same@example.com")).status_code == 201
        # Same email is new for the second app because it uses its own database.
        assert (await _register(b, "same@example.com")).status_code == 201

    assert _user_emails(tmp_path / "a" / "test.db") == ["same@example.com"]
    assert _user_emails(tmp_path / "b" / "test.db") == ["same@example.com"]


async def test_resources_are_released_after_failed_startup(tmp_path, monkeypatch):
    closed = []
    original_close = AppResources.close

    async def recording_close(self):
        closed.append(self)
        await original_close(self)

    monkeypatch.setattr(AppResources, "close", recording_close)
    missing_dir_db = f"sqlite+aiosqlite:///{tmp_path / 'missing' / 'test.db'}"
    app = create_app(make_test_config(tmp_path, SQL_DB_URL=missing_dir_db))

    with pytest.raises(Exception):
        async with LifespanManager(app):
            pass

    assert len(closed) == 1
    assert app.state.resources is None


async def test_request_without_running_lifespan_is_unavailable(tmp_path):
    app = create_app(make_test_config(tmp_path))

    async with _client(app) as client:
        response = await _register(client, "a@example.com")

    assert response.status_code == 503


def test_openapi_builds_without_external_services(tmp_path, no_external_connections):
    schema = create_app(make_test_config(tmp_path)).openapi()

    assert "/api/search" in schema["paths"]
    assert "/api/auth/register" in schema["paths"]
    assert no_external_connections == []


def test_openapi_does_not_depend_on_runtime_settings(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    schema_a = create_app(make_test_config(tmp_path / "a")).openapi()
    schema_b = create_app(make_test_config(tmp_path / "b", ALLOWED_ORIGIN="http://other")).openapi()

    assert schema_a == schema_b


def test_export_script_writes_schema_offline(tmp_path, no_external_connections):
    import export_openapi

    output = tmp_path / "openapi.json"
    export_openapi.export_schema(str(output))

    assert "/api/search" in json.loads(output.read_text())["paths"]
    assert no_external_connections == []
