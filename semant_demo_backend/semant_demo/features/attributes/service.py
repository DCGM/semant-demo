"""Collection attribute use cases (#331, ADR 0011): definitions and accepted assignments.

Every public function checks access itself (``features/user_collections/access.py``, ADR 0007)
before any other read or write: reading needs collection read access, definition writes
attribute-definition-edit access and assignments annotation-edit access (owner and shared users
for all three; none changes collection membership). Definitions are stored in SQL per collection
(``adapters/sql/attributes.py``); an attribute or value id of another collection is "not found".

The accepted assignments of an annotation are the array ``Annotation.attributeValues`` in its
collection's tenant, the one authoritative copy; every change also appends a change record (who,
when, previous and new values, manual or AI-assisted, the annotation's ``editVersion`` and the
definition's revision) that keeps the attribute's name and the values' labels and kinds as
defined then, so history does not take on a later rename or depend on the definition still existing. Assignments are written best effort per annotation (ADR 0002) and
checked against the annotation's ``attributeVersion``, which only assignments move: a write
based on an outdated copy is refused (``edit_conflict``) and changes nothing; one that finds the
annotation already as it asks counts as done without writing. The check runs under the span's
per-process lock (as ADR 0010). Only approved (``pos``) annotations receive values; proposals and
rejected annotations never carry accepted assignments, and nothing here inserts AI-proposed values.

Assignments need the attribute properties on the annotation collection
(``SpanRepository.attributes``); without them they are refused (503) while definitions still work.
"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from semant_demo.adapters.sql.attributes import AttributeRepository
from semant_demo.adapters.weaviate.writes import step_failure
from semant_demo.core.errors import InUseError, InvalidRequestError, NotFoundError, ServiceUnavailableError
from semant_demo.core.outcomes import StepFailure, outcome_of
from semant_demo.features.annotations.schemas import SpanType, TagSpan
from semant_demo.features.annotations.service import ATTRIBUTES_NOT_ENABLED as NOT_ENABLED
from semant_demo.features.annotations.service import AnnotationStore, use_tenant
from semant_demo.features.annotations import attribute_codec as codec
from semant_demo.features.attributes.schemas import (
    Attribute, AttributeAssignRequest, AttributeAssignResult, AttributeChange, AttributeChangeValue, AssignMode, AssignSource, Cardinality,
    PatchAttribute, PatchAttributeValue, PostAttribute, PostAttributeValue, ValueKind,
)
from semant_demo.features.user_collections import access
from semant_demo.features.user_collections.access import Principal

logger = logging.getLogger(__name__)

Id = str | UUID

ASSIGN_CONCURRENCY = 16
"""Annotations of one assign request written at the same time (each is a read and a write)."""
EDIT_CONFLICT = "Changed by someone else since it was loaded; nothing was saved."
USAGE_UNKNOWN = "Could not check which annotations hold these values; nothing was changed. Try again later."


@dataclass
class AttributeStore:
    """What attribute use cases read and write: the definitions and the annotation store."""
    definitions: AttributeRepository
    annotations: AnnotationStore


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _attribute_not_found() -> NotFoundError:
    return NotFoundError("Attribute not found")


def _check_kinds(existing: list[ValueKind], new: list[ValueKind]) -> None:
    """At most one Unknown and one Not applicable value per attribute."""
    kinds = [*existing, *new]
    for kind in (ValueKind.unknown, ValueKind.not_applicable):
        if kinds.count(kind) > 1:
            raise InvalidRequestError(f"An attribute has at most one {kind.value.replace('_', ' ')} value")


async def _read(store: AttributeStore, cid: UUID, attribute_id: Id) -> Attribute:
    attribute = await store.definitions.read(cid, access.parse_id(attribute_id, "Attribute"))
    if attribute is None:
        raise _attribute_not_found()
    return attribute


##############
# Definitions #
##############

async def list_attributes(store: AttributeStore, user: Principal | None, collection_id: Id) -> list[Attribute]:
    """The collection's attributes with their values (also retired ones), by name."""
    grant = await access.require_collection_read(store.annotations.collections, user, collection_id)
    return await store.definitions.read_all(grant.collection_id)


async def create_attribute(store: AttributeStore, user: Principal | None, collection_id: Id,
                           attribute: PostAttribute) -> Attribute:
    grant = await access.require_attribute_definition_edit(store.annotations.collections, user, collection_id)
    _check_kinds([], [v.kind for v in attribute.values])
    await access.require_tags_in_collection(store.annotations.tags, attribute.tag_ids, grant.collection_id)
    return await store.definitions.create(grant.collection_id, attribute, user.id)


