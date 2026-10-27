"""The append-only chunk import against the real test store (#313).

Collections as in production: chunks and documents served through aliases, the chunk
vector named ``Qwen3_Embedding_0_6B``, the #463 position properties and a tag reference.
The import creates missing empty documents and positioned chunks, appends after a
stored tail, replays without writing and refuses anything that would change, skip or
interleave stored chunks; a failed write blocks only its document and a rerun finishes
it. Existing objects (properties, references, vectors, update times) never change.
"""
import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from weaviate.classes.backup import BackupStorage
from weaviate.classes.config import Configure, DataType, Property, ReferenceProperty
from weaviate.classes.data import DataObject
from weaviate.classes.query import MetadataQuery, QueryReference

from semant_demo.adapters.weaviate import chunk_ingest as store
from semant_demo.features.documents.positions import ChunkPosition, chunk_positions
from semant_demo.maintenance import chunk_ingest, chunk_positions as backfill

pytestmark = pytest.mark.integration

DOCS, CHUNKS, TAGS = "IngestDocuments", "IngestChunks", "IngestTags"
DOCS_ALIAS, CHUNKS_ALIAS = "IngestDocumentsAlias", "IngestChunksAlias"
VECTOR = "Qwen3_Embedding_0_6B"
EXISTING, NEW, OTHER = UUID(int=1), UUID(int=2), UUID(int=3)
TAG = UUID(int=9)
TEXTS = ["hel", "lo world", "", ", ſtará 18", "48­", "konec."]
STORED = 3
"""Chunks 0..2 of EXISTING are stored before each test."""


def cid(document: UUID, i: int) -> UUID:
    return UUID(int=document.int * 1000 + i)


def line(document: UUID, i: int, **extra) -> dict:
    return {"id": str(cid(document, i)), "document": str(document), "order": i, "text": TEXTS[i],
            "language": "ces", **extra}


def quiet(_line: str) -> None:
    pass


@pytest.fixture
async def ingest_store(weaviate_client, collection_names):
    client = weaviate_client
    names = collection_names.model_copy(update={"document_collection_name": DOCS_ALIAS,
                                                 "chunks_collection_name": CHUNKS_ALIAS})

    async def drop():
        for alias in (CHUNKS_ALIAS, DOCS_ALIAS):
            if await client.alias.get(alias_name=alias):
                await client.alias.delete(alias_name=alias)
        for name in (CHUNKS, TAGS, DOCS, "IngestBareChunks"):
            await client.collections.delete(name)
    await drop()
    await client.collections.create(DOCS, vector_config=Configure.Vectors.self_provided(),
                                    properties=[Property(name="title", data_type=DataType.TEXT)])
    await client.collections.create(TAGS, properties=[Property(name="tag_name", data_type=DataType.TEXT)])
    await client.collections.create(
        CHUNKS, vector_config=[Configure.Vectors.self_provided(name=VECTOR)],
        properties=[Property(name="text", data_type=DataType.TEXT), Property(name="title", data_type=DataType.TEXT),
                    Property(name="order", data_type=DataType.INT),
                    Property(name="language", data_type=DataType.TEXT),
                    Property(name="start_page_id", data_type=DataType.TEXT),
                    Property(name="from_page", data_type=DataType.INT), Property(name="to_page", data_type=DataType.INT),
                    Property(name="end_paragraph", data_type=DataType.BOOL),
                    Property(name="yearIssued", data_type=DataType.INT, index_range_filters=True),
                    Property(name="startChar", data_type=DataType.INT), Property(name="startWord", data_type=DataType.INT),
                    Property(name="wordOpenAtStart", data_type=DataType.BOOL)],
        references=[ReferenceProperty(name="document", target_collection=DOCS),
                    ReferenceProperty(name="positiveTag", target_collection=TAGS)])
    await client.alias.create(alias_name=DOCS_ALIAS, target_collection=DOCS)
    await client.alias.create(alias_name=CHUNKS_ALIAS, target_collection=CHUNKS)
    await client.collections.get(DOCS).data.insert(uuid=EXISTING, properties={"title": "Kronika"})
    await client.collections.get(TAGS).data.insert(uuid=TAG, properties={"tag_name": "t"})
    positions = list(chunk_positions(TEXTS[:STORED]))
    result = await client.collections.get(CHUNKS).data.insert_many([
        DataObject(uuid=cid(EXISTING, i),
                   properties={"text": TEXTS[i], "order": i, "language": "ces", "title": f"chunk {i}", "yearIssued": 1920,
                               "startChar": positions[i].start_char, "startWord": positions[i].start_word,
                               "wordOpenAtStart": positions[i].word_open_at_start},
                   references={"document": EXISTING, "positiveTag": TAG}, vector={VECTOR: [0.1 * (i + 1), 0.2, 0.3]})
        for i in range(STORED)])
    assert not result.errors
    try:
        yield SimpleNamespace(client=client, names=names)
    finally:
        await drop()


