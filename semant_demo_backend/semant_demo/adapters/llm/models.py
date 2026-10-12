"""Server-side model tiers and the tiers each feature may use.

A tier (``tiny``/``small``/``medium``/``large``) names one provider and model, its
practical capabilities and its estimated price. Features ask for a tier, never for a
model; clients choose neither. The catalog is read from YAML (``LLM_MODELS_CONFIG``).
It holds no secrets: provider keys and default endpoints come from the environment.
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

    def estimated_cost(self, input_tokens: int, output_tokens: int) -> float | None:
        if self.input_price is None or self.output_price is None:
            return None
        return (input_tokens * self.input_price + output_tokens * self.output_price) / 1_000_000


@dataclass(frozen=True)
class FeaturePolicy:
    default: ModelTier
    allowed: frozenset[ModelTier]


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
                                            allowed=frozenset(_tiers(spec.get("allowed") or [spec["default"]])))
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
        policy = self.features.get(feature)
        if policy is None:
            raise LlmConfigurationError(f"No model tiers are configured for feature {feature!r}")
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


def _tiers(names: Iterable[str]) -> list[ModelTier]:
    return [ModelTier(n) for n in names]


def _tier(tier: ModelTier, spec: dict[str, Any]) -> TierModel:
    return TierModel(
        tier=tier,
        provider=Provider(spec["provider"]),
        model=str(spec["model"]),
        base_url=spec.get("base_url") or None,
        capabilities=frozenset(Capability(c) for c in spec.get("capabilities") or []),
        input_price=_price(spec.get("input_price")),
        output_price=_price(spec.get("output_price")),
    )


def _price(value: Any) -> float | None:
    return None if value is None else float(value)
