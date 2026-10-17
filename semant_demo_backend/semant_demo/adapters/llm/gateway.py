"""The one boundary for backend-owned LLM calls.

``LlmGateway`` resolves a feature's permitted tier (``models.py``) and builds the
LangChain chat model for it with a :class:`~semant_demo.adapters.llm.usage.UsageCallback`
attached, so RAG chains and graphs, agent tool subcalls, search summaries, the question
endpoint and span chat are all metered the same way. Simple callers use
:meth:`LlmGateway.complete` and :meth:`LlmGateway.stream`.

The feature's limits (``models.FeatureLimits``) bound every call: its output tokens are
capped, an oversized input is refused before sending, and inside
:meth:`LlmGateway.operation` the calls of one user-visible operation are counted and capped.
Provider requests have a timeout and a small retry count (``ProviderSettings``).

An operation given an :class:`~semant_demo.adapters.llm.usage.OperationBudget` (the
caller's daily AI allowance) is admitted by it before its first model call, which a
refusal prevents, and its calls are settled with it when it ends. Every request-scoped
LLM use case runs its calls in such an operation.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable, Sequence
from contextvars import Token
from dataclasses import dataclass
from functools import cache
from typing import Any

import logging

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from pydantic import SecretStr

from semant_demo.adapters.llm.models import Capability, ModelCatalog, Provider, TierModel
from semant_demo.adapters.llm.usage import (
    REPORTED_COST_KEY, LlmMetrics, LlmOperation, OperationBudget, UsageCallback, UsageRecorder, current_llm_operation,
    reported_cost,
)

logger = logging.getLogger(__name__)

Message = dict[str, str] | BaseMessage
"""A ``{"role", "content"}`` turn (``system``/``user``/``assistant``) or a LangChain message."""

# Sent instead of a missing key, which the SDKs would otherwise read from the process
# environment. The usage callback refuses the run before it is sent.
_UNSET_KEY = "unset"


@dataclass(frozen=True)
class ProviderSettings:
    """Provider credentials and default endpoints, from the environment."""
    openai_api_key: str = ""
    openai_base_url: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    google_api_key: str = ""
    timeout_seconds: float = 120.0
    """Timeout of one provider request."""
    max_retries: int = 1
    """SDK retries of a failed request (OpenAI-compatible and Google; Ollama does not retry)."""

    @classmethod
    def from_config(cls, config: Any) -> ProviderSettings:
        return cls(openai_api_key=config.OPENAI_API_KEY, openai_base_url=config.OPENAI_API_URL or None,
                   ollama_base_url=config.OLLAMA_URLS[0], google_api_key=config.GOOGLE_API_KEY,
                   timeout_seconds=config.LLM_TIMEOUT_SECONDS, max_retries=config.LLM_MAX_RETRIES)


class LlmGateway:
    """Application-scoped; built at startup from settings, the tier catalog and telemetry.

    ``http_transport`` replaces the network for OpenAI-compatible and Ollama providers
    (tests use an in-process fake).
    """

    def __init__(self, catalog: ModelCatalog, providers: ProviderSettings, metrics: LlmMetrics | None = None,
                 *, http_transport: httpx.AsyncBaseTransport | None = None):
        self.catalog = catalog
        self.providers = providers
        self.recorder = UsageRecorder(metrics)
        self._http_transport = http_transport
        self._models: dict[tuple, BaseChatModel] = {}
        self._settlements: set[asyncio.Task] = set()

    def tier_model(self, feature: str, tier: str | None = None, requires: Iterable[Capability] = ()) -> TierModel:
        """The model ``feature`` gets for ``tier`` (its default when ``None``); raises if not permitted."""
        return self.catalog.resolve(feature, tier, requires)

    def chat_model(self, feature: str, *, tier: str | None = None, temperature: float | None = None,
                   max_tokens: int | None = None, context_size: int | None = None,
                   requires: Iterable[Capability] = ()) -> BaseChatModel:
        """A metered LangChain chat model for ``feature``; shared by calls with the same options.

        ``max_tokens`` is capped by the feature's ``max_output_tokens`` (its value when
        ``None``). ``context_size`` applies to Ollama only. Raises ``LlmConfigurationError``
        when the feature may not use the tier or the tier lacks a required capability.
        """
        requires = tuple(sorted(requires))
        max_tokens = self._output_limit(feature, max_tokens)
        key = (feature, tier, temperature, max_tokens, context_size, requires)
        model = self._models.get(key)
        if model is None:
            tier_model = self.tier_model(feature, tier, requires)
            model = self._build(feature, tier_model, self._usage(feature, tier_model),
                                temperature, max_tokens, context_size)
            self._models[key] = model
        return model

    def operation(self, feature: str, budget: OperationBudget | None = None) -> OperationScope:
        """``async with``: count the model calls made inside as one user-visible operation
        of ``feature``, admitted by ``budget`` when one is given.

        A call beyond the feature's ``max_calls`` is refused (``LlmOperationLimitExceeded``).
        Inside another operation, the outer one keeps counting (and ``budget`` is unused).
        """
        return OperationScope(self, feature, budget)

    async def wait_for_settlements(self) -> None:
        """Wait for the settlements of ended operations (one may outlive its cancelled request)."""
        while self._settlements:
            await asyncio.gather(*self._settlements)

    async def _settle(self, budget: OperationBudget, admission: Any, operation: LlmOperation) -> None:
        # A task of its own, so that cancelling the request (a client disconnect) does not
        # cancel the settlement; the request's cancellation still propagates.
        task = asyncio.create_task(_settle_logged(budget, admission, operation))
        self._settlements.add(task)
        task.add_done_callback(self._settlements.discard)
        await asyncio.shield(task)

    async def complete(self, feature: str, messages: Sequence[Message], *, tier: str | None = None,
                       temperature: float | None = None, max_tokens: int | None = None,
                       context_size: int | None = None) -> str:
        """The reply text of one non-streamed call."""
        model = self.chat_model(feature, tier=tier, temperature=temperature, max_tokens=max_tokens,
                                context_size=context_size)
        reply = await model.ainvoke(list(messages))
        return message_text(reply.content)

    async def stream(self, feature: str, messages: Sequence[Message], *, tier: str | None = None,
                     temperature: float | None = None, max_tokens: int | None = None) -> AsyncIterator[str]:
        """Yield the reply's text deltas. A stream abandoned by its consumer is recorded as cancelled."""
        tier_model = self.tier_model(feature, tier)
        # A model per stream, so abandoning it cannot touch the runs of other requests.
        usage = self._usage(feature, tier_model)
        model = self._build(feature, tier_model, usage, temperature, self._output_limit(feature, max_tokens), None)
        try:
            async for chunk in model.astream(list(messages)):
                text = message_text(chunk.content)
                if text:
                    yield text
        finally:
            usage.abandon_runs()

    def _usage(self, feature: str, model: TierModel) -> UsageCallback:
        return UsageCallback(feature, model, self.recorder, self._missing_setting(model),
                             self.catalog.policy(feature).limits)

    def _output_limit(self, feature: str, max_tokens: int | None) -> int:
        limit = self.catalog.policy(feature).limits.max_output_tokens
        return limit if max_tokens is None else min(max_tokens, limit)

    def _missing_setting(self, model: TierModel) -> str | None:
        if model.provider == Provider.openai and not self.providers.openai_api_key:
            return "OPENAI_API_KEY"
        if model.provider == Provider.google and not self.providers.google_api_key:
            return "GOOGLE_API_KEY"
        return None

    def _build(self, feature: str, model: TierModel, usage: UsageCallback, temperature: float | None,
               max_tokens: int | None, context_size: int | None) -> BaseChatModel:
        providers = self.providers
        if model.provider == Provider.openai:
            options: dict[str, Any] = {}
            if self._http_transport is not None:
                options["http_async_client"] = httpx.AsyncClient(transport=self._http_transport)
            if model.reasoning is not None:
                # OpenRouter-specific Chat Completions parameters (not OpenAI SDK kwargs).
                options["extra_body"] = {"reasoning": dict(model.reasoning)}
            return _cost_reporting_chat_openai()(
                model=model.model, api_key=SecretStr(providers.openai_api_key or _UNSET_KEY),
                base_url=model.base_url or providers.openai_base_url,
                temperature=temperature if model.supports_temperature else None,
                max_tokens=max_tokens, stream_usage=True, timeout=providers.timeout_seconds,
                max_retries=providers.max_retries, callbacks=[usage], **options)
        if model.provider == Provider.ollama:
            from langchain_ollama import ChatOllama
            client_kwargs: dict[str, Any] = {"timeout": providers.timeout_seconds}
            if self._http_transport is not None:
                client_kwargs["transport"] = self._http_transport
            return ChatOllama(model=model.model, base_url=model.base_url or providers.ollama_base_url,
                              temperature=temperature, num_predict=max_tokens, num_ctx=context_size,
                              client_kwargs=client_kwargs, callbacks=[usage])
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model.model,
                                      google_api_key=SecretStr(providers.google_api_key or _UNSET_KEY),
                                      temperature=temperature, max_output_tokens=max_tokens,
                                      timeout=providers.timeout_seconds, max_retries=providers.max_retries,
                                      callbacks=[usage])


