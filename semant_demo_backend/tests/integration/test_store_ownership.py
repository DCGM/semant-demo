"""The test store is demonstrably isolated: owned by this run, reset per test, cleaned up selectively."""
from uuid import uuid4

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine
from weaviate.classes.tenants import Tenant, TenantActivityStatus
from weaviate.collections.classes.batch import DeleteManyReturn
from weaviate.collections.data.async_ import _DataCollectionAsync

from tests.seed import annotation_tenants, seed_weaviate
from tests.weaviate_store import (
    MARKER_COLLECTION,
    StoreNotOwned,
    _app_collections_in_drop_order,
    claim_store,
    create_app_schema,
    drop_app_collections,
    reset_app_collections,
)

pytestmark = pytest.mark.integration


async def test_instance_marker_holds_this_runs_token(weaviate_client, store_token):
    await claim_store(weaviate_client, store_token)

    marker = weaviate_client.collections.get(MARKER_COLLECTION)
    records = (await marker.query.fetch_objects(limit=10)).objects
    assert [r.properties["token"] for r in records] == [store_token]


async def test_other_run_token_is_refused(weaviate_client, store_token, collection_names):
    await claim_store(weaviate_client, store_token)

    with pytest.raises(StoreNotOwned):
        await claim_store(weaviate_client, f"{store_token}-other-run")
    with pytest.raises(StoreNotOwned):
        await drop_app_collections(weaviate_client, collection_names, f"{store_token}-other-run")


async def test_cleanup_drops_only_application_collections(weaviate_client, collection_names, store_token):
    await drop_app_collections(weaviate_client, collection_names, store_token)
    await create_app_schema(weaviate_client, collection_names)
    await weaviate_client.collections.create("UnrelatedProbe")
    try:
        await drop_app_collections(weaviate_client, collection_names, store_token)

        remaining = set((await weaviate_client.collections.list_all(simple=True)).keys())
        assert remaining == {MARKER_COLLECTION, "UnrelatedProbe"}
    finally:
        await weaviate_client.collections.delete("UnrelatedProbe")


async def test_marker_without_ownership_record_is_refused(weaviate_client, store_token):
    marker = weaviate_client.collections.get(MARKER_COLLECTION)
    await claim_store(weaviate_client, store_token)
    records = (await marker.query.fetch_objects(limit=10)).objects
    for record in records:
        await marker.data.delete_by_id(record.uuid)
    try:
        with pytest.raises(StoreNotOwned):
            await claim_store(weaviate_client, store_token)
    finally:
        for record in records:
            await marker.data.insert(record.properties, uuid=record.uuid)


async def test_seeded_store_holds_only_the_fixture_corpus(seeded_store, collection_names, corpus):
    chunks = seeded_store.collections.get(collection_names.chunks_collection_name)

    total = (await chunks.aggregate.over_all(total_count=True)).total_count

    assert total == len(corpus.chunks)


async def test_reset_empties_collections_without_recreating_them(
        seeded_store, collection_names, store_token, created_app_schema):
    chunks = seeded_store.collections.get(collection_names.chunks_collection_name)
    await chunks.data.insert({"text": "left behind by a test"})
    before = (await seeded_store.collections.list_all(simple=False))[collection_names.chunks_collection_name]

    await reset_app_collections(seeded_store, collection_names, store_token, created_app_schema)

    annotations, *others = _app_collections_in_drop_order(collection_names)
    # The multi-tenant annotations are emptied by removing their tenants.
    assert await seeded_store.collections.get(annotations).tenants.get() == {}
    for name in others:
        total = (await seeded_store.collections.get(name).aggregate.over_all(total_count=True)).total_count
        assert total == 0, name
    after = (await seeded_store.collections.list_all(simple=False))[collection_names.chunks_collection_name]
    assert after == before


async def test_reset_empties_kept_corpus_tenants_and_removes_the_others(
        seeded_store, collection_names, store_token, created_app_schema, corpus):
    annotations = seeded_store.collections.get(collection_names.annotation_collection_name)
    corpus_tenants = annotation_tenants(corpus)
    written, deactivated = sorted(corpus_tenants)[:2]
    await annotations.with_tenant(written).data.insert({"start": 0, "end": 1, "type": "left behind"})
    await annotations.tenants.update([Tenant(name=deactivated, activity_status=TenantActivityStatus.INACTIVE)])
    await annotations.tenants.create([Tenant(name=str(uuid4()))])

    await reset_app_collections(seeded_store, collection_names, store_token, created_app_schema,
                                keep_tenants=corpus_tenants)

    # Only active corpus tenants are kept, and they are empty.
    kept = await annotations.tenants.get()
    assert set(kept) == corpus_tenants - {deactivated}
    for name in kept:
        assert (await annotations.with_tenant(name).aggregate.over_all(total_count=True)).total_count == 0, name

    await seed_weaviate(seeded_store, collection_names, corpus, store_token)

    # The next test sees exactly the seeded spans, in active tenants.
    tenants = await annotations.tenants.get()
    assert set(tenants) == corpus_tenants
    assert all(t.activity_status == TenantActivityStatus.ACTIVE for t in tenants.values())
    stored = set()
    for name in tenants:
        stored |= {str(o.uuid) for o in (await annotations.with_tenant(name).query.fetch_objects(limit=1000)).objects}
    assert stored == {span["id"] for span in corpus.spans.values()}


