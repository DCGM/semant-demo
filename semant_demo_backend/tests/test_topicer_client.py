"""Topicer failures name only the error class or HTTP status, in logs and in suggestion events (#301)."""
import httpx
import pytest

from semant_demo.adapters.topicer.client import TopicerClient, TopicerError, TopicerTag

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
