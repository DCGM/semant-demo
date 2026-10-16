"""Production and the test instances search the Qwen vector (#385)."""
from pathlib import PurePosixPath

import pytest

from semant_demo.config import SCRIPT_PATH
from semant_demo.features.search.vectors import load_search_vectors_settings
from tests.test_deploy_feedback_storage import _env_value

APP_ROOT = PurePosixPath("/app")  # deploy/Dockerfile copies semant_demo_backend to /app


@pytest.mark.parametrize("template", [".env.example", ".env.test.example"])
def test_instances_select_the_qwen_search_vectors_shipped_in_the_image(template):
    path = PurePosixPath(_env_value(template, "SEARCH_VECTORS_CONFIG"))
    source = SCRIPT_PATH.parent / path.relative_to(APP_ROOT)

    settings = load_search_vectors_settings(source)
    [vector] = settings.vectors
    assert source.name == "search_vectors_qwen.yaml" and settings.default == vector.id
    assert vector.embedding.base_url == "http://qwen-embedder:8000/v1"
