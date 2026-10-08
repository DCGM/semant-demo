"""Multi-write operations report partial and total failure (ADR 0002, #201).

Failures are injected into real Weaviate writes (``fail_writes``); every test checks both
the reported outcome and the stored state: completed writes are kept, nothing is rolled
back, and loops over changing result sets terminate.
"""
import asyncio
import json
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from weaviate.classes.data import DataObject
from weaviate.exceptions import WeaviateTimeoutError

from semant_demo.routes import ai_assistance_routes

pytestmark = pytest.mark.integration


async def test_add_document_keeps_linked_chunks_when_one_link_fails(api_client, login, ids, store, fail_writes):
    c, gazette = ids.col["chronicles"], ids.doc["gazette"]
    fail_writes("reference_add", [ids.chunk["gazette_1"]])

    response = await api_client.post(f"/api/collections/{c}/documents/{gazette}", headers=await login("owner"))

    result = response.json()
    assert response.status_code == 200
    assert result["outcome"] == "partial"
    assert set(result["succeeded"]) == {ids.chunk["gazette_2"], gazette}
    assert [(f["item_id"], f["step"], f["uncertain"]) for f in result["failed"]] == [
        (ids.chunk["gazette_1"], "link_chunk", False)]
    assert c in await store.collections_of_chunk(ids.chunk["gazette_2"])
    assert c not in await store.collections_of_chunk(ids.chunk["gazette_1"])
    assert c in await store.collections_of_document(gazette)


async def test_add_document_fails_without_linking_the_document_when_no_chunk_links(
        api_client, login, ids, store, fail_writes):
    c, gazette = ids.col["chronicles"], ids.doc["gazette"]
    fail_writes("reference_add", [ids.chunk["gazette_1"], ids.chunk["gazette_2"]])

    result = (await api_client.post(f"/api/collections/{c}/documents/{gazette}", headers=await login("owner"))).json()

    assert result["outcome"] == "failed"
    assert result["succeeded"] == []
    assert result["unattempted"] == [gazette]
    assert c not in await store.collections_of_document(gazette)


async def test_timed_out_link_is_reported_as_uncertain(api_client, login, ids, fail_writes):
    c, gazette = ids.col["chronicles"], ids.doc["gazette"]
    fail_writes("reference_add", [ids.chunk["gazette_1"]], error=WeaviateTimeoutError("timed out"))

    result = (await api_client.post(f"/api/collections/{c}/documents/{gazette}", headers=await login("owner"))).json()

    assert [(f["item_id"], f["uncertain"]) for f in result["failed"]] == [(ids.chunk["gazette_1"], True)]


async def test_remove_document_keeps_document_while_a_chunk_stays_linked(api_client, login, ids, store, fail_writes):
    c, chronicle = ids.col["chronicles"], ids.doc["chronicle"]
    fail_writes("reference_delete", [ids.chunk["chronicle_2"]])

    result = (await api_client.delete(f"/api/collections/{c}/documents/{chronicle}", headers=await login("owner"))).json()

    assert result["outcome"] == "partial"
    assert result["succeeded"] == [ids.chunk["chronicle_1"]]
    assert result["unattempted"] == [chronicle]
    assert c not in await store.collections_of_chunk(ids.chunk["chronicle_1"])
    assert c in await store.collections_of_chunk(ids.chunk["chronicle_2"])
    assert c in await store.collections_of_document(chronicle)


async def test_add_chunk_reports_failed_document_link(api_client, login, ids, store, fail_writes):
    # The previous code logged this failure and reported plain success.
    c, chunk = ids.col["chronicles"], ids.chunk["gazette_1"]
    fail_writes("reference_add", [ids.doc["gazette"]])

    result = (await api_client.post(f"/api/user_collection/{c}/chunks/{chunk}", headers=await login("owner"))).json()

    assert result["outcome"] == "partial"
    assert result["succeeded"] == [chunk]
    assert [(f["item_id"], f["step"]) for f in result["failed"]] == [(ids.doc["gazette"], "link_document")]
    assert c in await store.collections_of_chunk(chunk)


async def test_bulk_span_update_reports_failed_spans(api_client, login, ids, store, fail_writes):
    lhota, praha = ids.span["lhota_automatic"], ids.span["praha_automatic"]
    fail_writes("update", [praha])

    response = await api_client.post("/api/tag_spans/bulk_update", headers=await login("annotator"),
                                     json={"span_ids": [lhota, praha], "update": {"type": "pos"}})

    result = response.json()
    assert result["outcome"] == "partial"
    assert [s["id"] for s in result["spans"]] == [lhota] == result["succeeded"]
    assert [f["item_id"] for f in result["failed"]] == [praha]
    assert (await store.span(lhota))["type"] == "pos"
    assert (await store.span(praha))["type"] == "auto"


async def test_scoped_span_delete_reports_failed_spans(api_client, login, ids, store, fail_writes):
    novak = ids.span["novak_manual"]
    fail_writes("delete_by_id", [novak])
    body = {"collection_id": ids.col["chronicles"], "document_id": ids.doc["chronicle"],
            "tag_ids": [ids.tag["person"], ids.tag["place"]]}

    result = (await api_client.post("/api/tag_spans/in_document/delete", headers=await login("owner"), json=body)).json()

    assert result["outcome"] == "partial"
    assert result["succeeded"] == [ids.span["brno_manual"]]
    assert result["deleted"] == 1
    assert [f["item_id"] for f in result["failed"]] == [novak]
    assert await store.span(novak) is not None
    assert await store.span(ids.span["brno_manual"]) is None


