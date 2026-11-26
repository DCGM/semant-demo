"""The runner's experiment configuration (#727): one YAML file that names the dataset, the
benchmark store, the embedding endpoints and vectors, a grid of search settings expanded into
``RunConfiguration``s, explicit configurations and the run budget (docs/SEARCH_BENCHMARK.md,
example: ``semant_demo/configs/search_benchmark/runner.example.yaml``).

Configuration ids are derived from the settings, so they are stable across runs and do not
depend on what else the grid holds (adding an alpha never renames an existing configuration)::

    text                              BM25 with the application's properties
    text.b-titles                     BM25 with the property set ``titles``
    vector.qwen.p-instruct            vector ``qwen`` with the query prefix ``instruct``
    hybrid.qwen.a0.5.ranked.p-none    hybrid, alpha 0.5, ranked fusion, prefix ``none``
    hybrid.qwen.a0.5.ranked.p-none.b-titles

Metadata filters are not part of a configuration: the benchmark measures relevance only (#727).
"""
from __future__ import annotations

import hashlib
import random
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from semant_demo.benchmarks.search_relevance.contracts import (
    ID_PATTERN, LANGUAGE_PATTERN, Dataset, Query, RunConfiguration, VectorSpec)
from semant_demo.benchmarks.search_relevance.store_api import EmbeddingEndpoint, StoreSpec

NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]*$"
"""A vector, query prefix or property set name: one segment of a configuration id (no dots)."""
ENV_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"
DEFAULT_PROPERTIES = "default"
"""The property set that means the application's own BM25 properties (``properties: None``)."""
Mode = Literal["text", "vector", "hybrid"]
Fusion = Literal["relativeScore", "ranked"]
Name = str


