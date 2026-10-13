"""Copying the document year to the chunks against the real test store (#153).

The fixture corpus: chronicle (1851, chunks chronicle_1-3), letters (1902, letters_1-2),
gazette (no year, gazette_1-2); the seeded chunks store their document's year. The tests
change document years, add chunks without a single document and check, write and check again.
"""
import json
from uuid import UUID

import pytest
from weaviate.classes.config import DataType, Property, ReferenceProperty
from weaviate.classes.data import DataObject
from weaviate.classes.query import QueryReference

from semant_demo.adapters.weaviate import chunk_year as store
from semant_demo.adapters.weaviate.search import ChunkSearchRepository
from semant_demo.features.search.schemas import ChunkQuery, FieldCondition, Op, SearchType
from semant_demo.maintenance import chunk_year
from tests.fakes import fake_embedding

pytestmark = pytest.mark.integration

ORPHAN, TWO_DOCUMENTS = (UUID(f"5e3a0000-0000-4000-8000-0000000ce00{n}") for n in range(1, 3))
ALL_WORDS = "Novák Požár Prahy rodinu Slavia trh"


def quiet(line: str) -> None:
    pass


async def found(client, names, keys, first: int, last: int) -> set[str]:
    hits = await ChunkSearchRepository(client, names).search(ChunkQuery(
        text=ALL_WORDS, mode=SearchType.text, limit=50,
        conditions=(FieldCondition("yearIssued", Op.greater_or_equal, first),
                    FieldCondition("yearIssued", Op.less_or_equal, last))))
    return {keys[str(h.id)] for h in hits}


async def test_check_write_and_check_again(seeded_store, collection_names, corpus, tmp_path):
    names, d = collection_names, {k: v["id"] for k, v in corpus.documents.items()}
    keys = {c["id"]: k for k, c in corpus.chunks.items()}
    documents = seeded_store.collections.get(names.document_collection_name)
    chunks = seeded_store.collections.get(names.chunks_collection_name)
    await documents.data.update(uuid=d["letters"], properties={"yearIssued": 1903})   # corrected
    await documents.data.update(uuid=d["chronicle"], properties={"yearIssued": None})  # removed
    await documents.data.update(uuid=d["gazette"], properties={"yearIssued": 1899})    # added
    inserted = await chunks.data.insert_many([
        DataObject(uuid=ORPHAN, properties={"text": "Bez dokumentu", "yearIssued": 1700}, vector={"default": fake_embedding("orphan")}),
        DataObject(uuid=TWO_DOCUMENTS, properties={"text": "Dva dokumenty"},
                   references={"document": [d["letters"], d["gazette"]]}, vector={"default": fake_embedding("two")}),
    ])
    assert not inserted.errors
    letters_1 = corpus.chunks["letters_1"]["id"]
    before = await chunks.query.fetch_object_by_id(letters_1, include_vector=True,
                                                   return_references=QueryReference(link_on="document"))

    check = await chunk_year.run(seeded_store, names, checkpoint=tmp_path / "check.json", endpoint="test",
                                 write=False, progress=quiet)

    assert check["counts"] == {"examined": 9, "consistent": 0, "no_year": 0, "set": 2, "change": 2, "clear": 3,
                               "no_document": 1, "missing_document": 0, "several_documents": 1,
                               "invalid_year": 0, "written": 0}
    assert check["year_property"] == {"data_type": "int", "range_index": True}
    assert any(not r["match"] for r in check["ranges"]) and chunk_year.exit_code(check) == 1
    manifest = [json.loads(line) for line in (tmp_path / "check.json.manifest.jsonl").read_text().splitlines()]
    assert {(m["id"], m["status"], m["stored_year"]) for m in manifest} == {
        (str(ORPHAN), "no_document", 1700), (str(TWO_DOCUMENTS), "several_documents", None)}
    assert await found(seeded_store, names, keys, 1851, 1851) == {"chronicle_1", "chronicle_2", "chronicle_3"}

    with pytest.raises(LookupError):  # a check checkpoint is not resumed as a write
        await chunk_year.run(seeded_store, names, checkpoint=tmp_path / "check.json", endpoint="test",
                             write=True, progress=quiet)
    written = await chunk_year.run(seeded_store, names, checkpoint=tmp_path / "write.json", endpoint="test",
                                   write=True, progress=quiet)

    assert written["counts"]["written"] == 7 and written["to_retry"] == 0 and written["property_added"] is None
    assert all(r["match"] for r in written["ranges"]) and chunk_year.exit_code(written) == 0
    assert await found(seeded_store, names, keys, 1851, 1851) == set()
    assert await found(seeded_store, names, keys, 1899, 1903) == {"gazette_1", "gazette_2", "letters_1", "letters_2"}
    assert await found(seeded_store, names, keys, 1903, 1903) == {"letters_1", "letters_2"}
    after = await chunks.query.fetch_object_by_id(letters_1, include_vector=True,
                                                  return_references=QueryReference(link_on="document"))
    assert after.properties == {**before.properties, "yearIssued": 1903}
    assert after.vector == before.vector
    assert [o.uuid for o in after.references["document"].objects] == [UUID(d["letters"])]
    for path, write in (("write.json", True), ("check.json", False)):
        with pytest.raises(LookupError, match="finished run"):  # a finished checkpoint never reports success again
            await chunk_year.run(seeded_store, names, checkpoint=tmp_path / path, endpoint="test", write=write,
                                 progress=quiet)
    untouched = await store.read_chunks(seeded_store, names.chunks_collection_name, [ORPHAN, TWO_DOCUMENTS])
    assert (untouched[ORPHAN].year, untouched[TWO_DOCUMENTS].year) == (1700, None)

    again = await chunk_year.run(seeded_store, names, checkpoint=tmp_path / "again.json", endpoint="test",
                                 write=False, progress=quiet)
    assert {a: again["counts"][a] for a in chunk_year.WRITES} == {"set": 0, "change": 0, "clear": 0}
    assert again["counts"]["consistent"] == 4 and again["counts"]["no_year"] == 3
    assert chunk_year.exit_code(again) == 0


