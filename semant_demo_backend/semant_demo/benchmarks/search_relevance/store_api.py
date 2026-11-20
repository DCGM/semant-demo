"""The interface of the benchmark store: a Weaviate owned by the benchmark, holding one dataset's
corpus, searched with the application's own passage search (#726 pooling, #727 runner).

Implemented by ``store.py``; the generator and the runner use only what is declared here, so
they can be developed and tested against a fake. Rules every implementation keeps:

* **Ownership.** It writes only to an instance that holds the benchmark's ownership marker with
  the expected token, and claims only an instance that is empty. It never drops, resets or
  writes to another instance: not the development stores, the automated-test stores or
  production (#727). Opening an owned instance again reuses its data.
* **Schema.** The application's collections, created as the backend expects them (the shape of
  the test schema; production's exact schema is #128). ``describe`` reports what was created,
  for the manifests: tokenization and indexes affect BM25.
* **Corpus.** ``load`` writes the dataset's corpus with its original chunk and document ids;
  loading the same dataset again writes nothing. A store holds one dataset (id and version) at
  a time; another one is refused until the store is recreated.
* **Vectors.** One named vector per ``VectorSpec``. Document embeddings are cached on disk by
  (model, document template, text hash), so recreating a store or adding a model never embeds a
  text twice; the query prefix does not change document vectors.
* **Search.** ``searcher`` returns the application's passage search
  (``features/search/service.search_passages``) over this store for one configuration, with the
  fusion type and BM25 properties the configuration sets.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from semant_demo.benchmarks.search_relevance.contracts import Dataset, RunConfiguration, VectorSpec


@dataclass(frozen=True)
class StoreSpec:
    """How to reach or start the benchmark's Weaviate."""
    name: str = "semant-search-benchmark"
    """Container and volume name when the store starts its own instance."""
    host: str | None = None
    """An existing instance (with its marker) instead of starting one; None: start or reuse the
    named container on loopback."""
    rest_port: int | None = None
    grpc_port: int | None = None
    token_file: Path = Path("~/.config/semant-demo/search-benchmark-store-token")
    """The ownership token, created on first use."""
    weaviate_image: str = "cr.weaviate.io/semitechnologies/weaviate:1.40.1"
    """The image of the application's Weaviate version."""


@dataclass(frozen=True)
class EmbeddingEndpoint:
    """Where a ``VectorSpec``'s model is served (an OpenAI-compatible ``/embeddings``)."""
    base_url: str
    api_key_env: str | None = None
    """Name of the environment variable with the key; None: no key."""
    timeout: float = 60.0
    batch_size: int = 32
    concurrency: int = 4


@dataclass(frozen=True)
class SearchOutcome:
    hits: list[tuple[UUID, float | None]]
    """Ranked (chunk id, score), best first."""
    embed_ms: float | None
    search_ms: float


Searcher = Callable[[str], Awaitable[SearchOutcome]]
"""Query text -> its ranked chunks in one configuration."""


@dataclass
class LoadReport:
    dataset_id: str
    version: str
    chunks_written: int = 0
    documents_written: int = 0
    already_loaded: bool = False


@dataclass
class VectorReport:
    vector: str
    embedded: int = 0
    from_cache: int = 0
    written: int = 0
    failed: dict[str, int] = field(default_factory=dict)
    """Failure class -> count; failed chunks have no vector (reported, never written empty)."""


class BenchmarkStore(Protocol):
    async def load(self, dataset: Dataset) -> LoadReport: ...

    async def ensure_vector(self, spec: VectorSpec, endpoint: EmbeddingEndpoint, cache_dir: Path) -> VectorReport: ...

    def searcher(self, configuration: RunConfiguration, endpoint: EmbeddingEndpoint | None) -> Searcher: ...

    async def describe(self) -> dict[str, Any]:
        """Weaviate version, collections and their schema, named vectors, loaded dataset."""
        ...

    async def close(self) -> None: ...


OpenStore = Callable[[StoreSpec], Awaitable[BenchmarkStore]]
"""``store.open_store``: connect to (or start) the owned instance, claim it if empty."""
