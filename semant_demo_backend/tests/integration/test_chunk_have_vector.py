"""Listing the stored named vector in ``Chunks.haveVector`` against the real test store (#805).

The seeded chunks store both named vectors (``default`` and ``SECOND_VECTOR``) and list them, as
the deployed chunks do since #805 (#816); the test clears their lists, as before the backfill,
adds a chunk storing only the second vector, checks, writes and checks again. Declaring the
property is tested on a collection of its own, since the seeded ``Chunks`` declares it.
"""
import json
from uuid import UUID

import pytest
from weaviate.classes.config import Configure, DataType, Property
from weaviate.classes.data import DataObject
from weaviate.classes.query import QueryReference

from semant_demo.adapters.weaviate import have_vector as store
from semant_demo.maintenance import chunk_have_vector
from tests.fakes import SECOND_EMBEDDING_DIM, SECOND_VECTOR, fake_embedding

pytestmark = pytest.mark.integration

ONLY_SECOND = UUID("5e3a0000-0000-4000-8000-0000000ce101")


def quiet(line: str) -> None:
    pass


async def test_check_write_and_check_again(seeded_store, collection_names, corpus, tmp_path):
    names = collection_names
    chunks = seeded_store.collections.get(names.chunks_collection_name)
    inserted = await chunks.data.insert_many([DataObject(
        uuid=ONLY_SECOND, properties={"text": "Jen druhý vektor"}, vector={SECOND_VECTOR: fake_embedding("second", SECOND_EMBEDDING_DIM)})])
    assert not inserted.errors
    for chunk in corpus.chunks.values():  # the seeded store as before the backfill
        await chunks.data.update(uuid=chunk["id"], properties={store.PROPERTY: None})
    seeded = len(corpus.chunks)
    sample = corpus.chunks["letters_1"]["id"]
    before = await chunks.query.fetch_object_by_id(sample, include_vector=True,
                                                   return_references=QueryReference(link_on="document"))

    def run(checkpoint: str, write: bool):
        return chunk_have_vector.run(seeded_store, names, checkpoint=tmp_path / checkpoint, endpoint="test",
                                     write=write, vector="default", progress=quiet)

    check = await run("check.json", False)
    assert check["counts"] == {"examined": seeded + 1, "consistent": 0, "set": seeded, "no_vector": 1,
                               "listed_without_vector": 0, "written": 0}
    assert check["property"] == vars(store.EXPECTED)
    assert chunk_have_vector.exit_code(check) == 1
    with pytest.raises(LookupError):  # a check checkpoint is not resumed as a write
        await run("check.json", True)

    written = await run("write.json", True)
    assert written["property_added"] is None and written["property"] == vars(store.EXPECTED)
    assert written["counts"]["written"] == seeded and written["to_retry"] == 0
    assert written["search_counts"] == {
        "expected_listed": seeded, "expected_not_listed": 1, "expected_all": seeded + 1,
        "listed": seeded, "not_listed": 1, "all": seeded + 1, "match": True, "attempts": 1}
    assert chunk_have_vector.exit_code(written) == 0
    manifest = [json.loads(line) for line in (tmp_path / "write.json.manifest.jsonl").read_text().splitlines()]
    assert manifest == [{"id": str(ONLY_SECOND), "status": "no_vector", "listed": None}]

    after = await chunks.query.fetch_object_by_id(sample, include_vector=True,
                                                  return_references=QueryReference(link_on="document"))
    assert after.properties.pop(store.PROPERTY) == ["default"] and before.properties.pop(store.PROPERTY) is None
    assert after.properties == before.properties and after.vector == before.vector
    assert ({o.uuid for o in after.references["document"].objects}
            == {o.uuid for o in before.references["document"].objects})
    only_second = await chunks.query.fetch_object_by_id(ONLY_SECOND)
    assert only_second.properties.get(store.PROPERTY) is None

    await chunks.data.update(uuid=ONLY_SECOND, properties={store.PROPERTY: ["default"]})  # a wrong claim
    await chunks.data.update(uuid=sample, properties={store.PROPERTY: [SECOND_VECTOR]})  # another name kept
    again = await run("again.json", True)
    assert again["counts"] == {"examined": seeded + 1, "consistent": seeded - 1, "set": 1, "no_vector": 0,
                                    "listed_without_vector": 1, "written": 1}
    assert again["search_counts"]["match"] and chunk_have_vector.exit_code(again) == 1
    stored = await chunks.query.fetch_object_by_id(sample)
    assert sorted(stored.properties[store.PROPERTY]) == sorted(["default", SECOND_VECTOR])


async def own_chunks(client, collection_names, name: str, *properties: Property):
    """Names whose chunks collection is ``name``, created with a ``default`` vector and one chunk storing it."""
    await client.collections.create(name, properties=[Property(name="text", data_type=DataType.TEXT), *properties],
                                    vector_config=Configure.Vectors.self_provided(name="default"))
    await client.collections.get(name).data.insert({"text": "úsek"}, vector={"default": fake_embedding("úsek")})
    return collection_names.model_copy(update={"chunks_collection_name": name})


async def test_a_write_declares_a_missing_property(seeded_store, collection_names, tmp_path):
    names = await own_chunks(seeded_store, collection_names, "HaveVectorUndeclared")
    try:
        written = await chunk_have_vector.run(seeded_store, names, checkpoint=tmp_path / "w.json", endpoint="test",
                                              write=True, vector="default", progress=quiet)
        assert written["property_added"] and written["property"] == vars(store.EXPECTED)
        assert written["counts"]["written"] == 1 and chunk_have_vector.exit_code(written) == 0
    finally:
        await seeded_store.collections.delete("HaveVectorUndeclared")


async def test_refuses_a_missing_vector_or_another_declaration(seeded_store, collection_names, tmp_path):
    with pytest.raises(LookupError, match="no named vector"):
        await chunk_have_vector.run(seeded_store, collection_names, checkpoint=tmp_path / "x.json", endpoint="test",
                                    write=True, vector="Missing", progress=quiet)
    assert not (tmp_path / "x.json").exists()
    names = await own_chunks(seeded_store, collection_names, "HaveVectorOtherwise",
                             Property(name=store.PROPERTY, data_type=DataType.TEXT))
    try:
        with pytest.raises(LookupError, match="declared as"):
            await chunk_have_vector.run(seeded_store, names, checkpoint=tmp_path / "y.json", endpoint="test",
                                        write=True, vector="default", progress=quiet)
    finally:
        await seeded_store.collections.delete("HaveVectorOtherwise")
