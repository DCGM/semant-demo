"""Annotation enrichment (#328): what the application derives for span annotations.

Text, context and positions (``derivation.py``) are stored with every create and
boundary edit. The contextual vector embeds ``template`` rendered with the span's left
context, text and right context (the span is marked within its neighborhood; tag, type
and AI metadata are not part of the input, so changing them never re-embeds). Queries
against it use the same model's query embedding.

The vector is configured by ``ANNOTATION_VECTOR_CONFIG`` (default
``configs/annotation_vector.yaml``; an empty value configures none). Its ``id`` is stored
with every vector and must change whenever the model, its dimensions, prefixes or the
template change: vectors of another ``id`` are not current and the backfill replaces them.

Nothing is derived unless the ``Annotation`` collection holds the derived properties
(and, for the vector, the named vector): they are added by the operator
(``python -m semant_demo.maintenance.annotation_enrichment add-schema``), never by a
request, which would let Weaviate's auto-schema guess their types.
"""
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from semant_demo.features.annotations.derivation import DERIVATION_VERSION, DerivedText, render_vector_input
from semant_demo.features.annotations.schemas import AnnotationRow, EnrichmentStatus, VectorStatus
from semant_demo.features.search.vectors import Embedder, EmbeddingSettings

DEFAULT_TEMPLATE = "{left}<<<{text}>>>{right}"


class AnnotationVectorSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    """Recorded with each vector; change it with the model, dimensions, prefixes or template."""
    target_vector: str = Field(default="contextual", pattern=r"^[_A-Za-z][_A-Za-z0-9]*$")
    """Named vector of the ``Annotation`` collection (a GraphQL name, see search vectors)."""
    template: str = DEFAULT_TEMPLATE
    """Embedding input; ``{left}``, ``{text}`` and ``{right}`` are replaced."""
    embedding: EmbeddingSettings


def load_annotation_vector_settings(path: str | Path | None) -> AnnotationVectorSettings | None:
    """The configured contextual vector, ``None`` for an empty path (no vector)."""
    if not path:
        return None
    with open(path, encoding="utf-8") as f:
        return AnnotationVectorSettings.model_validate(yaml.safe_load(f))


@dataclass(frozen=True)
class AnnotationVector:
    settings: AnnotationVectorSettings
    embedder: Embedder

    @property
    def id(self) -> str:
        return self.settings.id

    @property
    def target_vector(self) -> str:
        return self.settings.target_vector

    def input_of(self, derived: DerivedText) -> str:
        return render_vector_input(self.settings.template, derived)

    async def embed(self, derived: DerivedText) -> list[float]:
        return await self.embedder.embed_document(self.input_of(derived))

    async def embed_query(self, text: str) -> list[float]:
        return await self.embedder.embed_query(text)


@dataclass(frozen=True)
class Enrichment:
    """What this application derives for annotations, decided at startup."""
    derived: bool = False
    """The ``Annotation`` collection holds the derived properties: they are written."""
    vector: AnnotationVector | None = None
    """The configured contextual vector, when ``derived`` and the collection holds it."""

    @classmethod
    def disabled(cls) -> "Enrichment":
        return cls()


def text_current(row: AnnotationRow) -> bool:
    """The row's stored text, context and positions describe its current revision under the
    current derivation policy (``DERIVATION_VERSION``)."""
    return (row.enrichmentStatus == EnrichmentStatus.ready and (row.enrichedRevision or 0) == (row.revision or 0)
            and row.derivationVersion == DERIVATION_VERSION)


def vector_current(row: AnnotationRow, config_id: str | None) -> bool:
    """The row's contextual vector belongs to its current revision and configuration
    ``config_id``, and its text is current (every re-derivation marks the vector pending,
    so a vector of an older policy's text is never current)."""
    return (config_id is not None and row.vectorStatus == VectorStatus.ready and row.vectorConfig == config_id
            and (row.vectorRevision or 0) == (row.revision or 0) and text_current(row))
