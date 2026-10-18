"""Derived annotation text, context and positions (#328, features/annotations/derivation.py).

The derived text must be exactly the canonical text the stored UTF-16 offsets select,
also across chunks and around non-BMP and combining characters (the shared cases of
tests/fixtures/text_offsets.json). Positions count from the start of the span's gap-free
run of chunks; words follow the documented segmentation rule.
"""
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from semant_demo.features.annotations import derivation
from semant_demo.features.annotations.derivation import DocumentText, render_vector_input, word_spans
from semant_demo.features.annotations.offsets import InvalidSpanRange, code_point_offset

CASES = json.loads((Path(__file__).parent / "fixtures" / "text_offsets.json").read_text(encoding="utf-8"))["cases"]


def chunks(*texts, orders=None):
    orders = orders if orders is not None else range(len(texts))
    return [SimpleNamespace(id=UUID(int=i + 1), order=o, text=t) for i, (o, t) in enumerate(zip(orders, texts))]


def derive(parts, anchor, start, end):
    return DocumentText(parts).derive(parts[anchor].id, start, end)


def _local(text: str, start: int, end: int) -> str:
    return text[code_point_offset(text, start):code_point_offset(text, end)]


@pytest.mark.parametrize("case", [c for c in CASES if c["error"] is None], ids=lambda c: c["name"])
def test_derived_text_is_the_text_the_offsets_select(case):
    parts = chunks(*(c["text"] for c in case["chunks"]), orders=[c["order"] for c in case["chunks"]])
    expected = "".join(_local(case["chunks"][p["chunk"]]["text"], p["start"], p["end"]) for p in case["parts"])

    derived = derive(parts, case["anchor"], case["start"], case["end"])

    assert derived.text == expected
    assert derived.end_char - derived.start_char == case["end"] - case["start"]


@pytest.mark.parametrize("case", [c for c in CASES if c["error"] is not None], ids=lambda c: c["name"])
def test_offsets_that_describe_no_text_are_refused(case):
    parts = chunks(*(c["text"] for c in case["chunks"]), orders=[c["order"] for c in case["chunks"]])

    with pytest.raises(InvalidSpanRange) as e:
        derive(parts, case["anchor"], case["start"], case["end"])
    assert e.value.code == case["error"]


def test_non_bmp_and_combining_characters_round_trip_across_a_chunk_boundary():
    # "Nova" + combining acute in the first chunk, "k" in the second.
    parts = chunks("Jan Nova\u0301", "k 😀 zde")
    derived = derive(parts, 0, 4, 13)  # the combining mark is one unit, the emoji two: 6 + 1 + 2

    assert derived.text == "Nova\u0301k 😀"
    assert (derived.start_char, derived.end_char) == (4, 13)
    # "Nova\u0301k" is one word across the boundary; the emoji is no word.
    assert (derived.start_word, derived.end_word) == (1, 2)


def test_word_segmentation_rule():
    text = "Frýdek-Místek, don't ſtará 1848\u00adr. Nova\u0301k _x_ a+b"
    assert [text[s:e] for s, e in word_spans(text)] == [
        "Frýdek", "Místek", "don", "t", "ſtará", "1848\u00adr", "Nova\u0301k", "x", "a", "b"]


def test_positions_of_adjacent_overlapping_and_partial_word_spans():
    parts = chunks("Jan Novák a Brno")
    whole = derive(parts, 0, 4, 9)        # "Novák"
    adjacent = derive(parts, 0, 9, 11)    # " a"
    overlapping = derive(parts, 0, 0, 7)  # "Jan Nov": ends inside "Novák"
    inside = derive(parts, 0, 5, 7)       # "ov"
    punctuation_only = derive(chunks("Jan , Brno"), 0, 4, 5)

    assert (whole.start_word, whole.end_word) == (1, 2)
    assert (adjacent.start_word, adjacent.end_word) == (2, 3)
    assert (overlapping.start_word, overlapping.end_word) == (0, 2)
    assert (inside.text, inside.start_word, inside.end_word) == ("ov", 1, 2)
    # No word inside: the empty range at the next word.
    assert (punctuation_only.start_word, punctuation_only.end_word) == (1, 1)
    assert whole.end_char == adjacent.start_char


def test_positions_count_chunks_outside_the_collection_and_restart_after_a_gap():
    # Order 1 is present (whatever its collection), order 3 is missing: a new segment.
    parts = chunks("Jedna dvě ", "tři čtyři ", "pět šest", "sedm osm", orders=[0, 1, 2, 4])
    after_excluded = derive(parts, 2, 0, 3)  # "pět"
    after_gap = derive(parts, 3, 5, 8)       # "osm"

    assert (after_excluded.segment, after_excluded.start_char, after_excluded.start_word) == (0, 20, 4)
    assert (after_gap.segment, after_gap.start_char, after_gap.start_word) == (4, 5, 1)
    # Context never crosses the gap.
    assert after_gap.left_context == "sedm "
    assert after_excluded.right_context == " šest"


def test_context_is_bounded_and_does_not_cut_words(monkeypatch):
    monkeypatch.setattr(derivation, "CONTEXT_CHARS", 8)
    parts = chunks("alpha beta gamma TARGET delta epsilon")
    derived = derive(parts, 0, 17, 23)

    assert derived.text == "TARGET"
    # 8 code points before: "a gamma " -> the partial "a" of "beta" is dropped.
    assert derived.left_context == " gamma "
    # 8 after: " delta e" -> the partial "e" of "epsilon" is dropped.
    assert derived.right_context == " delta "


def test_context_reaching_the_segment_start_keeps_the_first_word(monkeypatch):
    monkeypatch.setattr(derivation, "CONTEXT_CHARS", 50)
    derived = derive(chunks("Roku 1848 přijel"), 0, 10, 16)

    assert (derived.left_context, derived.right_context) == ("Roku 1848 ", "")


def test_missing_anchor_chunk_is_invalid():
    with pytest.raises(InvalidSpanRange) as e:
        DocumentText(chunks("abc")).derive(UUID(int=99), 0, 1)
    assert e.value.code == "missing_anchor"


def test_vector_input_marks_the_span_and_keeps_braces_in_text():
    derived = derive(chunks("a {text} b"), 0, 2, 8)

    assert render_vector_input("{left}<<<{text}>>>{right}", derived) == "a <<<{text}>>> b"
