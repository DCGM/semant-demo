"""The classifier's CLI and models without Weaviate (data_tools/meta_data_enrichment, #590).

Every pipeline run and ``--create-test-collection`` write, so each needs
``--confirm-endpoint HOST:PORT`` equal to the configured Weaviate endpoint, checked before any
connection; the read-only ``--check`` needs none. The exit code follows the run's result. The
connection and the runs are replaced here; the pipeline itself is tested against Weaviate in
``tests/integration/test_classifier_tool.py``.
"""
import sys
from pathlib import Path

import httpx
import openai
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parents[2] / "data_tools" / "meta_data_enrichment"))
import semantmetaenricher.db as db  # noqa: E402
from semantmetaenricher.__main__ import main  # noqa: E402
from semantmetaenricher.models import APIModel, LocalHFClassifierModel, file_sha256  # noqa: E402
from semantmetaenricher.pipeline import EnrichmentPipeline, RunResult, valid_provenance  # noqa: E402

CONFIG = {
    "weaviate_host": "weaviate.example", "weaviate_port": 18080, "weaviate_grpc_port": 15051,
    "weaviate_api_key": None, "weaviate_headers": None, "collection": "Chunks",
    "provenance": "test-model-v1", "field_tasks": {"complexity": "complexity", "style": "style"},
    "filters": [], "batch_size": 4, "max_records": None, "max_consecutive_failures": 3,
    "max_retries": 0, "retry_delay": 0.0,
    "model": {"cls": "LocalHFClassifierModel", "config": {
        "model_path": "converted_model/", "device": "cpu", "input_prompt": "{{ text }}", "threshold": 0.5}},
}


@pytest.fixture
def config(tmp_path) -> str:
    path = tmp_path / "classifier.yaml"
    path.write_text(yaml.safe_dump(CONFIG))
    return str(path)


@pytest.fixture
def started(monkeypatch) -> list[str]:
    """What started: ``run`` (the pipeline) or ``create`` (the test collection); nothing connects."""
    calls = []

    def run(self):
        calls.append("run")
        return RunResult(collection="Chunks", provenance=self.provenance)

    def create(client, fields, replace=False):
        calls.append("create")

    def no_client(**kwargs):
        raise AssertionError(f"connected to Weaviate: {kwargs}")

    monkeypatch.setattr(EnrichmentPipeline, "run", run)
    monkeypatch.setattr(db, "create_test_collection", create)
    monkeypatch.setattr(db, "get_client", no_client)
    return calls


def run_cli(monkeypatch, *args) -> int:
    monkeypatch.setattr(sys, "argv", ["semantmetaenricher", *args])
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


@pytest.mark.parametrize("result, code", [
    (RunResult(collection="Chunks", provenance="test-model-v1", selected=2, classified=2, remaining=0), 0),
    (RunResult(collection="Chunks", provenance="test-model-v1", selected=2, classified=1, remaining=1), 1),
    (RunResult(collection="Chunks", provenance="test-model-v1", stopped="3 consecutive chunks failed", remaining=0), 1),
    (RunResult(collection="Chunks", provenance="test-model-v1", refused="no property"), 2),
])
def test_a_run_with_the_configured_endpoint_exits_by_its_result(monkeypatch, capsys, config, result, code):
    monkeypatch.setattr(EnrichmentPipeline, "run", lambda self: result)

    assert run_cli(monkeypatch, config, "--confirm-endpoint", "weaviate.example:18080") == code
    assert '"provenance": "test-model-v1"' in capsys.readouterr().out


@pytest.mark.parametrize("with_config, endpoint", [(True, "weaviate.example:18080"), (False, "localhost:8080")])
def test_the_test_collection_needs_the_endpoint_too(monkeypatch, capsys, config, started, with_config, endpoint):
    source = [config] if with_config else []

    assert run_cli(monkeypatch, "--create-test-collection", "--force", *source) == 2
    assert started == []
    assert f"configured Weaviate endpoint {endpoint}," in capsys.readouterr().err


def test_the_test_collection_is_created_with_the_configured_endpoint_and_fields(monkeypatch, config):
    created = []

    class Client:
        def close(self):
            created.append("closed")

    def client(**kwargs):
        created.append(kwargs["host"])
        return Client()

    def create(client, fields, replace=False):
        created.append((fields, replace))

    monkeypatch.setattr(db, "get_client", client)
    monkeypatch.setattr(db, "create_test_collection", create)

    assert run_cli(monkeypatch, "--create-test-collection", "--force", config,
                   "--confirm-endpoint", "weaviate.example:18080") == 0
    assert created == ["weaviate.example", (["complexity", "style"], True), "closed"]


