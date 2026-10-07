"""The test store is demonstrably isolated: owned by this run, reset per test, cleaned up selectively."""
import pytest

from tests.weaviate_store import (
    MARKER_COLLECTION,
    StoreNotOwned,
    claim_store,
    create_app_schema,
    drop_app_collections,
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
