"""Model calls of the benchmark stages through the backend's ``LlmGateway``: provenance,
calls with retries that report failures by class only, bounded concurrency and usage totals."""
import asyncio
from collections.abc import Callable
from typing import Any, TypeVar

from semant_demo.adapters.llm.gateway import LlmGateway
from semant_demo.adapters.llm.models import LlmConfigurationError, Provider
from semant_demo.adapters.llm.usage import LlmInputTooLarge, LlmRequestRefused

ATTEMPTS = 3
BACKOFF = 1.0
T = TypeVar("T")


class Refused(Exception):
    """The run cannot start or continue (configuration, a refused model call)."""


class InvalidReply(ValueError):
    """A model reply that cannot be used; its message is safe to report (no prompt or text)."""


USAGE_KEYS = ("calls", "failed_calls", "input_tokens", "output_tokens", "cost_usd", "unknown_cost_calls")


class UsageTotals:
    """Model usage of this process, recorded by the gateway (its ``LlmMetrics``)."""

    def __init__(self) -> None:
        self.totals: dict[str, float] = {key: 0 for key in USAGE_KEYS}

    def record_llm_call(self, *, attributes: dict[str, str], outcome: str, duration_seconds: float,
                        input_tokens: int | None, output_tokens: int | None, cost_usd: float | None) -> None:
        self.totals["calls"] += 1
        self.totals["failed_calls"] += outcome != "success"
        self.totals["input_tokens"] += input_tokens or 0
        self.totals["output_tokens"] += output_tokens or 0
        if cost_usd is None:
            self.totals["unknown_cost_calls"] += 1
        else:
            self.totals["cost_usd"] += cost_usd


def model_provenance(llm: LlmGateway, feature: str) -> dict[str, Any]:
    """What serves ``feature``; raises ``Refused`` when the catalog cannot or a provider setting is
    missing (no model call)."""
    try:
        model = llm.tier_model(feature)
        missing = llm.missing_setting(feature)
        limits = llm.catalog.policy(feature).limits
    except LlmConfigurationError as e:
        raise Refused(str(e)) from None
    if missing:
        raise Refused(f"{missing} is not set; the {model.tier} tier ({model.provider}) of {feature} needs it")
    endpoint = model.base_url or {Provider.openai: llm.providers.openai_base_url,
                                  Provider.ollama: llm.providers.ollama_base_url}.get(model.provider)
    return {"feature": feature, "tier": str(model.tier), "provider": str(model.provider), "model": model.model,
            "model_endpoint": endpoint, "max_input_tokens": limits.max_input_tokens,
            "max_output_tokens": limits.max_output_tokens}


async def ask(llm: LlmGateway, feature: str, messages: list[dict[str, str]], parse: Callable[[str], T]
              ) -> tuple[T | None, str | None]:
    """``(parsed reply, None)``, or ``(None, reason)`` after ``ATTEMPTS`` failed or invalid
    replies. The reason is an exception class or ``InvalidReply``'s message, never text.
    Raises ``Refused`` when the gateway refuses the feature."""
    limits = llm.catalog.policy(feature).limits
    context_size = (limits.max_input_tokens + limits.max_output_tokens
                    if limits.max_input_tokens and limits.max_output_tokens else None)
    reason = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            async with llm.operation(feature):
                reply = await llm.complete(feature, messages, context_size=context_size)
        except LlmInputTooLarge:
            return None, "too_large"
        except LlmRequestRefused as e:
            raise Refused(f"The model call was refused: {type(e).__name__}") from None
        except Exception as e:  # the provider's message may hold the prompt: the class only
            reason = f"model_failed: {type(e).__name__}"
        else:
            try:
                return parse(reply), None
            except InvalidReply as e:
                reason = f"invalid_output: {e}"
        if attempt < ATTEMPTS:
            await asyncio.sleep(BACKOFF * attempt)
    return None, reason


async def gather(items, concurrency: int, call) -> list:
    """``call`` for every item, at most ``concurrency`` at a time; on an error the others are
    cancelled before it propagates."""
    semaphore = asyncio.Semaphore(concurrency)

    async def one(item):
        async with semaphore:
            return await call(item)
    tasks = [asyncio.ensure_future(one(item)) for item in items]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
