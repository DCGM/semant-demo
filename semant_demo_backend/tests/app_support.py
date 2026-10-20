"""Shared helpers for tests that build the FastAPI application."""
from pathlib import Path

import yaml

from semant_demo.config import SCRIPT_PATH, Config

TEST_JWT_SECRET = "test-secret-key-long-enough-for-hmac-sha256-32bytes"


def write_offline_llm_catalog(path: Path) -> Path:
    """The default model tier catalog without per-tier endpoints, so every tier uses the
    configured ``OPENAI_API_URL`` / ``OLLAMA_URLS`` (a fake or unreachable host)."""
    catalog = yaml.safe_load((SCRIPT_PATH / "configs" / "llm_models.yaml").read_text())
    for tier in catalog["tiers"].values():
        tier.pop("base_url", None)
    path.write_text(yaml.safe_dump(catalog))
    return path


def make_test_config(tmp_dir: Path, **overrides: str) -> Config:
    """Settings isolated from the process environment and from live services.

    Network endpoints use the reserved `.invalid` TLD so an accidental connection
    attempt fails instead of reaching a real service.
    """
    rag_dir = tmp_dir / "rag_configs"
    rag_dir.mkdir(exist_ok=True)
    # Keep both OpenRouter and Ollama endpoints unreachable in isolated tests.
    llm_models_path = write_offline_llm_catalog(tmp_dir / "llm_models.yaml")
    environ = {
        "SQL_DB_URL": f"sqlite+aiosqlite:///{tmp_dir / 'test.db'}",
        "JWT_SECRET": TEST_JWT_SECRET,
        "WEAVIATE_HOST": "weaviate.invalid",
        "EMBEDDING_SERVICE_HOST": "embedding.invalid",
        "TOPICER_URL": "http://topicer.invalid",
        "OPENAI_API_URL": "http://openai.invalid",
        "OLLAMA_URLS": "http://ollama.invalid",
        "RAG_CONFIGS_PATH": str(rag_dir),
        "LLM_MODELS_CONFIG": str(llm_models_path),
        "STATIC_PATH": str(tmp_dir / "no_static"),
        "FEEDBACK_LOG_PATH": str(tmp_dir / "feedback.log.jsonl"),
        # The fixture store's `default` chunk vector, embedded by the unreachable
        # EMBEDDING_SERVICE_HOST above, not the deployed default (#385); tests inject embedders.
        "SEARCH_VECTORS_CONFIG": str(SCRIPT_PATH / "configs" / "search_vectors_gemma.yaml"),
        # No contextual annotation vector: its embedder would be a live provider (#328).
        "ANNOTATION_VECTOR_CONFIG": "",
    }
    environ.update(overrides)
    return Config(environ=environ)


class _UnavailableCollection:
    def __init__(self, name: str):
        self._name = name

    def __getattr__(self, attr):
        raise RuntimeError(f"Weaviate is not available in this test (collection {self._name!r})")


class _UnavailableCollections:
    def get(self, name: str) -> _UnavailableCollection:
        return _UnavailableCollection(name)


class OfflineWeaviate:
    """Stand-in Weaviate client for fast tests that do not use Weaviate.

    Repositories can be built on it; any query or write fails.
    """

    def __init__(self):
        self.collections = _UnavailableCollections()
        self.closed = False

    async def close(self) -> None:
        self.closed = True


async def offline_weaviate(config: Config) -> OfflineWeaviate:
    """``create_app(..., weaviate_connector=offline_weaviate)`` for apps without Weaviate."""
    return OfflineWeaviate()
