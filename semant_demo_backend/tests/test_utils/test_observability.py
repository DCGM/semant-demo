import json
import logging

import pytest

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from semant_demo.core.request_context import current_request_id
from semant_demo.main import create_app
from semant_demo.routes.dependencies import get_llm
from semant_demo.opentelemetry import (
    OpenTelemetry,
    UNMATCHED_ROUTE,
    RequestTelemetryMiddleware,
    UnhandledRequestError,
    feature_for_request,
    request_authentication,
    request_outcome,
)
from tests.app_support import make_test_config, offline_weaviate
from tests.fakes import FakeLlm


class RecordingInstrument:
    def __init__(self):
        self.calls = []

    def add(self, value, *, attributes):
        self.calls.append((value, attributes))

    def record(self, value, *, attributes):
        self.calls.append((value, attributes))


def test_feature_for_request_tracks_user_actions_only():
    assert feature_for_request("/api/rag", "POST") == "rag"
    assert feature_for_request("/api/search", "POST") == "search"
    assert feature_for_request("/api/ai/suggest_spans/optimized", "POST") == "ai_assistance"
    assert feature_for_request("/api/question", "POST") == "summarize"
    assert feature_for_request("/api/tags", "POST") == "tagging"
    assert feature_for_request("/api/tag_spans", "POST") == "tagging"
    assert feature_for_request("/api/tag_spans/bulk_update", "POST") == "tagging"

    assert feature_for_request("/api/rag/configurations", "GET") is None
    assert feature_for_request("/health", "GET") is None
    assert feature_for_request("/api/question/no-longer-a-route", "POST") is None


def test_usage_metric_attributes_are_low_cardinality():
    assert request_authentication(None) == "anonymous"
    assert request_authentication("Bearer token-value-is-not-recorded") == "bearer_token"
    assert request_outcome(201) == "success"
    assert request_outcome(401) == "client_error"
    assert request_outcome(503) == "server_error"


def test_classified_feature_paths_exist_in_the_api(tmp_path):
    """Feature metrics must follow route renames instead of silently counting nothing."""
    schema = create_app(make_test_config(tmp_path)).openapi()
    post_paths = [path for path, operations in schema["paths"].items() if "post" in operations]
    classified = {feature_for_request(path, "POST") for path in post_paths}
    assert {"rag", "search", "summarize", "ai_assistance", "tagging"} <= classified


def _recording_telemetry(counter=None, duration=None) -> OpenTelemetry:
    return OpenTelemetry(
        tracer=None,
        meter=None,
        logger=None,
        feature_request_counter=counter or RecordingInstrument(),
        feature_request_duration_histogram=duration or RecordingInstrument(),
        llm_call_counter=RecordingInstrument(),
        llm_call_duration_histogram=RecordingInstrument(),
        llm_token_counter=RecordingInstrument(),
        llm_cost_counter=RecordingInstrument(),
        trace_provider=None,
        meter_provider=None,
        log_provider=None,
        logging_handler=None,
        logging_instrumentator=None,
        system_metric_instrumentator=None,
        fastapi_instrumentator=None,
    )


def test_feature_request_records_counter_and_duration_with_same_attributes():
    counter = RecordingInstrument()
    duration = RecordingInstrument()
    telemetry = _recording_telemetry(counter, duration)

    telemetry.record_feature_request(
        feature="rag",
        authentication="bearer_token",
        status_code=201,
        duration_seconds=0.42,
    )

    expected_attributes = {
        "feature": "rag",
        "authentication": "bearer_token",
        "outcome": "success",
    }
    assert counter.calls == [(1, expected_attributes)]
    assert duration.calls == [(0.42, expected_attributes)]


def test_llm_call_records_known_tokens_and_cost_only():
    telemetry = _recording_telemetry()
    attributes = {"feature": "rag", "tier": "large", "provider": "openai", "model": "m", "usage_source": "provider"}

    telemetry.record_llm_call(attributes=attributes, outcome="success", duration_seconds=1.5,
                              input_tokens=100, output_tokens=20, cost_usd=0.001)
    telemetry.record_llm_call(attributes={**attributes, "usage_source": "estimated"}, outcome="error",
                              duration_seconds=0.1, input_tokens=None, output_tokens=None, cost_usd=None)

    assert telemetry.llm_call_counter.calls == [(1, {**attributes, "outcome": "success"}),
                                                (1, {**attributes, "usage_source": "estimated", "outcome": "error"})]
    assert [v for v, _ in telemetry.llm_call_duration_histogram.calls] == [1.5, 0.1]
    assert telemetry.llm_token_counter.calls == [(100, {**attributes, "token_type": "input"}),
                                                 (20, {**attributes, "token_type": "output"})]
    assert telemetry.llm_cost_counter.calls == [(0.001, attributes)]


