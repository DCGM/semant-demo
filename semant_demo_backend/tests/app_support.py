"""Shared helpers for tests that build the FastAPI application."""
from pathlib import Path

from semant_demo.config import Config

TEST_JWT_SECRET = "test-secret-key-long-enough-for-hmac-sha256-32bytes"


def make_test_config(tmp_dir: Path, **overrides: str) -> Config:
    """Settings isolated from the process environment and from live services.

    Network endpoints use the reserved `.invalid` TLD so an accidental connection
    attempt fails instead of reaching a real service.
    """
    rag_dir = tmp_dir / "rag_configs"
    rag_dir.mkdir(exist_ok=True)
    environ = {
        "SQL_DB_URL": f"sqlite+aiosqlite:///{tmp_dir / 'test.db'}",
        "JWT_SECRET": TEST_JWT_SECRET,
        "WEAVIATE_HOST": "weaviate.invalid",
        "EMBEDDING_SERVICE_HOST": "embedding.invalid",
        "TOPICER_URL": "http://topicer.invalid",
        "OPENAI_API_URL": "http://openai.invalid",
        "OLLAMA_URLS": "http://ollama.invalid",
        "RAG_CONFIGS_PATH": str(rag_dir),
        "STATIC_PATH": str(tmp_dir / "no_static"),
        "FEEDBACK_LOG_PATH": str(tmp_dir / "feedback.log.jsonl"),
    }
    environ.update(overrides)
    return Config(environ=environ)
