"""Token, cost and outcome records of LLM calls, collected by a LangChain callback.

Every chat model built by the gateway carries a :class:`UsageCallback`, so calls made
inside LangChain chains, LangGraph nodes and agent tool subcalls are recorded too. A
record is a structured log line and, when telemetry is enabled, metrics. Neither ever
contains prompts, messages, generated text, document snippets or API keys.

Token counts are provider-reported when the response carries usage, otherwise
estimated from the text length (``usage_source`` says which). Costs are always
estimates from the tier's configured prices, and absent when a price is unknown.
"""
from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from semant_demo.adapters.llm.models import TierModel
from semant_demo.core.request_context import current_request_id

logger = logging.getLogger(__name__)

CHARS_PER_TOKEN = 4
"""Rough average used only when a provider reports no usage."""


class LlmNotConfigured(RuntimeError):
    """The tier's provider has no credentials; raised before any request is sent."""


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

    @property
    def total_tokens(self) -> int | None:
        if self.input_tokens is None or self.output_tokens is None:
            return None
        return self.input_tokens + self.output_tokens

    @property
    def cost_usd(self) -> float | None:
        if self.input_tokens is None or self.output_tokens is None:
            return None
        return self.model.estimated_cost(self.input_tokens, self.output_tokens)

    def metric_attributes(self) -> dict[str, str]:
        return {"feature": self.feature, "tier": str(self.model.tier), "provider": str(self.model.provider),
                "model": self.model.model, "usage_source": self.usage_source}


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
            "llm.duration_ms": round(call.duration_seconds * 1000, 2),
        }
        for key, value in (("llm.input_tokens", call.input_tokens), ("llm.output_tokens", call.output_tokens),
                           ("llm.total_tokens", call.total_tokens), ("llm.estimated_cost_usd", call.cost_usd),
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


@dataclass
class _Run:
    started: float
    input_chars: int
    request_id: str | None
    output_chars: int = 0


class UsageCallback(AsyncCallbackHandler):
    """Records every run of the chat model it is attached to.

    With ``missing_setting`` set, it refuses each run before the request is sent
    (``LlmNotConfigured`` naming the setting), so an empty key never reaches a provider.
    """

    # Errors must propagate to refuse an unconfigured provider; recording never raises.
    raise_error = True

    def __init__(self, feature: str, model: TierModel, recorder: UsageRecorder, missing_setting: str | None = None):
        self.feature = feature
        self.model = model
        self.recorder = recorder
        self.missing_setting = missing_setting
        self._runs: dict[UUID, _Run] = {}

    async def on_chat_model_start(self, serialized: dict[str, Any], messages: list[list[BaseMessage]], *,
                                  run_id: UUID, **kwargs: Any) -> None:
        if self.missing_setting:
            raise LlmNotConfigured(f"{self.missing_setting} is not configured on the server")
        self._runs[run_id] = _Run(started=perf_counter(),
                                  input_chars=sum(_text_length(m.content) for batch in messages for m in batch),
                                  request_id=current_request_id.get())

    async def on_llm_new_token(self, token: str, *, run_id: UUID, **kwargs: Any) -> None:
        run = self._runs.get(run_id)
        if run is not None:
            run.output_chars += len(token)

    async def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        run = self._runs.pop(run_id, None)
        if run is None:
            return
        usage = _reported_usage(response)
        if usage is not None:
            self._record(run, "success", "provider", *usage)
        else:
            output_chars = sum(_text_length(g.text) for batch in response.generations for g in batch)
            self._record_estimate(run, "success", max(output_chars, run.output_chars))

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

    def _record_estimate(self, run: _Run, outcome: str, output_chars: int, error_type: str | None = None) -> None:
        self._record(run, outcome, "estimated", _estimate_tokens(run.input_chars), _estimate_tokens(output_chars),
                     error_type=error_type)

    def _record(self, run: _Run, outcome: str, usage_source: str, input_tokens: int | None,
                output_tokens: int | None, error_type: str | None = None) -> None:
        try:
            self.recorder.record(LlmCall(
                feature=self.feature, model=self.model, outcome=outcome, usage_source=usage_source,
                input_tokens=input_tokens, output_tokens=output_tokens,
                duration_seconds=perf_counter() - run.started, request_id=run.request_id, error_type=error_type))
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
