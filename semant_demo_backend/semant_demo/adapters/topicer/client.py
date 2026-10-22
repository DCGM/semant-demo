"""
Async client for the external Topicer service (``TOPICER_URL``).

Topicer exposes:

- ``POST /v1/tags/propose/texts`` — propose tag spans for a single provided text chunk.
- ``POST /v1/tags/propose/db/stream`` — propose tag spans for chunks stored in
  the database, streaming NDJSON results as each chunk completes.
- ``GET /v1/configs`` — the names of the configurations Topicer has loaded (#189).

Proposals are returned as Topicer sends them (``tag_span_proposals`` dicts with ``tag``,
``span_start``, ``span_end``, ``reason``, ``confidence``); validating them against the
request is the caller's job (``features/annotations/suggestions.py``).

Usage (DCGM/topicer#81): Topicer reports every provider attempt it made for a request
(``usage`` of a ``/texts`` response; the terminal ``usage_summary`` line of a stream).
It is parsed into :class:`TopicerUsage`; usage that is missing or malformed is ``None``,
which callers must treat as unknown, never as zero. The optimized stream sends the
backend's ``max_chunks`` (``TOPICER_MAX_CHUNKS_PER_TAG``); Topicer answers 422 when it is
above its own safety ceiling.
"""
from __future__ import annotations

import copy
import json
import logging
import time
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
    """A failed Topicer call. The message is safe for logs and suggestion events: the error
    class and HTTP status only, never Topicer's URL, its response or the request text.

    ``no_work``: Topicer certainly ran no model for the request (it could not be connected
    to, or refused the request before inference with 422); otherwise its usage is unknown.
    """

    def __init__(self, message: str, *, no_work: bool = False):
        super().__init__(message)
        self.no_work = no_work


