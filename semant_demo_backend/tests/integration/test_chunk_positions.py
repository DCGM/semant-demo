"""Chunk positions against the real test store (#463).

The seeded chunks store the positions the shared calculator gives them. The backfill
command declares the properties on a store without them, writes only the missing
positions, refuses to overwrite or to position documents whose orders are not
consecutive, and a second run changes nothing. Annotations read only the chunks around
them through narrow order ranges.
"""
from types import SimpleNamespace
from uuid import UUID

import pytest
from weaviate.classes.config import DataType, Property, ReferenceProperty
from weaviate.classes.data import DataObject
from weaviate.classes.query import QueryReference

from semant_demo.adapters.weaviate import chunk_positions as store
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.features.annotations import service
from semant_demo.features.annotations.schemas import PostSpan, SpanType
from semant_demo.features.documents.positions import ChunkPosition, chunk_positions
from semant_demo.maintenance import chunk_positions as backfill
from tests.integration.test_annotation_enrichment import make_store

pytestmark = pytest.mark.integration

DOCS, CHUNKS, ALIAS = "PositionDocuments", "PositionChunks", "PositionChunksAlias"
VALID, LONG, GAP, DUPLICATE, PARTIAL = (UUID(int=n) for n in range(1, 6))
TEXTS = {VALID: ["hel", "lo world", "", ", ſtará 18", "48­"], LONG: [f"Odstavec {i}. " for i in range(450)],
         GAP: ["a", "b"], DUPLICATE: ["a", "b", "c"], PARTIAL: ["a", "b"]}
ORDERS = {GAP: [0, 2], DUPLICATE: [5, 6, 6]}


def quiet(line: str) -> None:
    pass


def chunk_id(document: UUID, i: int) -> UUID:
    return UUID(int=document.int * 10000 + i)


@pytest.fixture
async def position_store(weaviate_client, collection_names):
    """Documents and chunks without position properties, chunks served through an alias."""
    client = weaviate_client
    names = collection_names.model_copy(update={"document_collection_name": DOCS, "chunks_collection_name": ALIAS})

    async def drop():
        if await client.alias.get(alias_name=ALIAS):
            await client.alias.delete(alias_name=ALIAS)
        for name in (CHUNKS, DOCS):
            await client.collections.delete(name)
    await drop()
    await client.collections.create(DOCS, properties=[Property(name="title", data_type=DataType.TEXT)])
    await client.collections.create(
        CHUNKS, properties=[Property(name="text", data_type=DataType.TEXT),
                            Property(name="order", data_type=DataType.INT),
                            Property(name="language", data_type=DataType.TEXT)],
        references=[ReferenceProperty(name="document", target_collection=DOCS)])
    await client.alias.create(alias_name=ALIAS, target_collection=CHUNKS)
    await client.collections.get(DOCS).data.insert_many([DataObject(uuid=d, properties={}) for d in TEXTS])
    result = await client.collections.get(CHUNKS).data.insert_many([
        DataObject(uuid=chunk_id(d, i), properties={"text": t, "order": ORDERS.get(d, range(10, 10 + len(texts)))[i],
                                                    "language": "ces"},
                   references={"document": d})
        for d, texts in TEXTS.items() for i, t in enumerate(texts)])
    assert not result.errors
    try:
        yield SimpleNamespace(client=client, names=names)
    finally:
        await drop()


async def stored_positions(client, document: UUID) -> list[ChunkPosition | None]:
    ids = [chunk_id(document, i) for i in range(len(TEXTS[document]))]
    positions = await store.read_positions(client, CHUNKS, ids)
    return [positions[i] for i in ids]


async def test_check_write_and_check_again(position_store, tmp_path):
    client, names = position_store.client, position_store.names
    before = await client.collections.get(CHUNKS).query.fetch_object_by_id(
        chunk_id(VALID, 1), include_vector=True, return_references=QueryReference(link_on="document"))

    check = await backfill.run(client, names, checkpoint=tmp_path / "check.json", endpoint="test", write=False,
                               progress=quiet)
    assert check["chunks"] == CHUNKS and check["missing_properties"] == list(store.PROPERTY_TYPES)
    assert check["counts"]["missing"] == 3 and check["counts"]["nonconsecutive"] == 2
    assert backfill.exit_code(check) == 1
    assert await store.declared_types(client, CHUNKS) == {}  # a check declares nothing

    written = await backfill.run(client, names, checkpoint=tmp_path / "write.json", endpoint="test", write=True,
                                 progress=quiet)
    assert written["properties_added"]["names"] == list(store.PROPERTY_TYPES)
    assert written["counts"] == {"documents": 5, "consistent": 0, "missing": 3, "conflict": 0, "nonconsecutive": 2,
                                 "no_chunks": 0, "chunks": 462, "chunks_missing": 457, "chunks_written": 457}
    assert (written["chunks_total"], written["chunks_not_reached"]) == (462, 0)
    assert backfill.exit_code(written) == 1  # the two nonconsecutive documents are reported
    reported = [line for line in (tmp_path / "write.json.manifest.jsonl").read_text().splitlines()]
    assert len(reported) == 2 and all("nonconsecutive" in line for line in reported)

    assert await stored_positions(client, VALID) == list(chunk_positions(TEXTS[VALID]))
    assert (await stored_positions(client, VALID))[1] == ChunkPosition(3, 1, True)  # "hel" + "lo world"
    assert await stored_positions(client, LONG) == list(chunk_positions(TEXTS[LONG]))
    assert await stored_positions(client, GAP) == [None, None]
    assert await stored_positions(client, DUPLICATE) == [None, None, None]
    after = await client.collections.get(CHUNKS).query.fetch_object_by_id(
        chunk_id(VALID, 1), include_vector=True, return_references=QueryReference(link_on="document"))
    assert {k: v for k, v in after.properties.items() if k not in store.PROPERTY_TYPES} == before.properties
    assert after.references["document"].objects[0].uuid == VALID and after.vector == before.vector

    again = await backfill.run(client, names, checkpoint=tmp_path / "again.json", endpoint="test", write=True,
                               progress=quiet)
    assert (again["counts"]["consistent"], again["counts"]["chunks_written"]) == (3, 0)
    assert again["properties_added"] is None


