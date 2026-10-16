"""RAG and app feedback HTTP routes (features/rag, features/feedback): configuration
loading, unknown configurations, answer feedback persistence and content-free error logs.
Pipelines answering through the LLM gateway are covered in test_llm/test_features.py."""
import json
import logging
import shutil
import sqlite3
from pathlib import Path

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from semant_demo.adapters.llm.gateway import LlmGateway, ProviderSettings
from semant_demo.adapters.llm.models import ModelCatalog
from semant_demo.config import Config
from semant_demo.features.rag import service as rag_service
from semant_demo.features.rag.registry import rag_factory
from semant_demo.main import create_app
from tests.app_support import make_test_config, offline_weaviate, write_offline_llm_catalog

FIXTURES = Path(__file__).parent / "fixtures" / "rag_configs"
SECRET_TEXT = "Kdo byl tajný kronikář?"


def test_factory_loads_valid_configurations_and_skips_broken_or_duplicate_ones(tmp_path):
    llm = LlmGateway(ModelCatalog.load(write_offline_llm_catalog(tmp_path / "llm_models.yaml")), ProviderSettings())
    registry = rag_factory(Config(environ={}), str(FIXTURES), llm)

    # Missing name, unknown class and a repeated id are skipped; both remaining load.
    assert set(registry.instances) == {"xandry12_TestRag", "xandry12_RagGenerator_min_params"}
    assert [c.id for c in registry.get_all_configurations()] == list(registry.instances)


@pytest.fixture
async def app_client(tmp_path):
    rag_dir = tmp_path / "rag_configs"
    rag_dir.mkdir()
    shutil.copy(FIXTURES / "test_config.yaml", rag_dir)
    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


def rag_body(rag_id="xandry12_TestRag"):
    return {"rag_id": rag_id, "rag_request": {"question": SECRET_TEXT, "rag_search": {}}}


async def test_configurations_and_answer_of_a_loaded_pipeline(app_client):
    configurations = await app_client.get("/api/rag/configurations")
    response = await app_client.post("/api/rag", json=rag_body())

    assert configurations.json() == [{"id": "xandry12_TestRag", "name": "Test Rag",
                                      "description": "Rag class and configuration used for purpose of testing"}]
    assert response.status_code == 200 and response.json()["rag_answer"] == "Router is working"


async def test_unknown_configuration_is_a_bad_request(app_client):
    answer = await app_client.post("/api/rag", json=rag_body("missing"))
    explain = await app_client.post("/api/rag/explain", json={
        "rag_id": "missing", "selected_text": "x", "full_answer": "x", "sources": []})

    assert (answer.status_code, answer.json()) == (400, {"detail": "Unknown RAG configuration: missing."})
    assert (explain.status_code, explain.json()) == (
        400, {"detail": "Unknown RAG configuration: missing used for explaining."})


async def test_pipelines_without_explanations_say_so(app_client):
    response = await app_client.post("/api/rag/explain", json={
        "rag_id": "xandry12_TestRag", "selected_text": "x", "full_answer": "x", "sources": []})

    assert response.json() == {"explanation": "This functionality is not supported by this RAG, try another."}


async def test_rag_request_logs_carry_no_question(app_client, caplog):
    caplog.set_level(logging.DEBUG)

    await app_client.post("/api/rag", json=rag_body())

    assert [r for r in caplog.records if r.name == rag_service.__name__][0].__dict__["rag.id"] == "xandry12_TestRag"
    assert "tajný" not in caplog.text


# ── answer feedback ────────────────────────────────────────────────────────

def feedback(rating, **fields):
    return {"rag_id": "xandry12_TestRag", "response_id": "r-1", "question": SECRET_TEXT, "answer": "Jan Novák.",
            "sources": [], "rating": rating, **fields}


def stored_feedback(tmp_path):
    with sqlite3.connect(tmp_path / "test.db") as conn:
        return conn.execute("SELECT response_id, question, rating, error_types, comment FROM rag_user_feedback"
                            ).fetchall()


async def test_rating_an_answer_again_replaces_its_rating(app_client, tmp_path):
    first = await app_client.post("/api/rag/feedback", json=feedback(1, comment="ok"))
    again = await app_client.post("/api/rag/feedback", json=feedback(-1, error_types=["wrong", "slow"]))

    assert first.json() == again.json() == {"status": "success"}
    assert stored_feedback(tmp_path) == [("r-1", SECRET_TEXT, -1, '"wrong,slow"', None)]


async def test_failed_feedback_write_is_a_content_free_server_error(app_client, tmp_path, monkeypatch, caplog):
    async def failing(session, **values):
        raise RuntimeError(f"INSERT failed for {values['question']}")
    monkeypatch.setattr(rag_service.feedback_store, "save_rag_feedback", failing)

    response = await app_client.post("/api/rag/feedback", json=feedback(1))

    assert (response.status_code, response.json()) == (500, {"detail": "Database error."})
    assert "RuntimeError" in caplog.text and "tajný" not in caplog.text
    assert stored_feedback(tmp_path) == []


# ── app feedback ───────────────────────────────────────────────────────────

APP_FEEDBACK = {"type": "bug", "subject": "Search", "message": f"  {SECRET_TEXT}  ", "email": None}


async def test_app_feedback_is_appended_to_the_feedback_log(app_client, tmp_path):
    response = await app_client.post("/api/v1/feedback", json=APP_FEEDBACK)

    [line] = (tmp_path / "feedback.log.jsonl").read_text(encoding="utf-8").splitlines()
    assert response.json() == {"status": "success"}
    assert {k: v for k, v in json.loads(line).items() if k not in ("timestamp", "user_agent")} == {
        "feedback_type": "bug", "subject": "Search", "message": SECRET_TEXT, "email": None, "source_ip": "127.0.0.1"}


async def test_empty_app_feedback_is_rejected(app_client, tmp_path):
    response = await app_client.post("/api/v1/feedback", json={**APP_FEEDBACK, "message": "  "})

    assert (response.status_code, response.json()) == (400, {"detail": "Message cannot be empty."})
    assert not (tmp_path / "feedback.log.jsonl").exists()


async def test_failed_webhook_delivery_does_not_log_the_webhook_url(tmp_path, caplog):
    webhook = "http://feedback.invalid/hooks/secret-token"
    app = create_app(make_test_config(tmp_path, FEEDBACK_WEBHOOK_URL=webhook), weaviate_connector=offline_weaviate)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/feedback", json=APP_FEEDBACK)

    assert (response.status_code, response.json()) == (500, {"detail": "Failed to deliver feedback."})
    assert "App feedback delivery error" in caplog.text
    assert "secret-token" not in caplog.text and "tajný" not in caplog.text
