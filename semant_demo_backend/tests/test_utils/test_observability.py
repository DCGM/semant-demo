from semant_demo.opentelemetry import (
    feature_for_request,
    request_authentication,
    request_outcome,
)


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
