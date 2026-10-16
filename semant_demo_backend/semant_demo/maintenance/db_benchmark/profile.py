"""Workload profiles (YAML) and the production-safety limits they are checked against."""
import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, PositiveFloat, PositiveInt

PROFILE_DIR = Path(__file__).resolve().parents[2] / "configs" / "db_benchmark"

ScenarioKind = Literal["search", "direct", "context", "document_view", "aggregate", "self_recall", "mixed"]
FilterKind = Literal["year_range", "language", "document_type", "tag", "user_collection"]


class SafetyLimits(BaseModel):
    """A profile beyond these limits needs ``--allow-heavy``."""
    max_concurrency: int = 10
    max_qps: float = 25.0
    max_requests_per_point: int = 200
    max_seconds_per_point: float = 60.0
    max_timeout: float = 60.0
    max_sampled_objects: int = 500


SAFE = SafetyLimits()


class Scenario(BaseModel):
    name: str
    kind: ScenarioKind
    description: str = ""
    mode: Literal["text", "vector", "hybrid"] | None = None
    """search / direct: the query call."""
    limit: PositiveInt = 10
    alpha: float = Field(0.5, ge=0, le=1)
    filter: FilterKind | None = None
    of: list[str] = Field(default_factory=list)
    """mixed: names of the scenarios a request is drawn from (uniformly)."""
    context_chunks: PositiveInt = 2
    """context: chunks read before and after the sampled chunk."""
    max_document_chunks: PositiveInt = 2000
    """document_view: documents with more chunks are skipped when sampling (keeps one request bounded)."""
    concurrency: list[PositiveInt] | None = Field(None, min_length=1)
    """Overrides the profile's levels (e.g. one level for an aggregate or a check)."""


class QueryInputs(BaseModel):
    sample_objects: PositiveInt = 100
    """Chunks sampled (seeded random cursor) for query vectors, terms, documents and contexts."""
    terms_per_query: PositiveInt = 2
    """BM25/hybrid text: this many of the longest words of the sampled chunk (never stored in results)."""
    year_ranges: list[tuple[int, int]] = Field(default_factory=lambda: [(1900, 1920)])
    languages: list[str] = Field(default_factory=lambda: ["ces"])
    document_types: list[str] = Field(default_factory=list)
    """Values of the document's ``documentType`` (filtered through the reference); empty: sampled."""
    sample_tags: int = Field(20, ge=0)
    """Tags that match at least one chunk (tags without chunks are skipped while sampling)."""
    sample_user_collections: int = Field(10, ge=0)
    """User collections with at least one chunk."""


class Collections(BaseModel):
    """Overrides of the application's collection names (aliases are fine)."""
    chunks: str | None = None
    documents: str | None = None
    tags: str | None = None
    user_collections: str | None = None
    spans: str | None = None


class Profile(BaseModel):
    name: str
    description: str = ""
    seed: int = 374
    concurrency: list[PositiveInt] = Field(default_factory=lambda: [1, 5, 10], min_length=1)
    requests_per_point: PositiveInt = 40
    max_seconds_per_point: PositiveFloat = 20.0
    warmup_requests: int = Field(5, ge=0)
    timeout: PositiveFloat = 30.0
    max_qps: PositiveFloat = 20.0
    """Total request starts per second across all workers (a pacing limit, not a target)."""
    pause_between_points: float = Field(2.0, ge=0)
    self_recall_k: PositiveInt = 10
    collections: Collections = Field(default_factory=Collections)
    queries: QueryInputs = Field(default_factory=QueryInputs)
    scenarios: list[Scenario]

    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()[:16]

    def violations(self, limits: SafetyLimits = SAFE) -> list[str]:
        """Where the profile exceeds the production-safe limits."""
        problems = []
        levels = set(self.concurrency) | {c for s in self.scenarios for c in (s.concurrency or [])}
        if max(levels, default=1) > limits.max_concurrency:
            problems.append(f"concurrency {max(levels)} > {limits.max_concurrency}")
        if self.max_qps > limits.max_qps:
            problems.append(f"max_qps {self.max_qps} > {limits.max_qps}")
        if self.requests_per_point > limits.max_requests_per_point:
            problems.append(f"requests_per_point {self.requests_per_point} > {limits.max_requests_per_point}")
        if self.max_seconds_per_point > limits.max_seconds_per_point:
            problems.append(f"max_seconds_per_point {self.max_seconds_per_point} > {limits.max_seconds_per_point}")
        if self.timeout > limits.max_timeout:
            problems.append(f"timeout {self.timeout} > {limits.max_timeout}")
        if self.queries.sample_objects > limits.max_sampled_objects:
            problems.append(f"sample_objects {self.queries.sample_objects} > {limits.max_sampled_objects}")
        return problems

    def check(self) -> None:
        names = [s.name for s in self.scenarios]
        if len(names) != len(set(names)):
            raise ValueError("scenario names must be unique")
        for s in self.scenarios:
            if s.kind in ("search", "direct") and s.mode is None:
                raise ValueError(f"scenario {s.name}: {s.kind} needs a mode")
            if s.kind == "direct" and s.filter is not None:
                raise ValueError(f"scenario {s.name}: direct scenarios take no filter")
            if s.kind == "mixed" and (not s.of or set(s.of) - set(names) or s.name in s.of):
                raise ValueError(f"scenario {s.name}: 'of' must name other scenarios")
        if not self.scenarios:
            raise ValueError("a profile needs at least one scenario")


def load_profile(name_or_path: str) -> Profile:
    """A profile by file path, or by name from ``configs/db_benchmark/``."""
    path = Path(name_or_path)
    if not path.exists():
        path = PROFILE_DIR / f"{name_or_path}.yaml"
    profile = Profile.model_validate(yaml.safe_load(path.read_text()))
    profile.check()
    return profile


def available_profiles() -> list[str]:
    return sorted(p.stem for p in PROFILE_DIR.glob("*.yaml"))


def apply_overrides(profile: Profile, overrides: dict[str, Any]) -> Profile:
    """The profile with top-level fields replaced (``None`` values are ignored)."""
    data = profile.model_dump()
    data.update({k: v for k, v in overrides.items() if v is not None})
    result = Profile.model_validate(data)
    result.check()
    return result
