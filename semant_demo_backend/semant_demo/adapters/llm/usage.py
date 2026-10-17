"""Token, cost and outcome records of LLM calls, collected by a LangChain callback.

Every chat model built by the gateway carries a :class:`UsageCallback`, so calls made
inside LangChain chains, LangGraph nodes and agent tool subcalls are recorded too. A
record is a structured log line and, when telemetry is enabled, metrics. Neither ever
contains prompts, messages, generated text, document snippets or API keys.

Token counts are provider-reported when the response carries usage, otherwise
estimated from the text length (``usage_source`` says which). The cost is the
provider-reported one when the response carries it (OpenRouter ``usage.cost``), else the
tokens times the tier's configured prices, or the configured rate of a self-hosted
(``local_rate``) tier; ``cost_source`` says which, and an unknown cost is never zero.

The callback also enforces the feature's limits before a request is sent: an estimated
input above ``max_input_tokens``, and calls beyond ``max_calls`` of the current
:class:`LlmOperation`, are refused with an :class:`LlmRequestRefused`.
"""
from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Protocol
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from semant_demo.adapters.llm.models import FeatureLimits, PriceBasis, TierModel
from semant_demo.core.request_context import current_request_id

logger = logging.getLogger(__name__)

CHARS_PER_TOKEN = 4
"""Rough average used when a provider reports no usage and for the input limit."""

REPORTED_COST_KEY = "provider_cost_usd"
"""``response_metadata`` key of the provider-reported cost of a call (``gateway.py`` sets it)."""


class LlmRequestRefused(RuntimeError):
    """The server refused a model call before sending it.

    The message is server-authored and safe to show; ``status_code`` is the HTTP status
    a route answers with.
    """
    status_code = 503


class LlmNotConfigured(LlmRequestRefused):
    """The tier's provider has no credentials; raised before any request is sent."""
    status_code = 502


class LlmInputTooLarge(LlmRequestRefused):
    """A call's estimated input exceeds the feature's ``max_input_tokens``."""
    status_code = 413


class LlmOperationLimitExceeded(LlmRequestRefused):
    """An operation would make more model calls than its feature's ``max_calls``."""


class LlmMetrics(Protocol):
    def record_llm_call(self, *, attributes: dict[str, str], outcome: str, duration_seconds: float,
                        input_tokens: int | None, output_tokens: int | None, cost_usd: float | None) -> None: ...


@dataclass(frozen=True)
class LlmCall:
    """One finished provider call; token counts and cost are ``None`` when unknown."""
    feature: str
    model: TierModel
    outcome: str
    """``success``, ``error`` or ``cancelled``."""
    usage_source: str
    """``provider`` (reported by the provider), ``estimated`` or ``unavailable``."""
    input_tokens: int | None
    output_tokens: int | None
    duration_seconds: float
    request_id: str | None = None
    error_type: str | None = None
    reported_cost_usd: float | None = None
    """The provider-reported cost of the call, when its response carried one."""

    @property
    def total_tokens(self) -> int | None:
        if self.input_tokens is None or self.output_tokens is None:
            return None
        return self.input_tokens + self.output_tokens

    @property
    def cost_source(self) -> str:
        """``provider`` (reported), ``price`` (tokens times the tier's list prices),
        ``local_rate`` (a self-hosted tier's configured rate) or ``unknown``."""
        if self.model.price_basis == PriceBasis.local_rate:
            return "local_rate" if self.total_tokens is not None else "unknown"
        if self.reported_cost_usd is not None:
            return "provider"
        if self.total_tokens is not None and self.model.input_price is not None and self.model.output_price is not None:
            return "price"
        return "unknown"

    @property
    def cost_usd(self) -> float | None:
        """The cost of ``cost_source``; ``None`` when it is unknown."""
        source = self.cost_source
        if source == "provider":
            return self.reported_cost_usd
        if source in ("price", "local_rate"):
            return self.model.estimated_cost(self.input_tokens, self.output_tokens)
        return None

    def metric_attributes(self) -> dict[str, str]:
        return {"feature": self.feature, "tier": str(self.model.tier), "provider": str(self.model.provider),
                "model": self.model.model, "usage_source": self.usage_source, "cost_source": self.cost_source}


