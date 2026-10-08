"""The chunk tag cleanup command refuses to write without a confirmed endpoint (#204)."""
import json

import pytest

from semant_demo.maintenance import chunk_tag_audit


@pytest.fixture
def no_connection(monkeypatch):
    async def refuse(config):
        raise AssertionError("must not connect")
    monkeypatch.setattr("semant_demo.adapters.weaviate.client.connect_weaviate", refuse)


@pytest.fixture
def report(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"endpoint": "localhost:8080", "issues": []}), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def local_endpoint(monkeypatch):
    for name in ("WEAVIATE_HOST", "WEAVIATE_REST_PORT"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("args", [
    ["--remove-unbacked"],                                                   # no --confirm-endpoint
    ["--remove-unbacked", "--confirm-endpoint", "weaviate.example:8080"],    # wrong endpoint
    ["--confirm-endpoint", "localhost:8080"],                                # no correction selected
])
async def test_apply_refuses_before_connecting(no_connection, report, args):
    assert await chunk_tag_audit._main(["--apply", str(report), *args]) == 2


async def test_apply_refuses_a_report_from_another_endpoint(no_connection, tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"endpoint": "server:8080", "issues": []}), encoding="utf-8")

    code = await chunk_tag_audit._main(["--apply", str(path), "--remove-unbacked",
                                        "--confirm-endpoint", "localhost:8080"])

    assert code == 2
