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
ALL_TAGS_WITH_TAG_IDS = "An attribute for all tags has no selected tags; send tag_ids empty with all_tags true"


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
    all_tags: bool = False
    """Applies to every tag of the collection, also tags created later; ``tag_ids`` is then empty."""
    tag_ids: list[UUID] = []
    """With ``all_tags`` false, the tags whose annotations the attribute applies to; empty: no tag,
    and no value can be assigned (#522)."""
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
    all_tags: bool = False
    """Explicit: an empty ``tag_ids`` alone means no tag, never All tags (#522)."""
    tag_ids: list[UUID] = Field(default=[], max_length=500)
    values: list[PostAttributeValue] = Field(default=[], max_length=MAX_VALUES_PER_ATTRIBUTE)

    @model_validator(mode="after")
    def check_scope(self) -> "PostAttribute":
        if self.all_tags and self.tag_ids:
            raise ValueError(ALL_TAGS_WITH_TAG_IDS)
        return self


class PatchAttribute(BaseModel):
    """The cardinality cannot be changed: existing assignments would turn contradictory."""
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    all_tags: bool | None = None
    """True: All tags (the selected tags are cleared). False: Selected tags, ``tag_ids`` or, when
    not sent, the tags selected now (none for an All tags attribute)."""
    tag_ids: list[UUID] | None = Field(default=None, max_length=500)
    """The selected tags; an All tags attribute takes them only with ``all_tags`` false."""
    add_tag_ids: list[UUID] | None = Field(default=None, max_length=500)
    """Tags to add to the selected tags as they are when the change is written, so a change of
    other tags made meanwhile is kept (#516). Only for a Selected tags attribute; not with
    ``tag_ids``."""
    remove_tag_ids: list[UUID] | None = Field(default=None, max_length=500)
    """Tags to take out of the selected tags, like ``add_tag_ids``; the last one leaves no tag."""
    retired: bool | None = None
    confirm_affected: int | None = Field(default=None, ge=0)
    """Confirms a narrowing of the tags that makes values on this many annotations stop applying
    (#568): the number a refusal (409 with ``confirm`` ``narrowing``) reported. Values are kept;
    a narrowing that affects another number is refused again with the new one."""

    @model_validator(mode="after")
    def check_any(self) -> "PatchAttribute":
        if all(v is None for v in (self.name, self.description, self.all_tags, self.tag_ids, self.add_tag_ids,
                                   self.remove_tag_ids, self.retired)):
            raise ValueError("Send at least one field to change")
        if self.all_tags and self.tag_ids:
            raise ValueError(ALL_TAGS_WITH_TAG_IDS)
        if self.changes_tags_by_id:
            if self.tag_ids is not None:
                raise ValueError("Send either tag_ids or add_tag_ids/remove_tag_ids, not both")
            if self.all_tags:
                raise ValueError(ALL_TAGS_WITH_TAG_IDS)
            if set(self.add_tag_ids or []) & set(self.remove_tag_ids or []):
                raise ValueError("A tag cannot be both added and removed")
        return self

    @property
    def changes_tags_by_id(self) -> bool:
        return self.add_tag_ids is not None or self.remove_tag_ids is not None


class AssignMode(str, Enum):
    add = "add"
    """Add the values to those the annotation has (a single-valued attribute: only when it has none
    or the same)."""
    remove = "remove"
    replace = "replace"
    """The annotation's values of the attribute become exactly ``value_ids`` (none: cleared)."""
    clear = "clear"
    """Remove every value of the attribute the annotation holds, without naming them (``value_ids``
    empty): like ``remove``, also on a non-approved annotation, a tag the attribute no longer
    applies to and a retired attribute, and for values no longer defined."""


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
        if self.mode == AssignMode.clear and self.value_ids:
            raise ValueError("clear removes every value; value_ids must be empty")
        if not self.value_ids and self.mode not in (AssignMode.replace, AssignMode.clear):
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
    """Annotations processed successfully: changed, or already as asked (a retry is safe)."""
    unchanged: list[str] = []
    """The part of ``succeeded`` that already held the requested values: nothing was written,
    no version counted up and no change recorded (#569)."""
    failed: list[StepFailure] = []
    versions: dict[UUID, int] = {}
    values: dict[UUID, list[UUID]] = {}
    """The annotation's accepted values of the attribute as stored now."""


class AttributeChangeValue(BaseModel):
    """A value of a change record with its label and kind as defined when the change was made.
    The id is the identity; label and kind are only what the history shows, so a later rename,
    retirement or deletion of the value does not change what a past decision says. Descriptions
    and examples are not kept: reading a decision as its definition then meant needs versioned
    definitions (#502)."""
    id: UUID
    label: str | None = None
    """None: the id had no definition when the change was made (deleted meanwhile)."""
    kind: ValueKind | None = None


class AttributeChange(BaseModel):
    """What the change record of one annotation and attribute holds (#331); immutable once
    written, readable without the current definitions."""
    id: int | None = None
    annotation_id: UUID
    attribute_id: UUID
    attribute_name: str
    """The attribute's name when the change was made."""
    previous: list[AttributeChangeValue]
    current: list[AttributeChangeValue]
    actor_id: UUID
    at: datetime
    source: AssignSource
    run_id: UUID | None = None
    annotation_edit_version: int | None = None
    attribute_revision: int
