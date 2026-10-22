"""Topicer failures name only the error class or HTTP status, in logs and in suggestion events (#301);
reported usage, the per-tag chunk limit and the stream's usage summary (#408)."""
import json

import httpx
import pytest

from semant_demo.adapters.topicer.client import TopicerClient, TopicerError, TopicerStreamSummary, TopicerTag

SECRET = "SECRET-MARKER"
TAG = TopicerTag(id="t1", name="Person", definition="A person", examples=[])


def _logged(caplog) -> str:
    # httpx's own INFO request log (configured URL and status) is not covered here.
    return "\n".join(r.getMessage() for r in caplog.records if r.name == "semant_demo.adapters.topicer.client")


def _client(handler) -> TopicerClient:
    return TopicerClient(f"http://{SECRET}-host", f"{SECRET}-config", 5.0, transport=httpx.MockTransport(handler))


def _failing(status: int):
    return lambda request: httpx.Response(status, text=f"{SECRET} response body")


def _unreachable(request):
    raise httpx.ConnectError(f"{SECRET} cannot connect", request=request)


@pytest.mark.parametrize("handler, expected", [(_failing(503), "HTTP 503"), (_unreachable, "ConnectError")])
async def test_failed_text_call_hides_url_and_response(handler, expected, caplog):
    with pytest.raises(TopicerError) as raised:
        await _client(handler).propose_for_text(chunk_id="c1", text="Jan Novák", tags=[TAG])

    assert str(raised.value) == expected
    assert _logged(caplog) == f"Topicer POST /v1/tags/propose/texts failed for chunk c1: {expected}"
    assert "Novák" not in _logged(caplog)


@pytest.mark.parametrize("handler, expected", [(_failing(500), "HTTP 500"), (_unreachable, "ConnectError")])
async def test_failed_stream_call_hides_url_and_response(handler, expected, caplog):
    with pytest.raises(TopicerError) as raised:
        async for _ in _client(handler).propose_for_db_stream(tag=TAG, collection_id="col", document_id="doc"):
            pass

    assert str(raised.value) == expected
    assert _logged(caplog) == f"Topicer POST /v1/tags/propose/db/stream failed (tag=t1, doc=doc): {expected}"


async def test_invalid_stream_line_is_logged_without_its_content(caplog):
    def handler(request):
        return httpx.Response(200, text=f'Jan Novák {SECRET}\n{{"id": "c1", "tag_span_proposals": []}}\n')

    events = [e async for e in _client(handler).propose_for_db_stream(tag=TAG, collection_id="col", document_id="doc")]

    assert events == [{"id": "c1", "tag_span_proposals": []}]
    assert _logged(caplog) == "Topicer stream produced a line that is not a JSON object (23 characters)"


# ── Usage and per-tag chunk limit (DCGM/topicer#81, #408) ──────────────────

USAGE = {"attempted_calls": 2, "completed_calls": 1, "failed_calls": 1, "calls": [
    {"provider": "openrouter", "model": "m", "outcome": "success", "input_tokens": 1200, "output_tokens": 160,
     "usage_source": "reported", "cost_usd": 0.002, "cost_source": "reported"},
    {"provider": "openrouter", "model": "m", "outcome": "error", "input_tokens": None, "output_tokens": None,
     "usage_source": "unknown", "cost_usd": None, "cost_source": "unknown"}]}


def _answer(body):
    # json.dumps, unlike httpx's json=, writes Infinity as Topicer's Python json would.
    return _client(lambda request: httpx.Response(200, content=json.dumps(body)))


async def test_text_answer_carries_its_reported_usage():
    answer = await _answer({"tag_span_proposals": [], "usage": USAGE}).propose_for_text(
        chunk_id="c1", text="Jan", tags=[TAG])

    assert answer.proposals == [] and answer.usage.attempted_calls == 2
    assert [(c.outcome, c.cost_usd, c.cost_source, c.input_tokens) for c in answer.usage.calls] == [
        ("success", 0.002, "reported", 1200), ("error", None, "unknown", None)]


