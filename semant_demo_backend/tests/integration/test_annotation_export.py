"""CSV export of a collection's annotations against real Weaviate (#719).

Through the API: the filter scope exports exactly the concordance's matches (in no particular order), with
the stored document-level UTF-16 positions (also of a cross-chunk annotation) and the anchor
chunk's language and classifications read from the store; selections keep annotations outside
the filters; users without access get no file. The chunk metadata read skips properties the
store does not declare.
"""
import csv
import io
from types import SimpleNamespace
from uuid import UUID

import pytest

from semant_demo.adapters.weaviate.chunk_tags import ChunkTagRepository
from semant_demo.adapters.weaviate.spans import SpanRepository
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.features.annotations import service
from semant_demo.features.annotations.enrichment import Enrichment
from semant_demo.features.annotations.schemas import PostSpan, SpanType
from semant_demo.features.annotations.service import AnnotationStore

pytestmark = pytest.mark.integration


@pytest.fixture
def store(seeded_store, collection_names, documents) -> AnnotationStore:
    spans = SpanRepository(seeded_store, collection_names)
    return AnnotationStore(collections=UserCollectionRepository(seeded_store, collection_names, spans),
                           tags=TagRepository(seeded_store, collection_names, spans), spans=spans,
                           chunk_tags=ChunkTagRepository(seeded_store, collection_names, spans),
                           documents=documents, enrichment=Enrichment(derived=True))


@pytest.fixture
def owner(ids):
    return SimpleNamespace(id=UUID(ids.user["owner"]), is_superuser=False)


async def create(store, owner, ids, chunk, start, end, tag="person", type=SpanType.pos) -> UUID:
    result = await service.create_span(store, owner, PostSpan(chunkId=ids.chunk[chunk], tagId=ids.tag[tag],
                                                              start=start, end=end, type=type))
    assert result.outcome == "complete"
    return UUID(result.id)


def parse(response) -> list[dict[str, str]]:
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"\xef\xbb\xbf")
    return list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"), newline="")))


async def test_filter_scope_exports_the_concordance_with_positions_and_anchor_chunk_metadata(
        store, owner, ids, corpus, api_client, login):
    first = corpus.chunks["chronicle_1"]["text"]
    cross = await create(store, owner, ids, "chronicle_1", 80, len(first) + 8)
    rejected = await create(store, owner, ids, "chronicle_2", 29, 33, tag="place", type=SpanType.neg)
    collection = ids.col["chronicles"]
    listed = await service.query_annotations(store, owner, collection, limit=200)
    path = f"/api/user_collections/{collection}/annotations/export"
    headers = await login("owner")

    response = await api_client.post(path, headers=headers, json={"scope": "filters", "filters": {},
                                                                  "chunk_metadata": True, "provenance": True})
    rows = parse(response)
    assert sorted(UUID(r["annotation_id"]) for r in rows) == sorted(r.id for r in listed.rows)
    assert response.headers["x-export-count"] == str(listed.total) == str(len(rows))
    exported = next(r for r in rows if UUID(r["annotation_id"]) == cross)
    stored = await store.spans.read_row(UUID(collection), cross)
    assert (int(exported["document_start_char"]), int(exported["document_end_char"])) == \
        (stored.documentStartChar, stored.documentEndChar)
    assert exported["text"] == stored.text and exported["status"] == "confirmed"
    # The anchor chunk's values (chronicle_1), not a later chunk's or the document's summary.
    assert (exported["chunk_language"], exported["chunk_communicative_mode"], exported["chunk_complexity"]) == \
        ("ces", "narration", "moderate")
    assert "created_by" in exported  # spans created here hold no provenance; the columns are present
    seeded = [r for r in rows if r["text_status"] == "pending"]
    assert seeded and all(r["document_start_char"] == r["text"] == "" for r in seeded)

    selected = await api_client.post(path, headers=headers, json={"scope": "selection",
                                                                  "annotation_ids": [str(rejected), str(cross)]})
    assert sorted((UUID(r["annotation_id"]), r["status"]) for r in parse(selected)) == \
        sorted([(cross, "confirmed"), (rejected, "rejected")])
    assert rejected not in {r.id for r in listed.rows}  # outside the default filters, exported as selected

    shared = await api_client.post(path, headers=await login("annotator"), json={"scope": "collection", "types": ["pos"]})
    outsider = await api_client.post(path, headers=await login("outsider"),
                                     json={"scope": "collection", "types": ["pos"]})
    assert shared.status_code == 200
    assert outsider.status_code == 404 and b"annotation_id" not in outsider.content


async def test_chunk_metadata_reads_only_declared_properties(documents, ids):
    chunks = [UUID(ids.chunk["chronicle_1"]), UUID(ids.chunk["letters_1"])]
    found = await documents.read_chunk_metadata(chunks, ["language", "communicative_mode", "not_declared"])
    assert found == {chunks[0]: {"language": "ces", "communicative_mode": ["narration"]},
                     chunks[1]: {"language": "ces", "communicative_mode": ["interaction"]}}
