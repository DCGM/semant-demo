"""Copying document visibility to the chunks against the real test store (#793).

The fixture corpus: chronicle (``public=true``, chunks chronicle_1-3), letters (``false``,
letters_1-2), gazette (no ``public``, gazette_1-2); the seeded chunks store
``documentPublic`` derived from their document. The tests change document rights, add chunks
without a single existing document, and check, write and check again; they cover the per-
document synchronization ``metadata_sync`` uses and declaring the property through an alias.
"""
import json
from uuid import UUID

import pytest
from weaviate.classes.config import DataType, Property, ReferenceProperty
from weaviate.classes.data import DataObject
from weaviate.classes.query import Filter

from semant_demo.adapters.weaviate import chunk_visibility as store
from semant_demo.maintenance import chunk_document_public as backfill
from tests.fakes import fake_embedding

pytestmark = pytest.mark.integration

ORPHAN, TWO_DOCUMENTS, UNFLAGGED, DANGLING = (UUID(f"5e3a0000-0000-4000-8000-0000000ce10{n}") for n in range(1, 5))
GONE = UUID("5e3a0000-0000-4000-8000-0000000ce1ff")


def quiet(line: str) -> None:
    pass


async def public_chunks(client, names, keys) -> set[str]:
    """What an unscoped search admits: ``documentPublic == true``."""
    response = await client.collections.get(names.chunks_collection_name).query.fetch_objects(
        filters=Filter.by_property(store.PROPERTY).equal(True), limit=100, return_properties=[])
    return {keys.get(str(o.uuid), str(o.uuid)) for o in response.objects}


async def flags(client, names, ids) -> dict[UUID, object]:
    return {i: c.public for i, c in (await store.read_chunks(client, names.chunks_collection_name, ids)).items()}


async def test_check_write_and_check_again_fail_closed(seeded_store, collection_names, corpus, tmp_path):
    names, d = collection_names, {k: UUID(v["id"]) for k, v in corpus.documents.items()}
    keys = {c["id"]: k for k, c in corpus.chunks.items()}
    documents = seeded_store.collections.get(names.document_collection_name)
    chunks = seeded_store.collections.get(names.chunks_collection_name)
    assert await public_chunks(seeded_store, names, keys) == {"chronicle_1", "chronicle_2", "chronicle_3"}
    await documents.data.update(uuid=d["chronicle"], properties={"public": False})  # restricted now
    await documents.data.update(uuid=d["letters"], properties={"public": True})     # published now
    await documents.data.insert(uuid=GONE, properties={"public": True})
    inserted = await chunks.data.insert_many([
        DataObject(uuid=ORPHAN, properties={"text": "Bez dokumentu", store.PROPERTY: True},
                   vector={"default": fake_embedding("orphan")}),
        DataObject(uuid=TWO_DOCUMENTS, properties={"text": "Dva dokumenty"},
                   references={"document": [d["letters"], d["chronicle"]]}, vector={"default": fake_embedding("two")}),
        DataObject(uuid=UNFLAGGED, properties={"text": "Bez příznaku"}, references={"document": d["gazette"]},
                   vector={"default": fake_embedding("unflagged")}),
        DataObject(uuid=DANGLING, properties={"text": "Smazaný dokument", store.PROPERTY: True},
                   references={"document": GONE}, vector={"default": fake_embedding("dangling")}),
    ])
    assert not inserted.errors
    await documents.data.delete_by_id(GONE)
    letters_1 = corpus.chunks["letters_1"]["id"]
    before = await chunks.query.fetch_object_by_id(letters_1, include_vector=True)

    check = await backfill.run(seeded_store, names, checkpoint=tmp_path / "check.json", endpoint="test",
                               write=False, progress=quiet)

    counts = check["counts"]
    # Weaviate resolves no reference to a deleted document: DANGLING reads as without one
    assert counts["reasons"] == {"public": 2, "restricted": 3, "unknown": 3, "no_document": 2,
                                 "missing_document": 0, "several_documents": 1}
    assert (counts["consistent"], counts["set"], counts["change"], counts["stale_true"]) == (2, 2, 7, 5)
    assert (counts["expected_true"], counts["expected_false"], counts["written"]) == (2, 9, 0)
    assert check["search_counts"]["match"] is False and check["search_counts"]["without_flag"] == 2
    assert backfill.exit_code(check) == 1
    manifest = [json.loads(line) for line in (tmp_path / "check.json.manifest.jsonl").read_text().splitlines()]
    assert {(m["id"], m["status"]) for m in manifest} == {
        (str(ORPHAN), "no_document"), (str(TWO_DOCUMENTS), "several_documents"), (str(DANGLING), "no_document")}
    with pytest.raises(LookupError):  # a check checkpoint is not resumed as a write
        await backfill.run(seeded_store, names, checkpoint=tmp_path / "check.json", endpoint="test", write=True,
                           progress=quiet)

    written = await backfill.run(seeded_store, names, checkpoint=tmp_path / "write.json", endpoint="test",
                                 write=True, progress=quiet)

    assert written["counts"]["written"] == 9 and written["to_retry"] == 0 and written["property_added"] is None
    assert written["search_counts"] == {"expected_true": 2, "expected_false": 9, "expected_all": 11, "true": 2,
                                        "false": 9, "all": 11, "without_flag": 0, "match": True}
    assert backfill.exit_code(written) == 0
    assert await public_chunks(seeded_store, names, keys) == {"letters_1", "letters_2"}
    after = await chunks.query.fetch_object_by_id(letters_1, include_vector=True)
    assert after.vector == before.vector  # a merge of the flag only
    assert {k: v for k, v in after.properties.items() if k != store.PROPERTY} == {
        k: v for k, v in before.properties.items() if k != store.PROPERTY}

    again = await backfill.run(seeded_store, names, checkpoint=tmp_path / "again.json", endpoint="test",
                               write=False, progress=quiet)
    assert again["counts"]["consistent"] == 11 and backfill.exit_code(again) == 0


