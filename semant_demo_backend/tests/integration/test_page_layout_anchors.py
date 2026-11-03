"""``Chunks.layoutStart`` and the page reads against the real test store (#541).

The fixture store, like the deployed stores, does not declare ``layoutStart``: reads work
without it. Declaring it is additive; a stored anchor then appears in every chunk
projection (document view, passage reads, Search, collection chunks, page chunks), and the
bounded page lookup selects chunks by their stored page range.
"""
from uuid import UUID

import pytest
from weaviate.classes.config import DataType, Property

from semant_demo.adapters.weaviate.layout_anchors import declare_layout_start, layout_start_state
from semant_demo.adapters.weaviate.search import ChunkSearchRepository
from semant_demo.features.documents.schemas import LayoutStart
from semant_demo.features.search.schemas import ChunkQuery, SearchType

pytestmark = pytest.mark.integration

ANCHOR = {"pageId": "5e3a0000-0000-4000-8000-0000000d1f02", "lineId": "r002-l001", "offset": 7, "match": "approximate"}


@pytest.fixture
async def anchored(seeded_store, collection_names, corpus):
    """The fixture store with ``layoutStart`` declared and stored on chunk ``chronicle_2``.
    The next ``seeded_store`` recreates the schema, as it differs."""
    chunks = collection_names.chunks_collection_name
    assert await layout_start_state(seeded_store, chunks) == "missing"
    await declare_layout_start(seeded_store, chunks)
    await declare_layout_start(seeded_store, chunks)  # repeatable
    assert await layout_start_state(seeded_store, chunks) == "declared"
    chunk_id = UUID(corpus.chunks["chronicle_2"]["id"])
    await seeded_store.collections.get(chunks).data.update(uuid=chunk_id, properties={"layoutStart": ANCHOR})
    return chunk_id


async def test_chunks_read_without_the_property(documents, corpus):
    chunk = await documents.read_chunk(UUID(corpus.chunks["chronicle_2"]["id"]))

    assert chunk.layoutStart is None


async def test_a_stored_anchor_appears_in_every_chunk_projection(anchored, documents, collections, seeded_store,
                                                                 collection_names, corpus):
    expected = LayoutStart(**ANCHOR)
    chronicle = UUID(corpus.documents["chronicle"]["id"])
    chronicles = UUID(corpus.collections["chronicles"]["id"])

    chunk = await documents.read_chunk(anchored)
    detail = await documents.read_chunks(chronicle, chronicles)
    listed = await collections.read_all_chunks_by_document(chronicle, chronicles)
    [hit] = [h for h in await ChunkSearchRepository(seeded_store, collection_names).search(
        ChunkQuery(text="slavnost Brně", mode=SearchType.text, limit=5)) if h.id == anchored]

    assert chunk.layoutStart == expected and isinstance(chunk.layoutStart.offset, int)
    assert {c.id: c.layoutStart for c in detail.chunks}[anchored] == expected
    assert {c.id: c.layoutStart for c in listed} == {UUID(corpus.chunks["chronicle_1"]["id"]): None, anchored: expected}
    assert hit.layoutStart == expected
    # Text and positions are unchanged by the anchor.
    assert chunk.text == corpus.chunks["chronicle_2"]["text"]


async def test_page_chunks_over_http(anchored, api_client, corpus):
    chronicle = corpus.documents["chronicle"]["id"]
    ids = {key: corpus.chunks[key]["id"] for key in ("chronicle_1", "chronicle_2", "chronicle_3")}

    page_1 = await api_client.get(f"/api/documents/{chronicle}/chunks/by_page", params={"page": 1})
    page_2 = await api_client.get(f"/api/documents/{chronicle}/chunks/by_page", params={"page": 2, "limit": 1})
    page_9 = await api_client.get(f"/api/documents/{chronicle}/chunks/by_page", params={"page": 9})
    window = await api_client.get(f"/api/documents/{chronicle}/chunks/{ids['chronicle_1']}/window")
    pages = await api_client.get(f"/api/documents/{chronicle}/pages")

    assert page_1.status_code == 200, page_1.text
    assert [c["id"] for c in page_1.json()["chunks"]] == [ids["chronicle_1"], ids["chronicle_2"]]
    assert page_1.json()["chunks"][1]["layoutStart"] == ANCHOR
    assert "layoutStart" not in page_1.json()["chunks"][0]
    assert ([c["id"] for c in page_2.json()["chunks"]], page_2.json()["has_more"]) == ([ids["chronicle_2"]], True)
    assert (page_9.json()["chunks"], page_9.json()["has_more"]) == ([], False)
    assert [c.get("layoutStart") for c in window.json()["chunks"]] == [None, ANCHOR, None]
    # The test app has no page asset directory: every document is text-only.
    assert pages.json() == {"document_id": chronicle, "available": False, "pages": []}


async def test_a_differently_declared_property_is_refused(weaviate_client, store_token):
    name = "LayoutConflictChunks"
    await weaviate_client.collections.delete(name)
    try:
        await weaviate_client.collections.create(name, properties=[Property(name="layoutStart", data_type=DataType.TEXT)])

        assert await layout_start_state(weaviate_client, name) == "conflict"
        with pytest.raises(ValueError, match="declared differently"):
            await declare_layout_start(weaviate_client, name)
    finally:
        await weaviate_client.collections.delete(name)
