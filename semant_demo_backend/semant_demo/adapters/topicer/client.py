"""
Async client for the external Topicer service (``TOPICER_URL``).

Topicer exposes:

- ``POST /v1/tags/propose/texts`` — propose tag spans for a single provided text chunk.
- ``POST /v1/tags/propose/db/stream`` — propose tag spans for chunks stored in
  the database, streaming NDJSON results as each chunk completes.

Proposals are returned as Topicer sends them (``tag_span_proposals`` dicts with ``tag``,
``span_start``, ``span_end``, ``reason``, ``confidence``); validating them against the
request is the caller's job (``features/annotations/suggestions.py``).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TopicerTag:
    """A tag as Topicer is asked to find it."""
    id: str
    name: str
    definition: str
    examples: list[str]

    def payload(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "description": self.definition,
                "examples": list(self.examples)}


class TopicerError(RuntimeError):
    pass


class TopicerClient:
    """Topicer at ``base_url`` with the named Topicer config.

    Built once per application by bootstrap from its config; holds no connection (each
    call opens its own). ``transport`` replaces the network in tests. HTTP and protocol
    errors raise ``TopicerError``.
    """

    def __init__(self, base_url: str, config_name: str, timeout: float,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = base_url
        self.config_name = config_name
        self.timeout = timeout
        self.transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=httpx.Timeout(self.timeout, connect=10.0),
                                 transport=self.transport)

    async def propose_for_text(self, *, chunk_id: str, text: str, tags: list[TopicerTag]) -> list[dict[str, Any]]:
        """
        Call ``POST /v1/tags/propose/texts`` for a single text + a list of tags.

        Returns the list of ``tag_span_proposals`` from Topicer's response.
        """
        body = {
            "text_chunk": {"id": str(chunk_id), "text": text},
            "tags": [t.payload() for t in tags],
        }
        path = "/v1/tags/propose/texts"
        try:
            async with self._client() as client:
                resp = await client.post(path, params={"config_name": self.config_name}, json=body)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Topicer POST %s%s failed for chunk %s: %s (%s)",
                           self.base_url, path, chunk_id, e, type(e).__name__)
            raise TopicerError(str(e)) from e
        proposals = data.get("tag_span_proposals") if isinstance(data, dict) else None
        if proposals is None:
            return []
        if not isinstance(proposals, list):
            raise TopicerError("tag_span_proposals is not a list")
        return proposals

    async def propose_for_db_stream(self, *, tag: TopicerTag, collection_id: str,
                                    document_id: str) -> AsyncGenerator[dict[str, Any], None]:
        """
        Call ``POST /v1/tags/propose/db/stream`` and yield each NDJSON object as it
        arrives. Each yielded object is a ``TextChunkWithTagSpanProposals`` dict::

            {"id": "<chunk_id>", "text": "...", "tag_span_proposals": [...]}

        Lines that are not JSON objects are logged and skipped.
        """
        body = {
            "tag": tag.payload(),
            "db_request": {"collection_id": str(collection_id), "document_id": str(document_id)},
        }
        path = "/v1/tags/propose/db/stream"
        try:
            async with self._client() as client:
                async with client.stream("POST", path, params={"config_name": self.config_name},
                                         json=body) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.strip():
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            event = None
                        if not isinstance(event, dict):
                            logger.warning("Topicer stream produced a line that is not a JSON object: %r", line)
                            continue
                        yield event
        except httpx.HTTPError as e:
            logger.warning("Topicer POST %s%s failed (tag=%s, doc=%s): %s (%s)",
                           self.base_url, path, tag.id, document_id, e, type(e).__name__)
            raise TopicerError(str(e)) from e
