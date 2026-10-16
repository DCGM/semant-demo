"""Configured search vectors (#217): the Weaviate named vector a vector or hybrid search
queries, and the embedding model that embeds its query.

The configuration (``SEARCH_VECTORS_CONFIG``, default ``configs/search_vectors.yaml``)
lists the vectors the application may use and names the default. A request selects one
by its ``id``; a request without a selection uses the default, an unknown id is refused.
Vectors are created and populated offline (``data_tools/embedder``, #192): nothing here
creates them or discovers vectors that the configuration does not list.

Bootstrap builds one embedder per configured vector (``adapters/embeddings``); the
search service resolves the selection and embeds the query; the Weaviate adapter only
receives the resolved ``target_vector``.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Protocol, Sequence

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from semant_demo.core.errors import InvalidRequestError
from semant_demo.features.search.schemas import SearchVectorInfo, SearchVectorsResponse


class EmbeddingSettings(BaseModel):
    """How the query of one vector is embedded.

    * ``embedding_service`` — the project's embedding service (``embedding_service/``),
      which adds its own query instruction. ``base_url`` defaults to
      ``EMBEDDING_SERVICE_HOST``/``_PORT``.
    * ``openai`` — an OpenAI-compatible ``/embeddings`` endpoint (e.g. vLLM, as used by
      the offline embedder). ``base_url`` (including ``/v1``) and ``model`` are required;
      the prefixes are prepended to the query (HyDE: document) text, e.g. an instruction.
      ``timeout`` is in seconds. The key, if any, is ``EMBEDDING_API_KEY``.
    """
    model_config = ConfigDict(extra="forbid")

    provider: Literal["embedding_service", "openai"]
    base_url: str | None = None
    model: str | None = None
    query_prefix: str = ""
    document_prefix: str = ""
    dimensions: int | None = Field(default=None, gt=0)
    timeout: float = Field(default=36.0, gt=0)

    @model_validator(mode="after")
    def _provider_fields(self) -> "EmbeddingSettings":
        if self.provider == "openai":
            if not self.base_url or not self.model:
                raise ValueError("an openai embedding needs base_url and model")
        elif self.model_fields_set & {"model", "query_prefix", "document_prefix", "dimensions", "timeout"}:
            raise ValueError("the embedding service has a fixed model, instruction and timeouts; "
                             "model, prefixes, dimensions and timeout are not supported")
        return self


class VectorSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    """Application identifier, sent by clients."""
    name: str
    description: str = ""
    target_vector: str = Field(min_length=1)
    """Weaviate named vector of the chunk collection."""
    embedding: EmbeddingSettings


class SearchVectorsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default: str
    vectors: list[VectorSettings] = Field(min_length=1)

    @model_validator(mode="after")
    def _ids(self) -> "SearchVectorsSettings":
        ids = [v.id for v in self.vectors]
        if len(set(ids)) != len(ids):
            raise ValueError("search vector ids must be unique")
        if self.default not in ids:
            raise ValueError(f"the default search vector {self.default!r} is not configured")
        return self


def load_search_vectors_settings(path: str | Path) -> SearchVectorsSettings:
    with open(path, encoding="utf-8") as f:
        return SearchVectorsSettings.model_validate(yaml.safe_load(f))


class Embedder(Protocol):
    async def embed_query(self, text: str) -> list[float]: ...

    async def embed_document(self, text: str) -> list[float]:
        """``text`` embedded as a document (HyDE: a query phrased as a document)."""
        ...


@dataclass(frozen=True)
class SearchVector:
    id: str
    name: str
    description: str
    target_vector: str
    embedder: Embedder


class SearchVectors:
    """The configured vectors of one application and its default."""

    def __init__(self, vectors: Sequence[SearchVector], default: str):
        self._by_id = {v.id: v for v in vectors}
        if len(self._by_id) != len(vectors) or default not in self._by_id:
            raise ValueError("search vectors need unique ids and a configured default")
        self.default = default

    @classmethod
    def build(cls, settings: SearchVectorsSettings,
              embedder: Callable[[EmbeddingSettings], Embedder]) -> "SearchVectors":
        return cls([SearchVector(v.id, v.name, v.description, v.target_vector, embedder(v.embedding))
                    for v in settings.vectors], settings.default)

    def resolve(self, vector_id: str | None) -> SearchVector:
        """The selected vector, the default when ``vector_id`` is None.

        Raises ``InvalidRequestError`` for a vector that is not configured.
        """
        if vector_id is None:
            return self._by_id[self.default]
        try:
            return self._by_id[vector_id]
        except KeyError:
            raise InvalidRequestError(f"Unknown search vector: {vector_id}.") from None

    def describe(self) -> SearchVectorsResponse:
        return SearchVectorsResponse(default_vector=self.default, vectors=[
            SearchVectorInfo(id=v.id, name=v.name, description=v.description) for v in self._by_id.values()])
