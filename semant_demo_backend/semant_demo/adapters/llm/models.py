"""Server-side model tiers and the tiers each feature may use.

A tier (``tiny``/``small``/``medium``/``large``) names one provider and model, its
practical capabilities and its estimated price. Features ask for a tier, never for a
model; clients choose neither. Each feature also has server-side limits on one call and
on the calls of one user-visible operation. The catalog is read from YAML
(``LLM_MODELS_CONFIG``). It holds no secrets: provider keys and default endpoints come
from the environment.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml


class ModelTier(StrEnum):
    tiny = "tiny"
    small = "small"
    medium = "medium"
    large = "large"


class Provider(StrEnum):
    openai = "openai"
    """Any OpenAI-compatible Chat Completions endpoint (OpenAI, OpenRouter)."""
    ollama = "ollama"
    google = "google"


class Capability(StrEnum):
    tools = "tools"
    """The model can call tools (function calling)."""


class PriceBasis(StrEnum):
    provider_list = "provider_list"
    """A hosted provider's list prices; a provider-reported call cost is preferred to them."""
    local_rate = "local_rate"
    """A USD-equivalent accounting rate of a self-hosted model; not a provider bill."""


class LlmConfigurationError(ValueError):
    """The model catalog is invalid, or a feature asked for a tier it may not use."""


@dataclass(frozen=True)
class TierModel:
    tier: ModelTier
    provider: Provider
    model: str
    base_url: str | None = None
    """Overrides the provider's endpoint from the environment for this tier."""
    capabilities: frozenset[Capability] = frozenset()
    input_price: float | None = None
    """Estimated USD per million input tokens; ``None`` when unknown."""
    output_price: float | None = None
    """Estimated USD per million output tokens; ``None`` when unknown."""
    price_basis: PriceBasis = PriceBasis.provider_list
    """What the prices are; ``local_rate`` tiers need both prices (zero is explicit)."""
    reasoning: dict[str, str | bool] | None = None
    """Optional OpenRouter ``reasoning`` payload, fixed server-side per tier."""
    supports_temperature: bool = True
    """Some current models reject non-default sampling temperatures altogether."""

    def estimated_cost(self, input_tokens: int, output_tokens: int) -> float | None:
        if self.input_price is None or self.output_price is None:
            return None
        return (input_tokens * self.input_price + output_tokens * self.output_price) / 1_000_000


@dataclass(frozen=True)
class FeatureLimits:
    """Server-side bounds of a feature's model work; clients cannot raise them."""
    max_output_tokens: int = 1024
    """Upper bound of a call's output (``max_tokens``), reasoning tokens included."""
    max_input_tokens: int = 16000
    """Input of one call, estimated from its length; a larger call is refused before sending."""
    max_calls: int = 1
    """Model calls of one user-visible operation (``LlmGateway.operation``)."""


@dataclass(frozen=True)
class FeaturePolicy:
    default: ModelTier
    allowed: frozenset[ModelTier]
    limits: FeatureLimits = FeatureLimits()


