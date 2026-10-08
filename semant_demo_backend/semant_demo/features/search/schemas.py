"""Neutral retrieval inputs passed from the search service to the search adapter.

They name application fields and options only; the adapter decides how they map to
stored properties, references and query calls. HTTP request/response models are still
``semant_demo.schemas.SearchRequest``/``SearchResponse`` (consolidated in #208).
"""
from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import UUID

from semant_demo.schemas import SearchType


class Op(str, Enum):
    equal = "equal"
    greater_or_equal = "greater_or_equal"
    less_or_equal = "less_or_equal"
    contains_any = "contains_any"


@dataclass(frozen=True)
class FieldCondition:
    """A chunk matches when its (or its document's) ``field`` satisfies ``op`` with ``value``."""
    field: str
    op: Op
    value: Any


@dataclass(frozen=True)
class TagFilter:
    """Chunks carrying any of ``tag_ids`` as a suggested (automatic) or approved (positive) tag.

    Only the enabled kinds are matched; at least one is enabled.
    """
    tag_ids: tuple[UUID, ...]
    automatic: bool
    positive: bool


@dataclass(frozen=True)
class ChunkQuery:
    """One retrieval: all conditions must hold (AND)."""
    text: str
    mode: SearchType
    limit: int
    alpha: float = 0.5
    """Hybrid weighting between vector (1.0) and keyword (0.0) scores."""
    vector: list[float] | None = None
    """Query embedding; required for vector and hybrid modes."""
    collection_id: UUID | None = None
    tags: TagFilter | None = None
    conditions: tuple[FieldCondition, ...] = ()
