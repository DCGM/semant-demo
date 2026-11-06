"""The endpoint confirmation of the offline embedder's CLI (data_tools/embedder, #596).

Every pipeline run and ``--create-test-collection`` write, so each needs
``--confirm-endpoint HOST:PORT`` equal to the configured Weaviate endpoint, checked before
any connection. The connection and the runs are replaced here; the pipeline itself is
tested against Weaviate in ``tests/integration/test_embedder_tool.py``.
"""
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parents[2] / "data_tools" / "embedder"))
import semantembedder.db as db  # noqa: E402
from semantembedder.__main__ import main  # noqa: E402
from semantembedder.pipeline import EmbeddingPipeline  # noqa: E402

CONFIG = {
    "weaviate_host": "weaviate.example", "weaviate_port": 18080, "weaviate_grpc_port": 15051,
    "weaviate_api_key": None, "weaviate_headers": None, "collection": "EmbedderTest",
    "vector_name": "tool_vector", "create_vector": True, "vector_index_type": "hnsw",
    "distance_metric": "cosine", "return_properties": None, "max_records": None, "scan_batch_size": 3,
    "embed_batch_size": 2, "max_concurrent_requests": 1, "max_concurrent_writes": 1, "max_retries": 0,
    "retry_delay": 0.0,
    "embedder": {"cls": "VLLMEmbedder", "config": {
        "base_url": "http://embedder.example/v1", "api_key": "test-key", "model_name": "fake",
        "input_template": "{{ text }}", "dimensions": None, "truncate_prompt_tokens": None,
        "extra_body": None, "timeout": 1.0, "max_retries": 0}},
}


@pytest.fixture
def config(tmp_path) -> str:
    path = tmp_path / "embedder.yaml"
    path.write_text(yaml.safe_dump(CONFIG))
    return str(path)


@pytest.fixture
def started(monkeypatch) -> list[str]:
    """What started: ``run`` (the pipeline) or ``create`` (the test collection); nothing connects."""
    calls = []

    def run(self):
        calls.append("run")

    async def create(client, replace=False):
        calls.append("create")

    def no_client(**kwargs):
        raise AssertionError(f"connected to Weaviate: {kwargs}")

    monkeypatch.setattr(EmbeddingPipeline, "run", run)
    monkeypatch.setattr(db, "create_test_collection", create)
    monkeypatch.setattr(db, "get_async_client", no_client)
    return calls


def run_cli(monkeypatch, *args) -> int:
    monkeypatch.setattr(sys, "argv", ["semantembedder", *args])
    with pytest.raises(SystemExit) as exit_:
        main()
    return exit_.value.code


@pytest.mark.parametrize("confirm", [[], ["--confirm-endpoint", "localhost:8080"],
                                     ["--confirm-endpoint", "weaviate.example:8080"],
                                     ["--confirm-endpoint", "weaviate.example"]])
def test_a_run_without_the_configured_endpoint_is_refused_before_connecting(monkeypatch, capsys, config, started,
                                                                            confirm):
    assert run_cli(monkeypatch, config, *confirm) == 2
    assert started == []
    assert "Refusing to run: configured Weaviate endpoint weaviate.example:18080" in capsys.readouterr().err


def test_a_run_with_the_configured_endpoint_starts(monkeypatch, config):
    calls = []
    monkeypatch.setattr(EmbeddingPipeline, "run", lambda self: calls.append((self.weaviate_host, self.weaviate_port)))
    monkeypatch.setattr(sys, "argv", ["semantembedder", config, "--confirm-endpoint", "weaviate.example:18080"])

    main()

    assert calls == [("weaviate.example", 18080)]


@pytest.mark.parametrize("with_config, endpoint", [(True, "weaviate.example:18080"), (False, "localhost:8080")])
def test_the_test_collection_needs_the_endpoint_too(monkeypatch, capsys, config, started, with_config, endpoint):
    source = [config] if with_config else []

    assert run_cli(monkeypatch, "--create-test-collection", "--force", *source) == 2
    assert started == []
    assert f"configured Weaviate endpoint {endpoint}," in capsys.readouterr().err


def test_the_test_collection_is_created_with_the_configured_endpoint(monkeypatch, config):
    created = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    def client(**kwargs):
        created.append(kwargs["host"])
        return Client()

    async def create(client, replace=False):
        created.append(replace)

    monkeypatch.setattr(db, "get_async_client", client)
    monkeypatch.setattr(db, "create_test_collection", create)

    assert run_cli(monkeypatch, "--create-test-collection", "--force", config,
                   "--confirm-endpoint", "weaviate.example:18080") == 0
    assert created == ["weaviate.example", True]


def test_generating_a_template_needs_no_endpoint(monkeypatch, tmp_path, started):
    assert run_cli(monkeypatch, "--init", str(tmp_path / "template.yaml")) == 0
    assert (tmp_path / "template.yaml").exists() and started == []
