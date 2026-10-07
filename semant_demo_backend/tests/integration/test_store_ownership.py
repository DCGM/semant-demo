"""The test store is demonstrably isolated: owned, reset per test, cleaned up selectively."""
import pytest

from tests.weaviate_store import (
    MARKER_COLLECTION,
    StoreNotOwned,
    claim_store,
    create_app_schema,
    drop_app_collections,
)

pytestmark = pytest.mark.integration


async def test_instance_carries_ownership_marker(weaviate_client):
    await claim_store(weaviate_client)

    assert await weaviate_client.collections.exists(MARKER_COLLECTION)


async def test_cleanup_drops_only_application_collections(weaviate_client, collection_names):
    await drop_app_collections(weaviate_client, collection_names)
    await create_app_schema(weaviate_client, collection_names)
    await weaviate_client.collections.create("UnrelatedProbe")
    try:
        await drop_app_collections(weaviate_client, collection_names)

        remaining = set((await weaviate_client.collections.list_all(simple=True)).keys())
        assert remaining == {MARKER_COLLECTION, "UnrelatedProbe"}
    finally:
        await weaviate_client.collections.delete("UnrelatedProbe")


async def test_marker_without_ownership_record_is_refused(weaviate_client):
    marker = weaviate_client.collections.get(MARKER_COLLECTION)
    await claim_store(weaviate_client)
    records = (await marker.query.fetch_objects(limit=10)).objects
    for record in records:
        await marker.data.delete_by_id(record.uuid)
    try:
        with pytest.raises(StoreNotOwned):
            await claim_store(weaviate_client)
    finally:
        for record in records:
            await marker.data.insert(record.properties, uuid=record.uuid)


async def test_seeded_store_holds_only_the_fixture_corpus(seeded_store, collection_names, corpus):
    chunks = seeded_store.collections.get(collection_names.chunks_collection_name)

    total = (await chunks.aggregate.over_all(total_count=True)).total_count

    assert total == len(corpus.chunks)
