from semant_demo.opentelemetry import (
    OpenTelemetry,
    feature_for_request,
    request_authentication,
    request_outcome,
)


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

    assert feature_for_request("/api/rag/configurations", "GET") is None
    assert feature_for_request("/health", "GET") is None


def test_usage_metric_attributes_are_low_cardinality():
    assert request_authentication(None) == "anonymous"
    assert request_authentication("Bearer token-value-is-not-recorded") == "bearer_token"
    assert request_outcome(201) == "success"
    assert request_outcome(401) == "client_error"
    assert request_outcome(503) == "server_error"


def test_feature_request_records_counter_and_duration_with_same_attributes():
    counter = RecordingInstrument()
    duration = RecordingInstrument()
    telemetry = OpenTelemetry(
        tracer=None,
        meter=None,
        logger=None,
        feature_request_counter=counter,
        feature_request_duration_histogram=duration,
        trace_provider=None,
        meter_provider=None,
        log_provider=None,
        logging_handler=None,
        logging_instrumentator=None,
        system_metric_instrumentator=None,
        fastapi_instrumentator=None,
    )

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
