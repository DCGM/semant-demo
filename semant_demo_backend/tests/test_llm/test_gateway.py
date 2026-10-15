"""LLM gateway (adapters/llm/): tier policy, LangChain models against fake HTTP providers,
and usage records for streamed, non-streamed, failed, abandoned and unmetered calls."""
import json
import logging

import httpx
import pytest
from httpx import ASGITransport
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from semant_demo.adapters.llm.gateway import FeatureChat, LlmGateway, ProviderSettings
from semant_demo.adapters.llm.models import Capability, LlmConfigurationError, ModelCatalog
from semant_demo.adapters.llm.usage import LlmNotConfigured
from semant_demo.config import SCRIPT_PATH
from semant_demo.core.request_context import current_request_id
from tests.corpus import load_corpus
from tests.fake_providers import create_fake_provider_app

API_KEY = "sk-test-secret-key"
PROMPT = "Kdo byl Jan Novák? [doc1] Jan Novák byl kronikář. [doc2] Novák psal kroniku."

CATALOG = {
    "tiers": {
        "tiny": {"provider": "ollama", "model": "fake-tiny", "input_price": 0, "output_price": 0},
        "small": {"provider": "openai", "model": "fake-small-no-usage"},
        "medium": {"provider": "openai", "model": "fake-medium", "capabilities": ["tools"],
                   "input_price": 2.0, "output_price": 10.0},
        "large": {"provider": "google", "model": "fake-gemini"},
    },
    "features": {
        "summary": {"default": "tiny", "allowed": ["tiny", "small"]},
        "chat": {"default": "medium"},
        "gemini": {"default": "large"},
    },
}


class RecordingMetrics:
    def __init__(self):
        self.calls = []

    def record_llm_call(self, **kwargs):
        self.calls.append(kwargs)


class CountingTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner):
        self.inner = inner
        self.paths = []
        self.payloads = []

    async def handle_async_request(self, request):
        self.paths.append(request.url.path)
        self.payloads.append(json.loads(request.content))
        return await self.inner.handle_async_request(request)


@pytest.fixture
def transport():
    return CountingTransport(ASGITransport(app=create_fake_provider_app(load_corpus())))


@pytest.fixture
def metrics():
    return RecordingMetrics()


def gateway(transport, metrics=None, catalog=None, **providers) -> LlmGateway:
    settings = {"openai_api_key": API_KEY, "openai_base_url": "http://fake/openai/v1",
                "ollama_base_url": "http://fake/ollama", **providers}
    return LlmGateway(ModelCatalog.from_dict(catalog or CATALOG), ProviderSettings(**settings), metrics,
                      http_transport=transport)


def messages(text=PROMPT):
    return [{"role": "system", "content": "Odpovídej stručně."}, {"role": "user", "content": text}]


# ── tier policy ────────────────────────────────────────────────────────────

def test_the_deployed_catalog_gives_every_feature_a_permitted_tier():
    catalog = ModelCatalog.load(SCRIPT_PATH / "configs" / "llm_models.yaml")

    assert set(catalog.features) == {"search_summary", "question", "span_chat", "rag"}
    for feature, policy in catalog.features.items():
        assert catalog.resolve(feature).tier == policy.default
    # Agentic RAG needs tool calling on the RAG default tier.
    assert Capability.tools in catalog.resolve("rag").capabilities


@pytest.mark.parametrize(("feature", "tier", "message"), [
    ("summary", "medium", "may not use tier medium"),
    ("summary", "gpt-4o", "Unknown model tier"),
    ("unknown", None, "No model tiers are configured"),
])
def test_a_feature_cannot_use_a_tier_or_model_it_is_not_allowed(feature, tier, message):
    with pytest.raises(LlmConfigurationError, match=message):
        ModelCatalog.from_dict(CATALOG).resolve(feature, tier)


def test_required_capabilities_are_checked():
    catalog = ModelCatalog.from_dict(CATALOG)

    assert catalog.resolve("chat", requires=[Capability.tools]).model == "fake-medium"
    with pytest.raises(LlmConfigurationError, match="lacks tools"):
        catalog.resolve("summary", requires=[Capability.tools])


@pytest.mark.parametrize(("features", "message"), [
    ({"x": {"default": "tiny", "allowed": ["small"]}}, "default tier tiny is not allowed"),
    ({"x": {"default": "huge"}}, "Invalid LLM model catalog"),
])
def test_an_inconsistent_catalog_is_rejected(features, message):
    tiers = {"tiny": CATALOG["tiers"]["tiny"], "small": CATALOG["tiers"]["small"]}
    with pytest.raises(LlmConfigurationError, match=message):
        ModelCatalog.from_dict({"tiers": tiers, "features": features})


