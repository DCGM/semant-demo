"""HTTP models of saved research selections (#824, parent #335)."""
from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from semant_demo.features.annotations.schemas import AnnotationFilters, AnnotationSort

MAX_SAVED_SELECTIONS = 200
"""Saved selections per collection."""
MAX_NAME_LENGTH = 200
MAX_SHOWN_ATTRIBUTES = 100


class SavedSelectionKind(str, Enum):
    live = "live"
    """A saved annotation query, evaluated again on every open (#824). Fixed selections of
    annotation identities are #825."""


class LiveQuery(BaseModel):
    """What a live filter keeps: the annotation query (#663) and how the workspace lists it.

    A Find similar source is not kept (it names one annotation); a similarity text is, as
    ``filters.ranking_query`` (#716), so opening ranks again by it."""
    model_config = ConfigDict(extra="forbid")

    filters: AnnotationFilters = Field(default_factory=AnnotationFilters)
    sort: AnnotationSort = AnnotationSort.document
    sort_attribute: UUID | None = None
    """With ``sort`` ``attribute`` only."""
    descending: bool = False
    shown_attribute_ids: list[UUID] = Field(default=[], max_length=MAX_SHOWN_ATTRIBUTES)
    """Attribute columns the workspace shows: a view setting, not a filter."""

    @model_validator(mode="after")
    def _sort_attribute(self) -> "LiveQuery":
        if (self.sort == AnnotationSort.attribute) != (self.sort_attribute is not None):
            raise ValueError("sort_attribute is required with the attribute sort and refused otherwise")
        return self


def _name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("A name is required")
    return value


class PostSavedSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=MAX_NAME_LENGTH)
    query: LiveQuery

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        return _name(value)


class PatchSavedSelection(BaseModel):
    """Renames a saved selection and/or replaces its query."""
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=MAX_NAME_LENGTH)
    query: LiveQuery | None = None

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return None if value is None else _name(value)

    @model_validator(mode="after")
    def _something(self) -> "PatchSavedSelection":
        if self.name is None and self.query is None:
            raise ValueError("Give a new name, a new query or both")
        return self


class SavedSelection(BaseModel):
    """A named, server-side research selection of one collection. Every reader of the collection
    sees it; its creator and the collection owner may rename, replace or delete it."""
    id: UUID
    collection_id: UUID
    kind: SavedSelectionKind
    name: str
    query: LiveQuery | None
    """None when the stored query no longer fits the current query model (``unreadable``)."""
    unreadable: bool = False
    created_by: UUID
    created_at: datetime
    updated_by: UUID
    updated_at: datetime
    can_edit: bool
    """Whether the requesting user may rename, replace or delete it."""
