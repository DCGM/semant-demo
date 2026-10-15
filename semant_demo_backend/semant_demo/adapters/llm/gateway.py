"""The one boundary for backend-owned LLM calls.

``LlmGateway`` resolves a feature's permitted tier (``models.py``) and builds the
LangChain chat model for it with a :class:`~semant_demo.adapters.llm.usage.UsageCallback`
attached, so RAG chains and graphs, agent tool subcalls, search summaries, the question
endpoint and span chat are all metered the same way. Simple callers use
:meth:`LlmGateway.complete` and :meth:`LlmGateway.stream`.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import logging

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from pydantic import SecretStr

from semant_demo.adapters.llm.models import Capability, ModelCatalog, Provider, TierModel
from semant_demo.adapters.llm.usage import LlmMetrics, UsageCallback, UsageRecorder

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

    @classmethod
    def from_config(cls, config: Any) -> ProviderSettings:
        return cls(openai_api_key=config.OPENAI_API_KEY, openai_base_url=config.OPENAI_API_URL or None,
                   ollama_base_url=config.OLLAMA_URLS[0], google_api_key=config.GOOGLE_API_KEY)


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

    def tier_model(self, feature: str, tier: str | None = None, requires: Iterable[Capability] = ()) -> TierModel:
        """The model ``feature`` gets for ``tier`` (its default when ``None``); raises if not permitted."""
        return self.catalog.resolve(feature, tier, requires)

    def chat_model(self, feature: str, *, tier: str | None = None, temperature: float | None = None,
                   max_tokens: int | None = None, context_size: int | None = None,
                   requires: Iterable[Capability] = ()) -> BaseChatModel:
        """A metered LangChain chat model for ``feature``; shared by calls with the same options.

        ``context_size`` applies to Ollama only. Raises ``LlmConfigurationError`` when the
        feature may not use the tier or the tier lacks a required capability.
        """
        requires = tuple(sorted(requires))
        key = (feature, tier, temperature, max_tokens, context_size, requires)
        model = self._models.get(key)
        if model is None:
            tier_model = self.tier_model(feature, tier, requires)
            model = self._build(feature, tier_model, UsageCallback(feature, tier_model, self.recorder,
                                                                   self._missing_setting(tier_model)),
                                temperature, max_tokens, context_size)
            self._models[key] = model
        return model

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
        usage = UsageCallback(feature, tier_model, self.recorder, self._missing_setting(tier_model))
        model = self._build(feature, tier_model, usage, temperature, max_tokens, None)
        try:
            async for chunk in model.astream(list(messages)):
                text = message_text(chunk.content)
                if text:
                    yield text
        finally:
            usage.abandon_runs()

    def _missing_setting(self, model: TierModel) -> str | None:
        if model.provider == Provider.openai and not self.providers.openai_api_key:
            return "OPENAI_API_KEY"
        if model.provider == Provider.google and not self.providers.google_api_key:
            return "GOOGLE_API_KEY"
        return None

    def _build(self, feature: str, model: TierModel, usage: UsageCallback, temperature: float | None,
               max_tokens: int | None, context_size: int | None) -> BaseChatModel:
        if model.provider == Provider.openai:
            from langchain_openai import ChatOpenAI
            options: dict[str, Any] = {}
            if self._http_transport is not None:
                options["http_async_client"] = httpx.AsyncClient(transport=self._http_transport)
            if model.reasoning is not None:
                # OpenRouter-specific Chat Completions parameters (not OpenAI SDK kwargs).
                options["extra_body"] = {"reasoning": dict(model.reasoning)}
            return ChatOpenAI(model=model.model, api_key=SecretStr(self.providers.openai_api_key or _UNSET_KEY),
                              base_url=model.base_url or self.providers.openai_base_url,
                              temperature=temperature if model.supports_temperature else None,
                              max_tokens=max_tokens, stream_usage=True,
                              callbacks=[usage], **options)
        if model.provider == Provider.ollama:
            from langchain_ollama import ChatOllama
            client_kwargs = {"transport": self._http_transport} if self._http_transport is not None else {}
            return ChatOllama(model=model.model, base_url=model.base_url or self.providers.ollama_base_url,
                              temperature=temperature, num_predict=max_tokens, num_ctx=context_size,
                              client_kwargs=client_kwargs, callbacks=[usage])
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model.model,
                                      google_api_key=SecretStr(self.providers.google_api_key or _UNSET_KEY),
                                      temperature=temperature, max_output_tokens=max_tokens, callbacks=[usage])


def limit_provider_sdk_logs() -> None:
    """Keep provider SDK request logs from the application logs at ``LOG_LEVEL=DEBUG``.

    The OpenAI SDK logs whole request bodies (prompts, retrieved text, questions) at
    DEBUG; its INFO and higher records still pass the root level as before.
    """
    root_level = logging.getLogger().getEffectiveLevel()
    logging.getLogger("openai").setLevel(max(logging.INFO, root_level))


class FeatureChat:
    """Streams a reply for one feature from instructions and ``{"role", "content"}`` turns."""

    def __init__(self, llm: LlmGateway, feature: str, *, temperature: float | None = None,
                 max_tokens: int | None = None):
        self.llm = llm
        self.feature = feature
        self.temperature = temperature
        self.max_tokens = max_tokens

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