def jsonl(tmp_path, name: str, records: list) -> list:
    path = tmp_path / name
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return [path]


async def run(s, tmp_path, inputs, checkpoint="run.json", write=True):
    result = await chunk_ingest.run(s.client, s.names, inputs, checkpoint=tmp_path / checkpoint, endpoint="test",
                                    write_=write, progress=quiet)
    return result, chunk_ingest.exit_code(result)


async def snapshot(client) -> dict:
    """Every object of the test collections with properties, references, vectors and update time."""
    objects = {}
    for name in (DOCS, CHUNKS):
        response = await client.collections.get(name).query.fetch_objects(
            limit=1000, include_vector=True, return_metadata=MetadataQuery(last_update_time=True),
            return_references=[QueryReference(link_on="document", return_properties=[]),
                               QueryReference(link_on="positiveTag", return_properties=[])] if name == CHUNKS else None)
        for o in response.objects:
            refs = {k: sorted(t.uuid for t in v.objects) for k, v in (o.references or {}).items()}
            objects[o.uuid] = (o.properties, refs, o.vector, o.metadata.last_update_time)
    return objects


def manifest(tmp_path, checkpoint="run.json") -> list[dict]:
    path = tmp_path / f"{checkpoint}.manifest.jsonl"
    return [json.loads(raw) for raw in path.read_text().splitlines()] if path.exists() else []


async def stored_chunk(client, document: UUID, i: int):
    return (await store.read_chunks(client, CHUNKS, [cid(document, i)], ("language",))).get(cid(document, i))


async def test_a_check_writes_nothing_and_a_fresh_import_creates_empty_documents_and_positioned_chunks(
        ingest_store, tmp_path):
    s = ingest_store
    inputs = jsonl(tmp_path, "new.jsonl", [line(NEW, i, title="Kronika", year=1920, vector_index=i)
                                           for i in range(len(TEXTS))])
    before = await snapshot(s.client)
    result, code = await run(s, tmp_path, inputs, "check.json", write=False)
    assert code == 0 and result["counts"]["new"] == 1 and result["counts"]["chunks_to_insert"] == len(TEXTS)
    assert await snapshot(s.client) == before

    result, code = await run(s, tmp_path, inputs)
    assert code == 0 and result["counts"]["chunks_inserted"] == len(TEXTS)
    assert result["counts"]["documents_created"] == 1
    assert result["ignored_fields"] == {"title": len(TEXTS), "year": len(TEXTS), "vector_index": len(TEXTS)}
    document = await s.client.collections.get(DOCS).query.fetch_object_by_id(NEW)
    assert document.properties == {"title": None}  # metadata comes from metadata_sync
    expected = list(chunk_positions(TEXTS))
    for i in range(len(TEXTS)):
        chunk = await stored_chunk(s.client, NEW, i)
        assert (chunk.document, chunk.order, chunk.text, chunk.fields, chunk.position) == (
            NEW, i, TEXTS[i], {"language": "ces"}, expected[i])
    # The backfill's own check agrees with the positions the import wrote.
    checked = await backfill.run(s.client, s.names, checkpoint=tmp_path / "positions.json", endpoint="test",
                                 write=False, progress=quiet)
    assert checked["counts"]["conflict"] == checked["counts"]["missing"] == 0
    assert checked["counts"]["consistent"] == 2