async def update_attribute(store: AttributeStore, user: Principal | None, collection_id: Id, attribute_id: Id,
                           patch: PatchAttribute) -> Attribute:
    """Renames, describes, retires or changes the tags of an attribute; ids of assigned values
    are untouched, so no annotation is rewritten. Narrowing the applicable tags (All tags to
    selected tags or to none, or leaving out a selected tag) of an attribute that annotations
    hold values of is refused (``InUseError``, 409, with the number of annotations affected):
    those values would stop being applicable. Removing the last selected tag leaves the
    attribute with no tag, never All tags (#522)."""
    grant = await access.require_attribute_definition_edit(store.annotations.collections, user, collection_id)
    if patch.all_tags is not None or patch.tag_ids is not None:
        current = await _read(store, grant.collection_id, attribute_id)
        all_tags, tag_ids = _scope_after(current, patch)
        if patch.tag_ids:
            await access.require_tags_in_collection(store.annotations.tags, patch.tag_ids, grant.collection_id)
        if not all_tags and (current.all_tags or not set(current.tag_ids) <= set(tag_ids)):
            used = await _usage(store, grant, current.id, outside_tags=tag_ids)
            if used:
                raise InUseError(f"{used} annotations with values of this attribute have a tag outside the new "
                                 "applicable tags; change or remove those values first.", used)
        patch = patch.model_copy(update={"all_tags": all_tags, "tag_ids": tag_ids})
    updated = await store.definitions.update(grant.collection_id, access.parse_id(attribute_id, "Attribute"), patch)
    if updated is None:
        raise _attribute_not_found()
    return updated


def _scope_after(current: Attribute, patch: PatchAttribute) -> tuple[bool, list[UUID]]:
    """``(all_tags, tag_ids)`` the patch leaves the attribute with. All tags is only ever chosen
    explicitly; an empty list of tags is no tag."""
    all_tags = current.all_tags if patch.all_tags is None else patch.all_tags
    if all_tags:
        if patch.tag_ids:
            raise InvalidRequestError("This attribute applies to all tags; send all_tags false to select tags.")
        return True, []
    return False, list(dict.fromkeys(current.tag_ids if patch.tag_ids is None else patch.tag_ids))


async def _usage(store: AttributeStore, grant, attribute_id: UUID, value_id: UUID | None = None,
                 outside_tags: list[UUID] | None = None) -> int:
    """Annotations holding values of the attribute (of the value). None without the attribute
    properties; when startup could not tell whether they exist, or the count fails, the guarded
    change is refused (503) rather than let through unchecked."""
    spans = store.annotations.spans
    if not spans.attributes and spans.attributes_checked:
        return 0
    try:
        return await spans.count_attribute_use(await use_tenant(store.annotations, grant), attribute_id, value_id,
                                               outside_tags)
    except Exception as exc:
        logger.warning("Could not count the annotations holding values of attribute %s: %s",
                       attribute_id, type(exc).__name__)
        raise ServiceUnavailableError(USAGE_UNKNOWN) from exc


async def delete_attribute(store: AttributeStore, user: Principal | None, collection_id: Id, attribute_id: Id) -> None:
    """Deletes an attribute no annotation holds a value of; otherwise ``InUseError`` (409) with
    the number of annotations affected, and the attribute can be retired instead."""
    grant = await access.require_attribute_definition_edit(store.annotations.collections, user, collection_id)
    attribute = await _read(store, grant.collection_id, attribute_id)
    used = await _usage(store, grant, attribute.id)
    if used:
        raise InUseError(f"{used} annotations have values of this attribute; retire it instead of deleting it.", used)
    await store.definitions.delete(grant.collection_id, attribute.id)


async def add_value(store: AttributeStore, user: Principal | None, collection_id: Id, attribute_id: Id,
                    value: PostAttributeValue) -> Attribute:
    grant = await access.require_attribute_definition_edit(store.annotations.collections, user, collection_id)
    attribute = await _read(store, grant.collection_id, attribute_id)
    _check_kinds([v.kind for v in attribute.values], [value.kind])
    added = await store.definitions.add_value(grant.collection_id, attribute.id, value)
    if added is None:
        raise _attribute_not_found()
    return added


async def update_value(store: AttributeStore, user: Principal | None, collection_id: Id, attribute_id: Id,
                       value_id: Id, patch: PatchAttributeValue) -> Attribute:
    """Renames, describes or retires a value; its id and its assignments stay."""
    grant = await access.require_attribute_definition_edit(store.annotations.collections, user, collection_id)
    updated = await store.definitions.update_value(
        grant.collection_id, access.parse_id(attribute_id, "Attribute"), access.parse_id(value_id, "Value"), patch)
    if updated is None:
        raise NotFoundError("Attribute or value not found")
    return updated


