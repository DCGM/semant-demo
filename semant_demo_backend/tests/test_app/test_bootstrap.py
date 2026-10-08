"""Application creation, lifecycle and OpenAPI export without external services."""
import json
import socket
import sqlite3

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from semant_demo.bootstrap import AppResources
from semant_demo.main import create_app
from semant_demo.adapters.weaviate.client import WeaviateUnavailable
from tests.app_support import OfflineWeaviate, make_test_config, offline_weaviate

REGISTER_URL = "/api/auth/register"


@pytest.fixture
def no_external_connections(monkeypatch):
    """Fail and record any outgoing socket connection."""
    attempts = []

    def refuse(self, address, *args, **kwargs):
        attempts.append(address)
        raise OSError(f"external connection attempted in test: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
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
    app = create_app(config, weaviate_connector=offline_weaviate)

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
    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
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
    app_a = create_app(make_test_config(tmp_path / "a"), weaviate_connector=offline_weaviate)
    app_b = create_app(make_test_config(tmp_path / "b"), weaviate_connector=offline_weaviate)

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
    app = create_app(make_test_config(tmp_path, SQL_DB_URL=missing_dir_db), weaviate_connector=offline_weaviate)

    with pytest.raises(Exception):
        async with LifespanManager(app):
            pass

    assert len(closed) == 1
    assert app.state.resources is None


async def test_weaviate_is_connected_once_at_startup_and_closed_at_shutdown(tmp_path, no_external_connections):
    clients = []

    async def connector(config):
        clients.append(OfflineWeaviate())
        return clients[-1]

    app = create_app(make_test_config(tmp_path), weaviate_connector=connector)

    async with LifespanManager(app), _client(app) as client:
        assert len(clients) == 1
        weaviate = app.state.resources.weaviate
        # Every repository uses the one application client.
        assert {id(r.client) for r in (weaviate.documents, weaviate.tags, weaviate.collections, weaviate.search,
                                       weaviate.spans, weaviate.chunk_tags)} \
            == {id(clients[0])}
        for _ in range(2):
            assert (await client.get("/health")).status_code == 200
        assert not clients[0].closed

    assert len(clients) == 1 and clients[0].closed
    assert no_external_connections == []


async def test_startup_fails_without_weaviate_and_releases_resources(tmp_path, monkeypatch):
    closed = []
    original_close = AppResources.close

    async def recording_close(self):
        closed.append(self)
        await original_close(self)

    async def unavailable(config):
        raise WeaviateUnavailable("Weaviate at weaviate.invalid is not ready.")

    monkeypatch.setattr(AppResources, "close", recording_close)
    app = create_app(make_test_config(tmp_path), weaviate_connector=unavailable)

    with pytest.raises(WeaviateUnavailable):
        async with LifespanManager(app):
            pass

    assert len(closed) == 1
    assert app.state.resources is None


async def test_default_connector_reports_unreachable_weaviate(tmp_path, no_external_connections):
    # Loopback port 1: the attempt is refused by the fixture, never sent anywhere.
    app = create_app(make_test_config(tmp_path, WEAVIATE_HOST="127.0.0.1", WEAVIATE_REST_PORT="1",
                                      WEAVIATE_GRPC_PORT="2"))

    with pytest.raises(WeaviateUnavailable, match="127.0.0.1:1"):
        async with LifespanManager(app):
            pass

    assert no_external_connections


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


def test_sql_tables_are_users_and_rag_feedback():
    from semant_demo.adapters.sql.tables import Base

    assert set(Base.metadata.tables) == {"user", "rag_user_feedback"}


async def test_startup_keeps_existing_users_and_feedback(tmp_path, no_external_connections):
    config = make_test_config(tmp_path)
    app = create_app(config, weaviate_connector=offline_weaviate)
    async with LifespanManager(app), _client(app) as client:
        assert (await _register(client, "kept@example.com")).status_code == 201
    with sqlite3.connect(tmp_path / "test.db") as conn:
        conn.execute("INSERT INTO rag_user_feedback (response_id, rag_id, question, answer, rating) "
                     "VALUES ('r1', 'rag', 'q', 'a', 1)")

    # A later start (e.g. a deployment) creates missing tables only.
    app = create_app(config, weaviate_connector=offline_weaviate)
    async with LifespanManager(app):
        pass

    assert _user_emails(tmp_path / "test.db") == ["kept@example.com"]
    with sqlite3.connect(tmp_path / "test.db") as conn:
        assert conn.execute("SELECT response_id FROM rag_user_feedback").fetchall() == [("r1",)]