async def test_repeating_a_completed_import_changes_nothing(ingest_store, tmp_path):
    s = ingest_store
    inputs = jsonl(tmp_path, "new.jsonl", [line(NEW, i) for i in range(4)] + [line(EXISTING, i) for i in range(STORED)])
    _, code = await run(s, tmp_path, inputs, "first.json")
    assert code == 0
    before = await snapshot(s.client)
    result, code = await run(s, tmp_path, inputs, "second.json")
    assert code == 0 and result["counts"]["chunks_inserted"] == 0 and result["counts"]["replayed"] == 2
    assert result["counts"]["chunks_replayed"] == 4 + STORED
    assert await snapshot(s.client) == before


async def test_an_append_continues_after_the_tail_and_keeps_the_stored_chunks(ingest_store, tmp_path):
    s = ingest_store
    before = await snapshot(s.client)
    # A replayed suffix of the stored chunks (order 2) followed by new ones.
    result, code = await run(s, tmp_path, jsonl(tmp_path, "append.jsonl", [line(EXISTING, i) for i in range(2, 6)]))
    assert code == 0 and result["counts"]["append"] == 1 and result["counts"]["chunks_inserted"] == 3
    after = await snapshot(s.client)
    assert {k: after[k] for k in before} == before  # existing objects untouched, tags and vectors included
    expected = list(chunk_positions(TEXTS))
    for i in range(3, 6):
        assert (await stored_chunk(s.client, EXISTING, i)).position == expected[i]


@pytest.mark.parametrize("records, reason", [
    ([line(EXISTING, 4)], "gap"),
    ([{**line(EXISTING, 1), "text": "changed"}, line(EXISTING, 2), line(EXISTING, 3)], "conflict"),
    ([{**line(NEW, 0), "id": str(cid(EXISTING, 0))}], "conflict"),
    ([line(EXISTING, 3, language=None, startChar=5)], "invalid_input"),
    ([line(EXISTING, 3, unknown=1)], "invalid_input"),
    ([line(NEW, 0), line(NEW, 2)], "invalid_input"),
])
async def test_input_that_would_change_skip_or_interleave_is_rejected_without_writing(
        ingest_store, tmp_path, records, reason):
    s = ingest_store
    before = await snapshot(s.client)
    result, code = await run(s, tmp_path, jsonl(tmp_path, "bad.jsonl", records))
    assert code == 1 and result["counts"]["rejected"] == 1
    assert [m["reason"].split(":")[0] for m in manifest(tmp_path)] == [reason]
    assert await snapshot(s.client) == before


async def test_a_failed_write_blocks_only_its_document_and_a_rerun_finishes_it(ingest_store, tmp_path, monkeypatch):
    s = ingest_store
    inputs = jsonl(tmp_path, "new.jsonl", [line(NEW, i) for i in range(5)] + [line(OTHER, i) for i in range(3)])
    real, calls = store.insert_chunk, []

    async def failing(client, collection, chunk_id, document_id, properties):
        calls.append(chunk_id)
        if chunk_id == cid(NEW, 2):
            raise ConnectionError("simulated")
        await real(client, collection, chunk_id, document_id, properties)
    monkeypatch.setattr(store, "insert_chunk", failing)
    result, code = await run(s, tmp_path, inputs)
    assert code == 1 and result["blocked"] == 1
    assert [await stored_chunk(s.client, NEW, i) is not None for i in range(5)] == [True, True, False, False, False]
    assert all([await stored_chunk(s.client, OTHER, i) is not None for i in range(3)])
    assert {m["status"] for m in manifest(tmp_path)} == {"blocked", "incomplete_document"}

    monkeypatch.setattr(store, "insert_chunk", real)
    result, code = await run(s, tmp_path, inputs)  # resumes the same checkpoint: retries the blocked document
    assert code == 0 and result["blocked"] == 0
    expected = list(chunk_positions(TEXTS[:5]))
    assert [(await stored_chunk(s.client, NEW, i)).position for i in range(5)] == expected


