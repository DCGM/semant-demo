"""The chunks' classification status property (#590): its declaration check and the schema
command's endpoint guard."""
import pytest

from semant_demo.adapters.weaviate import classification_provenance as provenance
from semant_demo.adapters.weaviate.chunk_summaries import DeclaredProperty
from semant_demo.maintenance import classification_provenance_schema


@pytest.mark.parametrize("declared, state", [
    ({}, "missing"),
    ({"classification_provenance": DeclaredProperty("text", "field", True)}, "present"),
    ({"classification_provenance": DeclaredProperty("text", "word", True)}, "different"),
    ({"classification_provenance": DeclaredProperty("text", "field", False)}, "different"),
    ({"classification_provenance": DeclaredProperty("text[]", "field", True)}, "different"),
])
def test_status(declared, state):
    assert provenance.status(declared) == state


@pytest.mark.parametrize("argv", [["--apply"], ["--apply", "--confirm-endpoint", "elsewhere:8080"]])
async def test_applying_needs_the_configured_endpoint_confirmed(monkeypatch, capsys, argv):
    monkeypatch.setenv("WEAVIATE_HOST", "localhost")
    monkeypatch.setenv("WEAVIATE_REST_PORT", "8080")

    assert await classification_provenance_schema._main(argv) == 2
    assert "Refusing to apply" in capsys.readouterr().err