@dataclass
class LlmOperation:
    """The model calls of one user-visible operation (a search's summaries, a RAG answer).

    Opened by ``LlmGateway.operation``; every metered call made while it is current
    counts towards ``max_calls`` and adds its usage here. A call still running when the
    operation ends is added when it finishes.
    """
    feature: str
    max_calls: int
    started_calls: int = 0
    finished_calls: int = 0
    cost_usd: float = 0.0
    """The sum of the known call costs."""
    unknown_cost_calls: int = 0
    cost_sources: set[str] = field(default_factory=set)

    def start_call(self) -> None:
        if self.started_calls >= self.max_calls:
            raise LlmOperationLimitExceeded(
                f"The request needs more than the {self.max_calls} language model calls allowed for it.")
        self.started_calls += 1

    def add(self, call: LlmCall) -> None:
        self.finished_calls += 1
        cost = call.cost_usd
        self.cost_sources.add(call.cost_source)
        if cost is None:
            self.unknown_cost_calls += 1
        else:
            self.cost_usd += cost


current_llm_operation: ContextVar[LlmOperation | None] = ContextVar("current_llm_operation", default=None)


class UsageRecorder:
    """Writes each :class:`LlmCall` to the log and, if given, to telemetry metrics."""

    def __init__(self, metrics: LlmMetrics | None = None):
        self.metrics = metrics

    def record(self, call: LlmCall) -> None:
        extra = {
            "llm.feature": call.feature,
            "llm.tier": str(call.model.tier),
            "llm.provider": str(call.model.provider),
            "llm.model": call.model.model,
            "llm.outcome": call.outcome,
            "llm.usage_source": call.usage_source,
            "llm.cost_source": call.cost_source,
            "llm.duration_ms": round(call.duration_seconds * 1000, 2),
        }
        for key, value in (("llm.input_tokens", call.input_tokens), ("llm.output_tokens", call.output_tokens),
                           ("llm.total_tokens", call.total_tokens), ("llm.cost_usd", call.cost_usd),
                           ("request.id", call.request_id), ("error.type", call.error_type)):
            if value is not None:
                extra[key] = value
        logger.log(logging.INFO if call.outcome == "success" else logging.WARNING,
                   "LLM call finished", extra=extra)
        if self.metrics is not None:
            try:
                self.metrics.record_llm_call(
                    attributes=call.metric_attributes(), outcome=call.outcome,
                    duration_seconds=call.duration_seconds, input_tokens=call.input_tokens,
                    output_tokens=call.output_tokens, cost_usd=call.cost_usd)
            except Exception:
                logger.exception("Failed to record LLM call metrics")

    def record_operation(self, operation: LlmOperation) -> None:
        extra = {"llm.feature": operation.feature, "llm.operation.calls": operation.started_calls,
                 "llm.operation.finished_calls": operation.finished_calls,
                 "llm.operation.max_calls": operation.max_calls,
                 "llm.operation.cost_usd": round(operation.cost_usd, 8),
                 "llm.operation.unknown_cost_calls": operation.unknown_cost_calls,
                 "llm.operation.cost_sources": ",".join(sorted(operation.cost_sources))}
        request_id = current_request_id.get()
        if request_id is not None:
            extra["request.id"] = request_id
        logger.info("LLM operation finished", extra=extra)


@dataclass
class _Run:
    started: float
    input_chars: int
    request_id: str | None
    operation: LlmOperation | None = None
    output_chars: int = 0


