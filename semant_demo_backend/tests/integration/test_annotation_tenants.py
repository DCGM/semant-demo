"""Annotation tenants against real Weaviate (#327): one tenant per user collection.

Creation of the collection when the chunks are reached through an alias (as in
production), lazy creation (a read never creates a tenant), isolation between tenants, inactive
tenants (activated on access), the recorded tenant use and the idle deactivation, the
collection deletion that removes the tenant (with failures and retry), and a backup and
restore of active and inactive tenants. The migration is in test_annotation_migration.py.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from weaviate.classes.backup import BackupStorage
from weaviate.classes.tenants import Tenant, TenantActivityStatus
from weaviate.collections.tenants.async_ import _TenantsAsync

from semant_demo.adapters.sql.tables import create_tables
from semant_demo.adapters.sql.tenant_activity import TenantActivity
from semant_demo.adapters.weaviate.spans import SpanRepository, create_annotation_collection
from semant_demo.features.annotations.schemas import PostSpan, SpanType
from semant_demo.maintenance.annotation_tenants import deactivate_idle, tenant_status

pytestmark = pytest.mark.integration


@pytest.fixture
def annotations(seeded_store, collection_names):
    return seeded_store.collections.get(collection_names.annotation_collection_name)


async def status_of(annotations, collection_id) -> TenantActivityStatus | None:
    tenant = await annotations.tenants.get_by_name(str(collection_id))
    return tenant.activity_status if tenant else None


async def deactivate(annotations, collection_id) -> None:
    await annotations.tenants.update([Tenant(name=str(collection_id), activity_status=TenantActivityStatus.INACTIVE)])
    assert await status_of(annotations, collection_id) == TenantActivityStatus.INACTIVE


def span_body(ids, chunk, tag, start=0, end=4, type_="pos"):
    return {"chunkId": ids.chunk[chunk], "tagId": ids.tag[tag], "start": start, "end": end, "type": type_}


# ── Collection creation ───────────────────────────────────────────────────

async def test_the_collection_references_the_chunks_also_through_an_alias(seeded_store, collection_names, ids):
    # Production reaches Chunks_test through the alias Chunks; a reference to an alias is refused.
    alias, annotation = "ChunksAlias327", "AnnotationAlias327"
    names = collection_names.model_copy(update={"chunks_collection_name": alias,
                                                "annotation_collection_name": annotation})
    await seeded_store.alias.create(alias_name=alias, target_collection=collection_names.chunks_collection_name)
    try:
        await create_annotation_collection(seeded_store, names)
        config = await seeded_store.collections.get(annotation).config.get()
        assert [(r.name, r.target_collections) for r in config.references] == [
            ("text_chunk", [collection_names.chunks_collection_name])]

        spans = SpanRepository(seeded_store, names)
        notes = UUID(ids.col["outsider_notes"])
        span = PostSpan(chunkId=ids.chunk["gazette_1"], tagId=ids.tag["outsider_tag"], start=0, end=5, type=SpanType.pos)
        span_id = await spans.insert(notes, span, UUID(ids.doc["gazette"]))
        assert [s.id for s in await spans.read_by_collection(notes)] == [str(span_id)]
        assert await spans.count_approved(notes) == 1  # filters through the text_chunk reference
    finally:
        if await seeded_store.collections.exists(annotation):
            await seeded_store.collections.delete(annotation)
        await seeded_store.alias.delete(alias_name=alias)


# ── Lazy creation ─────────────────────────────────────────────────────────

async def test_reads_never_create_a_tenant_and_the_first_write_does(api_client, login, ids, annotations):
    outsider, notes = await login("outsider"), ids.col["outsider_notes"]
    assert await status_of(annotations, notes) is None  # no spans in the fixture corpus

    listed = await api_client.get("/api/tag_spans", headers=outsider, params={"collection_id": notes})
    batch = await api_client.post("/api/tag_spans/batch", headers=outsider,
                                  json={"collection_id": notes, "chunk_ids": [ids.chunk["gazette_1"]]})
    stats = await api_client.get(f"/api/user_collections/{notes}/stats", headers=outsider)
    doc_stats = await api_client.get(f"/api/user_collections/{notes}/documents/{ids.doc['gazette']}/stats",
                                     headers=outsider)

    assert (listed.json(), batch.json()) == ([], {ids.chunk["gazette_1"]: []})
    assert stats.json()["annotations_count"] == 0 and doc_stats.json()["annotations_count"] == 0
    assert await status_of(annotations, notes) is None

    created = await api_client.post("/api/tag_spans", headers=outsider,
                                    json=span_body(ids, "gazette_1", "outsider_tag", 0, 5))

    assert created.status_code == 200 and created.json()["outcome"] == "complete"
    assert await status_of(annotations, notes) == TenantActivityStatus.ACTIVE
    listed = await api_client.get("/api/tag_spans", headers=outsider, params={"collection_id": notes})
    assert [s["id"] for s in listed.json()] == [created.json()["id"]]


async def test_concurrent_first_writes_of_several_workers_share_one_tenant(seeded_store, collection_names, ids,
                                                                           annotations):
    # Separate repositories stand for separate worker processes (no shared tenant cache).
    notes = UUID(ids.col["outsider_notes"])
    repositories = [SpanRepository(seeded_store, collection_names) for _ in range(6)]
    span = PostSpan(chunkId=ids.chunk["gazette_1"], tagId=ids.tag["outsider_tag"], start=0, end=5, type=SpanType.pos)

    created = await asyncio.gather(*(r.insert(notes, span, UUID(ids.doc["gazette"])) for r in repositories))

    assert len(set(created)) == 6
    assert list((await annotations.tenants.get()).keys()).count(str(notes)) == 1
    assert len(await repositories[0].read_by_collection(notes)) == 6


async def test_a_tenant_removed_by_another_worker_is_created_again_by_a_write(seeded_store, collection_names, ids):
    notes = UUID(ids.col["outsider_notes"])
    worker, other = SpanRepository(seeded_store, collection_names), SpanRepository(seeded_store, collection_names)
    span = PostSpan(chunkId=ids.chunk["gazette_1"], tagId=ids.tag["outsider_tag"], start=0, end=5, type=SpanType.pos)
    await worker.insert(notes, span, None)  # the worker now knows the tenant
    await other.remove_tenant(notes)

    span_id = await worker.insert(notes, span, None)

    assert [s.id for s in await other.read_by_collection(notes)] == [str(span_id)]


# ── Isolation ─────────────────────────────────────────────────────────────

async def test_the_same_span_id_in_two_tenants_stays_two_spans(seeded_store, collection_names, ids):
    # Tenants are separate namespaces: a copy with the same id elsewhere is never found here.
    spans = SpanRepository(seeded_store, collection_names)
    chronicles, newspapers = UUID(ids.col["chronicles"]), UUID(ids.col["newspapers"])
    novak = UUID(ids.span["novak_manual"])

    assert (await spans.read(chronicles, novak)).start == 34
    assert await spans.read(newspapers, novak) is None
    assert await spans.read_many(newspapers, [novak, UUID(ids.span["pozar_manual"])]) == {
        UUID(ids.span["pozar_manual"]): await spans.read(newspapers, UUID(ids.span["pozar_manual"]))}


# ── Inactive tenants ──────────────────────────────────────────────────────

async def test_an_inactive_tenant_is_activated_by_reads_and_writes(api_client, login, ids, annotations, store):
    owner, chronicles = await login("owner"), ids.col["chronicles"]
    await deactivate(annotations, chronicles)

    listed = await api_client.get("/api/tag_spans", headers=owner, params={"collection_id": chronicles})

    assert listed.status_code == 200 and len(listed.json()) == 5
    assert await status_of(annotations, chronicles) == TenantActivityStatus.ACTIVE

    await deactivate(annotations, chronicles)
    lhota = ids.span["lhota_automatic"]
    approved = await api_client.patch(f"/api/tag_spans/{lhota}", headers=owner, params={"collection_id": chronicles},
                                      json={"type": "pos"})
    stats = await api_client.get(f"/api/user_collections/{chronicles}/stats", headers=owner)

    assert approved.json()["outcome"] == "complete"
    assert (await store.span(lhota, chronicles))["type"] == "pos"
    assert stats.json()["annotations_count"] == 3  # novak, brno and the approved lhota


async def test_concurrent_requests_activate_an_inactive_tenant_once(api_client, login, ids, annotations):
    owner, chronicles = await login("owner"), ids.col["chronicles"]
    await deactivate(annotations, chronicles)

    responses = await asyncio.gather(*(
        api_client.get("/api/tag_spans", headers=owner, params={"collection_id": chronicles}) for _ in range(8)))

    assert [r.status_code for r in responses] == [200] * 8
    assert all(len(r.json()) == 5 for r in responses)
    assert await status_of(annotations, chronicles) == TenantActivityStatus.ACTIVE


# ── Recorded use and idle deactivation ────────────────────────────────────

@pytest.fixture
async def activity(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'activity.db'}")
    await create_tables(engine)
    clock = {"now": datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)}
    tracker = TenantActivity(async_sessionmaker(engine, expire_on_commit=False), touch_seconds=60,
                             now=lambda: clock["now"])
    tracker.clock = clock
    try:
        yield tracker
    finally:
        await engine.dispose()


async def test_requests_record_the_use_of_their_tenant(api_app, api_client, login, ids):
    owner = await login("owner")
    tracker = api_app.state.resources.tenant_activity
    assert await tracker.last_used() == {}

    await api_client.get("/api/tag_spans", headers=owner, params={"collection_id": ids.col["chronicles"]})
    await api_client.get(f"/api/user_collections/{ids.col['newspapers']}", headers=owner)  # no annotation use

    assert set(await tracker.last_used()) == {ids.col["chronicles"]}


async def test_idle_tenants_are_deactivated_and_used_ones_kept(seeded_store, collection_names, ids, annotations,
                                                                activity):
    spans = SpanRepository(seeded_store, collection_names)
    chronicles, newspapers = ids.col["chronicles"], ids.col["newspapers"]
    gone = str(uuid.uuid4())  # a record of a tenant that no longer exists
    await activity.touch(gone)

    # First run: the tenants have no record yet; they get one now and stay active.
    first = await deactivate_idle(spans, activity, 3600, execute=True)
    assert (first["idle"], first["deactivated"]) == ([], [])
    assert set(await activity.last_used()) == {chronicles, newspapers}

    activity.clock["now"] += timedelta(hours=2)
    await activity.touch(chronicles, force=True)  # chronicles was used recently
    dry = await deactivate_idle(spans, activity, 3600, execute=False)
    assert dry["idle"] == [newspapers] and dry["deactivated"] == []
    assert await status_of(annotations, newspapers) == TenantActivityStatus.ACTIVE

    done = await deactivate_idle(spans, activity, 3600, execute=True)

    assert (done["deactivated"], done["failed"]) == ([newspapers], [])
    assert await status_of(annotations, newspapers) == TenantActivityStatus.INACTIVE
    assert await status_of(annotations, chronicles) == TenantActivityStatus.ACTIVE
    # An inactive tenant keeps its spans and is activated by the next read.
    assert [s.id for s in await spans.read_by_collection(UUID(newspapers))] == [ids.span["pozar_manual"]]
    assert await status_of(annotations, newspapers) == TenantActivityStatus.ACTIVE
    status = {row["tenant"]: row for row in await tenant_status(spans, activity, {chronicles, newspapers})}
    assert not status[chronicles]["orphan"] and status[chronicles]["idle_seconds"] is not None


async def test_a_tenant_used_since_the_listing_is_not_deactivated(seeded_store, collection_names, ids, annotations,
                                                                   activity, monkeypatch):
    spans = SpanRepository(seeded_store, collection_names)
    newspapers = ids.col["newspapers"]
    await deactivate_idle(spans, activity, 3600, execute=True)  # records the tenants
    activity.clock["now"] += timedelta(hours=2)
    original = activity.last_used
    calls = {"n": 0}

    async def used_meanwhile(tenants=None):
        calls["n"] += 1
        if calls["n"] == 3:  # the re-check right before deactivating
            await activity.touch(newspapers, force=True)
        return await original(tenants)
    monkeypatch.setattr(activity, "last_used", used_meanwhile)

    result = await deactivate_idle(spans, activity, 3600, execute=True)

    assert newspapers in result["idle"] and newspapers in result["skipped_in_use"]
    assert newspapers not in result["deactivated"]
    assert await status_of(annotations, newspapers) == TenantActivityStatus.ACTIVE


async def test_a_long_operation_keeps_its_tenant_recorded_as_in_use(activity):
    tenant = str(uuid.uuid4())
    activity.touch_seconds = 0.05
    times = iter(datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc) + timedelta(minutes=m) for m in range(100))
    activity.now = lambda: next(times)

    async with activity.in_use(tenant):
        first = (await activity.last_used([tenant]))[tenant]
        await asyncio.sleep(0.2)
        during = (await activity.last_used([tenant]))[tenant]
    after = (await activity.last_used([tenant]))[tenant]

    assert first < during < after


# ── Collection deletion removes the tenant ────────────────────────────────

async def test_deleting_a_collection_removes_its_tenant_also_when_inactive(api_client, login, ids, annotations, store):
    newspapers = ids.col["newspapers"]
    await deactivate(annotations, newspapers)

    response = await api_client.delete(f"/api/user_collections/{newspapers}", headers=await login("owner"))

    assert response.status_code == 204
    assert await status_of(annotations, newspapers) is None
    # Other tenants are untouched.
    assert await store.span(ids.span["novak_manual"], ids.col["chronicles"]) is not None


@pytest.mark.parametrize("failure", ["raises", "no_effect", "lookup_fails"])
async def test_a_failed_tenant_removal_is_reported_and_a_retry_completes(
        api_client, login, ids, annotations, store, monkeypatch, failure):
    newspapers, owner = ids.col["newspapers"], await login("owner")
    original_remove, original_get = _TenantsAsync.remove, _TenantsAsync.get_by_name

    async def remove(self, tenants):
        if failure == "raises":
            raise RuntimeError("injected tenant removal failure")
        if failure == "lookup_fails":
            return await original_remove(self, tenants)
        return None  # reports success, removes nothing

    async def get_by_name(self, name):
        if failure == "lookup_fails":
            raise RuntimeError("injected tenant lookup failure")
        return await original_get(self, name)

    monkeypatch.setattr(_TenantsAsync, "remove", remove)
    monkeypatch.setattr(_TenantsAsync, "get_by_name", get_by_name)

    response = await api_client.delete(f"/api/user_collections/{newspapers}", headers=owner)

    assert response.status_code == 500
    assert response.json()["step"] == "delete_annotation_tenant"
    assert await store.collection(newspapers) is not None  # never deleted after an unconfirmed removal

    monkeypatch.undo()
    retry = await api_client.delete(f"/api/user_collections/{newspapers}", headers=owner)

    assert retry.status_code == 204
    assert await store.collection(newspapers) is None
    assert await status_of(annotations, newspapers) is None


# ── Backup and restore of active and inactive tenants ─────────────────────

async def test_backup_and_restore_keep_active_and_inactive_tenants(
        api_client, login, ids, seeded_store, collection_names, annotations, store):
    """Rehearsal on the test Weaviate (same version as deployed): a filesystem backup of the
    annotation collection restores every tenant with its spans and its activity status."""
    chronicles, newspapers = ids.col["chronicles"], ids.col["newspapers"]
    await deactivate(annotations, newspapers)
    counts_before = {t: (await annotations.with_tenant(t).aggregate.over_all(total_count=True)).total_count
                     for t in (chronicles,)}
    backup_id = f"tenants-{uuid.uuid4().hex[:12]}"

    backup = await seeded_store.backup.create(backup_id=backup_id, backend=BackupStorage.FILESYSTEM,
                                              include_collections=[collection_names.annotation_collection_name],
                                              wait_for_completion=True)
    assert backup.status.value == "SUCCESS"
    # The backup neither activated the inactive tenant nor changed the active one.
    assert await status_of(annotations, newspapers) == TenantActivityStatus.INACTIVE

    await seeded_store.collections.delete(collection_names.annotation_collection_name)
    restored = await seeded_store.backup.restore(backup_id=backup_id, backend=BackupStorage.FILESYSTEM,
                                                 include_collections=[collection_names.annotation_collection_name],
                                                 wait_for_completion=True)

    assert restored.status.value == "SUCCESS"
    assert await status_of(annotations, chronicles) == TenantActivityStatus.ACTIVE
    assert await status_of(annotations, newspapers) == TenantActivityStatus.INACTIVE
    assert (await annotations.with_tenant(chronicles).aggregate.over_all(total_count=True)).total_count == \
        counts_before[chronicles]
    owner = await login("owner")
    listed = await api_client.get("/api/tag_spans", headers=owner, params={"collection_id": newspapers})
    assert [s["id"] for s in listed.json()] == [ids.span["pozar_manual"]]
    assert (await store.span(ids.span["novak_manual"], chronicles))["start"] == 34
