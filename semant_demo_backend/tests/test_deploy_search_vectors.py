"""Production and the test instances search the Qwen vector (#385) and embed annotations with it (#328)."""
from pathlib import Path, PurePosixPath

import pytest

from semant_demo.config import SCRIPT_PATH, Config
from semant_demo.features.annotations.enrichment import load_annotation_vector_settings
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


@pytest.mark.parametrize("template", [".env.example", ".env.test.example"])
def test_instances_embed_annotations_with_the_qwen_embedder_shipped_in_the_image(template):
    # The Gemma embedding service is stopped there (#385); the annotation vector (#328) uses Qwen too.
    path = PurePosixPath(_env_value(template, "ANNOTATION_VECTOR_CONFIG"))
    settings = load_annotation_vector_settings(SCRIPT_PATH.parent / path.relative_to(APP_ROOT))

    assert path.name == "annotation_vector_qwen.yaml"
    assert settings.embedding.base_url == "http://qwen-embedder:8000/v1"
    assert settings.embedding.model == load_search_vectors_settings(
        SCRIPT_PATH / "configs" / "search_vectors_qwen.yaml").vectors[0].embedding.model


@pytest.mark.parametrize("template", [".env.example", ".env.test.example"])
def test_the_default_vector_configuration_is_the_one_the_instances_select(template):
    # Without the settings, an instance searches and embeds as production does.
    default = Config(environ={})
    for name in ("SEARCH_VECTORS_CONFIG", "ANNOTATION_VECTOR_CONFIG"):
        deployed = SCRIPT_PATH.parent / PurePosixPath(_env_value(template, name)).relative_to(APP_ROOT)
        assert Path(getattr(default, name)) == deployed