async def test_failed_writes_are_retried_by_resuming(seeded_store, collection_names, corpus, tmp_path, monkeypatch):
    names = collection_names
    letters = corpus.documents["letters"]["id"]
    await seeded_store.collections.get(names.document_collection_name).data.update(
        uuid=letters, properties={"yearIssued": 1903})
    failing = UUID(corpus.chunks["letters_1"]["id"])
    set_chunk_year, attempts = store.set_chunk_year, []

    async def flaky(client, collection, chunk_id, year):
        if chunk_id == failing and len(attempts) < chunk_year.ATTEMPTS:
            attempts.append(chunk_id)
            raise TimeoutError("uncertain")
        await set_chunk_year(client, collection, chunk_id, year)
    monkeypatch.setattr(store, "set_chunk_year", flaky)
    monkeypatch.setattr(chunk_year, "BACKOFF", 0)
    checkpoint = tmp_path / "write.json"

    first = await chunk_year.run(seeded_store, names, checkpoint=checkpoint, endpoint="test", write=True,
                                 progress=quiet)
    assert (first["counts"]["written"], first["to_retry"], first["ranges"]) == (1, 1, None)
    assert chunk_year.exit_code(first) == 1

    resumed = await chunk_year.run(seeded_store, names, checkpoint=checkpoint, endpoint="test", write=True,
                                   progress=quiet)
    assert (resumed["counts"]["written"], resumed["to_retry"]) == (2, 0)
    assert all(r["match"] for r in resumed["ranges"]) and chunk_year.exit_code(resumed) == 0
    lines = [json.loads(line) for line in (tmp_path / "write.json.manifest.jsonl").read_text().splitlines()]
    assert [(m["id"], m["status"]) for m in lines] == [(str(failing), "failed"), (str(failing), "verified_on_retry")]
    with pytest.raises(LookupError, match="finished run"):
        await chunk_year.run(seeded_store, names, checkpoint=checkpoint, endpoint="test", write=True, progress=quiet)


