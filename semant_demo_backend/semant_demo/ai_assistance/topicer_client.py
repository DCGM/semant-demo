"""
Async client for the external Topicer service.

Topicer (running by default at http://localhost:8089) exposes:

- ``POST /v1/tags/propose/texts`` — propose tag spans for a single provided text chunk.
- ``POST /v1/tags/propose/db/stream`` — propose tag spans for chunks stored in
  the database, streaming NDJSON results as each chunk completes.
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import httpx

from semant_demo.config import config

logger = logging.getLogger(__name__)


def _tag_payload(tag: dict[str, Any]) -> dict[str, Any]:
    """Convert an internal tag dict into the schema Topicer expects."""
    return {
        "id": str(tag["id"]),
        "name": tag.get("name") or "",
        "description": tag.get("definition") or "",
        "examples": list(tag.get("examples") or []),
    }


class TopicerError(RuntimeError):
    pass


@asynccontextmanager
async def topicer_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    timeout = httpx.Timeout(config.TOPICER_TIMEOUT, connect=10.0)
    async with httpx.AsyncClient(base_url=config.TOPICER_URL, timeout=timeout) as client:
        yield client


async def propose_for_text_chunk(
    client: httpx.AsyncClient,
    *,
    chunk_id: str,
    chunk_text: str,
    tags: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Call ``POST /v1/tags/propose/texts`` for a single chunk + a list of tags.

    Returns the list of ``tag_span_proposals`` from Topicer's response.
    """
    body = {
        "text_chunk": {"id": str(chunk_id), "text": chunk_text},
        "tags": [_tag_payload(t) for t in tags],
    }
    try:
        resp = await client.post(
            "/v1/tags/propose/texts",
            params={"config_name": config.TOPICER_CONFIG_NAME},
            json=body,
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning("Topicer /tags/propose/texts failed for chunk %s: %s", chunk_id, e)
        raise TopicerError(str(e)) from e

    data = resp.json()
    return list(data.get("tag_span_proposals") or [])


async def propose_for_db_stream(
    client: httpx.AsyncClient,
    *,
    tag: dict[str, Any],
    collection_id: str,
    document_id: str,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Call ``POST /v1/tags/propose/db/stream`` and yield each NDJSON object as it
    arrives. Each yielded object is a ``TextChunkWithTagSpanProposals`` dict::

        {"id": "<chunk_id>", "text": "...", "tag_span_proposals": [...]}
    """
    body = {
        "tag": _tag_payload(tag),
        "db_request": {
            "collection_id": str(collection_id),
            "document_id": str(document_id),
        },
    }
    try:
        async with client.stream(
            "POST",
            "/v1/tags/propose/db/stream",
            params={"config_name": config.TOPICER_CONFIG_NAME},
            json=body,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.strip():
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Topicer stream produced non-JSON line: %r", line)
    except httpx.HTTPError as e:
        logger.warning(
            "Topicer /tags/propose/db/stream failed (tag=%s, doc=%s): %s",
            tag.get("id"), document_id, e,
        )
        raise TopicerError(str(e)) from e
