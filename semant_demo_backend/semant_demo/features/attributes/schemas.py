"""HTTP and internal models of collection attributes (#331, ADR 0011)."""
from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from semant_demo.core.outcomes import StepFailure, WriteOutcome

MAX_VALUES_PER_ATTRIBUTE = 200
MAX_ASSIGN_BATCH = 200
"""Annotations one assignment request changes (as a review, #459)."""
MAX_VALUES_PER_ASSIGNMENT = 50


class Cardinality(str, Enum):
    single = "single"
    """At most one accepted value per annotation."""
    multi = "multi"


class ValueKind(str, Enum):
    value = "value"
    unknown = "unknown"
    """Explicitly assigned "Unknown": a decision, distinct from no assignment."""
    not_applicable = "not_applicable"
    """Explicitly assigned "Not applicable"."""


class AttributeValue(BaseModel):
    id: UUID
    label: str
    description: str = ""
    examples: list[str] = []
    kind: ValueKind = ValueKind.value
    retired: bool = False
    """A retired value keeps its existing assignments but cannot be assigned again."""


class Attribute(BaseModel):
    id: UUID
    name: str
    description: str = ""
    cardinality: Cardinality
    tag_ids: list[UUID] = []
    """Tags whose annotations the attribute applies to; empty: every tag of the collection."""
    retired: bool = False
    revision: int = 1
    """Counts edits of the definition and its values; change records name it."""
    values: list[AttributeValue] = []


class PostAttributeValue(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    examples: list[str] = Field(default=[], max_length=20)
    kind: ValueKind = ValueKind.value


class PatchAttributeValue(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    examples: list[str] | None = Field(default=None, max_length=20)
    retired: bool | None = None

    @model_validator(mode="after")
    def check_any(self) -> "PatchAttributeValue":
        if all(v is None for v in (self.label, self.description, self.examples, self.retired)):
            raise ValueError("Send at least one field to change")
        return self


class PostAttribute(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    cardinality: Cardinality = Cardinality.single
    tag_ids: list[UUID] = Field(default=[], max_length=500)
    values: list[PostAttributeValue] = Field(default=[], max_length=MAX_VALUES_PER_ATTRIBUTE)


class PatchAttribute(BaseModel):
    """The cardinality cannot be changed: existing assignments would turn contradictory."""
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    tag_ids: list[UUID] | None = Field(default=None, max_length=500)
    retired: bool | None = None

    @model_validator(mode="after")
    def check_any(self) -> "PatchAttribute":
        if all(v is None for v in (self.name, self.description, self.tag_ids, self.retired)):
            raise ValueError("Send at least one field to change")
        return self


class AssignMode(str, Enum):
    add = "add"
    """Add the values to those the annotation has (a single-valued attribute: only when it has none
    or the same)."""
    remove = "remove"
    replace = "replace"
    """The annotation's values of the attribute become exactly ``value_ids`` (none: cleared)."""


class AssignSource(str, Enum):
    manual = "manual"
    ai_assisted = "ai_assisted"
    """A person's decision on a value an AI run proposed (``run_id``)."""


class AttributeAssignRequest(BaseModel):
    """One assignment of values of one attribute to up to ``MAX_ASSIGN_BATCH`` annotations,
    each on its own; ``expected_versions`` are their ``attributeVersion`` as the client knows it."""
    attribute_id: UUID
    annotation_ids: list[UUID] = Field(min_length=1, max_length=MAX_ASSIGN_BATCH)
    expected_versions: dict[UUID, int]
    mode: AssignMode
    value_ids: list[UUID] = Field(default=[], max_length=MAX_VALUES_PER_ASSIGNMENT)
    source: AssignSource = AssignSource.manual
    run_id: UUID | None = None

    @model_validator(mode="after")
    def check_request(self) -> "AttributeAssignRequest":
        if any(i not in self.expected_versions for i in self.annotation_ids):
            raise ValueError("expected_versions must give the version of every annotation")
        if not self.value_ids and self.mode != AssignMode.replace:
            raise ValueError("Choose at least one value")
        if (self.run_id is not None) != (self.source == AssignSource.ai_assisted):
            raise ValueError("run_id is required for ai_assisted assignments and not allowed otherwise")
        return self


class AttributeAssignResult(BaseModel):
    """Per-annotation outcome (best effort, nothing is rolled back; ADR 0002). ``versions`` and
    ``values`` are given for every annotation whose current state is known, saved or refused for
    a conflict, so a client can show it instead of its stale copy."""
    outcome: WriteOutcome
    succeeded: list[str] = []
    failed: list[StepFailure] = []
    versions: dict[UUID, int] = {}
    values: dict[UUID, list[UUID]] = {}
    """The annotation's accepted values of the attribute as stored now."""


class AttributeChange(BaseModel):
    """What the change record of one annotation and attribute holds (#331)."""
    id: int | None = None
    annotation_id: UUID
    attribute_id: UUID
    previous: list[UUID]
    current: list[UUID]
    actor_id: UUID
    at: datetime
    source: AssignSource
    run_id: UUID | None = None
    annotation_edit_version: int | None = None
    attribute_revision: int
