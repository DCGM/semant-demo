"""AI suggestion streams against real Weaviate, with deterministic Topicer stand-ins (#207).

Saved suggestions must reload through the span API and be findable by tag-filtered
search; a provider failure keeps what was saved; a client disconnect on a real server
stops the remaining provider calls. The workflow's cases are covered with fakes in
tests/test_suggestions.py.
"""
import asyncio
import json
import socket

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

pytestmark = pytest.mark.integration


NO_SUMMARY = {"search_title_generate": False, "search_summary_generate": False,
              "search_results_summary_generate": False}


def lines_of(response):
    *results, end = [json.loads(line) for line in response.text.splitlines()]
    assert end["event"] == "end" and all(r["event"] == "result" for r in results)
    return results, end


def text_provider(answer):
    """A Topicer stand-in whose ``/v1/tags/propose/texts`` answers ``await answer(text, tags)``."""
    app = FastAPI()

    @app.post("/v1/tags/propose/texts")
    async def propose(body: dict):
        result = await answer(body["text_chunk"]["text"], body["tags"])
        if isinstance(result, JSONResponse):
            return result
        return {"text_chunk": body["text_chunk"], "tag_span_proposals": result}
    return app


def proposal(tag_id, start, end):
    return {"tag": {"id": tag_id}, "span_start": start, "span_end": end, "reason": "test", "confidence": 0.9}


@pytest.fixture
def reload_spans(api_client, login, ids):
    async def read(chunk_keys, collection="chronicles"):
        response = await api_client.post("/api/tag_spans/batch", headers=await login("owner"), json={
            "collection_id": ids.col[collection], "chunk_ids": [ids.chunk[k] for k in chunk_keys]})
        assert response.status_code == 200, response.text
        return {span["id"]: span for spans in response.json().values() for span in spans}
    return read


async def test_saved_suggestions_reload_and_are_findable_by_tag(api_client, login, ids, fake_topicer, reload_spans):
    body = {"collection_id": ids.col["chronicles"], "document_id": ids.doc["chronicle"],
            "tag_ids": [ids.tag["person"], ids.tag["place"]]}

    response = await api_client.post("/api/ai/suggest_spans/thorough", headers=await login("annotator"), json=body)

    results, end = lines_of(response)
    announced = {s["id"]: s for r in results for s in r["spans"]}
    assert (end["outcome"], end["saved"]) == ("complete", 2)  # "Jan Novák" in both chunks ("Brno" in none)
    stored = await reload_spans(["chronicle_1", "chronicle_2"])
    assert all(stored[i] == announced[i] and stored[i]["type"] == "auto" for i in announced)
    # chronicle_2 had no automatic "person" reference before; "odjel" occurs only there.
    search = await api_client.post("/api/search", headers=await login("owner"), json={
        "query": "odjel", "type": "text", "user_collection_id": ids.col["chronicles"],
        "tag_uuids": [ids.tag["person"]], "positive": False, "automatic": True, **NO_SUMMARY})
    assert search.status_code == 200, search.text
    assert [r["id"] for r in search.json()["results"]] == [ids.chunk["chronicle_2"]]


async def test_provider_failure_after_partial_success_keeps_saved_suggestions(
        api_client, login, ids, corpus, use_topicer, reload_spans):
    async def answer(text, tags):
        if text == corpus.chunks["chronicle_1"]["text"]:
            return [proposal(ids.tag["person"], 34, 43)]
        return JSONResponse(status_code=503, content={"detail": "overloaded"})
    use_topicer(text_provider(answer))
    body = {"collection_id": ids.col["chronicles"], "document_id": ids.doc["chronicle"],
            "tag_ids": [ids.tag["person"]]}

    response = await api_client.post("/api/ai/suggest_spans/thorough", headers=await login("owner"), json=body)

    results, end = lines_of(response)
    assert (end["outcome"], end["saved"], end["provider_failures"]) == ("partial", 1, 1)
    assert any(r["error"] and r["error"].startswith("topicer:") for r in results)
    [saved] = [s for r in results for s in r["spans"]]
    assert (saved["start"], saved["end"]) == (34, 43)
    assert saved["id"] in await reload_spans(["chronicle_1"])