class ConfigError(ValueError):
    """An experiment configuration that cannot be run; the message says why."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StoreSettings(_Model):
    """``StoreSpec``: where the benchmark-owned Weaviate runs (never another instance)."""
    name: str = StoreSpec.name
    host: str | None = None
    rest_port: int | None = Field(None, ge=1, le=65535)
    grpc_port: int | None = Field(None, ge=1, le=65535)
    token_file: Path = StoreSpec.token_file
    weaviate_image: str = StoreSpec.weaviate_image

    def spec(self) -> StoreSpec:
        return StoreSpec(name=self.name, host=self.host, rest_port=self.rest_port, grpc_port=self.grpc_port,
                         token_file=self.token_file.expanduser(), weaviate_image=self.weaviate_image)


class EndpointSettings(_Model):
    """An OpenAI-compatible ``/embeddings`` endpoint. The key is never written here: only the
    name of the environment variable that holds it."""
    base_url: str = Field(min_length=1)
    api_key_env: str | None = Field(None, pattern=ENV_PATTERN)
    timeout: float = Field(60.0, gt=0)
    batch_size: int = Field(32, ge=1)
    concurrency: int = Field(4, ge=1)

    def endpoint(self) -> EmbeddingEndpoint:
        return EmbeddingEndpoint(base_url=self.base_url, api_key_env=self.api_key_env, timeout=self.timeout,
                                 batch_size=self.batch_size, concurrency=self.concurrency)


class VectorSettings(_Model):
    """One named vector of the store. A different document template needs another vector (other
    document embeddings); a different query prefix does not, so prefixes are named variants."""
    model: str = Field(min_length=1)
    target_vector: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    document_template: str = "{text}"
    dimensions: int | None = Field(None, ge=1)
    max_input_tokens: int | None = Field(None, ge=1)
    """Documents cut to this many tokens by the server (``VectorSpec.max_input_tokens``)."""
    query_prefixes: dict[Name, str] = Field(default_factory=lambda: {"none": ""}, min_length=1)

    @field_validator("document_template")
    @classmethod
    def _template(cls, value: str) -> str:
        if "{text}" not in value:
            raise ValueError("document_template must contain {text}")
        return value

    @field_validator("query_prefixes")
    @classmethod
    def _prefix_names(cls, value: dict[str, str]) -> dict[str, str]:
        _names(value, "query prefix")
        return value

    def spec(self, vector_id: str, prefix: str = "") -> VectorSpec:
        return VectorSpec(id=vector_id, model=self.model, target_vector=self.target_vector, query_prefix=prefix,
                          document_template=self.document_template, dimensions=self.dimensions,
                          max_input_tokens=self.max_input_tokens)


class Grid(_Model):
    """Every combination of these settings becomes a configuration; vector and hybrid ones for
    each vector (``vectors``; default all) and each of its selected query prefixes."""
    modes: tuple[Mode, ...] = Field(min_length=1)
    vectors: tuple[Name, ...] | None = None
    alphas: tuple[float, ...] = Field((0.5,), min_length=1)
    fusions: tuple[Fusion, ...] = Field(("relativeScore",), min_length=1)
    query_prefixes: dict[Name, tuple[Name, ...]] = Field(default_factory=dict)
    """Vector id -> the prefix variants to run; default all the vector's variants."""
    properties: tuple[Name, ...] = Field((DEFAULT_PROPERTIES,), min_length=1)
    """BM25 property set names (``bm25_properties``) for text and hybrid configurations."""

    @field_validator("alphas")
    @classmethod
    def _alphas(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if any(not 0 <= a <= 1 for a in value):
            raise ValueError("alphas must be between 0 and 1")
        return value


class ExplicitConfiguration(_Model):
    """One configuration named by hand, in addition to the grid; vector, prefix and property
    set are referred to by name."""
    configuration_id: str = Field(pattern=ID_PATTERN)
    mode: Mode
    alpha: float | None = Field(None, ge=0, le=1)
    fusion: Fusion | None = None
    vector: Name | None = None
    query_prefix: Name | None = None
    """A variant of the vector's ``query_prefixes``; default its only variant."""
    properties: Name = DEFAULT_PROPERTIES
    depth: int | None = Field(None, ge=1)


class Budget(_Model):
    """Which queries run and how fast. Subsets are deterministic for a seed: whole intents are
    sampled first (so their translations stay together), then queries."""
    languages: tuple[str, ...] | None = None
    """Query languages (ISO 639-3); default all."""
    intents: tuple[str, ...] | None = None
    """Intent ids; default all."""
    max_intents: int | None = Field(None, ge=1)
    max_queries: int | None = Field(None, ge=1)
    seed: int = 0
    concurrency: int = Field(4, ge=1)
    """Searches in flight; latency is measured under this load."""
    max_qps: float | None = Field(None, gt=0)
    """Searches started per second at most; None: unlimited."""

    @field_validator("languages")
    @classmethod
    def _languages(cls, value: tuple[str, ...] | None) -> tuple[str, ...] | None:
        if value is not None and any(not re.match(LANGUAGE_PATTERN, v) for v in value):
            raise ValueError("languages are ISO 639-3 codes (ces, eng, deu)")
        return value


class RunnerConfig(_Model):
    dataset: Path
    """The frozen dataset directory (relative paths are relative to the config file)."""
    runs_dir: Path = Path("~/semant-search-benchmark/runs")
    cache_dir: Path = Path("~/.cache/semant-demo/search-benchmark/embeddings")
    """Document embedding cache of the store (by model, template and text hash)."""
    store: StoreSettings = StoreSettings()
    endpoints: dict[Name, EndpointSettings] = Field(default_factory=dict)
    """Vector id -> where its model is served."""
    vectors: dict[Name, VectorSettings] = Field(default_factory=dict)
    bm25_properties: dict[Name, dict[str, float] | None] = Field(default_factory=dict)
    """Named BM25 property sets with boosts; ``default`` is the application's (null)."""
    depth: int = Field(100, ge=1)
    grid: Grid | None = None
    configurations: tuple[ExplicitConfiguration, ...] = ()
    budget: Budget = Budget()

    @model_validator(mode="after")
    def _references(self) -> "RunnerConfig":
        _names(self.vectors, "vector")
        _names(self.bm25_properties, "property set")
        if self.bm25_properties.get(DEFAULT_PROPERTIES, None) is not None:
            raise ValueError(f"bm25_properties.{DEFAULT_PROPERTIES} is the application's set: leave it null")
        for name, properties in self.bm25_properties.items():
            if properties is not None and (not properties or any(b <= 0 for b in properties.values())):
                raise ValueError(f"bm25_properties.{name}: name at least one property, with positive boosts")
        unknown = sorted(set(self.endpoints) - set(self.vectors))
        if unknown:
            raise ValueError(f"endpoints for unknown vectors: {', '.join(unknown)}")
        targets: dict[str, str] = {}
        for vector_id, vector in self.vectors.items():
            if vector.target_vector in targets:
                raise ValueError(f"vectors {targets[vector.target_vector]} and {vector_id} share the target vector "
                                 f"{vector.target_vector}")
            targets[vector.target_vector] = vector_id
        without = sorted(set(self.vectors) - set(self.endpoints))
        if without:
            raise ValueError(f"vectors without an endpoint: {', '.join(without)} (endpoints.<vector id>)")
        if self.grid is None and not self.configurations:
            raise ValueError("neither a grid nor configurations")
        return self

    def property_set(self, name: str) -> dict[str, float] | None:
        if name == DEFAULT_PROPERTIES:
            return None
        if name not in self.bm25_properties:
            raise ConfigError(f"unknown BM25 property set {name}")
        return self.bm25_properties[name]

    def endpoint(self, vector_id: str) -> EmbeddingEndpoint:
        if vector_id not in self.endpoints:
            raise ConfigError(f"vector {vector_id} has no endpoint")
        return self.endpoints[vector_id].endpoint()


def _names(names, what: str) -> None:
    bad = [n for n in names if not re.match(NAME_PATTERN, n)]
    if bad:
        raise ValueError(f"{what} names are letters, digits, '_' and '-': {', '.join(bad)}")


def load_config(path: Path) -> tuple[RunnerConfig, str]:
    """The configuration of a YAML file, with relative paths resolved against its directory, and
    the file's SHA-256 (recorded in the run's manifest)."""
    raw = path.read_bytes()
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ConfigError(f"{path}: not YAML: {e}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: not a mapping")
    try:
        config = RunnerConfig.model_validate(data)
    except ValidationError as e:
        error = e.errors()[0]
        where = ".".join(str(p) for p in error["loc"])
        raise ConfigError(f"{path}: {where}: {error['msg']}" if where else f"{path}: {error['msg']}") from None
    base = path.resolve().parent

    def resolve(p: Path) -> Path:
        p = p.expanduser()
        return p if p.is_absolute() else base / p

    config = config.model_copy(update={"dataset": resolve(config.dataset), "runs_dir": resolve(config.runs_dir),
                                       "cache_dir": resolve(config.cache_dir),
                                       "store": config.store.model_copy(
                                           update={"token_file": resolve(config.store.token_file)})})
    return config, hashlib.sha256(raw).hexdigest()


# ---- expansion ----------------------------------------------------------------------------

def _alpha(alpha: float) -> str:
    return format(alpha, "g")


def configuration_id(mode: str, vector: str | None = None, alpha: float | None = None, fusion: str | None = None,
                     prefix: str | None = None, properties: str = DEFAULT_PROPERTIES) -> str:
    parts = [mode]
    if mode != "text":
        parts.append(vector)
    if mode == "hybrid":
        parts += [f"a{_alpha(alpha)}", fusion or "default"]
    if mode != "text":
        parts.append(f"p-{prefix}")
    if mode != "vector" and properties != DEFAULT_PROPERTIES:
        parts.append(f"b-{properties}")
    return ".".join(parts)


def _vector(config: RunnerConfig, vector_id: str | None, prefix: str | None) -> tuple[VectorSpec, str]:
    if vector_id is None:
        raise ConfigError("a vector or hybrid configuration needs a vector")
    if vector_id not in config.vectors:
        raise ConfigError(f"unknown vector {vector_id}")
    vector = config.vectors[vector_id]
    if prefix is None:
        if len(vector.query_prefixes) != 1:
            raise ConfigError(f"vector {vector_id} has several query prefixes: name one")
        prefix = next(iter(vector.query_prefixes))
    if prefix not in vector.query_prefixes:
        raise ConfigError(f"vector {vector_id} has no query prefix {prefix}")
    config.endpoint(vector_id)
    return vector.spec(vector_id, vector.query_prefixes[prefix]), prefix


def expand(config: RunnerConfig) -> list[RunConfiguration]:
    """The configurations of the grid, then the explicit ones; each id once. The same id with
    other settings, or the same settings under two ids, is refused."""
    found: dict[str, RunConfiguration] = {}

    def add(configuration: RunConfiguration) -> None:
        known = found.get(configuration.configuration_id)
        if known is not None and known != configuration:
            raise ConfigError(f"configuration {configuration.configuration_id} is defined twice with other settings")
        found[configuration.configuration_id] = configuration

    def make(**fields) -> RunConfiguration:
        try:
            return RunConfiguration(**fields)
        except ValidationError as e:
            raise ConfigError(e.errors()[0]["msg"]) from None

    grid = config.grid
    if grid is not None:
        vector_ids = list(grid.vectors) if grid.vectors is not None else list(config.vectors)
        unknown = sorted(set(grid.query_prefixes) - set(config.vectors))
        if unknown:
            raise ConfigError(f"grid.query_prefixes for unknown vectors: {', '.join(unknown)}")
        if set(grid.modes) - {"text"} and not vector_ids:
            raise ConfigError("vector and hybrid modes need a vector")
        for name in grid.properties:
            config.property_set(name)
        for mode in dict.fromkeys(grid.modes):
            if mode == "text":
                for name in dict.fromkeys(grid.properties):
                    add(make(configuration_id=configuration_id("text", properties=name), mode="text",
                             properties=config.property_set(name), depth=config.depth))
                continue
            for vector_id in dict.fromkeys(vector_ids):
                if vector_id not in config.vectors:
                    raise ConfigError(f"grid.vectors: unknown vector {vector_id}")
                prefixes = grid.query_prefixes.get(vector_id) or tuple(config.vectors[vector_id].query_prefixes)
                for prefix in dict.fromkeys(prefixes):
                    spec, _ = _vector(config, vector_id, prefix)
                    if mode == "vector":
                        add(make(configuration_id=configuration_id("vector", vector_id, prefix=prefix), mode="vector",
                                 vector=spec, depth=config.depth))
                        continue
                    for alpha in dict.fromkeys(grid.alphas):
                        for fusion in dict.fromkeys(grid.fusions):
                            for name in dict.fromkeys(grid.properties):
                                add(make(configuration_id=configuration_id("hybrid", vector_id, alpha, fusion, prefix,
                                                                           name),
                                         mode="hybrid", alpha=alpha, fusion=fusion, vector=spec,
                                         properties=config.property_set(name), depth=config.depth))
    for explicit in config.configurations:
        spec = None
        if explicit.mode != "text":
            spec, _ = _vector(config, explicit.vector, explicit.query_prefix)
        elif explicit.vector is not None or explicit.query_prefix is not None:
            raise ConfigError(f"{explicit.configuration_id}: a text configuration has no vector")
        add(make(configuration_id=explicit.configuration_id, mode=explicit.mode, alpha=explicit.alpha,
                 fusion=explicit.fusion, vector=spec,
                 properties=None if explicit.mode == "vector" else config.property_set(explicit.properties),
                 depth=explicit.depth or config.depth))
    by_settings: dict[str, str] = {}
    for configuration in found.values():
        key = configuration.model_dump_json(exclude={"configuration_id"})
        if key in by_settings:
            raise ConfigError(f"configurations {by_settings[key]} and {configuration.configuration_id} "
                              f"have the same settings")
        by_settings[key] = configuration.configuration_id
    return list(found.values())


def select(configurations: list[RunConfiguration], ids: list[str] | None) -> list[RunConfiguration]:
    """The configurations named by ``--configurations`` (all when None), in config order."""
    if ids is None:
        return configurations
    known = {c.configuration_id for c in configurations}
    unknown = [i for i in ids if i not in known]
    if unknown:
        raise ConfigError(f"unknown configurations: {', '.join(unknown)}")
    return [c for c in configurations if c.configuration_id in set(ids)]


# ---- budget -------------------------------------------------------------------------------

def select_queries(dataset: Dataset, budget: Budget) -> list[Query]:
    """The queries the budget selects, sorted by id; the same for the same dataset and budget."""
    intents = sorted(dataset.intents)
    if budget.intents is not None:
        unknown = sorted(set(budget.intents) - set(intents))
        if unknown:
            raise ConfigError(f"budget.intents not in the dataset: {', '.join(unknown[:5])}")
        intents = sorted(set(budget.intents))
    if budget.max_intents is not None and len(intents) > budget.max_intents:
        intents = sorted(random.Random(f"intents:{budget.seed}").sample(intents, budget.max_intents))
    if budget.languages is not None:
        present = {q.language for q in dataset.queries.values()}
        unknown = sorted(set(budget.languages) - present)
        if unknown:
            raise ConfigError(f"budget.languages without queries in the dataset: {', '.join(unknown)}")
    chosen = set(intents)
    queries = [q for _, q in sorted(dataset.queries.items())
               if q.intent_id in chosen and (budget.languages is None or q.language in budget.languages)]
    if budget.max_queries is not None and len(queries) > budget.max_queries:
        queries = sorted(random.Random(f"queries:{budget.seed}").sample(queries, budget.max_queries),
                         key=lambda q: q.query_id)
    if not queries:
        raise ConfigError("the budget selects no query")
    return queries