class OperationScope:
    """One user-visible operation of a feature (``LlmGateway.operation``).

    Entering it admits the operation against its budget (unless :meth:`admit` did so
    already) and makes it the current operation; leaving it settles its calls with the
    budget. A streamed reply admits before its response starts and enters the scope in
    the stream, so a refusal is still an HTTP error. An operation admitted and never
    entered stays unsettled: its reservation remains charged.
    """

    def __init__(self, gateway: LlmGateway, feature: str, budget: OperationBudget | None):
        self.gateway = gateway
        self.feature = feature
        self.budget = budget
        self._admission: Any = None
        self._admitted = False
        self._operation: LlmOperation | None = None
        self._token: Token | None = None

    async def admit(self) -> None:
        """Admit the operation against its budget now; raises the budget's refusal."""
        if self._admitted or self.budget is None or current_llm_operation.get() is not None:
            return
        reserve_usd = self.gateway.catalog.policy(self.feature).limits.reserve_usd
        self._admission = await self.budget.admit(self.feature, reserve_usd)
        self._admitted = True

    async def __aenter__(self) -> LlmOperation:
        current = current_llm_operation.get()
        if current is not None:
            return current
        await self.admit()
        self._operation = LlmOperation(self.feature, self.gateway.catalog.policy(self.feature).limits.max_calls)
        self._token = current_llm_operation.set(self._operation)
        return self._operation

    async def __aexit__(self, *exc_info: Any) -> None:
        operation, self._operation = self._operation, None
        if operation is None:
            return
        current_llm_operation.reset(self._token)
        self.gateway.recorder.record_operation(operation)
        if self._admitted:
            await self.gateway._settle(self.budget, self._admission, operation)