async def test_chunks_become_public_only_while_their_document_still_is(seeded_store, collection_names, corpus):
    names = collection_names
    chunks_name = names.chunks_collection_name
    documents_name = names.document_collection_name
    letters = UUID(corpus.documents["letters"]["id"])
    ids = [UUID(corpus.chunks[k]["id"]) for k in ("letters_1", "letters_2")]
    page = list((await store.read_chunks(seeded_store, chunks_name, ids)).values())
    # planned from a stale read that saw letters public; it is restricted when written
    failed, lines, written = await backfill._apply(seeded_store, chunks_name, documents_name, page,
                                                   dict.fromkeys(ids, True), 4, backfill._Pacer(None))

    assert sorted(failed) == sorted(ids) and written == 0
    assert all("no longer public" in line["reason"] for line in lines)
    assert await flags(seeded_store, names, ids) == dict.fromkeys(ids, False)
    assert (await store.read_document_public(seeded_store, documents_name, [letters]))[letters] is False


async def test_an_interrupted_write_resumes_and_retries_its_failures(seeded_store, collection_names, corpus,
                                                                    tmp_path, monkeypatch):
    names = collection_names
    chronicle = UUID(corpus.documents["chronicle"]["id"])
    await seeded_store.collections.get(names.document_collection_name).data.update(
        uuid=chronicle, properties={"public": False})
    failing = UUID(corpus.chunks["chronicle_2"]["id"])
    original = store.set_chunk_public

    async def flaky(client, collection, chunk_id, value):
        if chunk_id == failing:
            raise TimeoutError("timed out")
        await original(client, collection, chunk_id, value)
    monkeypatch.setattr(store, "set_chunk_public", flaky)
    monkeypatch.setattr("semant_demo.maintenance.chunk_year.BACKOFF", 0)
    checkpoint = tmp_path / "write.json"

    first = await backfill.run(seeded_store, names, checkpoint=checkpoint, endpoint="test", write=True, limit=4,
                               progress=quiet)

    assert not first["done"] and first["counts"]["examined"] == 4 and backfill.exit_code(first) == 1
    monkeypatch.setattr(store, "set_chunk_public", original)
    resumed = await backfill.run(seeded_store, names, checkpoint=checkpoint, endpoint="test", write=True,
                                 progress=quiet)

    assert resumed["done"] and resumed["to_retry"] == 0 and resumed["counts"]["examined"] == 7
    assert resumed["search_counts"]["match"] and backfill.exit_code(resumed) == 0
    assert (await flags(seeded_store, names, [failing]))[failing] is False
    lines = [json.loads(line) for line in (tmp_path / "write.json.manifest.jsonl").read_text().splitlines()]
    assert [(m["id"], m["status"]) for m in lines] == [(str(failing), "failed"), (str(failing), "verified_on_retry")]
    with pytest.raises(LookupError, match="finished run"):
        await backfill.run(seeded_store, names, checkpoint=checkpoint, endpoint="test", write=True, progress=quiet)


async def test_sync_document_also_sets_chunks_without_a_flag_and_verifies_all(seeded_store, collection_names,
                                                                              corpus):
    names, chunks_name = collection_names, collection_names.chunks_collection_name
    chronicle = UUID(corpus.documents["chronicle"]["id"])
    ids = [UUID(corpus.chunks[f"chronicle_{n}"]["id"]) for n in (1, 2, 3)]
    await seeded_store.collections.get(chunks_name).data.update(uuid=ids[0], properties={store.PROPERTY: None})
    assert (await flags(seeded_store, names, ids))[ids[0]] is None

    lowered = await backfill.sync_document(seeded_store, chunks_name, chronicle, False)

    assert (lowered.written, lowered.chunks, lowered.verified, lowered.error) == (3, 3, True, None)
    assert await flags(seeded_store, names, ids) == dict.fromkeys(ids, False)
    raised = await backfill.sync_document(seeded_store, chunks_name, chronicle, True)
    assert (raised.written, raised.verified) == (3, True)
    unchanged = await backfill.sync_document(seeded_store, chunks_name, chronicle, True)
    assert (unchanged.written, unchanged.verified) == (0, True)