async def test_a_conflicting_position_is_reported_and_never_overwritten(position_store, tmp_path):
    client, names = position_store.client, position_store.names
    await store.add_position_properties(client, CHUNKS, list(store.PROPERTY_TYPES))
    await client.collections.get(CHUNKS).data.update(uuid=chunk_id(PARTIAL, 1), properties={"startChar": 7})
    wrong = ChunkPosition(0, 0, True)
    await store.write_position(client, CHUNKS, chunk_id(VALID, 0), wrong)

    written = await backfill.run(client, names, checkpoint=tmp_path / "write.json", endpoint="test", write=True,
                                 progress=quiet)

    assert written["counts"]["conflict"] == 2 and written["counts"]["missing"] == 1  # LONG only
    assert await stored_positions(client, VALID) == [wrong, None, None, None, None]
    assert await stored_positions(client, PARTIAL) == [None, None]
    assert backfill.exit_code(written) == 1


async def test_a_property_of_another_type_is_refused_before_writing(position_store, tmp_path):
    client, names = position_store.client, position_store.names
    await client.collections.get(CHUNKS).config.add_property(Property(name="startWord", data_type=DataType.TEXT))

    with pytest.raises(LookupError, match="separate, reviewed migration"):
        await backfill.run(client, names, checkpoint=tmp_path / "write.json", endpoint="test", write=True,
                           progress=quiet)
    assert await store.declared_types(client, CHUNKS) == {"startWord": "text"}


async def test_an_interrupted_write_resumes_from_its_checkpoint(position_store, tmp_path, monkeypatch):
    client, names = position_store.client, position_store.names
    monkeypatch.setattr(backfill, "DOCUMENT_PAGE", 2)
    checkpoint = tmp_path / "write.json"

    first = await backfill.run(client, names, checkpoint=checkpoint, endpoint="test", write=True, limit=2,
                               progress=quiet)
    assert not first["done"] and first["counts"]["documents"] == 2
    with pytest.raises(LookupError, match="different mode"):
        await backfill.run(client, names, checkpoint=checkpoint, endpoint="test", write=False, progress=quiet)

    rest = await backfill.run(client, names, checkpoint=checkpoint, endpoint="test", write=True, progress=quiet)
    assert rest["done"] and rest["counts"]["documents"] == 5 and rest["counts"]["chunks_written"] == 457
    with pytest.raises(LookupError, match="finished run"):
        await backfill.run(client, names, checkpoint=checkpoint, endpoint="test", write=True, progress=quiet)


# ── Annotations read only the chunks around them ─────────────────────────

async def test_order_range_reads_return_positions_without_a_sort(seeded_store, documents, corpus):
    chronicle = UUID(corpus.documents["chronicle"]["id"])
    texts = [corpus.chunks[k]["text"] for k in ("chronicle_1", "chronicle_2", "chronicle_3")]

    chunks = await documents.read_chunk_texts_in_range(chronicle, 1, 5)

    assert [c.order for c in chunks] == [1, 2]
    expected = list(chunk_positions(texts))[1:]
    assert [(c.start_char, c.start_word, c.word_open_at_start) for c in chunks] == \
        [(p.start_char, p.start_word, p.word_open_at_start) for p in expected]
    assert await documents.read_chunk_texts_in_range(chronicle, 3, 9) == []


async def test_a_span_on_chunks_without_positions_is_saved_with_failed_derived_data(
        seeded_store, collection_names, ids, corpus):
    embedder = SimpleNamespace(embed_document=None, embed_query=None)
    annotation_store = make_store(seeded_store, collection_names, embedder)
    annotation_store.documents = DocumentRepository(seeded_store, collection_names)  # positions not declared
    owner = SimpleNamespace(id=UUID(ids.user["owner"]), is_superuser=False)

    created = await service.create_span(annotation_store, owner, PostSpan(
        chunkId=ids.chunk["chronicle_1"], tagId=ids.tag["person"], start=34, end=43, type=SpanType.pos))

    assert created.outcome == "partial"
    assert [(f.step, f.message) for f in created.failed] == [
        ("derive_annotation", "MissingChunkPositions: chunk positions are missing or inconsistent (#463)")]
    row = await annotation_store.spans.read_row(UUID(ids.col["chronicles"]), UUID(created.id))
    assert (row.enrichmentStatus, row.text, row.documentStartChar) == ("failed", "", None)