def _middleware_app(telemetry: OpenTelemetry | None) -> RequestTelemetryMiddleware:
    async def search(request):
        return JSONResponse({"ok": True}, status_code=201)

    async def stream(request):
        async def lines():
            yield b"one\n"
            yield b"two\n"
        return StreamingResponse(lines(), media_type="application/x-ndjson")

    app = Starlette(routes=[
        Route("/api/search", search, methods=["POST"]),
        Route("/api/ai/suggest_spans/optimized", stream, methods=["POST"]),
        Route("/health", search, methods=["GET"]),
    ])
    return RequestTelemetryMiddleware(app, telemetry=telemetry)


async def test_request_id_is_available_while_the_request_is_served():
    async def endpoint(request):
        return JSONResponse({"request_id": current_request_id.get()})

    app = RequestTelemetryMiddleware(Starlette(routes=[Route("/api/search", endpoint, methods=["POST"])]))
    async with _client(app) as client:
        response = await client.post("/api/search", headers={"X-Request-ID": "req-7"})

    assert response.json() == {"request_id": "req-7"}
    assert current_request_id.get() is None


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_middleware_returns_request_id_and_records_feature_metrics():
    counter = RecordingInstrument()
    async with _client(_middleware_app(_recording_telemetry(counter))) as client:
        given = await client.post("/api/search", headers={"X-Request-ID": "req-1", "Authorization": "Bearer t"})
        generated = await client.get("/health")

    assert given.status_code == 201
    assert given.headers["X-Request-ID"] == "req-1"
    assert generated.headers["X-Request-ID"]
    assert counter.calls == [(1, {"feature": "search", "authentication": "bearer_token", "outcome": "success"})]


async def test_middleware_passes_streamed_responses_through():
    counter = RecordingInstrument()
    async with _client(_middleware_app(_recording_telemetry(counter))) as client:
        response = await client.post("/api/ai/suggest_spans/optimized")

    assert response.text == "one\ntwo\n"
    assert counter.calls == [(1, {"feature": "ai_assistance", "authentication": "anonymous", "outcome": "success"})]


async def test_middleware_logs_without_telemetry():
    async with _client(_middleware_app(None)) as client:
        response = await client.post("/api/search")

    assert response.status_code == 201
    assert response.headers["X-Request-ID"]


def test_telemetry_is_disabled_unless_configured(tmp_path):
    app = create_app(make_test_config(tmp_path))

    assert app.state.telemetry is None


QUESTION = "Who owned the mill in Lhota?"
QUESTION_IN_URL = "Who%20owned%20the%20mill%20in%20Lhota%3F"


def _path_text_app() -> FastAPI:
    app = FastAPI()

    @app.post("/api/echo/{text}")
    async def echo(text: str):
        if text.startswith("fail"):
            raise RuntimeError("endpoint failed")
        return {"ok": True}

    app.add_middleware(RequestTelemetryMiddleware)
    return app


def _request_records(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "semant_demo.opentelemetry"]


def _exported_values(record: logging.LogRecord) -> str:
    return " ".join(str(value) for value in vars(record).values())


async def test_completed_request_is_logged_at_info_with_route_template(caplog):
    caplog.set_level(logging.INFO, logger="semant_demo.opentelemetry")
    async with _client(_path_text_app()) as client:
        response = await client.post(f"/api/echo/{QUESTION_IN_URL}?context={QUESTION_IN_URL}")

    assert response.status_code == 200
    [record] = _request_records(caplog)
    assert record.levelno == logging.INFO
    assert record.getMessage() == "HTTP request completed"
    assert record.__dict__["http.route"] == "/api/echo/{text}"
    assert record.__dict__["http.response.status_code"] == 200
    assert "Lhota" not in _exported_values(record)