async def test_each_app_gets_its_own_copy_of_the_seeded_users_database(api_app, seeded_users_db, corpus):
    database = make_url(api_app.state.config.SQL_DB_URL).database
    assert database != str(seeded_users_db)

    engine = create_async_engine(api_app.state.config.SQL_DB_URL)
    template = create_async_engine(f"sqlite+aiosqlite:///{seeded_users_db}")
    try:
        async with engine.begin() as conn:
            await conn.execute(text('DELETE FROM "user"'))
        async with template.connect() as conn:
            remaining = (await conn.execute(text('SELECT count(*) FROM "user"'))).scalar_one()
    finally:
        await engine.dispose()
        await template.dispose()

    assert remaining == len(corpus.users)


async def test_reset_recreates_a_changed_schema(seeded_store, collection_names, store_token, created_app_schema):
    tags = seeded_store.collections.get(collection_names.tag_collection_name)
    # Auto-schema adds properties on insert, so a test can change the schema implicitly.
    await tags.data.insert({"tag_name": "x", "unexpected": "auto-schema property"})

    await reset_app_collections(seeded_store, collection_names, store_token, created_app_schema)

    properties = {p.name for p in (await tags.config.get()).properties}
    assert "unexpected" not in properties
    assert (await tags.aggregate.over_all(total_count=True)).total_count == 0


async def test_reset_refuses_another_runs_store(seeded_store, collection_names, store_token, created_app_schema):
    with pytest.raises(StoreNotOwned):
        await reset_app_collections(seeded_store, collection_names, f"{store_token}-other-run", created_app_schema)

    chunks = seeded_store.collections.get(collection_names.chunks_collection_name)
    assert (await chunks.aggregate.over_all(total_count=True)).total_count > 0


@pytest.fixture
def fake_delete_many(monkeypatch, collection_names):
    """Replace ``delete_many`` on the Chunks collection with ``fake(original, self, where)``.

    Fails the test after ``max_calls`` calls, so a reset that keeps retrying cannot hang
    the suite.
    """
    original = _DataCollectionAsync.delete_many

    def install(fake, max_calls=5):
        calls = []

        async def wrapper(self, where, **kwargs):
            if self.name != collection_names.chunks_collection_name:
                return await original(self, where, **kwargs)
            calls.append(where)
            assert len(calls) <= max_calls, "reset kept calling delete_many without stopping"
            return await fake(original, self, where)

        monkeypatch.setattr(_DataCollectionAsync, "delete_many", wrapper)
        return calls
    return install


@pytest.mark.parametrize("failed, successful", [(2, 1), (3, 0)], ids=["some-failed", "all-failed"])
async def test_reset_fails_when_deletions_fail(
        seeded_store, collection_names, store_token, created_app_schema, fake_delete_many, failed, successful):
    async def failing(original, self, where):
        return DeleteManyReturn(failed=failed, matches=failed + successful, objects=None, successful=successful)
    calls = fake_delete_many(failing)

    with pytest.raises(RuntimeError, match="deletions failed"):
        await reset_app_collections(seeded_store, collection_names, store_token, created_app_schema)
    assert len(calls) == 1


async def test_reset_fails_when_deletion_makes_no_progress(
        seeded_store, collection_names, store_token, created_app_schema, fake_delete_many):
    async def stuck(original, self, where):
        return DeleteManyReturn(failed=0, matches=3, objects=None, successful=0)
    calls = fake_delete_many(stuck)

    with pytest.raises(RuntimeError, match="no progress"):
        await reset_app_collections(seeded_store, collection_names, store_token, created_app_schema)
    assert len(calls) == 1


async def test_reset_repeats_partial_batches_until_empty(
        seeded_store, collection_names, store_token, created_app_schema, fake_delete_many, corpus):
    chunks = seeded_store.collections.get(collection_names.chunks_collection_name)

    async def one_per_batch(original, self, where):
        # Like a server whose QUERY_MAXIMUM_RESULTS is 1: one object deleted per call.
        objects = (await chunks.query.fetch_objects(limit=1)).objects
        if not objects:
            return await original(self, where)
        await chunks.data.delete_by_id(objects[0].uuid)
        total = (await chunks.aggregate.over_all(total_count=True)).total_count
        return DeleteManyReturn(failed=0, matches=total + 1, objects=None, successful=1)

    calls = fake_delete_many(one_per_batch, max_calls=len(corpus.chunks) + 1)

    await reset_app_collections(seeded_store, collection_names, store_token, created_app_schema)

    assert (await chunks.aggregate.over_all(total_count=True)).total_count == 0
    assert len(calls) == len(corpus.chunks) + 1


async def test_the_local_development_reset_refuses_a_test_store(seeded_store, weaviate_client, collection_names,
                                                                corpus, tmp_path, monkeypatch):
    """The persistent development tooling (#438) never drops a store it did not create."""
    from tests import local_dev

    class Unclosed:
        collections = weaviate_client.collections

        async def close(self):
            pass

    async def connect(profile):
        return Unclosed()

    monkeypatch.setattr(local_dev, "connect", connect)
    before = set((await weaviate_client.collections.list_all(simple=True)).keys())

    with pytest.raises(local_dev.Refused, match="without the local development marker"):
        await local_dev.cmd_reset(local_dev.Profile(data_dir=tmp_path), yes=True)

    assert set((await weaviate_client.collections.list_all(simple=True)).keys()) == before
    chunks = weaviate_client.collections.get(collection_names.chunks_collection_name)
    assert (await chunks.aggregate.over_all(total_count=True)).total_count == len(corpus.chunks)