async def test_deletion_terminates_when_a_full_page_keeps_failing(
        api_client, login, ids, seeded_store, collection_names, fail_writes):
    # More failing spans than one 500-object page: the old loop refetched the same page forever.
    spans = seeded_store.collections.get(collection_names.span_collection_name)
    extra = await spans.data.insert_many([
        DataObject(properties={"start": 0, "end": 4, "type": "auto"},
                   references={"tag": ids.tag["place"], "text_chunk": ids.chunk["chronicle_1"]})
        for _ in range(501)
    ])
    assert not extra.has_errors
    fail_writes("delete_by_id", collection="Span")
    body = {"collection_id": ids.col["chronicles"], "document_id": ids.doc["chronicle"], "tag_ids": [ids.tag["place"]]}

    response = await asyncio.wait_for(
        api_client.post("/api/ai/auto_spans/delete", headers=await login("owner"), json=body), timeout=120)

    result = response.json()
    assert result["outcome"] == "failed"
    assert result["deleted"] == 0
    assert len(result["failed"]) == 502  # the 501 extra spans and the corpus' lhota_automatic


async def test_cascade_stops_when_deletes_do_not_take_effect(
        api_client, login, ids, store, seeded_store, collection_names, fail_writes):
    # A delete that reports success but leaves the span in place must not loop forever.
    # The cascade refetches its first 100-span page, so the guard matters for a full page.
    spans = seeded_store.collections.get(collection_names.span_collection_name)
    extra = await spans.data.insert_many([
        DataObject(properties={"start": 0, "end": 4, "type": "pos"},
                   references={"tag": ids.tag["place"], "text_chunk": ids.chunk["chronicle_1"]})
        for _ in range(100)
    ])
    assert not extra.has_errors
    fail_writes("delete_by_id", collection="Span", no_op=True)

    response = await asyncio.wait_for(
        api_client.delete(f"/api/tags/{ids.tag['place']}", headers=await login("owner")), timeout=60)

    assert response.status_code == 500
    assert await store.tag(ids.tag["place"]) is not None



async def test_cascade_stops_when_deletes_on_a_short_page_do_not_take_effect(
        api_client, login, ids, store, collection_names, fail_writes):
    # Only the corpus' few `place` spans match: a short last page must also be re-queried.
    fail_writes("delete_by_id", collection=collection_names.span_collection_name, no_op=True)

    response = await asyncio.wait_for(
        api_client.delete(f"/api/tags/{ids.tag['place']}", headers=await login("owner")), timeout=60)

    assert response.status_code == 500
    assert await store.tag(ids.tag["place"]) is not None
    assert await store.span(ids.span["brno_manual"]) is not None

# ── AI suggestions ─────────────────────────────────────────────────────────

def events_of(response):
    return [json.loads(line) for line in response.text.splitlines()]


async def test_ai_storage_failures_are_reported(api_client, login, ids, store, fake_topicer, fail_writes):
    spans_before = await store.span_count()
    fail_writes("insert", collection="Span")
    body = {"collection_id": ids.col["chronicles"], "document_id": ids.doc["chronicle"], "tag_ids": [ids.tag["person"]]}

    response = await api_client.post("/api/ai/suggest_spans/thorough", headers=await login("annotator"), json=body)

    events = events_of(response)
    assert sorted(e["unsaved"] for e in events) == [1, 1]
    assert all(e["spans"] == [] and "storage failure" in e["error"] for e in events)
    assert await store.span_count() == spans_before


async def test_ai_proposals_for_chunks_outside_the_collection_are_not_saved(
        api_client, login, ids, store, corpus, monkeypatch):
    # A provider returning a chunk that is not in the collection (chronicle_3 is in newspapers).
    provider = FastAPI()

    @provider.post("/v1/tags/propose/db/stream")
    async def stream(body: dict):
        foreign = corpus.chunks["chronicle_3"]
        event = {"id": foreign["id"], "text": foreign["text"], "tag_span_proposals": [
            {"tag": {"id": ids.tag["person"]}, "span_start": 0, "span_end": 5}]}
        return StreamingResponse(iter([json.dumps(event) + "\n"]), media_type="application/x-ndjson")

    @asynccontextmanager
    async def client():
        async with AsyncClient(transport=ASGITransport(app=provider), base_url="http://fake") as c:
            yield c

    monkeypatch.setattr(ai_assistance_routes, "topicer_client", client)
    spans_before = await store.span_count()
    body = {"collection_id": ids.col["chronicles"], "document_id": ids.doc["chronicle"], "tag_ids": [ids.tag["person"]]}

    response = await api_client.post("/api/ai/suggest_spans/optimized", headers=await login("owner"), json=body)

    [event] = events_of(response)
    assert (event["spans"], event["unsaved"]) == ([], 1)
    assert "chunk outside the collection" in event["error"]
    assert await store.span_count() == spans_before
