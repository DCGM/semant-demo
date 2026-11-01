"""The chunk-value summary commands (#529, maintenance/chunk_summaries.py and chunk_summary_schema.py):
per-document accumulation, property checks, exit codes and refusals. Recomputation and filtering
against a store are in tests/integration/test_chunk_summaries.py.
"""
from uuid import uuid4

import pytest

from semant_demo.adapters.weaviate.chunk_summaries import DeclaredProperty, expected_properties
from semant_demo.maintenance import chunk_summaries, chunk_summary_schema
from semant_demo.maintenance.chunk_summaries import DIMENSIONS, Summaries, exit_code, property_status
from semant_demo.features.search.filters import TASK_CLASSES


def test_every_classification_and_the_chunk_language_are_summarized():
    assert DIMENSIONS == ("language", *TASK_CLASSES)
    assert set(expected_properties(["language", "style"])) == \
        {"chunk_language", "chunk_style", "chunk_summaries_computed_at"}


def test_summaries_keep_the_distinct_values_of_each_document_by_dimension():
    summaries = Summaries(("language", "style", "complexity"))
    first, second, without_chunks = uuid4(), uuid4(), uuid4()
    summaries.add(first, {"language": ("ces",), "style": ("formal",)})
    summaries.add(second, {"language": ("deu",), "style": ()})
    summaries.add(first, {"language": ("ces",), "style": ("informal", "formal")})

    assert summaries.distinct_values() == {"language": 2, "style": 2, "complexity": 0}
    assert summaries.pop(first) == {"language": ("ces",), "style": ("formal", "informal"), "complexity": ()}
    assert summaries.pop(second) == {"language": ("deu",), "style": (), "complexity": ()}
    assert summaries.pop(without_chunks) == {"language": (), "style": (), "complexity": ()}
    assert summaries.masks == {}


def test_summary_properties_must_be_declared_as_expected():
    declared = {
        "chunk_language": DeclaredProperty("text[]", "field", True),
        "chunk_style": DeclaredProperty("text[]", "word", True),  # would match "easy" in "very_easy"
    }

    missing, different = property_status(declared, ["language", "style", "complexity"])

    assert missing == ["chunk_complexity", "chunk_summaries_computed_at"]
    assert list(different) == ["chunk_style"]
    assert different["chunk_style"]["expected"]["tokenization"] == "field"


def _result(mode="write", missing=(), **documents):
    counts = {"never_computed": 0, "changed": 0, "unchanged": 0, "failed": 0} | documents
    return {"mode": mode, "missing_properties": list(missing), "different_properties": {},
            "counts": {"documents": counts}}


@pytest.mark.parametrize("result, code", [
    (_result(), 0),
    (_result(failed=1), 1),
    (_result("dry_run", unchanged=3), 0),
    (_result("dry_run", unchanged=2, changed=1), 1),
    (_result("dry_run", never_computed=3), 1),
    (_result("dry_run", missing=["chunk_style"], unchanged=3), 1),
])
def test_exit_code(result, code):
    assert exit_code(result) == code


async def test_an_existing_report_is_refused_before_the_store_is_read(tmp_path):
    report = tmp_path / "report.json"
    report.write_text("{}")

    with pytest.raises(chunk_summaries.Refused, match="exists"):
        await chunk_summaries.run(None, None, report=report, endpoint="test", write=False)


@pytest.mark.parametrize("module, argv", [
    (chunk_summaries, ["--write", "report.json", "--confirm-endpoint", "elsewhere:8080"]),
    (chunk_summaries, ["--write", "report.json"]),
    (chunk_summary_schema, ["--apply", "--confirm-endpoint", "elsewhere:8080"]),
])
async def test_writing_needs_the_configured_endpoint_confirmed(monkeypatch, capsys, module, argv):
    monkeypatch.setenv("WEAVIATE_HOST", "localhost")
    monkeypatch.setenv("WEAVIATE_REST_PORT", "8080")

    assert await module._main(argv) == 2
    assert "Refusing to" in capsys.readouterr().err