def test_undefined_tiers_are_rejected():
    with pytest.raises(LlmConfigurationError, match="undefined tiers: large"):
        ModelCatalog.from_dict({"tiers": {"tiny": CATALOG["tiers"]["tiny"]},
                                "features": {"x": {"default": "tiny", "allowed": ["tiny", "large"]}}})



def test_deployed_openrouter_catalog_has_explicit_pricing_and_profiles():
    catalog = ModelCatalog.load(SCRIPT_PATH / "configs" / "llm_models.yaml")
    assert all(t.provider == "openai" for t in catalog.tiers.values())
    assert all(t.input_price is not None and t.output_price is not None for t in catalog.tiers.values())
    assert catalog.resolve("search_summary").reasoning == {"enabled": False}
    assert catalog.resolve("rag", "small").reasoning["effort"] == "low"
    assert catalog.resolve("question").model == "google/gemini-3.8-flash"
    assert catalog.resolve("rag").tier == "medium"
    assert catalog.resolve("rag", "large").model == "anthropic/claude-sonnet-5.5"


@pytest.mark.parametrize("reasoning", [
    {"enabled": False, "effort": "low"},
    {"effort": "wrong"},
    {"exclude": "false"},
])
def test_catalog_rejects_invalid_reasoning_settings(reasoning):
    with pytest.raises(LlmConfigurationError):
        ModelCatalog.from_dict({
            "tiers": {"small": {"provider": "openai", "model": "example", "reasoning": reasoning}},
            "features": {"x": {"default": "small"}},
        })


async def test_openrouter_request_applies_tier_reasoning_and_omits_claude_temperature(transport):
    catalog = ModelCatalog.load(SCRIPT_PATH / "configs" / "llm_models.yaml")
    llm = LlmGateway(catalog, ProviderSettings(openai_api_key=API_KEY,
                     openai_base_url="http://fake/openai/v1"), http_transport=transport)
    await llm.complete("search_summary", messages(), temperature=0.0, max_tokens=50)
    await llm.complete("rag", messages(), tier="small", temperature=0.4, max_tokens=100)
    await llm.complete("question", messages(), temperature=0.2, max_tokens=100)
    await llm.complete("rag", messages(), tier="large", temperature=0.3, max_tokens=100)

    assert transport.paths == ["/openai/v1/chat/completions"] * 4
    tiny, small, medium, large = transport.payloads
    assert tiny["reasoning"] == {"enabled": False}
    assert small["reasoning"] == {"effort": "low", "exclude": True}
    assert medium["reasoning"] == {"effort": "low", "exclude": True}
    assert large["reasoning"] == {"effort": "low", "exclude": True}
    assert "temperature" not in tiny and "temperature" not in small and "temperature" not in large
    assert medium["temperature"] == 0.2



# ── non-streamed calls ─────────────────────────────────────────────────────

async def test_openai_compatible_call_records_provider_usage_and_estimated_cost(transport, metrics):
    reply = await gateway(transport, metrics).complete("chat", messages(), temperature=0.0, max_tokens=50)

    assert reply == "Fake summary of 2 passage(s); last [doc2]."
    assert transport.paths == ["/openai/v1/chat/completions"]
    [call] = metrics.calls
    assert call["attributes"] == {"feature": "chat", "tier": "medium", "provider": "openai",
                                  "model": "fake-medium", "usage_source": "provider"}
    input_tokens = len(" ".join(m["content"] for m in messages()).split())
    assert (call["outcome"], call["input_tokens"], call["output_tokens"]) == ("success", input_tokens, 7)
    assert call["cost_usd"] == pytest.approx((input_tokens * 2.0 + 7 * 10.0) / 1_000_000)


async def test_ollama_call_records_provider_usage(transport, metrics):
    reply = await gateway(transport, metrics).complete("summary", messages())

    assert reply == "Fake summary of 2 passage(s); last [doc2]."
    assert transport.paths == ["/ollama/api/chat"]
    [call] = metrics.calls
    assert call["attributes"]["provider"] == "ollama" and call["attributes"]["usage_source"] == "provider"
    assert call["output_tokens"] == 7 and call["cost_usd"] == 0


async def test_missing_provider_usage_is_estimated_not_reported_as_zero(transport, metrics):
    await gateway(transport, metrics).complete("summary", messages(), tier="small")

    [call] = metrics.calls
    assert call["attributes"]["usage_source"] == "estimated"
    assert call["input_tokens"] > 0 and call["output_tokens"] > 0
    assert call["cost_usd"] is None   # the small tier has no price