async def test_suggestion_offsets_are_stored_in_utf16_units(api_client, login, ids, corpus, use_topicer, reload_spans):
    text = corpus.chunks["letters_2"]["text"]  # ends with an emoji: one code point, two UTF-16 units

    async def answer(sent, tags):
        return [proposal(ids.tag["person"], sent.index("Karel"), len(sent))] if sent == text else []
    use_topicer(text_provider(answer))
    body = {"collection_id": ids.col["chronicles"], "document_id": ids.doc["letters"],
            "tag_ids": [ids.tag["person"]]}

    response = await api_client.post("/api/ai/suggest_spans/thorough", headers=await login("owner"), json=body)

    [saved] = [s for r in lines_of(response)[0] for s in r["spans"]]
    assert (saved["start"], saved["end"]) == (text.index("Karel"), len(text) + 1)
    assert saved["id"] in await reload_spans(["letters_2"])


async def test_selection_suggestion_across_chunks_is_stored_like_a_user_span(
        api_client, login, ids, corpus, use_topicer, reload_spans):
    first, second = corpus.chunks["letters_1"]["text"], corpus.chunks["letters_2"]["text"]
    selected = first[first.index("ošklivé"):] + second[:len("Pozdravuj")]

    async def answer(sent, tags):
        return [proposal(ids.tag["person"], 0, len(sent))] if sent == selected else []
    use_topicer(text_provider(answer))
    body = {"collection_id": ids.col["chronicles"], "document_id": ids.doc["letters"],
            "chunk_ids": [ids.chunk["letters_1"], ids.chunk["letters_2"]],
            "selection_start": first.index("ošklivé"), "selection_end": len(first) + len("Pozdravuj"),
            "tag_ids": [ids.tag["person"]]}

    response = await api_client.post("/api/ai/suggest_spans/selection", headers=await login("owner"), json=body)

    results, end = lines_of(response)
    [saved] = [s for r in results for s in r["spans"]]
    assert end["outcome"] == "complete"
    assert (saved["chunkId"], saved["start"], saved["end"]) == (
        ids.chunk["letters_1"], first.index("ošklivé"), len(first) + len("Pozdravuj"))
    # The same offsets are accepted for a user-created span (offset validation, #206).
    manual = await api_client.post("/api/tag_spans", headers=await login("owner"), json={
        "chunkId": saved["chunkId"], "tagId": saved["tagId"], "start": saved["start"], "end": saved["end"],
        "type": "pos"})
    assert manual.status_code == 200, manual.text
    assert saved["id"] in await reload_spans(["letters_1"])


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_disconnect_on_a_real_server_stops_remaining_provider_calls(
        api_app, login, ids, corpus, use_topicer, reload_spans, store):
    # In-process transports buffer responses; this runs the app on uvicorn and closes the socket.
    cancelled, started = asyncio.Event(), asyncio.Event()

    async def answer(text, tags):
        if text == corpus.chunks["chronicle_1"]["text"]:
            return [proposal(ids.tag["person"], 34, 43)]
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
    use_topicer(text_provider(answer))
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(api_app, host="127.0.0.1", port=port, lifespan="off", log_level="warning"))
    serving = asyncio.create_task(server.serve())
    try:
        while not server.started:
            await asyncio.sleep(0.01)
        headers = await login("owner")
        spans_before = await store.span_count()
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=30) as client:
            async with client.stream("POST", "/api/ai/suggest_spans/thorough", headers=headers, json={
                    "collection_id": ids.col["chronicles"], "document_id": ids.doc["chronicle"],
                    "tag_ids": [ids.tag["person"]]}) as response:
                first = json.loads(await anext(response.aiter_lines()))
                await asyncio.wait_for(started.wait(), 10)
            # Leaving the block closes the connection before the stream ended.

        await asyncio.wait_for(cancelled.wait(), 10)
        assert len(first["spans"]) == 1
        assert first["spans"][0]["id"] in await reload_spans(["chronicle_1"])
        assert await store.span_count() == spans_before + 1
    finally:
        server.should_exit = True
        await serving