@dataclass(frozen=True)
class ModelCatalog:
    tiers: dict[ModelTier, TierModel]
    features: dict[str, FeaturePolicy]

    @classmethod
    def load(cls, path: str | Path) -> ModelCatalog:
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(yaml.safe_load(f) or {})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelCatalog:
        try:
            tiers = {ModelTier(name): _tier(ModelTier(name), spec) for name, spec in (data.get("tiers") or {}).items()}
            features = {name: FeaturePolicy(default=ModelTier(spec["default"]),
                                            allowed=frozenset(_tiers(spec.get("allowed") or [spec["default"]])),
                                            limits=_limits(spec.get("limits") or {}))
                        for name, spec in (data.get("features") or {}).items()}
        except (KeyError, TypeError, ValueError) as e:
            raise LlmConfigurationError(f"Invalid LLM model catalog: {e!r}") from e
        for name, policy in features.items():
            if policy.default not in policy.allowed:
                raise LlmConfigurationError(f"Feature {name!r}: default tier {policy.default} is not allowed")
            missing = sorted(t for t in policy.allowed if t not in tiers)
            if missing:
                raise LlmConfigurationError(f"Feature {name!r} allows undefined tiers: {', '.join(missing)}")
        return cls(tiers=tiers, features=features)

    def resolve(self, feature: str, tier: str | None = None,
                requires: Iterable[Capability] = ()) -> TierModel:
        """The model of ``tier`` (the feature's default when ``None``) if the feature may use it."""
        policy = self.policy(feature)
        try:
            selected = policy.default if tier is None else ModelTier(tier)
        except ValueError:
            raise LlmConfigurationError(f"Unknown model tier {tier!r}") from None
        if selected not in policy.allowed:
            allowed = ", ".join(sorted(policy.allowed))
            raise LlmConfigurationError(f"Feature {feature!r} may not use tier {selected} (allowed: {allowed})")
        model = self.tiers[selected]
        lacking = sorted(set(requires) - model.capabilities)
        if lacking:
            raise LlmConfigurationError(f"Tier {selected} ({model.model}) lacks {', '.join(lacking)} "
                                        f"needed by feature {feature!r}")
        return model

    def policy(self, feature: str) -> FeaturePolicy:
        policy = self.features.get(feature)
        if policy is None:
            raise LlmConfigurationError(f"No model tiers are configured for feature {feature!r}")
        return policy


def _tiers(names: Iterable[str]) -> list[ModelTier]:
    return [ModelTier(n) for n in names]


def _tier(tier: ModelTier, spec: dict[str, Any]) -> TierModel:
    reasoning = spec.get("reasoning")
    provider = Provider(spec["provider"])
    if reasoning is not None:
        if provider != Provider.openai or not isinstance(reasoning, dict) or not reasoning:
            raise ValueError("reasoning requires a non-empty OpenAI-compatible tier mapping")
        if set(reasoning) - {"enabled", "effort", "exclude"}:
            raise ValueError("Unsupported reasoning options")
        if "effort" in reasoning and reasoning["effort"] not in {
            "none", "minimal", "low", "medium", "high", "xhigh", "max"
        }:
            raise ValueError("Unsupported reasoning effort")
        for flag in ("enabled", "exclude"):
            if flag in reasoning and not isinstance(reasoning[flag], bool):
                raise ValueError(f"reasoning.{flag} must be a boolean")
        if reasoning.get("enabled") is False and "effort" in reasoning:
            raise ValueError("Disabled reasoning cannot have an effort")
    supports_temperature = spec.get("supports_temperature", True)
    if not isinstance(supports_temperature, bool):
        raise ValueError("supports_temperature must be a boolean")
    input_price, output_price = _price(spec.get("input_price")), _price(spec.get("output_price"))
    price_basis = PriceBasis(spec.get("price_basis", PriceBasis.provider_list))
    if price_basis == PriceBasis.local_rate and (input_price is None or output_price is None):
        raise ValueError("A local_rate tier needs input_price and output_price")
    return TierModel(
        tier=tier,
        provider=provider,
        model=str(spec["model"]),
        base_url=spec.get("base_url") or None,
        capabilities=frozenset(Capability(c) for c in spec.get("capabilities") or []),
        input_price=input_price,
        output_price=output_price,
        price_basis=price_basis,
        reasoning=reasoning,
        supports_temperature=supports_temperature,
    )


def _price(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or float(value) < 0:
        raise ValueError("Prices must be non-negative numbers")
    return float(value)


def _limits(spec: dict[str, Any]) -> FeatureLimits:
    unknown = set(spec) - set(FeatureLimits.__dataclass_fields__)
    if unknown:
        raise ValueError(f"Unsupported limits: {', '.join(sorted(unknown))}")
    for name, value in spec.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"limits.{name} must be a positive integer")
    return FeatureLimits(**spec)
