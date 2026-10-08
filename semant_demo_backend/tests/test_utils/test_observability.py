import json

from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from semant_demo.config import SCRIPT_PATH
from semant_demo.main import create_app
from semant_demo.opentelemetry import (
    OpenTelemetry,
    RequestTelemetryMiddleware,
    feature_for_request,
    request_authentication,
    request_outcome,
)
from tests.app_support import make_test_config


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
    assert feature_for_request("/api/tags", "POST") == "tagging"
    assert feature_for_request("/api/tag_spans", "POST") == "tagging"
    assert feature_for_request("/api/tag_spans/bulk_update", "POST") == "tagging"

    assert feature_for_request("/api/rag/configurations", "GET") is None
    assert feature_for_request("/health", "GET") is None


def test_usage_metric_attributes_are_low_cardinality():
    assert request_authentication(None) == "anonymous"
    assert request_authentication("Bearer token-value-is-not-recorded") == "bearer_token"
    assert request_outcome(201) == "success"
    assert request_outcome(401) == "client_error"
    assert request_outcome(503) == "server_error"


def test_classified_feature_paths_exist_in_the_api():
    """Feature metrics must follow route renames instead of silently counting nothing."""
    schema = json.loads((SCRIPT_PATH.parent / "openapi.json").read_text())
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