async def test_an_uncertain_write_that_arrived_is_verified_and_continues(ingest_store, tmp_path, monkeypatch):
    s = ingest_store
    real = store.insert_chunk

    async def timed_out(client, collection, chunk_id, document_id, properties):
        await real(client, collection, chunk_id, document_id, properties)
        if chunk_id == cid(NEW, 1):
            raise TimeoutError("the write arrived, the answer did not")
    monkeypatch.setattr(store, "insert_chunk", timed_out)
    result, code = await run(s, tmp_path, jsonl(tmp_path, "new.jsonl", [line(NEW, i) for i in range(3)]))
    assert code == 0 and result["counts"]["chunks_inserted"] == 3


async def test_an_existing_id_is_never_overwritten(ingest_store):
    s = ingest_store
    before = await snapshot(s.client)
    with pytest.raises(store.AlreadyExists):
        await store.insert_chunk(s.client, CHUNKS_ALIAS, cid(EXISTING, 0), EXISTING, {"text": "x", "order": 0})
    with pytest.raises(store.AlreadyExists):
        await store.insert_document(s.client, DOCS_ALIAS, EXISTING)
    assert await snapshot(s.client) == before


async def test_a_schema_without_positions_is_refused_before_writing(ingest_store, tmp_path):
    s = ingest_store
    await s.client.collections.create("IngestBareChunks", properties=[
        Property(name="text", data_type=DataType.TEXT), Property(name="order", data_type=DataType.INT)],
        references=[ReferenceProperty(name="document", target_collection=DOCS)])
    names = s.names.model_copy(update={"chunks_collection_name": "IngestBareChunks"})
    with pytest.raises(LookupError, match="startChar is missing"):
        await chunk_ingest.run(s.client, names, jsonl(tmp_path, "new.jsonl", [line(NEW, 0)]),
                               checkpoint=tmp_path / "run.json", endpoint="test", write_=True, progress=quiet)
    assert not await s.client.collections.get(DOCS).query.fetch_object_by_id(NEW)


async def test_the_backup_must_hold_the_chunks_and_documents(ingest_store):
    s = ingest_store
    target = await chunk_ingest.preflight(s.client, s.names)
    with pytest.raises(LookupError, match="No successful"):
        await chunk_ingest.check_backup(s.client, target, "missing-backup")
    await s.client.backup.create(backup_id="ingest-documents", backend=BackupStorage.FILESYSTEM,
                                 include_collections=[DOCS], wait_for_completion=True)
    with pytest.raises(LookupError, match="does not hold"):
        await chunk_ingest.check_backup(s.client, target, "ingest-documents")
    await s.client.backup.create(backup_id="ingest-both", backend=BackupStorage.FILESYSTEM,
                                 include_collections=[DOCS, CHUNKS], wait_for_completion=True)
    await chunk_ingest.check_backup(s.client, target, "ingest-both")


async def test_inserted_chunks_have_no_vector_until_the_embedder_runs(ingest_store, tmp_path):
    s = ingest_store
    _, code = await run(s, tmp_path, jsonl(tmp_path, "new.jsonl", [line(NEW, 0)]))
    assert code == 0
    chunk = await s.client.collections.get(CHUNKS).query.fetch_object_by_id(cid(NEW, 0), include_vector=True)
    assert chunk.vector == {}
    assert ChunkPosition(0, 0, False) == (await stored_chunk(s.client, NEW, 0)).position
