"""Suite-wide test policy.

Tests without an ``integration``, ``live`` or ``benchmark`` marker are fast tests: they
must not open network connections. Loopback is refused too, so a fast test cannot reach
a local development Weaviate or provider by accident. Unix sockets remain allowed.
"""
import socket

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from semant_demo.main import create_app
from tests.app_support import make_test_config

NETWORK_MARKERS = ("integration", "live", "benchmark")


class NetworkAccessInFastTest(OSError):
    pass


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


@pytest.fixture
async def client(tmp_path):
    """HTTP client for a fresh application with its own empty SQLite database."""
    app = create_app(make_test_config(tmp_path))
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
