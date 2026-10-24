"""Annotation enrichment (#328): what the application derives for span annotations.

Text, context and positions (``derivation.py``) are stored with every create and
boundary edit. The contextual vector embeds ``template`` rendered with the span's left
context, text and right context (the span is marked within its neighborhood; tag, type
and AI metadata are not part of the input, so changing them never re-embeds). Queries
against it use the same model's query embedding.

The vector is configured by ``ANNOTATION_VECTOR_CONFIG`` (default
``configs/annotation_vector_qwen.yaml``; an empty value configures none). Its ``id`` is stored
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
    """Recorded with each vector; change it with the model, dimensions, prefixes, template or input policy."""
    target_vector: str = Field(default="contextual", pattern=r"^[_A-Za-z][_A-Za-z0-9]*$")
    """Named vector of the ``Annotation`` collection (a GraphQL name, see search vectors)."""
    template: str = DEFAULT_TEMPLATE
    """Embedding input; ``{left}``, ``{text}`` and ``{right}`` are replaced."""
    max_input_chars: int | None = Field(default=None, gt=0)
    """Maximum rendered input characters; context is shortened before the span text."""
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
        rendered = render_vector_input(self.settings.template, derived)
        limit = self.settings.max_input_chars

        if limit is None or len(rendered) <= limit:
            return rendered

        empty = DerivedText(
            text="",
            left_context="",
            right_context="",
            start_char=derived.start_char,
            end_char=derived.end_char,
            start_word=derived.start_word,
            end_word=derived.end_word,
        )
        template_size = len(render_vector_input(self.settings.template, empty))

        available = limit - template_size
        if available < 0:
            raise ValueError(
                "annotation vector template does not fit max_input_chars"
            )

        # The span itself is too long: remove all context and keep its start.
        if len(derived.text) > available:
            shortened = DerivedText(
                text=derived.text[:available],
                left_context="",
                right_context="",
                start_char=derived.start_char,
                end_char=derived.end_char,
                start_word=derived.start_word,
                end_word=derived.end_word,
            )
            return render_vector_input(self.settings.template, shortened)

        # Keep the whole span and use the remaining budget for context.
        context_budget = available - len(derived.text)

        left_budget = (context_budget + 1) // 2
        right_budget = context_budget - left_budget

        left = derived.left_context[-left_budget:] if left_budget else ""
        right = derived.right_context[:right_budget]

        # If one side has less context than its share, give the unused budget
        # to the other side.
        unused_left = left_budget - len(left)
        unused_right = right_budget - len(right)

        if unused_left:
            right = derived.right_context[:right_budget + unused_left]

        if unused_right:
            extra_left = left_budget + unused_right
            left = derived.left_context[-extra_left:] if extra_left else ""

        shortened = DerivedText(
            text=derived.text,
            left_context=left,
            right_context=right,
            start_char=derived.start_char,
            end_char=derived.end_char,
            start_word=derived.start_word,
            end_word=derived.end_word,
        )

        return render_vector_input(self.settings.template, shortened)

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