async def _settle_logged(budget: OperationBudget, admission: Any, operation: LlmOperation) -> None:
    try:
        await budget.settle(admission, operation)
    except Exception as e:
        # Content-free; the operation's reservation stays charged.
        logger.error("LLM operation settlement failed: %s", type(e).__name__)


@cache
def _cost_reporting_chat_openai() -> type[BaseChatModel]:
    """``ChatOpenAI`` that keeps a reported call cost (OpenRouter ``usage.cost``).

    LangChain drops the fields of ``usage`` it does not know; this subclass copies the cost
    into the reply's ``response_metadata`` (``REPORTED_COST_KEY``), for streamed replies
    from the final usage chunk, where the usage callback reads it.
    """
    from langchain_openai import ChatOpenAI

    class CostReportingChatOpenAI(ChatOpenAI):
        def _create_chat_result(self, response: Any, generation_info: dict | None = None) -> Any:
            result = super()._create_chat_result(response, generation_info)
            response_dict = response if isinstance(response, dict) else response.model_dump()
            cost = reported_cost(response_dict.get("usage"))
            if cost is not None and result.generations:
                result.generations[0].message.response_metadata[REPORTED_COST_KEY] = cost
            return result

        def _convert_chunk_to_generation_chunk(self, chunk: dict, default_chunk_class: type,
                                               base_generation_info: dict | None) -> Any:
            generation = super()._convert_chunk_to_generation_chunk(chunk, default_chunk_class,
                                                                    base_generation_info)
            cost = reported_cost(chunk.get("usage"))
            if generation is not None and cost is not None:
                generation.message.response_metadata[REPORTED_COST_KEY] = cost
            return generation

    return CostReportingChatOpenAI


def limit_provider_sdk_logs() -> None:
    """Keep provider SDK request logs from the application logs at ``LOG_LEVEL=DEBUG``.

    The OpenAI SDK logs whole request bodies (prompts, retrieved text, questions) at
    DEBUG; its INFO and higher records still pass the root level as before.
    """
    root_level = logging.getLogger().getEffectiveLevel()
    logging.getLogger("openai").setLevel(max(logging.INFO, root_level))


class FeatureChat:
    """Streams a reply for one feature from instructions and ``{"role", "content"}`` turns;
    run it inside :meth:`operation`."""

    def __init__(self, llm: LlmGateway, feature: str, *, temperature: float | None = None,
                 max_tokens: int | None = None):
        self.llm = llm
        self.feature = feature
        self.temperature = temperature
        self.max_tokens = max_tokens

    def operation(self, budget: OperationBudget | None = None) -> OperationScope:
        return self.llm.operation(self.feature, budget)

    async def stream(self, instructions: str, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        async for delta in self.llm.stream(self.feature, [{"role": "system", "content": instructions}, *messages],
                                           temperature=self.temperature, max_tokens=self.max_tokens):
            yield delta


def message_text(content: str | list[Any]) -> str:
    """The text of a LangChain message ``content`` (a string or a list of content parts)."""
    if isinstance(content, str):
        return content
    return "".join(part if isinstance(part, str) else part.get("text", "")
                   for part in content
                   if isinstance(part, str) or (isinstance(part, dict) and part.get("type") == "text"))
