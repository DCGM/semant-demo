"""The generator's configuration (#726): one YAML file, validated (unknown keys are refused).

See ``semant_demo/configs/search_benchmark_generator.yaml`` for a documented example.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from semant_demo.adapters.llm.models import ModelCatalog
from semant_demo.benchmarks.search_relevance.contracts import ID_PATTERN, RunConfiguration, VectorSpec, to_json
from semant_demo.benchmarks.search_relevance.languages import DEFAULT
from semant_demo.benchmarks.search_relevance.prompts import STYLES
from semant_demo.benchmarks.search_relevance.store_api import EmbeddingEndpoint, StoreSpec

INTENTS_FEATURE = "search_benchmark_intents"
TRANSLATION_FEATURE = "search_benchmark_translation"
JUDGE_FEATURE = "search_benchmark_judge"
FEATURES = (INTENTS_FEATURE, TRANSLATION_FEATURE, JUDGE_FEATURE)
ENV_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"
"""An environment variable's name (``api_key_env`` names one; it never holds the key itself)."""


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Seeds(_Section):
    sample: int = 0
    intents: int = 0
    judge: int = 0


class SourceSection(_Section):
    """The semANT store sampled from (read only). Without a host, ``Config()`` (the environment)."""
    host: str | None = None
    rest_port: int | None = None
    grpc_port: int | None = None
    description: str = ""
    """A human description for the manifest (never a credential)."""
    query_timeout: float = 120.0


class SampleSection(_Section):
    per_language: int | dict[str, int] = 100
    """Target chunks per corpus language (an int for all, or per language)."""
    min_chars: int = Field(100, ge=1)
    max_per_document: int = Field(20, ge=1)
    """At most this many sampled chunks from one document (context chunks not counted)."""
    oversample: float = Field(3.0, ge=1)
    """Candidates drawn per wanted chunk, so the per-document cap and strata can be honoured."""
    cursor_batch: int = Field(50, ge=1, le=1000)
    """Chunks read after one random id (ids are random UUIDs, so a batch is a random sample)."""
    max_draws: int = Field(2000, ge=1)
    """Random-cursor reads at most; a language still short is then sampled through windows."""
    window: int = Field(200, ge=1)
    max_windows: int = Field(20, ge=0)
    """Language-filtered windows per short language at most (rare languages)."""
    strata: Literal["balanced", "proportional"] = "balanced"
    """``balanced``: round-robin over (period, document type) strata of the candidates;
    ``proportional``: as drawn."""
    period_years: int = Field(25, ge=1)
    context_fraction: float = Field(0.1, ge=0, le=1)
    """Share of sampled chunks whose neighbours (``context_neighbours`` on each side) are added."""
    context_neighbours: int = Field(1, ge=0)
    include_import_sources: bool = True
    """Add the source chunks of imported intents (``intents.import``) to the corpus."""


class ImportSection(_Section):
    path: Path
    """JSON Lines: ``question`` (or ``query``), ``language``; optional ``corpus_id``/``chunk_id`` (its
    source chunk), ``need``, ``style``, ``intent_id``."""
    limit: int | None = Field(None, ge=0)
    """Imported intents at most (a seeded, language-balanced selection)."""


class IntentsSection(_Section):
    count: int = Field(30, ge=0)
    """Generated intents, spread evenly across the corpus languages."""
    styles: dict[str, float] = Field(default_factory=lambda: {
        "keywords": 0.25, "question": 0.25, "entity": 0.15, "long_question": 0.15, "paraphrase": 0.1, "ocr": 0.1})
    """Style -> share of the intents of each language."""
    style_descriptions: dict[str, str] = Field(default_factory=dict)
    """Descriptions of styles not in the built-in list (or replacing one)."""
    max_copied_words: int = Field(5, ge=1)
    """A query repeating more consecutive words of its passage is a near-copy: regenerated once, then dropped."""
    max_passage_chars: int = Field(3000, ge=100)
    spare: float = Field(0.5, ge=0)
    """Spare source chunks per intent, used when one fails or stays a near-copy."""
    one_per_document: bool = True
    imports: ImportSection | None = Field(None, alias="import")

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    @model_validator(mode="after")
    def _styles(self) -> "IntentsSection":
        if not self.styles or any(v < 0 for v in self.styles.values()) or not sum(self.styles.values()):
            raise ValueError("styles needs positive shares")
        unknown = [s for s in self.styles if s not in STYLES and s not in self.style_descriptions]
        if unknown:
            raise ValueError(f"styles without a description: {', '.join(unknown)}")
        return self

    def descriptions(self) -> dict[str, str]:
        return {**STYLES, **self.style_descriptions}


class TranslationSection(_Section):
    back_translate_fraction: float = Field(0.0, ge=0, le=1)
    """Share of translations translated back to check consistency (word overlap)."""
    min_back_overlap: float = Field(0.3, ge=0, le=1)
    require_all_languages: bool = True
    """Drop an intent without a query in every query language (all language pairs stay comparable)."""


class EndpointSection(_Section):
    base_url: str
    api_key_env: str | None = Field(None, pattern=ENV_PATTERN)
    """The name of the environment variable holding the key (never the key); it must be set when pooling."""
    timeout: float = 60.0
    batch_size: int = 32
    concurrency: int = 4

    def endpoint(self) -> EmbeddingEndpoint:
        return EmbeddingEndpoint(**self.model_dump())


