"""The fast-test network guard in conftest refuses connections, including loopback."""
import asyncio
import socket

import pytest

from tests.conftest import NetworkAccessInFastTest


@pytest.mark.parametrize("address", [("127.0.0.1", 8080), ("192.0.2.1", 80)])
def test_fast_tests_cannot_connect(address):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        with pytest.raises(NetworkAccessInFastTest):
            sock.connect(address)
        with pytest.raises(NetworkAccessInFastTest):
            sock.connect_ex(address)


async def test_fast_tests_cannot_open_async_connections():
    with pytest.raises(NetworkAccessInFastTest):
        await asyncio.open_connection("127.0.0.1", 8080)