class UsageCallback(AsyncCallbackHandler):
    """Records every run of the chat model it is attached to.

    Before the request is sent, it refuses a run (an :class:`LlmRequestRefused`) when
    ``missing_setting`` is set (``LlmNotConfigured`` naming the setting, so an empty key
    never reaches a provider), when the estimated input exceeds ``limits.max_input_tokens``,
    or when the current :class:`LlmOperation` has no calls left. Refused runs are logged,
    not recorded as calls.
    """

    # Errors must propagate to refuse a run; recording never raises.
    raise_error = True

    def __init__(self, feature: str, model: TierModel, recorder: UsageRecorder, missing_setting: str | None = None,
                 limits: FeatureLimits = FeatureLimits()):
        self.feature = feature
        self.model = model
        self.recorder = recorder
        self.missing_setting = missing_setting
        self.limits = limits
        self._runs: dict[UUID, _Run] = {}

    async def on_chat_model_start(self, serialized: dict[str, Any], messages: list[list[BaseMessage]], *,
                                  run_id: UUID, **kwargs: Any) -> None:
        if self.missing_setting:
            raise LlmNotConfigured(f"{self.missing_setting} is not configured on the server")
        input_chars = sum(_text_length(m.content) for batch in messages for m in batch)
        operation = current_llm_operation.get()
        try:
            if _estimate_tokens(input_chars) > self.limits.max_input_tokens:
                raise LlmInputTooLarge("The request is too large for the language model "
                                       f"(about {self.limits.max_input_tokens} tokens are allowed).")
            if operation is not None:
                operation.start_call()
        except LlmRequestRefused as e:
            logger.warning("LLM call refused", extra={"llm.feature": self.feature, "llm.tier": str(self.model.tier),
                                                      "error.type": type(e).__name__})
            raise
        self._runs[run_id] = _Run(started=perf_counter(), input_chars=input_chars,
                                  request_id=current_request_id.get(), operation=operation)

    async def on_llm_new_token(self, token: str, *, run_id: UUID, **kwargs: Any) -> None:
        run = self._runs.get(run_id)
        if run is not None:
            run.output_chars += len(token)

    async def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        run = self._runs.pop(run_id, None)
        if run is None:
            return
        usage = _reported_usage(response)
        cost = _reported_cost(response)
        if usage is not None:
            self._record(run, "success", "provider", *usage, reported_cost=cost)
        else:
            output_chars = sum(_text_length(g.text) for batch in response.generations for g in batch)
            self._record_estimate(run, "success", max(output_chars, run.output_chars), reported_cost=cost)

    async def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        run = self._runs.pop(run_id, None)
        if run is None:
            return
        outcome = "cancelled" if isinstance(error, asyncio.CancelledError) else "error"
        self._record_estimate(run, outcome, run.output_chars, error_type=type(error).__name__)

    def abandon_runs(self) -> None:
        """Record runs that will never end (their consumer was cancelled) as cancelled."""
        for run_id in list(self._runs):
            run = self._runs.pop(run_id)
            self._record_estimate(run, "cancelled", run.output_chars)

    def _record_estimate(self, run: _Run, outcome: str, output_chars: int, error_type: str | None = None,
                         reported_cost: float | None = None) -> None:
        self._record(run, outcome, "estimated", _estimate_tokens(run.input_chars), _estimate_tokens(output_chars),
                     error_type=error_type, reported_cost=reported_cost)

    def _record(self, run: _Run, outcome: str, usage_source: str, input_tokens: int | None,
                output_tokens: int | None, error_type: str | None = None,
                reported_cost: float | None = None) -> None:
        try:
            call = LlmCall(
                feature=self.feature, model=self.model, outcome=outcome, usage_source=usage_source,
                input_tokens=input_tokens, output_tokens=output_tokens,
                duration_seconds=perf_counter() - run.started, request_id=run.request_id, error_type=error_type,
                reported_cost_usd=reported_cost)
            if run.operation is not None:
                run.operation.add(call)
            self.recorder.record(call)
        except Exception:
            logger.exception("Failed to record LLM usage")


def _reported_usage(response: LLMResult) -> tuple[int, int] | None:
    """Summed provider-reported (input, output) tokens, or ``None`` if any generation lacks usage."""
    input_tokens = output_tokens = 0
    generations = [g for batch in response.generations for g in batch]
    if not generations:
        return None
    for generation in generations:
        usage = getattr(generation.message, "usage_metadata", None) if isinstance(generation, ChatGeneration) else None
        if not usage or usage.get("input_tokens") is None or usage.get("output_tokens") is None:
            return None
        input_tokens += usage["input_tokens"]
        output_tokens += usage["output_tokens"]
    return input_tokens, output_tokens


def _reported_cost(response: LLMResult) -> float | None:
    """The summed provider-reported cost, or ``None`` if any generation lacks one."""
    generations = [g for batch in response.generations for g in batch]
    costs = [(g.message.response_metadata or {}).get(REPORTED_COST_KEY) if isinstance(g, ChatGeneration) else None
             for g in generations]
    if not costs or any(c is None for c in costs):
        return None
    return float(sum(costs))


def reported_cost(usage: Any) -> float | None:
    """The call cost in an OpenRouter ``usage`` object, or ``None`` when it has none.

    For a call on the account's own provider key (``is_byok``) OpenRouter reports its fee
    as ``cost`` and the provider's charge as ``cost_details.upstream_inference_cost``.
    """
    if not isinstance(usage, dict):
        return None
    cost = usage.get("cost")
    if isinstance(cost, bool) or not isinstance(cost, (int, float)):
        return None
    upstream = (usage.get("cost_details") or {}).get("upstream_inference_cost")
    if usage.get("is_byok") and isinstance(upstream, (int, float)) and not isinstance(upstream, bool):
        cost += upstream
    return float(cost)


def _estimate_tokens(chars: int) -> int:
    return math.ceil(chars / CHARS_PER_TOKEN)


def _text_length(content: str | Sequence[Any]) -> int:
    if isinstance(content, str):
        return len(content)
    total = 0
    for part in content:
        if isinstance(part, str):
            total += len(part)
        elif isinstance(part, dict) and isinstance(part.get("text"), str):
            total += len(part["text"])
    return total
