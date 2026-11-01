"""Collection attributes (features/attributes, #331) called directly, with a real SQLite
repository and in-memory spans.

Definitions (unique names, retirement, deletion only while unused, per-collection ids), the
accepted-assignment rules (approved annotations only, tag applicability, cardinality, Unknown /
Not applicable exclusivity, retired values), the ``attributeVersion`` conflict check and its
"already as asked" exception, uncertain and failed writes, change records, access and denied
requests reaching nothing. The stored encoding and the Weaviate filters: ``test_attribute_codec``
below and tests/integration/test_annotation_attributes.py.
"""
import asyncio
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from weaviate.exceptions import WeaviateTimeoutError

from semant_demo.adapters.sql.attributes import AttributeRepository
from semant_demo.adapters.sql.base import Base
from semant_demo.core.errors import InUseError, InvalidRequestError, NotFoundError, ServiceUnavailableError
from semant_demo.features.annotations.schemas import SpanType, TagSpan
from semant_demo.features.annotations.service import AnnotationStore
from semant_demo.features.annotations import attribute_codec as codec
from semant_demo.features.attributes import service
from semant_demo.features.attributes.schemas import (
    AssignMode, AssignSource, AttributeAssignRequest, PatchAttribute, PatchAttributeValue, PostAttribute,
    PostAttributeValue, ValueKind,
)
from semant_demo.features.attributes.service import AttributeStore
from semant_demo.features.user_collections.access import AccessDenied, AuthenticationRequired, ResourceNotFound

OWNER, SHARED, OTHER = (SimpleNamespace(id=uuid4(), is_superuser=False) for _ in range(3))
COLLECTION, SECOND_COLLECTION = uuid4(), uuid4()
PERSON, PLACE, SECOND_TAG = uuid4(), uuid4(), uuid4()
APPROVED, SUGGESTION, REJECTED, PLACE_SPAN = (uuid4() for _ in range(4))


class FakeCollections:
    async def read_access_record(self, cid):
        return {COLLECTION: (OWNER.id, {SHARED.id}), SECOND_COLLECTION: (OWNER.id, set())}.get(cid)


class FakeTags:
    async def read_collection_ids(self, ids):
        owners = {PERSON: [COLLECTION], PLACE: [COLLECTION], SECOND_TAG: [SECOND_COLLECTION]}
        return {t: owners[t] for t in ids if t in owners}


class FakeSpans:
    """Spans per collection like the annotation tenants; only the attribute properties are modelled."""

    def __init__(self):
        self.attributes = True
        self.attributes_checked = True
        self.provenance = True
        self.spans: dict = {}
        self.stored: dict = {}
        """Stored ``attributeValues`` per (collection, span)."""
        self.writes: list = []
        self.fail: Exception | None = None
        self.fail_read: Exception | None = None
        self.counted = 0
        self._locks: dict = {}

    def lock(self, span_id):
        return self._locks.setdefault(span_id, asyncio.Lock())

    async def read_assignments(self, cid, span_id):
        if self.fail_read is not None:
            raise self.fail_read
        span = self.spans.get((cid, span_id))
        return (span.model_copy(deep=True), list(self.stored.get((cid, span_id), []))) if span else None

    async def write_attributes(self, cid, span_id, values, version):
        if self.fail is not None:
            raise self.fail
        self.writes.append((span_id, sorted(values), version))
        self.stored[(cid, span_id)] = sorted(set(values))
        self.spans[(cid, span_id)].attributeVersion = version

    async def count_attribute_use(self, cid, attribute_id, value_id=None, outside_tags=None):
        if not self.attributes:
            raise RuntimeError("no such property: attributeValues")
        self.counted += 1
        total = 0
        for (c, sid), span in self.spans.items():
            values = [str(v) for v in codec.group(self.stored.get((c, sid))).get(attribute_id, [])]
            outside = outside_tags is None or UUID(span.tagId) not in outside_tags
            total += c == cid and outside and (bool(values) if value_id is None else str(value_id) in values)
        return total


class FakeActivity:
    async def touch(self, cid):
        pass


def span(span_id, tag=PERSON, type=SpanType.pos, cid=COLLECTION):
    return TagSpan(id=str(span_id), chunkId=str(uuid4()), tagId=str(tag), start=0, end=3, type=type, editVersion=4)