async def test_write_declares_the_property_through_an_alias(weaviate_client, store_token, collection_names,
                                                            tmp_path):
    """A store whose chunks lack ``yearIssued``, served through an alias as in the deployment."""
    client, docs, chunks, alias = weaviate_client, "YearDocuments", "YearChunks", "YearChunksAlias"
    names = collection_names.model_copy(update={"document_collection_name": docs, "chunks_collection_name": alias})
    first, second = UUID(int=1), UUID(int=2)

    async def drop():
        if await client.alias.get(alias_name=alias):
            await client.alias.delete(alias_name=alias)
        for name in (chunks, docs):
            await client.collections.delete(name)
    await drop()
    try:
        await client.collections.create(docs, properties=[Property(name="yearIssued", data_type=DataType.NUMBER)])
        await client.collections.create(chunks, properties=[Property(name="text", data_type=DataType.TEXT)],
                                        references=[ReferenceProperty(name="document", target_collection=docs)])
        await client.alias.create(alias_name=alias, target_collection=chunks)
        await client.collections.get(docs).data.insert_many([
            DataObject(uuid=first, properties={"yearIssued": 1941.0}), DataObject(uuid=second, properties={})])
        await client.collections.get(chunks).data.insert_many([
            DataObject(uuid=UUID(int=10 + n), properties={"text": f"chunk {n}"},
                       references={"document": first if n < 2 else second}) for n in range(3)])

        check = await chunk_year.run(client, names, checkpoint=tmp_path / "check.json", endpoint="test",
                                     write=False, progress=quiet)
        assert check["chunks"] == chunks and check["year_property"] is None and check["ranges"] is None
        assert (check["counts"]["set"], check["counts"]["no_year"]) == (2, 1) and chunk_year.exit_code(check) == 1

        written = await chunk_year.run(client, names, checkpoint=tmp_path / "write.json", endpoint="test",
                                       write=True, progress=quiet)
        assert written["property_added"] and written["year_property"] == {"data_type": "int", "range_index": True}
        assert written["counts"]["written"] == 2 and chunk_year.exit_code(written) == 0
        assert written["ranges"] == [{"first": 1941, "last": 1941, "expected": 2, "found": 2, "match": True},
                                     {"first": 1940, "last": 1952, "expected": 2, "found": 2, "match": True}]
    finally:
        await drop()


async def test_a_year_property_without_range_index_is_refused_before_writing(weaviate_client, collection_names,
                                                                             tmp_path):
    client, docs, chunks = weaviate_client, "YearDocuments", "YearChunks"
    names = collection_names.model_copy(update={"document_collection_name": docs, "chunks_collection_name": chunks})
    chunk_id = UUID(int=10)

    async def drop():
        for name in (chunks, docs):
            await client.collections.delete(name)
    await drop()
    try:
        await client.collections.create(docs, properties=[Property(name="yearIssued", data_type=DataType.INT)])
        await client.collections.create(
            chunks, properties=[Property(name="yearIssued", data_type=DataType.INT, index_range_filters=False)],
            references=[ReferenceProperty(name="document", target_collection=docs)])
        await client.collections.get(docs).data.insert(uuid=UUID(int=1), properties={"yearIssued": 1941})
        await client.collections.get(chunks).data.insert(uuid=chunk_id, properties={},
                                                         references={"document": UUID(int=1)})

        with pytest.raises(LookupError, match="range index"):
            await chunk_year.run(client, names, checkpoint=tmp_path / "write.json", endpoint="test", write=True,
                                 progress=quiet)
        assert (await store.read_chunks(client, chunks, [chunk_id]))[chunk_id].year is None  # nothing written

        check = await chunk_year.run(client, names, checkpoint=tmp_path / "check.json", endpoint="test",
                                     write=False, progress=quiet)
        assert check["year_property"] == {"data_type": "int", "range_index": False}
        assert check["counts"]["set"] == 1 and chunk_year.exit_code(check) == 1
    finally:
        await drop()
