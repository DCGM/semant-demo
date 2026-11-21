"""Suite-wide test policy.

Tests without an ``integration``, ``live`` or ``benchmark`` marker are fast tests: they
must not open network connections. Loopback is refused too, so a fast test cannot reach
a local development Weaviate or provider by accident. Unix sockets remain allowed.

SQLite databases opened through SQLAlchemy in tests do not wait for the disk, except in
tests marked ``sqlite_durable``, and passwords are hashed with a minimal work factor. The OpenAPI schema of the default test
settings is generated once per run (#848).
"""
import copy
import socket
import sys
from functools import partial

import fastapi_users.password
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy import event
from sqlalchemy.engine import Engine

from semant_demo.main import create_app
from tests.app_support import make_test_config, offline_weaviate

NETWORK_MARKERS = ("integration", "live", "benchmark")


class NetworkAccessInFastTest(OSError):
    pass


_sqlite_durable = False
"""True while a ``sqlite_durable`` test runs: its databases keep SQLite's own synchronization."""


def _skip_sqlite_fsync(dbapi_connection, connection_record):
    # Every ordinary test database is a throwaway file, so durability after a crash does not
    # matter; transactions, locking and isolation are unchanged. Waiting for fsync made
    # up most of an application's startup (its schema creation) on a disk-backed tmp_path.
    if not _sqlite_durable and "sqlite" in type(dbapi_connection).__module__:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA synchronous=OFF")
        cursor.close()


@pytest.fixture(autouse=True, scope="session")
def sqlite_without_fsync():
    event.listen(Engine, "connect", _skip_sqlite_fsync)
    yield
    event.remove(Engine, "connect", _skip_sqlite_fsync)


@pytest.fixture(autouse=True)
def sqlite_durability(request, monkeypatch):
    """Durability and recovery tests (marker ``sqlite_durable``) open SQLite databases with
    the synchronization setting production uses."""
    if request.node.get_closest_marker("sqlite_durable"):
        monkeypatch.setattr(sys.modules[__name__], "_sqlite_durable", True)


@pytest.fixture(autouse=True, scope="session")
def cheap_password_hashing():
    """Argon2id with its minimum work factor for passwords hashed in this process (users the
    tests register, log in or seed). Hashing and verification run the same code; only the
    deliberately slow cost parameters, ~0.1 s per hash with the defaults, are lowered."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(fastapi_users.password, "Argon2Hasher",
                      partial(Argon2Hasher, time_cost=1, memory_cost=8, parallelism=1))
        yield


@pytest.fixture(autouse=True)
def deny_network_in_fast_tests(request, monkeypatch):
    if any(request.node.get_closest_marker(name) for name in NETWORK_MARKERS):
        return

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def guard(original):
        def connect(self, address, *args, **kwargs):
            if self.family == socket.AF_UNIX:
                return original(self, address, *args, **kwargs)
            raise NetworkAccessInFastTest(
                f"fast test attempted a network connection to {address!r}; "
                "use a fake or mark the test as integration/live"
            )
        return connect

    monkeypatch.setattr(socket.socket, "connect", guard(original_connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guard(original_connect_ex))


@pytest.fixture(scope="session")
def _default_openapi_schema(tmp_path_factory) -> dict:
    return create_app(make_test_config(tmp_path_factory.mktemp("openapi"))).openapi()


@pytest.fixture
def openapi_schema(_default_openapi_schema) -> dict:
    """The OpenAPI schema of an application with the default test settings, a copy of its
    own per test. It depends only on the code (``test_app/test_bootstrap.py``), and
    generating it takes ~0.75 s."""
    return copy.deepcopy(_default_openapi_schema)


@pytest.fixture
async def client(tmp_path):
    """HTTP client for a fresh application with its own empty SQLite database."""
    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