async def test_failed_request_log_does_not_contain_path_text(caplog):
    caplog.set_level(logging.INFO, logger="semant_demo.opentelemetry")
    transport = ASGITransport(app=_path_text_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/echo/fail%20secret%20Lhota")

    assert response.status_code == 500
    [record] = _request_records(caplog)
    assert record.getMessage().startswith("HTTP request failed: RuntimeError\n")
    assert record.__dict__["http.route"] == "/api/echo/{text}"
    assert "Lhota" not in _exported_values(record)


async def test_unmatched_path_is_logged_as_placeholder(caplog):
    caplog.set_level(logging.INFO, logger="semant_demo.opentelemetry")
    async with _client(_path_text_app()) as client:
        response = await client.get("/no/such/Lhota")

    assert response.status_code == 404
    [record] = _request_records(caplog)
    assert record.__dict__["http.route"] == UNMATCHED_ROUTE
    assert "Lhota" not in _exported_values(record)


@pytest.mark.parametrize("question", [QUESTION_IN_URL, "fail%20Lhota"], ids=["success", "error"])
async def test_server_span_does_not_contain_path_or_query_text(question):
    spans = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(spans))
    app = _path_text_app()
    FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider, meter_provider=MeterProvider())
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(f"/api/echo/{question}?context={QUESTION_IN_URL}")
    finally:
        FastAPIInstrumentor.uninstrument_app(app)

    [server_span] = [span for span in spans.get_finished_spans() if span.kind.name == "SERVER"]
    assert server_span.attributes["http.target"] == "/api/echo/{text}"
    for span in spans.get_finished_spans():
        assert "Lhota" not in json.dumps(dict(span.attributes)) + span.name


async def test_question_text_is_in_neither_the_url_nor_request_logs_nor_server_span(tmp_path, caplog):
    private_question = "Kdo byl tajný kronikář v Lhotě?"
    spans = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(spans))
    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    app.dependency_overrides[get_llm] = lambda: FakeLlm(lambda messages: "Nevím [doc1].")
    FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider, meter_provider=MeterProvider())
    search_request = {"query": "kronika", "tag_uuids": [], "positive": False, "automatic": False}
    search_response = {"results": [], "search_request": search_request, "time_spent": 0.1, "search_log": []}
    caplog.set_level(logging.DEBUG)
    try:
        async with app.router.lifespan_context(app):
            async with _client(app) as client:
                response = await client.post("/api/question", json={
                    "question_text": private_question, "search_response": search_response})
    finally:
        FastAPIInstrumentor.uninstrument_app(app)

    assert response.status_code == 200 and response.json()["summary"] == "Nevím [doc1]."
    # The request target, which proxies and uvicorn's access log record, carries no text.
    assert str(response.request.url) == "http://test/api/question"
    [record] = _request_records(caplog)
    assert record.__dict__["http.route"] == "/api/question"
    assert "Lhot" not in caplog.text and "kronikář" not in caplog.text
    [server_span] = [span for span in spans.get_finished_spans() if span.kind.name == "SERVER"]
    assert server_span.attributes["http.target"] == "/api/question"
    for span in spans.get_finished_spans():
        assert "Lhot" not in json.dumps(dict(span.attributes)) + span.name


SECRET_ERROR_TEXT = "SECRET-MARKER provider body"


def _failing_app() -> FastAPI:
    app = FastAPI()

    @app.post("/api/fail")
    async def fail():
        try:
            raise ValueError(SECRET_ERROR_TEXT)
        except ValueError as e:
            raise RuntimeError(SECRET_ERROR_TEXT) from e

    app.add_middleware(RequestTelemetryMiddleware)
    return app


async def test_unhandled_error_is_logged_with_its_stack_but_no_exception_text(caplog):
    caplog.set_level(logging.INFO, logger="semant_demo.opentelemetry")
    async with _client(_failing_app()) as client:
        with pytest.raises(UnhandledRequestError) as raised:
            await client.post("/api/fail")

    [record] = _request_records(caplog)
    assert record.levelno == logging.ERROR and record.exc_info is None
    assert record.__dict__["error.type"] == "RuntimeError"
    message = record.getMessage()
    assert "in fail" in message and "RuntimeError (message omitted)" in message
    assert "ValueError (message omitted)" in message
    assert "SECRET-MARKER" not in _exported_values(record)
    # What the server and the server span see: the class name only, no chained original.
    assert str(raised.value) == "RuntimeError" and raised.value.__suppress_context__


async def test_server_span_records_no_exception_text():
    spans = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(spans))
    app = _failing_app()
    FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider, meter_provider=MeterProvider())
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/fail")
    finally:
        FastAPIInstrumentor.uninstrument_app(app)

    assert response.status_code == 500
    events = [event for span in spans.get_finished_spans() for event in span.events]
    assert [event.attributes["exception.type"] for event in events if event.name == "exception"]
    assert "SECRET-MARKER" not in json.dumps([dict(event.attributes) for event in events])
