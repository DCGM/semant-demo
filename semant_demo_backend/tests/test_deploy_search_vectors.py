"""Production searches the Qwen vector (#385); the test instances keep the default until the
test Weaviate has that vector."""
from pathlib import PurePosixPath

from semant_demo.config import SCRIPT_PATH
from semant_demo.features.search.vectors import load_search_vectors_settings
from tests.test_deploy_feedback_storage import DEPLOY, _env_value

APP_ROOT = PurePosixPath("/app")  # deploy/Dockerfile copies semant_demo_backend to /app


def test_production_selects_the_qwen_search_vectors_shipped_in_the_image():
    path = PurePosixPath(_env_value(".env.example", "SEARCH_VECTORS_CONFIG"))
    source = SCRIPT_PATH.parent / path.relative_to(APP_ROOT)

    settings = load_search_vectors_settings(source)
    assert source.name == "search_vectors_qwen.yaml"
    assert [v.target_vector for v in settings.vectors] == ["Qwen3-Embedding-0-6B"]


def test_test_instances_keep_the_default_search_vectors():
    assert "SEARCH_VECTORS_CONFIG=" not in (DEPLOY / ".env.test.example").read_text()