async def delete_value(store: AttributeStore, user: Principal | None, collection_id: Id, attribute_id: Id,
                       value_id: Id) -> Attribute:
    """Deletes a value no annotation holds; otherwise ``InUseError`` (409) with the number of
    annotations affected, and the value can be retired instead."""
    grant = await access.require_attribute_definition_edit(store.annotations.collections, user, collection_id)
    attribute = await _read(store, grant.collection_id, attribute_id)
    vid = access.parse_id(value_id, "Value")
    if all(v.id != vid for v in attribute.values):
        raise NotFoundError("Attribute or value not found")
    used = await _usage(store, grant, attribute.id, vid)
    if used:
        raise InUseError(f"{used} annotations have this value; retire it instead of deleting it.", used)
    deleted = await store.definitions.delete_value(grant.collection_id, attribute.id, vid)
    if deleted is None:
        raise NotFoundError("Attribute or value not found")
    return deleted


##############
# Assignments #
##############

def _item_failure(annotation_id: UUID, step: str, message: str) -> StepFailure:
    return StepFailure(item_id=str(annotation_id), step=step, message=message)


def _result_values(mode: AssignMode, previous: list[UUID], asked: list[UUID]) -> list[UUID]:
    if mode == AssignMode.add:
        return [*previous, *[v for v in asked if v not in previous]]
    if mode == AssignMode.remove:
        return [v for v in previous if v not in asked]
    return list(dict.fromkeys(asked))


def _snapshot(attribute: Attribute, value_ids: list[UUID]) -> list[AttributeChangeValue]:
    """The values as the attribute defines them now, for a change record (an id it no longer
    defines keeps no label)."""
    known = {v.id: v for v in attribute.values}
    return [AttributeChangeValue(id=v, label=known[v].label, kind=known[v].kind) if v in known
            else AttributeChangeValue(id=v) for v in value_ids]


@dataclass
class _Item:
    """What one annotation's assignment came to: exactly one of ``failure`` and ``saved``."""
    annotation_id: UUID
    failure: StepFailure | None = None
    version: int | None = None
    values: list[UUID] | None = None
    record_failure: StepFailure | None = None
    """Set when that record could not be written; the assignment stays."""


def _type_failure(request: AttributeAssignRequest, span: TagSpan, sid: UUID) -> StepFailure | None:
    """Only approved annotations take values (removing is always allowed). Checked before "already
    as asked": values kept on a rejected annotation are not accepted ones, so asking for them again
    is no success."""
    if request.mode == AssignMode.remove or span.type == SpanType.pos:
        return None
    return _item_failure(sid, "check_annotation_type",
                         "Only approved annotations take attribute values; approve it first.")


def _rule_failure(attribute: Attribute, request: AttributeAssignRequest, span: TagSpan, previous: list[UUID],
                  result: list[UUID], sid: UUID) -> StepFailure | None:
    """Why the assignment is not allowed for this annotation, or None. Removing is always allowed.
    The annotation type is checked earlier (``_type_failure``)."""
    if request.mode == AssignMode.remove:
        return None
    if not attribute.all_tags and UUID(span.tagId) not in attribute.tag_ids:
        return _item_failure(sid, "check_applicable", "This attribute does not apply to the annotation's tag.")
    retired = {v.id for v in attribute.values if v.retired}
    if any(v in retired for v in result if v not in previous):
        return _item_failure(sid, "check_value", "A retired value cannot be assigned again.")
    if attribute.cardinality == Cardinality.single and len(result) > 1:
        return _item_failure(sid, "check_cardinality",
                             "A single-valued attribute has one value; replace it instead of adding another.")
    kinds = {v.id: v.kind for v in attribute.values}
    if len(result) > 1 and any(kinds.get(v, ValueKind.value) != ValueKind.value for v in result):
        return _item_failure(sid, "check_value", "Unknown and Not applicable cannot be combined with other values.")
    return None