async def test_document_mode_follows_each_listed_document(seeded_store, collection_names, corpus, tmp_path):
    names = collection_names
    d = {k: UUID(v["id"]) for k, v in corpus.documents.items()}
    await seeded_store.collections.get(names.document_collection_name).data.update(
        uuid=d["chronicle"], properties={"public": False})
    listed = [d["chronicle"], d["letters"], GONE]

    check = await backfill.run_documents(seeded_store, names, listed, checkpoint=tmp_path / "check.json",
                                         endpoint="test", write=False, progress=quiet)
    assert check["counts"] == {"public": 0, "not_public": 2, "missing_document": 1, "verified": 1,
                                    "mismatched": 1, "failed": 0, "written": 0}
    assert backfill.documents_exit_code(check) == 1

    written = await backfill.run_documents(seeded_store, names, listed[:2], checkpoint=tmp_path / "write.json",
                                           endpoint="test", write=True, progress=quiet)
    assert (written["counts"]["verified"], written["counts"]["written"], written["to_retry"]) == (2, 3, 0)
    assert backfill.documents_exit_code(written) == 0
    keys = {c["id"]: k for k, c in corpus.chunks.items()}
    assert await public_chunks(seeded_store, names, keys) == set()


async def test_write_declares_the_property_through_an_alias(weaviate_client, collection_names, tmp_path):
    """A store whose chunks lack ``documentPublic``, served through an alias as in the deployment."""
    client, docs, chunks, alias = weaviate_client, "VisibilityDocuments", "VisibilityChunks", "VisibilityChunksAlias"
    names = collection_names.model_copy(update={"document_collection_name": docs, "chunks_collection_name": alias})
    public, restricted = UUID(int=1), UUID(int=2)

    async def drop():
        if await client.alias.get(alias_name=alias):
            await client.alias.delete(alias_name=alias)
        for name in (chunks, docs):
            await client.collections.delete(name)
    await drop()
    try:
        await client.collections.create(docs, properties=[Property(name="public", data_type=DataType.BOOL)])
        await client.collections.create(chunks, properties=[Property(name="text", data_type=DataType.TEXT)],
                                        references=[ReferenceProperty(name="document", target_collection=docs)])
        await client.alias.create(alias_name=alias, target_collection=chunks)
        await client.collections.get(docs).data.insert_many([
            DataObject(uuid=public, properties={"public": True}), DataObject(uuid=restricted, properties={})])
        await client.collections.get(chunks).data.insert_many([
            DataObject(uuid=UUID(int=10 + n), properties={"text": f"chunk {n}"},
                       references={"document": public if n < 2 else restricted}) for n in range(3)])

        check = await backfill.run(client, names, checkpoint=tmp_path / "check.json", endpoint="test",
                                   write=False, progress=quiet)
        assert check["chunks"] == chunks and check["flag_property"] is None and check["search_counts"] is None
        assert check["counts"]["set"] == 3 and backfill.exit_code(check) == 1

        written = await backfill.run(client, names, checkpoint=tmp_path / "write.json", endpoint="test",
                                     write=True, progress=quiet)
        assert written["property_added"] and written["flag_property"] == {"data_type": "boolean", "filterable": True}
        assert written["counts"]["written"] == 3 and backfill.exit_code(written) == 0
        assert (written["search_counts"]["true"], written["search_counts"]["false"]) == (2, 1)
    finally:
        await drop()


async def test_a_flag_of_another_type_is_refused_before_writing(weaviate_client, collection_names, tmp_path):
    client, docs, chunks = weaviate_client, "VisibilityDocuments", "VisibilityChunks"
    names = collection_names.model_copy(update={"document_collection_name": docs, "chunks_collection_name": chunks})

    async def drop():
        for name in (chunks, docs):
            await client.collections.delete(name)
    await drop()
    try:
        await client.collections.create(docs, properties=[Property(name="public", data_type=DataType.BOOL)])
        await client.collections.create(chunks, properties=[Property(name=store.PROPERTY, data_type=DataType.TEXT)],
                                        references=[ReferenceProperty(name="document", target_collection=docs)])
        with pytest.raises(LookupError, match="filterable boolean"):
            await backfill.run(client, names, checkpoint=tmp_path / "write.json", endpoint="test", write=True,
                               progress=quiet)
    finally:
        await drop()