@pytest.fixture
async def definitions(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'attributes.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield AttributeRepository(async_sessionmaker(engine, expire_on_commit=False))
    await engine.dispose()


@pytest.fixture
def spans():
    fake = FakeSpans()
    for sid, tag, type in ((APPROVED, PERSON, SpanType.pos), (SUGGESTION, PERSON, SpanType.auto),
                           (REJECTED, PERSON, SpanType.neg), (PLACE_SPAN, PLACE, SpanType.pos)):
        fake.spans[(COLLECTION, sid)] = span(sid, tag, type)
    return fake


@pytest.fixture
def store(definitions, spans):
    annotations = AnnotationStore(collections=FakeCollections(), tags=FakeTags(), spans=spans, chunk_tags=None,
                                  documents=None, activity=FakeActivity())
    return AttributeStore(definitions=definitions, annotations=annotations)


def attribute_body(**kwargs):
    """All tags unless tags are given: All tags is chosen explicitly (#522)."""
    kwargs.setdefault("name", "speaker_type")
    if "tag_ids" not in kwargs:
        kwargs.setdefault("all_tags", True)
    kwargs.setdefault("values", [PostAttributeValue(label="Author"), PostAttributeValue(label="Narrator")])
    return PostAttribute(**kwargs)


async def define(store, **kwargs):
    return await service.create_attribute(store, OWNER, COLLECTION, attribute_body(**kwargs))


def assign(attribute, annotations, mode, values, versions=None, **kwargs):
    return AttributeAssignRequest(
        attribute_id=attribute.id, annotation_ids=annotations, mode=mode, value_ids=[v.id for v in values],
        expected_versions={a: (versions or {}).get(a, 0) for a in annotations}, **kwargs)


def values_of(spans, sid, attribute):
    return [str(v) for v in codec.group(spans.stored.get((COLLECTION, sid))).get(attribute.id, [])]


# ── The stored encoding ───────────────────────────────────────────────────

def test_the_codec_is_unambiguous_and_strict():
    a, v = uuid4(), uuid4()
    assert codec.decode(codec.encode(a, v)) == (a, v)
    assert codec.encode(a, v) == f"{a}:{v}" and codec.attribute_pattern(a) == f"{a}:*"
    for bad in ("", "x", f"{a}", f"{a}:", f"{a}:{v}:{v}", f"{a}-{v}", f"{a}:{v} ", f"{str(a).upper()}:{v}",
                f"{a}:{str(v)[:-1]}"):
        with pytest.raises(ValueError):
            codec.decode(bad)
    # Fixed-length parts: no element is a prefix of another, so a prefix selects one attribute only.
    other = uuid4()
    assert not codec.encode(other, v).startswith(f"{a}:")
    assert codec.group([codec.encode(a, v), "junk", codec.encode(a, other)]) == {a: [v, other]}


# ── Definitions ───────────────────────────────────────────────────────────

async def test_definitions_are_unique_per_collection_and_rename_keeps_their_ids(store):
    attribute = await define(store, name="Speaker")
    assert [v.label for v in attribute.values] == ["Author", "Narrator"] and attribute.revision == 1
    with pytest.raises(InvalidRequestError):
        await define(store, name=" speaker ")
    with pytest.raises(InvalidRequestError):
        await define(store, name="other", values=[PostAttributeValue(label="Same"), PostAttributeValue(label="same ")])
    # Another collection of the same user may use the name.
    second = await service.create_attribute(store, OWNER, SECOND_COLLECTION, attribute_body(name="Speaker"))
    assert second.id != attribute.id

    renamed = await service.update_attribute(store, SHARED, COLLECTION, attribute.id, PatchAttribute(name="Voice"))
    assert (renamed.id, renamed.name, renamed.revision) == (attribute.id, "Voice", 2)
    value = renamed.values[0]
    relabeled = await service.update_value(store, OWNER, COLLECTION, attribute.id, value.id,
                                           PatchAttributeValue(label="Writer", description="Who writes"))
    assert [(v.id, v.label) for v in relabeled.values][0] == (value.id, "Writer") and relabeled.revision == 3
    assert [a.name for a in await service.list_attributes(store, SHARED, COLLECTION)] == ["Voice"]
    assert [a.name for a in await service.list_attributes(store, OWNER, SECOND_COLLECTION)] == ["Speaker"]


async def test_definitions_of_another_collection_are_not_found_and_access_is_checked_first(store, spans):
    attribute = await define(store)
    with pytest.raises(NotFoundError):
        await service.update_attribute(store, OWNER, SECOND_COLLECTION, attribute.id, PatchAttribute(name="x"))
    with pytest.raises(NotFoundError):
        await service.delete_value(store, OWNER, SECOND_COLLECTION, attribute.id, attribute.values[0].id)
    with pytest.raises(NotFoundError):
        await service.delete_value(store, OWNER, COLLECTION, attribute.id, uuid4())
    with pytest.raises(ResourceNotFound):
        await service.list_attributes(store, OTHER, COLLECTION)
    with pytest.raises(ResourceNotFound):
        await service.create_attribute(store, OTHER, COLLECTION, attribute_body(name="x"))
    with pytest.raises(AuthenticationRequired):
        await service.list_attributes(store, None, COLLECTION)
    with pytest.raises(ResourceNotFound):
        await service.update_attribute(store, OWNER, "not-a-uuid", attribute.id, PatchAttribute(name="x"))
    # A tag of another collection cannot restrict the attribute.
    with pytest.raises(ResourceNotFound):
        await define(store, name="limited", tag_ids=[SECOND_TAG])
    assert spans.writes == []


async def test_only_one_unknown_and_one_not_applicable_value(store):
    attribute = await define(store, values=[PostAttributeValue(label="Unknown", kind=ValueKind.unknown)])
    with pytest.raises(InvalidRequestError):
        await service.add_value(store, OWNER, COLLECTION, attribute.id,
                                PostAttributeValue(label="Also unknown", kind=ValueKind.unknown))
    added = await service.add_value(store, OWNER, COLLECTION, attribute.id,
                                    PostAttributeValue(label="n/a", kind=ValueKind.not_applicable))
    assert [v.kind for v in added.values] == [ValueKind.unknown, ValueKind.not_applicable]
    with pytest.raises(InvalidRequestError):
        await define(store, name="two", values=[PostAttributeValue(label="a", kind=ValueKind.unknown),
                                                PostAttributeValue(label="b", kind=ValueKind.unknown)])


async def test_used_definitions_are_not_deleted_but_can_be_retired(store, spans):
    attribute = await define(store)
    author, narrator = attribute.values
    await service.assign_attributes(store, OWNER, COLLECTION, assign(attribute, [APPROVED], AssignMode.add, [author]))

    with pytest.raises(InUseError) as used:
        await service.delete_value(store, OWNER, COLLECTION, attribute.id, author.id)
    assert used.value.affected == 1
    with pytest.raises(InUseError):
        await service.delete_attribute(store, OWNER, COLLECTION, attribute.id)
    after = await service.delete_value(store, OWNER, COLLECTION, attribute.id, narrator.id)
    assert [v.label for v in after.values] == ["Author"]
    retired = await service.update_value(store, OWNER, COLLECTION, attribute.id, author.id,
                                         PatchAttributeValue(retired=True))
    assert retired.values[0].retired and values_of(spans, APPROVED, attribute) == [str(author.id)]

    await service.assign_attributes(store, OWNER, COLLECTION,
                                    assign(attribute, [APPROVED], AssignMode.remove, [author], {APPROVED: 1}))
    await service.delete_attribute(store, OWNER, COLLECTION, attribute.id)
    assert await service.list_attributes(store, OWNER, COLLECTION) == []


async def test_definitions_work_but_assignments_are_refused_without_the_attribute_properties(store, spans):
    spans.attributes = False
    attribute = await define(store)
    await service.delete_attribute(store, OWNER, COLLECTION, attribute.id)  # nothing to count
    attribute = await define(store)
    with pytest.raises(ServiceUnavailableError, match="add-schema"):
        await service.assign_attributes(store, OWNER, COLLECTION,
                                        assign(attribute, [APPROVED], AssignMode.add, attribute.values[:1]))
    assert spans.writes == [] and spans.counted == 0


async def test_usage_guarded_changes_are_refused_when_whether_values_exist_is_unknown(store, spans):
    attribute = await define(store, tag_ids=[PERSON])
    author = attribute.values[0]
    await service.assign_attributes(store, OWNER, COLLECTION, assign(attribute, [APPROVED], AssignMode.add, [author]))
    # Startup could not read the schema: the values may well be there, so nothing counts as unused.
    spans.attributes, spans.attributes_checked = False, False
    with pytest.raises(ServiceUnavailableError):
        await service.delete_attribute(store, OWNER, COLLECTION, attribute.id)
    with pytest.raises(ServiceUnavailableError):
        await service.delete_value(store, OWNER, COLLECTION, attribute.id, author.id)
    with pytest.raises(ServiceUnavailableError):
        await service.update_attribute(store, OWNER, COLLECTION, attribute.id, PatchAttribute(tag_ids=[PLACE]))
    # A count that fails on a store with the properties is no "unused" either.
    spans.attributes, spans.attributes_checked = True, True

    async def failing(*args):
        raise RuntimeError("weaviate is down")
    spans.count_attribute_use = failing
    with pytest.raises(ServiceUnavailableError):
        await service.delete_attribute(store, OWNER, COLLECTION, attribute.id)
    assert [a.id for a in await service.list_attributes(store, OWNER, COLLECTION)] == [attribute.id]
    assert (await service.list_attributes(store, OWNER, COLLECTION))[0].tag_ids == [PERSON]


def test_public_spans_do_not_carry_attribute_values():
    from semant_demo.adapters.weaviate.spans import to_span

    stored = SimpleNamespace(uuid=REJECTED, properties={
        "chunkId": uuid4(), "tagId": PERSON, "start": 0, "end": 3, "type": "neg",
        "attributeValues": [codec.encode(uuid4(), uuid4())], "attributeVersion": 2})
    public = to_span(stored).model_dump()
    assert "attributes" not in public and public["attributeVersion"] == 2


# ── Assignments ───────────────────────────────────────────────────────────

async def test_assignment_modes_on_a_multi_valued_attribute_and_the_change_records(store, spans, definitions):
    attribute = await define(store, name="topic", cardinality="multi", values=[PostAttributeValue(label=x) for x in "abc"])
    a, b, c = attribute.values

    first = await service.assign_attributes(store, SHARED, COLLECTION, assign(attribute, [APPROVED], AssignMode.add, [a, b]))
    assert (first.outcome.value, first.succeeded, first.versions) == ("complete", [str(APPROVED)], {APPROVED: 1})
    assert sorted(first.values[APPROVED]) == sorted([a.id, b.id])
    second = await service.assign_attributes(store, OWNER, COLLECTION,
                                             assign(attribute, [APPROVED], AssignMode.add, [c], {APPROVED: 1}))
    assert second.versions == {APPROVED: 2}
    await service.assign_attributes(store, OWNER, COLLECTION,
                                    assign(attribute, [APPROVED], AssignMode.remove, [a], {APPROVED: 2}))
    await service.assign_attributes(store, OWNER, COLLECTION,
                                    assign(attribute, [APPROVED], AssignMode.replace, [a], {APPROVED: 3}))
    assert values_of(spans, APPROVED, attribute) == [str(a.id)]
    cleared = await service.assign_attributes(store, OWNER, COLLECTION,
                                              assign(attribute, [APPROVED], AssignMode.replace, [], {APPROVED: 4}))
    assert cleared.values == {APPROVED: []} and spans.spans[(COLLECTION, APPROVED)].attributeVersion == 5

    changes = await service.read_attribute_changes(store, SHARED, COLLECTION, APPROVED)
    # Values are stored sorted (as in Weaviate), so the order within one record is not the request's.
    assert [(ch.actor_id, ids(ch.previous), ids(ch.current), ch.source) for ch in changes][:2] == [
        (SHARED.id, [], sorted([a.id, b.id]), AssignSource.manual),
        (OWNER.id, sorted([a.id, b.id]), sorted([a.id, b.id, c.id]), AssignSource.manual)]
    assert [ch.annotation_edit_version for ch in changes] == [4] * 5 and {ch.attribute_revision for ch in changes} == {1}
    assert await definitions.read_changes(SECOND_COLLECTION, APPROVED) == []


async def test_other_attributes_of_the_annotation_are_kept(store, spans):
    speaker, topic = await define(store), await define(store, name="topic", cardinality="multi")
    await service.assign_attributes(store, OWNER, COLLECTION,
                                    assign(speaker, [APPROVED], AssignMode.add, speaker.values[:1]))
    await service.assign_attributes(store, OWNER, COLLECTION,
                                    assign(topic, [APPROVED], AssignMode.add, topic.values, {APPROVED: 1}))
    await service.assign_attributes(store, OWNER, COLLECTION,
                                    assign(topic, [APPROVED], AssignMode.replace, [], {APPROVED: 2}))
    assert values_of(spans, APPROVED, speaker) == [str(speaker.values[0].id)]
    assert values_of(spans, APPROVED, topic) == []


async def test_per_item_rules_report_what_was_not_changed_and_why(store, spans):
    place_only = await define(store, name="place_kind", tag_ids=[PLACE])
    request = assign(place_only, [APPROVED, SUGGESTION, REJECTED, PLACE_SPAN, uuid4()], AssignMode.add,
                     place_only.values[:1])
    result = await service.assign_attributes(store, OWNER, COLLECTION, request)

    assert result.succeeded == [str(PLACE_SPAN)] and result.outcome.value == "partial"
    steps = {f.item_id: f.step for f in result.failed}
    assert steps == {str(APPROVED): "check_applicable", str(SUGGESTION): "check_annotation_type",
                     str(REJECTED): "check_annotation_type", str(request.annotation_ids[4]): "find_annotation"}
    assert [w[0] for w in spans.writes] == [PLACE_SPAN]


async def test_values_kept_on_a_rejected_annotation_are_not_accepted_by_asking_again(store, spans, definitions):
    attribute = await define(store)
    author = attribute.values[0]
    spans.stored[(COLLECTION, REJECTED)] = [codec.encode(attribute.id, author.id)]  # assigned, then rejected
    again = await service.assign_attributes(store, OWNER, COLLECTION,
                                            assign(attribute, [REJECTED], AssignMode.add, [author]))
    assert again.succeeded == [] and [f.step for f in again.failed] == ["check_annotation_type"]
    assert REJECTED not in again.values and spans.writes == []
    # Removing them is allowed on any annotation.
    removed = await service.assign_attributes(store, OWNER, COLLECTION,
                                              assign(attribute, [REJECTED], AssignMode.remove, [author]))
    assert removed.succeeded == [str(REJECTED)] and values_of(spans, REJECTED, attribute) == []
    assert len(await definitions.read_changes(COLLECTION, REJECTED)) == 1


async def test_cardinality_and_exclusive_unknown_and_retired_values(store, spans):
    attribute = await define(store, values=[PostAttributeValue(label="Author"), PostAttributeValue(label="Narrator"),
                                            PostAttributeValue(label="Unknown", kind=ValueKind.unknown)])
    author, narrator, unknown = attribute.values
    await service.assign_attributes(store, OWNER, COLLECTION, assign(attribute, [APPROVED], AssignMode.add, [author]))

    again = await service.assign_attributes(store, OWNER, COLLECTION,
                                            assign(attribute, [APPROVED], AssignMode.add, [author], {APPROVED: 0}))
    assert again.succeeded == [str(APPROVED)] and len(spans.writes) == 1  # already as asked: no write, no conflict
    different = await service.assign_attributes(store, OWNER, COLLECTION,
                                                assign(attribute, [APPROVED], AssignMode.add, [narrator], {APPROVED: 1}))
    assert [f.step for f in different.failed] == ["check_cardinality"]
    with pytest.raises(InvalidRequestError, match="one value"):
        await service.assign_attributes(store, OWNER, COLLECTION,
                                        assign(attribute, [APPROVED], AssignMode.replace, [author, narrator], {APPROVED: 1}))

    multi = await define(store, name="multi", cardinality="multi",
                         values=[PostAttributeValue(label="x"), PostAttributeValue(label="Not applicable",
                                                                                  kind=ValueKind.not_applicable)])
    x, na = multi.values
    with pytest.raises(InvalidRequestError, match="combined"):
        await service.assign_attributes(store, OWNER, COLLECTION, assign(multi, [APPROVED], AssignMode.add, [x, na]))
    await service.assign_attributes(store, OWNER, COLLECTION,
                                    assign(multi, [APPROVED], AssignMode.add, [x], {APPROVED: 1}))
    combined = await service.assign_attributes(store, OWNER, COLLECTION,
                                               assign(multi, [APPROVED], AssignMode.add, [na], {APPROVED: 2}))
    assert [f.step for f in combined.failed] == ["check_value"]
    # Not applicable is a decision, not an absence.
    await service.assign_attributes(store, OWNER, COLLECTION, assign(multi, [PLACE_SPAN], AssignMode.add, [na]))
    assert values_of(spans, PLACE_SPAN, multi) == [str(na.id)]

    retire = await service.update_value(store, OWNER, COLLECTION, multi.id, x.id, PatchAttributeValue(retired=True))
    assert retire.values[0].retired
    refused = await service.assign_attributes(store, OWNER, COLLECTION,
                                              assign(multi, [PLACE_SPAN], AssignMode.replace, [x], {PLACE_SPAN: 1}))
    assert [f.step for f in refused.failed] == ["check_value"]
    await service.update_attribute(store, OWNER, COLLECTION, multi.id, PatchAttribute(retired=True))
    with pytest.raises(InvalidRequestError, match="retired"):
        await service.assign_attributes(store, OWNER, COLLECTION, assign(multi, [PLACE_SPAN], AssignMode.add, [na], {PLACE_SPAN: 1}))
    removed = await service.assign_attributes(store, OWNER, COLLECTION,
                                              assign(multi, [PLACE_SPAN], AssignMode.remove, [na], {PLACE_SPAN: 1}))
    assert removed.succeeded == [str(PLACE_SPAN)]


async def test_a_stale_version_changes_nothing_and_reports_the_current_state(store, spans):
    attribute = await define(store, cardinality="multi")
    author, narrator = attribute.values
    await service.assign_attributes(store, OWNER, COLLECTION, assign(attribute, [APPROVED], AssignMode.add, [author]))

    stale = await service.assign_attributes(
        store, SHARED, COLLECTION, assign(attribute, [APPROVED, PLACE_SPAN], AssignMode.add, [narrator]))
    assert stale.succeeded == [str(PLACE_SPAN)]
    assert [(f.item_id, f.step) for f in stale.failed] == [(str(APPROVED), "edit_conflict")]
    assert stale.versions == {APPROVED: 1, PLACE_SPAN: 1} and stale.values[APPROVED] == [author.id]
    assert values_of(spans, APPROVED, attribute) == [str(author.id)]
    # The writer's own retry of a write that landed (the annotation is as asked) is no conflict.
    retry = await service.assign_attributes(store, OWNER, COLLECTION,
                                            assign(attribute, [APPROVED], AssignMode.add, [author]))
    assert retry.outcome.value == "complete" and len(spans.writes) == 2


async def test_concurrent_requests_for_one_annotation_cannot_both_win(store, spans):
    attribute = await define(store)
    author, narrator = attribute.values
    one, two = await asyncio.gather(
        service.assign_attributes(store, OWNER, COLLECTION, assign(attribute, [APPROVED], AssignMode.replace, [author])),
        service.assign_attributes(store, SHARED, COLLECTION, assign(attribute, [APPROVED], AssignMode.replace, [narrator])))
    assert sorted([len(one.succeeded), len(two.succeeded)]) == [0, 1]
    assert spans.spans[(COLLECTION, APPROVED)].attributeVersion == 1


async def test_failed_and_uncertain_writes_are_reported_per_item_and_not_recorded(store, spans, definitions):
    attribute = await define(store)
    author = attribute.values[0]
    spans.fail = WeaviateTimeoutError("slow")
    uncertain = await service.assign_attributes(store, OWNER, COLLECTION,
                                                assign(attribute, [APPROVED], AssignMode.add, [author]))
    assert uncertain.outcome.value == "failed" and uncertain.succeeded == []
    assert [(f.step, f.uncertain) for f in uncertain.failed] == [("update_attributes", True)]
    spans.fail = RuntimeError("down")
    failed = await service.assign_attributes(store, OWNER, COLLECTION,
                                             assign(attribute, [APPROVED], AssignMode.add, [author]))
    assert [(f.step, f.uncertain) for f in failed.failed] == [("update_attributes", False)]
    assert await definitions.read_changes(COLLECTION, APPROVED) == []


def clear(attribute, annotations, versions=None):
    return assign(attribute, annotations, AssignMode.clear, [], versions)


def test_clear_names_no_values_and_other_modes_name_some():
    attribute = SimpleNamespace(id=uuid4())
    with pytest.raises(ValueError, match="value_ids must be empty"):
        AttributeAssignRequest(attribute_id=attribute.id, annotation_ids=[APPROVED], expected_versions={APPROVED: 0},
                               mode=AssignMode.clear, value_ids=[uuid4()])
    # `remove` with no values stays an error, not a disguised clear.
    with pytest.raises(ValueError, match="at least one value"):
        AttributeAssignRequest(attribute_id=attribute.id, annotation_ids=[APPROVED], expected_versions={APPROVED: 0},
                               mode=AssignMode.remove, value_ids=[])


async def test_clear_removes_every_held_value_without_naming_the_vocabulary(store, spans, definitions):
    # A single-valued attribute with more values than one request may name (50).
    many = await define(store, name="place_name", values=[PostAttributeValue(label=f"v{i}") for i in range(60)])
    await service.assign_attributes(store, OWNER, COLLECTION, assign(many, [APPROVED], AssignMode.add, [many.values[57]]))
    topic = await define(store, name="topic", cardinality="multi")
    await service.assign_attributes(store, OWNER, COLLECTION,
                                    assign(topic, [APPROVED], AssignMode.add, topic.values, {APPROVED: 1}))
    assert len(values_of(spans, APPROVED, topic)) == 2

    cleared = await service.assign_attributes(store, OWNER, COLLECTION, clear(many, [APPROVED], {APPROVED: 2}))
    assert cleared.succeeded == [str(APPROVED)] and cleared.values == {APPROVED: []}
    several = await service.assign_attributes(store, OWNER, COLLECTION, clear(topic, [APPROVED], {APPROVED: 3}))
    assert several.succeeded == [str(APPROVED)] and values_of(spans, APPROVED, topic) == []
    assert values_of(spans, APPROVED, many) == []
    # Recorded as any change, previous values with their labels.
    last = (await definitions.read_changes(COLLECTION, APPROVED))[-1]
    assert sorted(v.label for v in last.previous) == ["Author", "Narrator"] and last.current == []
    # Nothing held: already as asked, no write, no conflict for a stale version.
    again = await service.assign_attributes(store, OWNER, COLLECTION, clear(topic, [APPROVED], {APPROVED: 0}))
    assert again.succeeded == [str(APPROVED)] and again.failed == []


async def test_clear_reaches_values_kept_on_rejected_and_inapplicable_annotations(store, spans, definitions):
    person = await define(store, tag_ids=[PERSON])
    author = person.values[0]
    spans.stored[(COLLECTION, REJECTED)] = [codec.encode(person.id, author.id)]  # assigned, then rejected
    spans.stored[(COLLECTION, PLACE_SPAN)] = [codec.encode(person.id, author.id)]  # assigned, then retagged
    # A retired value and an id the attribute no longer defines.
    await service.update_value(store, OWNER, COLLECTION, person.id, author.id, PatchAttributeValue(retired=True))
    gone = uuid4()
    spans.stored[(COLLECTION, APPROVED)] = [codec.encode(person.id, author.id), codec.encode(person.id, gone)]
    await service.update_attribute(store, OWNER, COLLECTION, person.id, PatchAttribute(retired=True))

    result = await service.assign_attributes(store, OWNER, COLLECTION, clear(person, [REJECTED, PLACE_SPAN, APPROVED]))
    assert sorted(result.succeeded) == sorted(str(i) for i in (REJECTED, PLACE_SPAN, APPROVED)) and result.failed == []
    for sid in (REJECTED, PLACE_SPAN, APPROVED):
        assert values_of(spans, sid, person) == []
    # A stale version is still a conflict: clearing never overwrites a newer decision.
    spans.stored[(COLLECTION, APPROVED)] = [codec.encode(person.id, author.id)]
    stale = await service.assign_attributes(store, OWNER, COLLECTION, clear(person, [APPROVED], {APPROVED: 0}))
    assert [f.step for f in stale.failed] == ["edit_conflict"]


async def test_a_failed_read_is_reported_as_such_not_as_a_missing_annotation(store, spans, definitions):
    attribute = await define(store)
    spans.fail_read = WeaviateTimeoutError("slow")
    result = await service.assign_attributes(store, OWNER, COLLECTION,
                                             assign(attribute, [APPROVED], AssignMode.add, [attribute.values[0]]))
    assert [(f.item_id, f.step, f.uncertain) for f in result.failed] == [(str(APPROVED), "read_annotation", True)]
    assert spans.writes == [] and await definitions.read_changes(COLLECTION, APPROVED) == []
    # The annotation is there: once the store answers, the same request saves it.
    spans.fail_read = None
    again = await service.assign_attributes(store, OWNER, COLLECTION,
                                            assign(attribute, [APPROVED], AssignMode.add, [attribute.values[0]]))
    assert again.succeeded == [str(APPROVED)]


async def test_saved_assignments_are_kept_when_their_records_cannot_be_written(store, spans, monkeypatch):
    attribute = await define(store)

    async def broken(*args):
        raise RuntimeError("database is locked")
    monkeypatch.setattr(store.definitions, "record_changes", broken)
    result = await service.assign_attributes(store, OWNER, COLLECTION,
                                             assign(attribute, [APPROVED], AssignMode.add, attribute.values[:1]))
    assert result.succeeded == [str(APPROVED)] and result.outcome.value == "partial"
    assert [(f.step, f.item_id) for f in result.failed] == [("record_attribute_changes", str(APPROVED))]
    assert values_of(spans, APPROVED, attribute) == [str(attribute.values[0].id)]


async def test_one_failed_record_does_not_cost_the_records_of_the_other_annotations(store, spans, definitions,
                                                                                    monkeypatch):
    attribute = await define(store)
    other = uuid4()
    spans.spans[(COLLECTION, other)] = span(other)
    record = definitions.record_changes

    async def fails_for_one(cid, changes):
        if changes[0].annotation_id == APPROVED:
            raise RuntimeError("database is locked")
        await record(cid, changes)
    monkeypatch.setattr(definitions, "record_changes", fails_for_one)
    result = await service.assign_attributes(store, OWNER, COLLECTION,
                                             assign(attribute, [APPROVED, other], AssignMode.add, attribute.values[:1]))

    assert sorted(result.succeeded) == sorted([str(APPROVED), str(other)])
    assert [(f.step, f.item_id) for f in result.failed] == [("record_attribute_changes", str(APPROVED))]
    assert await definitions.read_changes(COLLECTION, APPROVED) == []
    assert len(await definitions.read_changes(COLLECTION, other)) == 1


async def test_consecutive_changes_of_one_annotation_are_recorded_in_order(store, spans, definitions, monkeypatch):
    attribute = await define(store)
    author, narrator = attribute.values
    record = definitions.record_changes
    first = True

    async def slow_first(cid, changes):
        nonlocal first
        if first:
            first = False
            await asyncio.sleep(0.05)
        await record(cid, changes)
    monkeypatch.setattr(definitions, "record_changes", slow_first)
    a = service.assign_attributes(store, OWNER, COLLECTION, assign(attribute, [APPROVED], AssignMode.replace, [author]))
    b = service.assign_attributes(store, OWNER, COLLECTION, assign(attribute, [APPROVED], AssignMode.replace, [narrator],
                                                                   {APPROVED: 1}))
    first_result, second_result = await asyncio.gather(a, b)

    history = await definitions.read_changes(COLLECTION, APPROVED)
    assert (first_result.outcome.value, second_result.outcome.value) == ("complete", "complete")
    assert [(ids(c.previous), ids(c.current)) for c in history] == [([], [author.id]), ([author.id], [narrator.id])]


def ids(values):
    return sorted(v.id for v in values)


def recorded(change):
    return (change.attribute_name, [(v.label, v.kind) for v in change.previous],
            [(v.label, v.kind) for v in change.current])


async def test_history_keeps_the_names_and_labels_of_the_time_after_a_rename(store):
    attribute = await define(store, values=[PostAttributeValue(label="Author"),
                                            PostAttributeValue(label="Unknown", kind=ValueKind.unknown)])
    author, unknown = attribute.values
    await service.assign_attributes(store, OWNER, COLLECTION, assign(attribute, [APPROVED], AssignMode.add, [author]))
    await service.update_attribute(store, OWNER, COLLECTION, attribute.id, PatchAttribute(name="voice"))
    await service.update_value(store, OWNER, COLLECTION, attribute.id, author.id, PatchAttributeValue(label="Writer"))
    renamed = await service.update_value(store, OWNER, COLLECTION, attribute.id, unknown.id,
                                         PatchAttributeValue(label="Not known", retired=True))
    await service.assign_attributes(store, OWNER, COLLECTION,
                                    assign(renamed, [APPROVED], AssignMode.replace, [], {APPROVED: 1}))

    history = await service.read_attribute_changes(store, OWNER, COLLECTION, APPROVED)
    assert [recorded(c) for c in history] == [
        ("speaker_type", [], [("Author", ValueKind.value)]),
        ("voice", [("Writer", ValueKind.value)], [])]
    assert [ids(c.current) for c in history] == [[author.id], []]  # the ids stay the identity


async def test_history_stays_readable_after_the_definitions_are_deleted(store, definitions):
    attribute = await define(store)
    author, narrator = attribute.values
    await service.assign_attributes(store, OWNER, COLLECTION, assign(attribute, [APPROVED], AssignMode.add, [author]))
    await service.assign_attributes(store, OWNER, COLLECTION,
                                    assign(attribute, [APPROVED], AssignMode.replace, [], {APPROVED: 1}))
    await service.delete_value(store, OWNER, COLLECTION, attribute.id, author.id)
    await service.delete_attribute(store, OWNER, COLLECTION, attribute.id)
    assert await definitions.read_all(COLLECTION) == []

    history = await service.read_attribute_changes(store, OWNER, COLLECTION, APPROVED)
    assert [recorded(c) for c in history] == [
        ("speaker_type", [], [("Author", ValueKind.value)]),
        ("speaker_type", [("Author", ValueKind.value)], [])]
    assert [c.attribute_id for c in history] == [attribute.id] * 2


async def test_a_stored_id_without_a_definition_is_recorded_without_a_label(store, spans):
    attribute = await define(store)
    orphan = uuid4()  # e.g. a value deleted between its usage count and its deletion
    spans.stored[(COLLECTION, APPROVED)] = [codec.encode(attribute.id, orphan)]
    await service.assign_attributes(store, OWNER, COLLECTION,
                                    assign(attribute, [APPROVED], AssignMode.replace, attribute.values[:1]))

    [change] = await service.read_attribute_changes(store, OWNER, COLLECTION, APPROVED)
    assert [(v.id, v.label, v.kind) for v in change.previous] == [(orphan, None, None)]
    assert [v.label for v in change.current] == ["Author"]


async def test_a_batch_writes_a_bounded_number_of_annotations_at_a_time(store, spans, monkeypatch):
    attribute = await define(store)
    ids = [uuid4() for _ in range(service.ASSIGN_CONCURRENCY * 3)]
    for sid in ids:
        spans.spans[(COLLECTION, sid)] = span(sid)
    running = peak = 0
    write = spans.write_attributes

    async def counted(*args):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        await write(*args)
        running -= 1
    monkeypatch.setattr(spans, "write_attributes", counted)
    result = await service.assign_attributes(store, OWNER, COLLECTION,
                                             assign(attribute, ids, AssignMode.add, attribute.values[:1]))

    assert len(result.succeeded) == len(ids)
    assert 1 < peak <= service.ASSIGN_CONCURRENCY


async def test_tags_cannot_be_narrowed_while_annotations_hold_values_but_can_be_widened(store, spans):
    attribute = await define(store, tag_ids=[PERSON])
    free = await define(store, name="free")
    await service.assign_attributes(store, OWNER, COLLECTION, assign(attribute, [APPROVED], AssignMode.add,
                                                                    attribute.values[:1]))
    await service.assign_attributes(store, OWNER, COLLECTION, assign(free, [APPROVED], AssignMode.add,
                                                                    free.values[:1], {APPROVED: 1}))
    for narrowed, patch in ((attribute, PatchAttribute(tag_ids=[PLACE])),
                            (free, PatchAttribute(all_tags=False, tag_ids=[PLACE])),
                            # Down to no tag at all, from selected tags and from All tags (#522).
                            (attribute, PatchAttribute(tag_ids=[])), (free, PatchAttribute(all_tags=False))):
        with pytest.raises(InUseError) as used:
            await service.update_attribute(store, OWNER, COLLECTION, narrowed.id, patch)
        assert used.value.affected == 1
    # Values on an annotation whose tag stays applicable do not block narrowing the other tags.
    both = await define(store, name="both", tag_ids=[PERSON, PLACE])
    await service.assign_attributes(store, OWNER, COLLECTION, assign(both, [APPROVED], AssignMode.add,
                                                                    both.values[:1], {APPROVED: 2}))
    kept = await service.update_attribute(store, OWNER, COLLECTION, both.id, PatchAttribute(tag_ids=[PERSON]))
    assert kept.tag_ids == [PERSON]
    everywhere = await service.update_attribute(store, OWNER, COLLECTION, free.id,
                                                PatchAttribute(all_tags=False, tag_ids=[PERSON]))
    assert (everywhere.all_tags, everywhere.tag_ids) == (False, [PERSON])
    with pytest.raises(InUseError):
        await service.update_attribute(store, OWNER, COLLECTION, both.id, PatchAttribute(tag_ids=[PLACE]))
    widened = await service.update_attribute(store, OWNER, COLLECTION, attribute.id,
                                             PatchAttribute(tag_ids=[PERSON, PLACE]))
    assert set(widened.tag_ids) == {PERSON, PLACE}
    to_all = await service.update_attribute(store, OWNER, COLLECTION, attribute.id, PatchAttribute(all_tags=True))
    assert (to_all.all_tags, to_all.tag_ids) == (True, [])

    unused = await define(store, name="unused", tag_ids=[PERSON])
    narrowed = await service.update_attribute(store, OWNER, COLLECTION, unused.id, PatchAttribute(tag_ids=[PLACE]))
    assert narrowed.tag_ids == [PLACE]
    # Removing the last selected tag leaves no tag; it never makes the attribute global.
    emptied = await service.update_attribute(store, OWNER, COLLECTION, unused.id, PatchAttribute(tag_ids=[]))
    assert (emptied.all_tags, emptied.tag_ids) == (False, [])
    assert [(a.all_tags, a.tag_ids) for a in await service.list_attributes(store, OWNER, COLLECTION)
            if a.id == unused.id] == [(False, [])]


async def test_all_tags_selected_tags_and_no_tags_are_distinct(store, definitions):
    everywhere = await define(store, name="everywhere")
    some = await define(store, name="some", tag_ids=[PERSON, PERSON])
    none = await define(store, name="none", tag_ids=[])
    implicit = await service.create_attribute(store, OWNER, COLLECTION, PostAttribute(name="implicit"))
    stored = {a.name: (a.all_tags, a.tag_ids) for a in await definitions.read_all(COLLECTION)}
    assert stored == {"everywhere": (True, []), "some": (False, [PERSON]), "none": (False, []),
                      "implicit": (False, [])}
    assert (everywhere.all_tags, some.all_tags, none.all_tags, implicit.all_tags) == (True, False, False, False)

    # All tags has no selected tags, and an All tags attribute selects tags only explicitly.
    with pytest.raises(ValueError, match="all_tags"):
        PostAttribute(name="both", all_tags=True, tag_ids=[PERSON])
    with pytest.raises(ValueError, match="all_tags"):
        PatchAttribute(all_tags=True, tag_ids=[PERSON])
    with pytest.raises(InvalidRequestError, match="all_tags false"):
        await service.update_attribute(store, OWNER, COLLECTION, everywhere.id, PatchAttribute(tag_ids=[PERSON]))
    # Choosing All tags clears the selected tags; leaving it keeps none selected.
    assert (await service.update_attribute(store, OWNER, COLLECTION, some.id, PatchAttribute(all_tags=True))
            ).model_dump(include={"all_tags", "tag_ids"}) == {"all_tags": True, "tag_ids": []}
    assert (await service.update_attribute(store, OWNER, COLLECTION, some.id, PatchAttribute(all_tags=False))
            ).model_dump(include={"all_tags", "tag_ids"}) == {"all_tags": False, "tag_ids": []}
    # An unchanged scope sent again is no narrowing.
    assert (await service.update_attribute(store, OWNER, COLLECTION, none.id, PatchAttribute(tag_ids=[]))).tag_ids == []


async def test_an_attribute_for_no_tag_takes_no_new_values(store, spans):
    none = await define(store, name="none", tag_ids=[])
    added = await service.assign_attributes(store, OWNER, COLLECTION, assign(none, [APPROVED, PLACE_SPAN],
                                                                            AssignMode.add, none.values[:1]))
    assert added.succeeded == []
    assert {f.step for f in added.failed} == {"check_applicable"}
    replaced = await service.assign_attributes(store, OWNER, COLLECTION, assign(none, [APPROVED], AssignMode.replace,
                                                                               none.values[:1]))
    assert [f.step for f in replaced.failed] == ["check_applicable"]
    assert spans.writes == []
    # Values kept from before (e.g. the tags were narrowed when none were held) can be removed.
    spans.stored[(COLLECTION, APPROVED)] = [codec.encode(none.id, none.values[0].id)]
    removed = await service.assign_attributes(store, OWNER, COLLECTION, assign(none, [APPROVED], AssignMode.remove,
                                                                              none.values[:1]))
    assert removed.succeeded == [str(APPROVED)]
    assert values_of(spans, APPROVED, none) == []


async def test_ai_assisted_assignments_name_a_run_but_are_not_accepted_before_runs_exist(store, definitions):
    attribute = await define(store)
    run = uuid4()
    with pytest.raises(ValueError):
        assign(attribute, [APPROVED], AssignMode.add, attribute.values[:1], source=AssignSource.ai_assisted)
    with pytest.raises(ValueError):
        assign(attribute, [APPROVED], AssignMode.add, attribute.values[:1], run_id=run)
    with pytest.raises(InvalidRequestError, match="#338"):
        await service.assign_attributes(store, OWNER, COLLECTION, assign(
            attribute, [APPROVED], AssignMode.add, attribute.values[:1], source=AssignSource.ai_assisted, run_id=run))
    assert await definitions.read_changes(COLLECTION, APPROVED) == []


async def test_denied_assignments_reach_no_storage_and_values_of_other_attributes_are_not_found(store, spans):
    speaker, topic = await define(store), await define(store, name="topic")
    for user, error in ((OTHER, ResourceNotFound), (None, AuthenticationRequired)):
        with pytest.raises(error):
            await service.assign_attributes(store, user, COLLECTION, assign(speaker, [APPROVED], AssignMode.add,
                                                                            speaker.values[:1]))
    with pytest.raises(NotFoundError, match="Value"):
        await service.assign_attributes(store, OWNER, COLLECTION, assign(speaker, [APPROVED], AssignMode.add,
                                                                        topic.values[:1]))
    # An attribute id of another collection is not found, and so is its collection's data.
    foreign = await service.create_attribute(store, OWNER, SECOND_COLLECTION, attribute_body(name="foreign"))
    with pytest.raises(NotFoundError, match="Attribute"):
        await service.assign_attributes(store, OWNER, COLLECTION, assign(foreign, [APPROVED], AssignMode.add,
                                                                        foreign.values[:1]))
    with pytest.raises(NotFoundError, match="Attribute"):
        await service.assign_attributes(store, OWNER, SECOND_COLLECTION,
                                        assign(speaker, [APPROVED], AssignMode.add, speaker.values[:1]))
    with pytest.raises(ResourceNotFound):
        await service.read_attribute_changes(store, OTHER, COLLECTION, APPROVED)
    assert spans.writes == []


def test_requests_are_validated_before_anything_is_read():
    attribute_id, annotation = uuid4(), uuid4()
    with pytest.raises(ValueError, match="expected_versions"):
        AttributeAssignRequest(attribute_id=attribute_id, annotation_ids=[annotation], expected_versions={},
                               mode=AssignMode.add, value_ids=[uuid4()])
    with pytest.raises(ValueError, match="at least one value"):
        AttributeAssignRequest(attribute_id=attribute_id, annotation_ids=[annotation],
                               expected_versions={annotation: 0}, mode=AssignMode.add)
    with pytest.raises(ValueError):
        AttributeAssignRequest(attribute_id=attribute_id, annotation_ids=[uuid4() for _ in range(201)],
                               expected_versions={}, mode=AssignMode.replace)
    with pytest.raises(ValueError):
        PatchAttribute()
    with pytest.raises(ValueError):
        PatchAttributeValue()


async def test_deleting_the_definitions_of_a_collection_keeps_other_collections(store, definitions):
    mine = await define(store)
    other = await service.create_attribute(store, OWNER, SECOND_COLLECTION, attribute_body())
    await service.assign_attributes(store, OWNER, COLLECTION, assign(mine, [APPROVED], AssignMode.add, mine.values[:1]))

    await definitions.delete_collection(COLLECTION)
    await definitions.delete_collection(COLLECTION)  # safe to repeat
    assert await definitions.read_all(COLLECTION) == [] and await definitions.read_changes(COLLECTION, APPROVED) == []
    assert [a.id for a in await definitions.read_all(SECOND_COLLECTION)] == [other.id]


class _Collections(FakeCollections):
    def __init__(self, fail: Exception | None = None):
        self.deleted: list = []
        self.fail = fail

    async def delete(self, cid):
        if self.fail is not None:
            raise self.fail
        self.deleted.append(cid)


async def test_a_collection_is_deleted_before_its_definitions_and_they_survive_a_failed_deletion(store, definitions):
    from semant_demo.features.user_collections import service as collection_service

    attribute = await define(store)
    await service.assign_attributes(store, OWNER, COLLECTION,
                                    assign(attribute, [APPROVED], AssignMode.add, attribute.values[:1]))
    failing = _Collections(RuntimeError("weaviate is down"))
    with pytest.raises(RuntimeError):
        await collection_service.delete_collection(failing, OWNER, COLLECTION, definitions)
    assert [a.id for a in await definitions.read_all(COLLECTION)] == [attribute.id]
    assert len(await definitions.read_changes(COLLECTION, APPROVED)) == 1

    collections = _Collections()
    await collection_service.delete_collection(collections, OWNER, COLLECTION, definitions)
    assert collections.deleted == [COLLECTION] and await definitions.read_all(COLLECTION) == []


async def test_a_failed_definition_cleanup_after_the_collection_is_gone_is_reported(definitions):
    from semant_demo.core.errors import IncompleteWriteError
    from semant_demo.features.user_collections import service as collection_service

    class Broken:
        async def delete_collection(self, cid):
            raise RuntimeError("database is locked")
    collections = _Collections()
    with pytest.raises(IncompleteWriteError) as error:
        await collection_service.delete_collection(collections, OWNER, COLLECTION, Broken())
    assert error.value.step == "delete_attribute_definitions" and collections.deleted == [COLLECTION]
    assert error.value.completed == {"delete_collection": 1}
    with pytest.raises(AccessDenied):  # a shared user may not delete the collection or its definitions
        await collection_service.delete_collection(collections, SHARED, COLLECTION, definitions)