async def _assign_one(store: AttributeStore, cid: UUID, attribute: Attribute, request: AttributeAssignRequest,
                      sid: UUID, actor: UUID) -> _Item:
    spans = store.annotations.spans
    async with spans.lock(sid):
        try:
            found = await spans.read_assignments(cid, sid)
        except Exception as exc:
            return _Item(sid, failure=step_failure("find_annotation", sid, exc))
        if found is None:
            return _Item(sid, failure=_item_failure(
                sid, "find_annotation", "No such annotation in this collection; it may have been deleted."))
        span, stored = found
        failure = _type_failure(request, span, sid)
        if failure is not None:
            return _Item(sid, failure=failure)
        grouped = codec.group(stored)
        previous = grouped.get(attribute.id, [])
        result = _result_values(request.mode, previous, request.value_ids)
        if set(result) == set(previous):
            # Already as asked: a retry of a write that landed is no conflict.
            return _Item(sid, version=span.attributeVersion, values=previous)
        if span.attributeVersion != request.expected_versions[sid]:
            return _Item(sid, failure=_item_failure(sid, "edit_conflict", EDIT_CONFLICT),
                         version=span.attributeVersion, values=previous)
        failure = _rule_failure(attribute, request, span, previous, result, sid)
        if failure is not None:
            return _Item(sid, failure=failure)
        others = [codec.encode(a, v) for a, vs in grouped.items() if a != attribute.id for v in vs]
        version = span.attributeVersion + 1
        try:
            await spans.write_attributes(cid, sid, [*others, *(codec.encode(attribute.id, v) for v in result)],
                                         version)
        except Exception as exc:
            return _Item(sid, failure=step_failure("update_attributes", sid, exc))
        # Recorded under the lock too, so consecutive changes of one annotation are stored in the
        # order they were made and their previous / current values chain.
        item = _Item(sid, version=version, values=result)
        change = AttributeChange(
            annotation_id=sid, attribute_id=attribute.id, attribute_name=attribute.name,
            previous=_snapshot(attribute, previous), current=_snapshot(attribute, result), actor_id=actor,
            at=_now(), source=request.source, run_id=request.run_id,
            annotation_edit_version=span.editVersion if spans.provenance else None,
            attribute_revision=attribute.revision)
        try:
            await store.definitions.record_changes(cid, [change])
        except Exception as exc:
            item.record_failure = step_failure("record_attribute_changes", sid, exc)
        return item


async def assign_attributes(store: AttributeStore, user: Principal | None, collection_id: Id,
                            request: AttributeAssignRequest) -> AttributeAssignResult:
    """
    Adds, removes or replaces the values of one attribute on up to ``MAX_ASSIGN_BATCH``
    approved annotations, each on its own: written best effort and reported per item (nothing is
    rolled back). A refused request (400/404) changed nothing; per item, ``failed`` names why an
    annotation was not changed (``find_annotation``, ``edit_conflict``, ``check_annotation_type``,
    ``check_applicable``, ``check_value``, ``check_cardinality``, ``update_attributes`` -
    ``uncertain`` on a timeout). Each saved change is recorded right after its write, under the same lock; when that fails the
    assignment stays and ``record_attribute_changes`` is reported for that annotation.
    """
    grant = await access.require_annotation_edit(store.annotations.collections, user, collection_id)
    spans = store.annotations.spans
    if not spans.attributes:
        raise ServiceUnavailableError(NOT_ENABLED)
    if request.source == AssignSource.ai_assisted:
        raise InvalidRequestError("AI-assisted assignments come with attribute proposals (#338) and are not "
                                  "accepted yet: a run cannot be checked.")
    attribute = await _read(store, grant.collection_id, request.attribute_id)
    ids = list(dict.fromkeys(request.annotation_ids))
    asked = list(dict.fromkeys(request.value_ids))
    known = {v.id: v for v in attribute.values}
    if any(v not in known for v in asked):
        raise NotFoundError("Value not found")
    if request.mode != AssignMode.remove:
        if attribute.retired:
            raise InvalidRequestError("This attribute is retired; values can only be removed.")
        if attribute.cardinality == Cardinality.single and len(asked) > 1:
            raise InvalidRequestError("A single-valued attribute takes one value.")
        if len(asked) > 1 and any(known[v].kind != ValueKind.value for v in asked):
            raise InvalidRequestError("Unknown and Not applicable cannot be combined with other values.")
    request = request.model_copy(update={"annotation_ids": ids, "value_ids": asked})
    cid = await use_tenant(store.annotations, grant)
    limit = asyncio.Semaphore(ASSIGN_CONCURRENCY)

    async def bounded(sid: UUID) -> _Item:
        async with limit:
            return await _assign_one(store, cid, attribute, request, sid, user.id)

    items = await asyncio.gather(*(bounded(sid) for sid in ids))

    failed = [i.failure for i in items if i.failure is not None]
    saved = [i for i in items if i.failure is None]
    failed.extend(i.record_failure for i in saved if i.record_failure is not None)
    return AttributeAssignResult(
        outcome=outcome_of(len(saved), len(failed)), succeeded=[str(i.annotation_id) for i in saved], failed=failed,
        versions={i.annotation_id: i.version for i in items if i.version is not None},
        values={i.annotation_id: i.values for i in items if i.values is not None})


async def read_attribute_changes(store: AttributeStore, user: Principal | None, collection_id: Id,
                                 annotation_id: Id) -> list[AttributeChange]:
    """The annotation's attribute change records (who, when, previous and new values with the names
    and labels of that time), oldest first; also for attributes and values deleted since."""
    grant = await access.require_collection_read(store.annotations.collections, user, collection_id)
    return await store.definitions.read_changes(grant.collection_id, access.parse_id(annotation_id, "Annotation"))