class PoolingMethodSection(_Section):
    id: str = Field(pattern=ID_PATTERN)
    description: str = ""
    mode: Literal["text", "vector", "hybrid"]
    depth: int = Field(30, ge=1)
    alpha: float | None = None
    fusion: Literal["relativeScore", "ranked"] | None = None
    properties: dict[str, float] | None = None
    vector: VectorSpec | None = None
    endpoint: EndpointSection | None = None

    def configuration(self) -> RunConfiguration:
        return RunConfiguration(configuration_id=self.id, mode=self.mode, alpha=self.alpha, fusion=self.fusion,
                                vector=self.vector, properties=self.properties, depth=self.depth)

    @model_validator(mode="after")
    def _valid(self) -> "PoolingMethodSection":
        if self.mode == "text" and (self.vector is not None or self.endpoint is not None):
            raise ValueError(f"pooling method {self.id}: a text method takes no vector or endpoint")
        self.configuration()
        if self.mode != "text" and self.endpoint is None:
            raise ValueError(f"pooling method {self.id}: a {self.mode} method needs an endpoint")
        if self.id == "source":
            raise ValueError("pooling method id 'source' is reserved for source chunks")
        return self


class StoreSection(_Section):
    name: str = "semant-search-benchmark"
    host: str | None = None
    rest_port: int | None = None
    grpc_port: int | None = None
    token_file: Path = Path("~/.config/semant-demo/search-benchmark-store-token")

    def spec(self) -> StoreSpec:
        return StoreSpec(name=self.name, host=self.host, rest_port=self.rest_port, grpc_port=self.grpc_port,
                         token_file=self.token_file.expanduser())


class PoolingSection(_Section):
    methods: tuple[PoolingMethodSection, ...] = Field(min_length=1)
    max_candidates_per_intent: int = Field(40, ge=1)
    """Source chunks included; the others by their best rank in any method and query."""
    max_judgments: int | None = Field(None, ge=1)
    """Budget of (intent, chunk) pairs over all intents; the per-intent cap is lowered to fit."""
    store: StoreSection = StoreSection()
    concurrency: int = Field(8, ge=1)

    @model_validator(mode="after")
    def _unique(self) -> "PoolingSection":
        ids = [m.id for m in self.methods]
        if len(set(ids)) != len(ids):
            raise ValueError("pooling method ids must be unique")
        specs: dict[str, VectorSpec] = {}
        for method in self.methods:
            if method.vector is not None and specs.setdefault(method.vector.id, method.vector) != method.vector:
                raise ValueError(f"vector {method.vector.id}: pooling methods sharing a vector id must share its "
                                 "whole spec (model, target_vector, prefix, template, dimensions)")
        return self

    def missing_key_envs(self) -> list[str]:
        """The ``api_key_env`` variables of the pooling endpoints that are not set."""
        names = {m.endpoint.api_key_env for m in self.methods if m.endpoint and m.endpoint.api_key_env}
        return sorted(name for name in names if not os.environ.get(name))


class JudgeSection(_Section):
    max_chars: int = Field(2500, ge=100)
    """Passage characters shown to the judge; a longer passage is cut and the prompt says so."""
    per_language_fraction: float = Field(0.0, ge=0, le=1)
    """Share of intents judged once per query language (``language_grades``, ``consistent``)."""
    aggregation: Literal["median", "min", "source"] = "median"
    """How per-language grades become ``grade``: the median (the lower one of an even count), the
    minimum, or the source-language grade."""


class GeneratorConfig(_Section):
    dataset_id: str = Field(pattern=ID_PATTERN)
    version: str = Field(pattern=ID_PATTERN)
    description: str = ""
    languages: tuple[str, ...] = DEFAULT
    """Corpus (source-document) languages."""
    query_languages: tuple[str, ...] = DEFAULT
    seeds: Seeds = Seeds()
    models: dict[str, Any]
    """A model catalog (``ModelCatalog`` format) declaring the features of ``FEATURES``."""
    concurrency: int = Field(4, ge=1)
    """Model calls at once."""
    source: SourceSection = SourceSection()
    sample: SampleSection = SampleSection()
    intents: IntentsSection = IntentsSection()
    translation: TranslationSection = TranslationSection()
    pooling: PoolingSection
    judge: JudgeSection = JudgeSection()
    limitations: tuple[str, ...] = ()
    """Known limitations to state in the manifest besides the generated ones."""

    @model_validator(mode="after")
    def _check(self) -> "GeneratorConfig":
        catalog = ModelCatalog.from_dict(self.models)
        missing = [f for f in FEATURES if f not in catalog.features]
        if missing:
            raise ValueError(f"models does not declare {', '.join(missing)}")
        if not self.languages or not self.query_languages:
            raise ValueError("languages and query_languages must not be empty")
        return self

    def catalog(self) -> ModelCatalog:
        return ModelCatalog.from_dict(self.models)

    def target(self, language: str) -> int:
        per = self.sample.per_language
        return per.get(language, 0) if isinstance(per, dict) else per

    def section_hash(self, *names: str) -> str:
        data = self.model_dump(mode="json", by_alias=True)
        return hashlib.sha256(to_json({name: data.get(name) for name in names}).encode()).hexdigest()


def load_config(path: Path) -> tuple[GeneratorConfig, dict[str, Any], str]:
    """The configuration, its raw data and the SHA-256 of the file."""
    raw = path.read_bytes()
    data = yaml.safe_load(raw) or {}
    return GeneratorConfig.model_validate(data), data, hashlib.sha256(raw).hexdigest()
