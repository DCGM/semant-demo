"""An MCP client session against an in-process application (#635), as a remote client sees it:
Streamable HTTP at ``/mcp`` over the ASGI app, no network."""
import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult

BASE_URL = "http://localhost"


@asynccontextmanager
async def mcp_session(app, headers: dict[str, str] | None = None) -> AsyncIterator[ClientSession]:
    """An initialized client session of the started ``app``."""
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL, headers=headers) as http:
        async with streamable_http_client(f"{BASE_URL}/mcp", http_client=http) as (read, write, *_):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


def structured(result: CallToolResult) -> dict[str, Any]:
    """The structured answer of a successful call (also checks its JSON text content)."""
    assert not result.isError, result.content
    assert json.loads(result.content[0].text) == result.structuredContent
    return result.structuredContent


def error_text(result: CallToolResult) -> str:
    assert result.isError, result.structuredContent
    return result.content[0].text