def test_an_existing_test_collection_is_a_refusal(monkeypatch, config):
    class Client:
        def close(self):
            pass

    def create(client, fields, replace=False):
        raise db.Refused("already exists")

    monkeypatch.setattr(db, "get_client", lambda **kwargs: Client())
    monkeypatch.setattr(db, "create_test_collection", create)

    assert run_cli(monkeypatch, "--create-test-collection", config, "--confirm-endpoint", "weaviate.example:18080") == 2


@pytest.mark.parametrize("confirm", [[], ["--confirm-endpoint", "localhost:8080"]])
@pytest.mark.parametrize("remaining, code", [(0, 0), (5, 1)])
def test_the_read_only_check_needs_no_endpoint(monkeypatch, config, started, confirm, remaining, code):
    monkeypatch.setattr(EnrichmentPipeline, "check", lambda self: RunResult(
        collection="Chunks", provenance=self.provenance, selected=remaining, remaining=remaining))

    assert run_cli(monkeypatch, config, "--check", *confirm) == code
    assert started == []


@pytest.mark.parametrize("provenance", [None, "", "UNPROCESSED", " test-model-v1", "test-model-v1 "])
def test_a_config_without_a_valid_provenance_is_refused(monkeypatch, tmp_path, started, provenance):
    path = tmp_path / "classifier.yaml"
    path.write_text(yaml.safe_dump({**CONFIG, "provenance": provenance}))

    assert run_cli(monkeypatch, str(path), "--confirm-endpoint", "weaviate.example:18080") == 2
    assert started == []


def test_valid_provenance():
    assert valid_provenance("mmbert-multitask-2026-07-15")
    assert not any(valid_provenance(v) for v in (None, "", "UNPROCESSED", " x", 3))


def api_model(tmp_path, **settings) -> APIModel:
    prompt = tmp_path / "complexity.j2"
    prompt.write_text("Classify: {{ text }}")
    return APIModel(api_key="test-key", base_url="http://127.0.0.1:9/v1", model_name="fake", temperature=0.0,
                    max_tokens=10, task_prompts={"complexity": str(prompt)},
                    task_classes={"complexity": ["easy", "expert"]}, concurrency_limit=1, **settings)


def test_a_failed_api_request_is_none_not_an_empty_classification(tmp_path, monkeypatch):
    model = api_model(tmp_path)

    async def fail(**kwargs):
        raise openai.APIConnectionError(request=httpx.Request("POST", "http://127.0.0.1:9/v1"))

    with model:
        monkeypatch.setattr(model.client.beta.chat.completions, "parse", fail)
        assert model.generate_batch([{"text": "a"}], ["complexity"]) == [{"complexity": None}]


def test_an_unrenderable_prompt_is_none(tmp_path):
    model = api_model(tmp_path)
    model.task_templates["complexity"] = model.jinja_env.from_string("{{ missing.attribute }}")

    with model:
        assert model.generate_batch([{"text": "a"}], ["complexity"]) == [{"complexity": None}]


def test_the_api_model_labels_and_fingerprint(tmp_path):
    model = api_model(tmp_path)

    assert model.labels("complexity") == ["easy", "expert"] and model.labels("style") is None
    fingerprint = model.fingerprint()
    assert fingerprint["model_name"] == "fake" and fingerprint["base_url"] == "http://127.0.0.1:9/v1"
    assert fingerprint["task_prompts_sha256"] == {"complexity": file_sha256(str(tmp_path / "complexity.j2"))}


def test_the_local_model_fingerprint_hashes_every_file_without_loading_it(tmp_path):
    for name, content in {"config.json": b"{}", "heads.bin": b"heads", "pytorch_model.bin": b"weights"}.items():
        (tmp_path / name).write_bytes(content)
    model = LocalHFClassifierModel(model_path=str(tmp_path), device="cpu", input_prompt="{{ text }}", threshold=0.5)

    fingerprint = model.fingerprint()

    assert fingerprint["files_sha256"] == {name: file_sha256(str(tmp_path / name))
                                           for name in ("config.json", "heads.bin", "pytorch_model.bin")}
    assert model._model is None
