"""Span coordinates against the cases shared with the frontend (tests/fixtures/text_offsets.json)."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from semant_demo.features.annotations.offsets import (
    ChunkSpan, InvalidSpanRange, check_span_range, project_span, text_length,
)

CASES = json.loads((Path(__file__).parent / "fixtures" / "text_offsets.json").read_text(encoding="utf-8"))["cases"]


def chunks_of(case):
    return [SimpleNamespace(**c) for c in case["chunks"]]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_projection(case):
    parts = project_span(chunks_of(case), case["anchor"], case["start"], case["end"])

    assert parts == [ChunkSpan(p["chunk"], p["start"], p["end"]) for p in case["parts"]]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_validation(case):
    run = chunks_of(case)[case["anchor"]:]
    if case["error"] is None:
        check_span_range(run, case["start"], case["end"])
    else:
        with pytest.raises(InvalidSpanRange) as raised:
            check_span_range(run, case["start"], case["end"])
        assert raised.value.code == case["error"]


def test_lengths_are_utf16_units_not_code_points():
    assert (len("Karel 😀"), text_length("Karel 😀")) == (7, 8)
    assert text_length("Novák") == len("Novák") == 6


def test_validation_needs_only_the_chunks_the_span_reaches():
    # A span inside its anchor chunk is valid without reading any following chunk.
    check_span_range([SimpleNamespace(order=4, text="abc")], 0, 3)
    with pytest.raises(InvalidSpanRange) as raised:
        check_span_range([SimpleNamespace(order=4, text="abc")], 0, 4)
    assert raised.value.code == "past_end"