@pytest.mark.parametrize("usage", [
    None,                                                   # an older Topicer
    {"calls": "many"},
    {"calls": [{"cost_usd": "0.1"}]},
    {"calls": [{"cost_usd": -1.0}]},
    {"calls": [{"cost_usd": float("inf")}]},
])
async def test_missing_or_malformed_text_usage_is_unknown(usage):
    answer = await _answer({"tag_span_proposals": [], "usage": usage}).propose_for_text(
        chunk_id="c1", text="Jan", tags=[TAG])

    assert answer.usage is None


async def test_unitemized_attempts_are_counted():
    answer = await _answer({"tag_span_proposals": [], "usage": {**USAGE, "attempted_calls": 5}}).propose_for_text(
        chunk_id="c1", text="Jan", tags=[TAG])

    assert (len(answer.usage.calls), answer.usage.attempted_calls) == (2, 5)


async def test_every_stream_request_sends_the_configured_chunk_limit():
    seen = []

    def handler(request):
        seen.append((dict(request.url.params), request.content))
        return httpx.Response(200, text="")

    client = TopicerClient("http://topicer", "llm-openrouter", 5.0, max_chunks_per_tag=20,
                           transport=httpx.MockTransport(handler))
    for _ in range(2):
        [e async for e in client.propose_for_db_stream(tag=TAG, collection_id="col", document_id="doc")]

    assert [params for params, _ in seen] == [{"config_name": "llm-openrouter", "max_chunks": "20"}] * 2
    assert all(b'"db_request":{"collection_id":"col","document_id":"doc"}' in body.replace(b" ", b"")
               for _, body in seen)


async def test_stream_summary_is_yielded_apart_from_chunks_and_other_events_are_skipped(caplog):
    summary = {"event": "usage_summary", "status": "complete", "tag_id": "t1", "max_chunks": 40,
               "max_chunks_source": "request", "processed_chunks": 40, "limit_reached": True,
               "candidates_truncated": True, "usage": USAGE}
    lines = [{"id": "c1", "tag_span_proposals": []}, {"event": "progress"}, summary]

    events = [e async for e in _answer_stream(lines)]

    chunk, parsed = events
    assert chunk == {"id": "c1", "tag_span_proposals": []}
    assert isinstance(parsed, TopicerStreamSummary)
    assert (parsed.max_chunks, parsed.processed_chunks, parsed.limit_reached, parsed.candidates_truncated) == \
        (40, 40, True, True)
    assert len(parsed.usage.calls) == 2
    assert "unknown or malformed event" in caplog.text


@pytest.mark.parametrize("broken", [
    {"status": "complete", "processed_chunks": 1},          # no usage
    {"status": "done", "processed_chunks": 1, "usage": USAGE},
    {"status": "complete", "processed_chunks": -1, "usage": USAGE},
    {"status": "complete", "processed_chunks": 1, "usage": {"calls": [{"cost_usd": "x"}]}},
])
async def test_a_malformed_summary_is_not_yielded(broken):
    events = [e async for e in _answer_stream([{"event": "usage_summary", **broken}])]

    assert events == []


@pytest.mark.parametrize("handler, no_work", [
    (_failing(422), True), (_unreachable, True), (_failing(500), False), (_failing(429), False)])
async def test_only_certainly_unprocessed_requests_are_marked_as_no_work(handler, no_work):
    with pytest.raises(TopicerError) as raised:
        async for _ in _client(handler).propose_for_db_stream(tag=TAG, collection_id="col", document_id="doc"):
            pass

    assert raised.value.no_work is no_work


@pytest.mark.parametrize("limit", [0, -1, True, 2.5])
def test_an_invalid_chunk_limit_is_refused(limit):
    with pytest.raises(ValueError, match="TOPICER_MAX_CHUNKS_PER_TAG"):
        TopicerClient("http://topicer", "c", 5.0, max_chunks_per_tag=limit)


def _answer_stream(lines):
    text = "".join(json.dumps(line) + "\n" for line in lines)
    return _client(lambda request: httpx.Response(200, text=text)).propose_for_db_stream(
        tag=TAG, collection_id="col", document_id="doc")
