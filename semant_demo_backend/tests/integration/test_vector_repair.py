"""Integration check: a vector-only partial update preserves chunk data (#375)."""
import pytest
from weaviate.classes.query import QueryReference

from semant_demo.maintenance.vector_repair import _self_hit

pytestmark = pytest.mark.integration


async def test_rewriting_existing_named_vector_preserves_properties_and_references(
        seeded_store, collection_names, corpus):
    collection = seeded_store.collections.get(collection_names.chunks_collection_name)
    uuid = corpus.chunks["letters_1"]["id"]
    kwargs = dict(include_vector=True,
                  return_references=[QueryReference(link_on="document", return_properties=[])])
    before = await collection.query.fetch_object_by_id(uuid, **kwargs)
    assert before is not None and "default" in before.vector
    assert await _self_hit(collection, before, "default")

    # Same update operation as the temporary repair, on test-owned data only.
    await collection.data.update(uuid=before.uuid, vector={"default": before.vector["default"]})
    after = await collection.query.fetch_object_by_id(uuid, **kwargs)
    assert after.properties == before.properties
    assert after.vector == before.vector
    assert [x.uuid for x in after.references["document"].objects] == [
        x.uuid for x in before.references["document"].objects]
