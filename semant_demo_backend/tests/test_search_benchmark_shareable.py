"""Manifests leave out where things run (#712): hosts, URLs and local paths."""
from semant_demo.benchmarks.search_relevance.shareable import NOT_RECORDED, shareable


def test_private_values_are_left_out_at_any_depth_and_the_rest_is_kept():
    manifest = {"store": {"host": "10.0.0.5", "rest_port": 8080, "token_file": "/home/x/token"},
                "models": {"judge": {"model": "qwen3.5:9b", "model_endpoint": "http://gpu-host:11434"}},
                "methods": [{"id": "vector", "endpoint": "http://embedder/v1", "settings": {"base_url": "http://e/v1"}}],
                "source": {"description": "test database", "host": None}}
    assert shareable(manifest) == {
        "store": {"host": NOT_RECORDED, "rest_port": 8080, "token_file": NOT_RECORDED},
        "models": {"judge": {"model": "qwen3.5:9b", "model_endpoint": NOT_RECORDED}},
        "methods": [{"id": "vector", "endpoint": NOT_RECORDED, "settings": {"base_url": NOT_RECORDED}}],
        "source": {"description": "test database", "host": None}}