def _failure(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        return f"HTTP {e.response.status_code}"
    return type(e).__name__


def _error(e: Exception) -> TopicerError:
    refused = isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 422
    return TopicerError(_failure(e), no_work=refused or isinstance(e, httpx.ConnectError))


@dataclass(frozen=True)
class TopicerCall:
    """One provider attempt that Topicer reports (a retried request is several)."""
    provider: str
    model: str
    outcome: str
    """``success``, ``error`` or ``cancelled``."""
    usage_source: str
    """``reported`` or ``unknown``."""
    cost_source: str
    """``reported`` (by the provider), ``estimated`` (tokens times Topicer's prices) or ``unknown``."""
    cost_usd: float | None
    """``None``: unknown, never zero."""
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class TopicerUsage:
    calls: list[TopicerCall]
    attempted_calls: int
    """Attempts Topicer counted; more than ``len(calls)`` means some are not itemized."""


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _usage(raw: Any) -> TopicerUsage | None:
    """Topicer's ``LLMUsage``, or ``None`` when it is missing or malformed (unknown usage)."""
    if not isinstance(raw, dict) or not isinstance(raw.get("calls"), list):
        return None
    calls = []
    for call in raw["calls"]:
        if not isinstance(call, dict):
            return None
        cost = call.get("cost_usd")
        if cost is not None and (isinstance(cost, bool) or not isinstance(cost, int | float)
                                 or not 0 <= cost < float("inf")):
            return None
        calls.append(TopicerCall(
            provider=str(call.get("provider") or ""), model=str(call.get("model") or ""),
            outcome=str(call.get("outcome") or "unknown"), usage_source=str(call.get("usage_source") or "unknown"),
            cost_source=str(call.get("cost_source") or "unknown") if cost is not None else "unknown",
            cost_usd=None if cost is None else float(cost),
            input_tokens=_optional_int(call.get("input_tokens")), output_tokens=_optional_int(call.get("output_tokens"))))
    attempted = _optional_int(raw.get("attempted_calls"))
    return TopicerUsage(calls=calls, attempted_calls=max(attempted or 0, len(calls)))


@dataclass(frozen=True)
class TopicerProposals:
    """A ``/texts`` answer: the proposals and the usage of the request (``None``: unknown)."""
    proposals: list[dict[str, Any]]
    usage: TopicerUsage | None


@dataclass(frozen=True)
class TopicerStreamSummary:
    """The terminal ``usage_summary`` line of a database stream (Topicer ``TagProposalUsageSummary``)."""
    status: str
    """``complete``, ``partial`` (some chunks failed) or ``failed``."""
    max_chunks: int | None
    processed_chunks: int
    limit_reached: bool
    """``processed_chunks`` reached ``max_chunks`` (also when no candidate was left out)."""
    candidates_truncated: bool
    """More candidate chunks existed than ``max_chunks``; they were excluded."""
    usage: TopicerUsage | None


def _stream_summary(event: dict[str, Any]) -> TopicerStreamSummary | None:
    status, processed = event.get("status"), _optional_int(event.get("processed_chunks"))
    usage = _usage(event.get("usage"))
    if status not in ("complete", "partial", "failed") or processed is None or usage is None:
        return None
    return TopicerStreamSummary(status=status, max_chunks=_optional_int(event.get("max_chunks")),
                                processed_chunks=processed, limit_reached=event.get("limit_reached") is True,
                                candidates_truncated=event.get("candidates_truncated") is True, usage=usage)


CONFIGS_TIMEOUT = 10.0
"""Seconds for ``GET /v1/configs``, which needs no inference (proposal calls use ``timeout``)."""
CONFIGS_MAX_AGE = 60.0
"""Seconds a configuration list is reused; Topicer changes it only when it is redeployed."""


class TopicerClient:
    """Topicer at ``base_url`` with the named Topicer config.

    Built once per application by bootstrap from its config; holds no connection (each
    call opens its own). ``max_chunks_per_tag`` is sent as ``max_chunks`` with every
    database stream (semANT's policy, ``TOPICER_MAX_CHUNKS_PER_TAG``; never a caller's
    value). ``transport`` replaces the network in tests. HTTP and protocol errors raise
    ``TopicerError``.
    """

    def __init__(self, base_url: str, config_name: str, timeout: float, max_chunks_per_tag: int = 40,
                 transport: httpx.AsyncBaseTransport | None = None):
        """Raises ``ValueError`` when ``max_chunks_per_tag`` is not a positive integer."""
        if isinstance(max_chunks_per_tag, bool) or not isinstance(max_chunks_per_tag, int) or max_chunks_per_tag <= 0:
            raise ValueError("TOPICER_MAX_CHUNKS_PER_TAG must be a positive integer")
        self.base_url = base_url
        self.config_name = config_name
        self.timeout = timeout
        self.max_chunks_per_tag = max_chunks_per_tag
        self.transport = transport
        self._configs: tuple[float, list[str]] | None = None

    def with_config(self, config_name: str) -> "TopicerClient":
        """The same Topicer and settings with another of its configurations (#189)."""
        other = copy.copy(self)
        other.config_name = config_name
        return other

    def _client(self, timeout: float | None = None) -> httpx.AsyncClient:
        timeout = self.timeout if timeout is None else timeout
        return httpx.AsyncClient(base_url=self.base_url, timeout=httpx.Timeout(timeout, connect=10.0),
                                 transport=self.transport)

    async def list_configs(self) -> list[str]:
        """Call ``GET /v1/configs``: the names of the configurations Topicer has loaded.

        A list read in the last ``CONFIGS_MAX_AGE`` seconds is reused; failures are not.
        """
        if self._configs is not None and time.monotonic() - self._configs[0] < CONFIGS_MAX_AGE:
            return list(self._configs[1])
        path = "/v1/configs"
        try:
            async with self._client(CONFIGS_TIMEOUT) as client:
                resp = await client.get(path)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Topicer GET %s failed: %s", path, _failure(e))
            raise _error(e) from e
        if not isinstance(data, list) or not all(isinstance(name, str) for name in data):
            raise TopicerError("configs is not a list of names")
        self._configs = (time.monotonic(), list(data))
        return data

    async def propose_for_text(self, *, chunk_id: str, text: str, tags: list[TopicerTag]) -> TopicerProposals:
        """
        Call ``POST /v1/tags/propose/texts`` for a single text + a list of tags.

        Returns the ``tag_span_proposals`` of Topicer's response and its ``usage``.
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
            logger.warning("Topicer POST %s failed for chunk %s: %s", path, chunk_id, _failure(e))
            raise _error(e) from e
        if not isinstance(data, dict):
            data = {}
        proposals = data.get("tag_span_proposals")
        if proposals is not None and not isinstance(proposals, list):
            raise TopicerError("tag_span_proposals is not a list")
        return TopicerProposals(proposals=proposals or [], usage=_usage(data.get("usage")))

    async def propose_for_db_stream(self, *, tag: TopicerTag, collection_id: str, document_id: str
                                    ) -> AsyncGenerator[dict[str, Any] | TopicerStreamSummary, None]:
        """
        Call ``POST /v1/tags/propose/db/stream?max_chunks=<max_chunks_per_tag>`` and yield
        each chunk result as it arrives, a ``TextChunkWithTagSpanProposals`` dict::

            {"id": "<chunk_id>", "text": "...", "tag_span_proposals": [...]}

        and the terminal ``usage_summary`` line as a :class:`TopicerStreamSummary`. A stream
        that ends without it (an older Topicer, an interruption) has unknown usage. Lines
        that are not JSON objects, a malformed summary and other events are logged and
        skipped, never yielded as chunks.
        """
        body = {
            "tag": tag.payload(),
            "db_request": {"collection_id": str(collection_id), "document_id": str(document_id)},
        }
        path = "/v1/tags/propose/db/stream"
        try:
            async with self._client() as client:
                params = {"config_name": self.config_name, "max_chunks": self.max_chunks_per_tag}
                async with client.stream("POST", path, params=params, json=body) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.strip():
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            event = None
                        if not isinstance(event, dict):
                            logger.warning("Topicer stream produced a line that is not a JSON object "
                                           "(%d characters)", len(line))
                            continue
                        if "event" not in event:
                            yield event
                        elif event["event"] == "usage_summary" and (summary := _stream_summary(event)):
                            yield summary
                        else:
                            logger.warning("Topicer stream produced an unknown or malformed event line "
                                           "(%d characters)", len(line))
        except httpx.HTTPError as e:
            logger.warning("Topicer POST %s failed (tag=%s, doc=%s): %s", path, tag.id, document_id, _failure(e))
            raise _error(e) from e
