"""The test store is demonstrably isolated: owned by this run, reset per test, cleaned up selectively."""
import pytest
from weaviate.collections.classes.batch import DeleteManyReturn
from weaviate.collections.data.async_ import _DataCollectionAsync

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

    for name in _app_collections_in_drop_order(collection_names):
        total = (await seeded_store.collections.get(name).aggregate.over_all(total_count=True)).total_count
        assert total == 0, name
    after = (await seeded_store.collections.list_all(simple=False))[collection_names.chunks_collection_name]
    assert after == before


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