async def test_calls_inside_langchain_chains_are_metered(transport, metrics):
    model = gateway(transport, metrics).chat_model("chat", temperature=0.0)
    chain = ChatPromptTemplate.from_messages([("user", "{question}")]) | model | StrOutputParser()

    await chain.ainvoke({"question": PROMPT})
    await chain.ainvoke({"question": PROMPT})

    assert [c["attributes"]["feature"] for c in metrics.calls] == ["chat", "chat"]
    assert all(c["attributes"]["usage_source"] == "provider" for c in metrics.calls)


async def test_models_with_the_same_options_are_shared(transport):
    llm = gateway(transport)

    assert llm.chat_model("chat", temperature=0.2) is llm.chat_model("chat", temperature=0.2)
    assert llm.chat_model("chat", temperature=0.2) is not llm.chat_model("chat", temperature=0.3)


async def test_provider_errors_are_recorded_and_raised(transport, metrics):
    llm = gateway(transport, metrics, openai_base_url="http://fake/unfaked/v1")

    with pytest.raises(Exception):
        await llm.complete("chat", messages())

    [call] = metrics.calls
    assert call["outcome"] == "error" and call["attributes"]["usage_source"] == "estimated"
    assert call["input_tokens"] > 0 and call["output_tokens"] == 0


@pytest.mark.parametrize(("feature", "setting"), [("chat", "OPENAI_API_KEY"), ("gemini", "GOOGLE_API_KEY")])
async def test_a_provider_without_a_key_is_refused_before_any_request(transport, metrics, feature, setting,
                                                                      monkeypatch):
    # Not even a key in the process environment is used.
    monkeypatch.setenv("OPENAI_API_KEY", "process-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "process-key")
    llm = gateway(transport, metrics, openai_api_key="", google_api_key="")

    with pytest.raises(LlmNotConfigured, match=f"{setting} is not configured on the server"):
        await llm.complete(feature, messages())

    assert transport.paths == [] and metrics.calls == []


# ── streamed calls ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(("feature", "path"), [("chat", "/openai/v1/chat/completions"),
                                               ("summary", "/ollama/api/chat")])
async def test_streamed_reply_records_provider_usage(transport, metrics, feature, path):
    chat = FeatureChat(gateway(transport, metrics), feature, temperature=0.4, max_tokens=100)

    deltas = [d async for d in chat.stream("Odpovídej stručně.", [{"role": "user", "content": PROMPT}])]

    assert len(deltas) > 1 and "".join(deltas) == "Fake summary of 2 passage(s); last [doc2]."
    assert transport.paths == [path]
    [call] = metrics.calls
    assert (call["outcome"], call["attributes"]["usage_source"], call["output_tokens"]) == ("success", "provider", 7)


async def test_abandoned_stream_records_the_partial_call_as_cancelled(transport, metrics):
    stream = gateway(transport, metrics).stream("chat", messages())

    first = await anext(stream)
    await stream.aclose()

    [call] = metrics.calls
    assert call["outcome"] == "cancelled" and call["attributes"]["usage_source"] == "estimated"
    assert call["output_tokens"] == -(-len(first) // 4)


async def test_missing_key_fails_a_stream_before_any_request(transport, metrics):
    chat = FeatureChat(gateway(transport, metrics, openai_api_key=""), "chat")

    with pytest.raises(LlmNotConfigured, match="OPENAI_API_KEY"):
        [d async for d in chat.stream("instructions", [{"role": "user", "content": "?"}])]
    assert transport.paths == [] and metrics.calls == []


# ── content-free records ───────────────────────────────────────────────────

async def test_usage_log_carries_identity_but_no_content_or_secrets(transport, caplog):
    caplog.set_level(logging.INFO, logger="semant_demo.adapters.llm.usage")
    token = current_request_id.set("req-123")
    try:
        await gateway(transport).complete("chat", messages())
    finally:
        current_request_id.reset(token)

    [record] = [r for r in caplog.records if r.name == "semant_demo.adapters.llm.usage"]
    fields = {k: v for k, v in vars(record).items() if k.startswith(("llm.", "request."))}
    assert fields["request.id"] == "req-123"
    assert fields["llm.feature"] == "chat" and fields["llm.tier"] == "medium" and fields["llm.model"] == "fake-medium"
    assert fields["llm.usage_source"] == "provider" and fields["llm.estimated_cost_usd"] > 0
    rendered = record.getMessage() + repr(vars(record))
    for secret_or_content in (API_KEY, "Novák", "kronik", "Fake summary"):
        assert secret_or_content not in rendered
