"""Annotation migration and tenant commands without Weaviate (#327).

Validation of legacy spans, record comparison, the refusals of the command line before
it connects anywhere, and the throttled tenant activity record. Storage behavior is in
tests/integration/test_annotation_migration.py and test_annotation_tenants.py.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from semant_demo.adapters.sql.tables import create_tables
from semant_demo.adapters.sql.tenant_activity import TenantActivity
from semant_demo.adapters.weaviate.annotation_migration import LegacySpan, SourceChunk, TargetSpan
from semant_demo.maintenance import annotation_migration as migration
from semant_demo.maintenance import annotation_tenants

COLLECTION, OTHER, DOCUMENT = uuid4(), uuid4(), uuid4()
TAG, CHUNK = uuid4(), uuid4()


def lookups(tag_owners=None, collections=None):
    found = migration.Lookups(store=None)
    found.tag_owners = {TAG: [COLLECTION]} if tag_owners is None else tag_owners
    found.collections = {COLLECTION: True} if collections is None else collections
    return found


def legacy(tags=(TAG,), chunks=(CHUNK,), **properties) -> LegacySpan:
    return LegacySpan(uuid4(), {"start": 0, "end": 3, "type": "pos", **properties}, list(tags), list(chunks))


CHUNKS = {CHUNK: SourceChunk(CHUNK, [DOCUMENT], [COLLECTION])}


def test_a_valid_span_goes_to_its_tags_collection_with_its_document():
    assert migration.classify(legacy(), lookups(), CHUNKS) == (None, COLLECTION, DOCUMENT)


@pytest.mark.parametrize("span, found, chunks, reason", [
    (legacy(type="maybe"), lookups(), CHUNKS, "invalid_type"),
    (legacy(type=None), lookups(), CHUNKS, "invalid_type"),
    (legacy(start=3, end=3), lookups(), CHUNKS, "invalid_offsets"),
    (legacy(start=-1), lookups(), CHUNKS, "invalid_offsets"),
    (legacy(start=True), lookups(), CHUNKS, "invalid_offsets"),
    (legacy(end=None), lookups(), CHUNKS, "invalid_offsets"),
    (legacy(tags=()), lookups(), CHUNKS, "no_tag_reference"),
    (legacy(tags=(TAG, uuid4())), lookups(), CHUNKS, "several_tag_references"),
    (legacy(), lookups(tag_owners={}), CHUNKS, "tag_missing"),
    (legacy(), lookups(tag_owners={TAG: []}), CHUNKS, "tag_without_collection"),
    (legacy(), lookups(tag_owners={TAG: [COLLECTION, OTHER]}), CHUNKS, "tag_in_several_collections"),
    (legacy(), lookups(collections={COLLECTION: False}), CHUNKS, "collection_missing"),
    (legacy(chunks=()), lookups(), CHUNKS, "no_chunk_reference"),
    (legacy(chunks=(CHUNK, uuid4())), lookups(), CHUNKS, "several_chunk_references"),
    (legacy(), lookups(), {}, "chunk_missing"),
    (legacy(), lookups(), {CHUNK: SourceChunk(CHUNK, [], [COLLECTION])}, "chunk_without_document"),
], ids=lambda v: v if isinstance(v, str) else "")
def test_invalid_spans_are_skipped_with_their_reason_never_guessed(span, found, chunks, reason):
    assert migration.classify(span, found, chunks) == (reason, None, None)


def test_the_same_collection_twice_is_one_owner():
    assert migration.classify(legacy(), lookups(tag_owners={TAG: [COLLECTION, COLLECTION]}), CHUNKS)[1] == COLLECTION


def test_the_copy_keeps_offsets_type_and_ai_metadata():
    span = legacy(type="auto", reason="Název obce.", confidence=1)

    properties = migration.target_properties(span, DOCUMENT)

    assert properties == {"tagId": TAG, "chunkId": CHUNK, "documentId": DOCUMENT, "start": 0, "end": 3,
                          "type": "auto", "reason": "Název obce.", "confidence": 1.0}
    stored = TargetSpan(span.id, {**{k: str(v) if k.endswith("Id") else v for k, v in properties.items()}})
    assert migration.same_record(properties, stored)
    assert not migration.same_record(properties, TargetSpan(span.id, {**stored.properties, "type": "pos"}))
    assert not migration.same_record(properties, TargetSpan(span.id, {**stored.properties, "reason": None}))


def test_tag_inventory_lists_tags_without_exactly_one_collection():
    orphan, double = uuid4(), uuid4()
    inventory = migration.tag_inventory({TAG: [COLLECTION], orphan: [], double: [COLLECTION, OTHER]})

    assert inventory == {"total": 3, "single_collection": 1, "without_collection": [str(orphan)],
                         "several_collections": [str(double)]}


# ── Command line refusals (before connecting) ────────────────────────────

@pytest.fixture
def endpoint(monkeypatch):
    monkeypatch.setenv("WEAVIATE_HOST", "localhost")
    monkeypatch.setenv("WEAVIATE_REST_PORT", "8080")

    async def no_connection(*args, **kwargs):
        raise AssertionError("must refuse before connecting")
    monkeypatch.setattr("semant_demo.adapters.weaviate.client.connect_weaviate", no_connection)
    return "localhost:8080"


@pytest.mark.parametrize("extra", [[], ["--confirm-endpoint", "elsewhere:8080", "--backup-id", "b"],
                                   ["--confirm-endpoint", "localhost:8080"],
                                   ["--confirm-endpoint", "localhost:8080", "--offline-backup", " "]],
                         ids=["no-confirmation", "other-endpoint", "no-backup", "blank-offline-backup"])
async def test_backfill_execute_refuses_without_confirmed_endpoint_and_backup(endpoint, tmp_path, extra):
    args = ["backfill", "--state", str(tmp_path / "s.json"), "--execute", *extra]
    assert await migration._main(args) == 2


def test_a_backup_id_and_an_offline_backup_exclude_each_other(endpoint, tmp_path):
    with pytest.raises(SystemExit):
        migration._parser().parse_args(["backfill", "--state", "s", "--execute", "--backup-id", "b",
                                        "--offline-backup", "/copy"])


async def test_backfill_refuses_a_non_positive_batch(endpoint, tmp_path):
    assert await migration._main(["backfill", "--state", str(tmp_path / "s.json"), "--batch-size", "0"]) == 2


@pytest.mark.parametrize("env, args", [
    ({}, ["deactivate-idle", "--execute", "--confirm-endpoint", "localhost:8080"]),
    ({"ANNOTATION_TENANT_DEACTIVATION_ENABLED": "true"}, ["deactivate-idle", "--execute"]),
    ({"ANNOTATION_TENANT_DEACTIVATION_ENABLED": "true"}, ["deactivate-idle", "--idle-seconds", "100"]),
], ids=["disabled", "unconfirmed-endpoint", "idle-shorter-than-3-touches"])
async def test_tenant_deactivation_refuses_unless_enabled_confirmed_and_long_enough(endpoint, monkeypatch, env, args):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert await annotation_tenants._main(args) == 2


# ── Tenant activity record ───────────────────────────────────────────────

@pytest.fixture
async def activity(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'a.db'}")
    await create_tables(engine)
    clock = {"now": datetime(2026, 10, 18, tzinfo=timezone.utc)}
    tracker = TenantActivity(async_sessionmaker(engine, expire_on_commit=False), 60, now=lambda: clock["now"])
    yield tracker, clock
    await engine.dispose()


async def test_touches_are_throttled_per_process_unless_forced(activity):
    tracker, clock = activity
    tenant = str(uuid4())
    await tracker.touch(tenant)
    first = (await tracker.last_used())[tenant]

    clock["now"] += timedelta(seconds=30)
    await tracker.touch(tenant)  # within touch_seconds: not written
    assert (await tracker.last_used())[tenant] == first

    await tracker.touch(tenant, force=True)
    assert (await tracker.last_used())[tenant] == first + timedelta(seconds=30)


async def test_a_failed_record_never_fails_the_request(activity, monkeypatch):
    tracker, _ = activity

    def broken():
        raise ConnectionError("database down")
    monkeypatch.setattr(tracker, "session_maker", broken)

    await tracker.touch(uuid4())  # logged, not raised


async def test_unseen_tenants_get_a_record_and_known_ones_keep_theirs(activity):
    tracker, clock = activity
    known, unseen = str(uuid4()), str(uuid4())
    await tracker.touch(known)
    clock["now"] += timedelta(hours=1)

    await tracker.record_unseen([known, unseen])
    await tracker.forget([])

    last = await tracker.last_used()
    assert (last[known], last[unseen]) == (clock["now"] - timedelta(hours=1), clock["now"])
    await tracker.forget([known])
    assert set(await tracker.last_used()) == {unseen}


def test_touch_seconds_must_be_positive():
    with pytest.raises(ValueError):
        TenantActivity(async_sessionmaker(), 0)
