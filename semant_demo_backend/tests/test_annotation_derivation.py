"""Derived annotation text, context and positions (#328, #463, features/annotations/derivation.py).

The derived text must be exactly the canonical text the stored UTF-16 offsets select,
also across chunks and around non-BMP and combining characters (the shared cases of
tests/fixtures/text_offsets.json). Positions are absolute in the document and computed
from the anchor chunk's stored position and the text after it; they and the context
equal what #328 derived from the whole text of a document with consecutive chunks
(``_whole_document``, a copy of that derivation, is the oracle).
"""
import bisect
import json
import random
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from semant_demo.features.annotations import derivation
from semant_demo.features.annotations.derivation import (
    MissingChunkPositions, SpanSource, derive as derive_source, render_vector_input,
)
from semant_demo.features.annotations.offsets import InvalidSpanRange, check_span_range, code_point_offset, text_length
from semant_demo.features.documents.positions import chunk_positions, is_word, word_spans

CASES = json.loads((Path(__file__).parent / "fixtures" / "text_offsets.json").read_text(encoding="utf-8"))["cases"]


def chunks(*texts, orders=None):
    """Chunks with the positions the shared calculator gives them (orders taken as consecutive)."""
    orders = orders if orders is not None else range(len(texts))
    return [SimpleNamespace(id=UUID(int=i + 1), order=o, text=t, start_char=p.start_char, start_word=p.start_word,
                            word_open_at_start=p.word_open_at_start)
            for i, (o, t, p) in enumerate(zip(orders, texts, chunk_positions(texts)))]


def derive(parts, anchor, start, end, first=0, last=None):
    """Derive from ``parts[first:last]`` only (a window of the document)."""
    last = len(parts) if last is None else last
    source = SpanSource(parts[first:last], anchor - first, first == 0, last == len(parts))
    return derive_source(source, start, end)


def _whole_document(parts, anchor, start, end):
    """#328's derivation from the whole text of a document with consecutive chunks."""
    check_span_range(parts[anchor:], start, end)
    text = "".join(c.text for c in parts)
    words = word_spans(text)
    word_starts, word_ends = [s for s, _ in words], [e for _, e in words]
    prefix = sum(text_length(c.text) for c in parts[:anchor])
    start_char, end_char = prefix + start, prefix + end
    a, b = code_point_offset(text, start_char), code_point_offset(text, end_char)
    left = max(0, a - derivation.CONTEXT_CHARS)
    if 0 < left < a and is_word(text[left - 1]) and is_word(text[left]):
        left = min(a, word_ends[bisect.bisect_right(word_starts, left) - 1])
    right = min(len(text), b + derivation.CONTEXT_CHARS)
    if b < right < len(text) and is_word(text[right - 1]) and is_word(text[right]):
        right = max(b, word_starts[bisect.bisect_right(word_starts, right) - 1])
    return derivation.DerivedText(
        text=text[a:b], left_context=text[left:a], right_context=text[b:right], start_char=start_char,
        end_char=end_char, start_word=bisect.bisect_right(word_ends, a), end_word=bisect.bisect_left(word_starts, b))


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


def test_worked_example_of_the_issue():
    # "hel" + "lo world": "lo" is part of the word "hello", the first word.
    derived = derive(chunks("hel", "lo world"), 1, 0, 2)

    assert (derived.text, derived.start_char, derived.end_char) == ("lo", 3, 5)
    assert (derived.start_word, derived.end_word) == (0, 1)
    assert (derived.left_context, derived.right_context) == ("hel", " world")


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


def test_positions_are_absolute_and_count_chunks_outside_the_collection():
    # Order 1 is part of the document whatever its collection; the first order need not be 0.
    parts = chunks("Jedna dvě ", "tři čtyři ", "pět šest", "sedm osm", orders=[7, 8, 9, 10])
    after_excluded = derive(parts, 2, 0, 3)  # "pět"
    later = derive(parts, 3, 5, 8)           # "osm"

    assert (after_excluded.start_char, after_excluded.start_word, after_excluded.end_word) == (20, 4, 5)
    # "šest" + "sedm" is one word "šestsedm": chunks are concatenated without separators.
    assert (later.start_char, later.start_word, later.end_word) == (33, 6, 7)
    assert later.left_context == "Jedna dvě tři čtyři pět šestsedm "
    assert after_excluded.right_context == " šestsedm osm"


def test_context_is_bounded_and_does_not_cut_words(monkeypatch):
    monkeypatch.setattr(derivation, "CONTEXT_CHARS", 8)
    parts = chunks("alpha beta gamma TARGET delta epsilon")
    derived = derive(parts, 0, 17, 23)

    assert derived.text == "TARGET"
    # 8 code points before: "a gamma " -> the partial "a" of "beta" is dropped.
    assert derived.left_context == " gamma "
    # 8 after: " delta e" -> the partial "e" of "epsilon" is dropped.
    assert derived.right_context == " delta "


def test_context_reaching_the_document_start_keeps_the_first_word(monkeypatch):
    monkeypatch.setattr(derivation, "CONTEXT_CHARS", 50)
    derived = derive(chunks("Roku 1848 přijel"), 0, 10, 16)

    assert (derived.left_context, derived.right_context) == ("Roku 1848 ", "")


ALPHABET = ["a", "b", "ž", "1", " ", " ", "-", ".", "\u0301", "\u00ad", "😀", "ſ"]


def _random_text(rng, length):
    return "".join(rng.choice(ALPHABET) for _ in range(length))


def test_local_derivation_equals_the_whole_document_derivation(monkeypatch):
    # Random documents (empty chunks, words across chunk boundaries, non-BMP and combining
    # characters, punctuation-only spans), every span derived from the smallest window that
    # covers its context, compared with #328's derivation from the whole text.
    monkeypatch.setattr(derivation, "CONTEXT_CHARS", 6)
    rng = random.Random(463)
    compared = 0
    for _ in range(400):
        parts = chunks(*(_random_text(rng, rng.choice([0, 1, 3, 5, 9])) for _ in range(rng.randrange(1, 9))))
        anchors = [i for i, c in enumerate(parts) if c.text]
        if not anchors:
            continue
        anchor = rng.choice(anchors)
        rest = sum(text_length(c.text) for c in parts[anchor:])
        start = rng.randrange(text_length(parts[anchor].text))
        end = rng.randrange(start + 1, rest + 1)
        expected = _whole_document(parts, anchor, start, end)
        first, last = _window(parts, anchor, start, end)

        assert derive(parts, anchor, start, end, first, last) == expected, (parts, anchor, start, end)
        compared += 1
    assert compared > 300


def _window(parts, anchor, start, end):
    """The fewest chunks around the span that cover its context (as ``source.py`` reads)."""
    last = anchor + 1
    while last < len(parts):
        local = "".join(c.text for c in parts[anchor:last])
        if text_length(local) >= end and len(local) - code_point_offset(local, end) > derivation.CONTEXT_CHARS:
            break
        last += 1
    first = anchor
    while first > 0 and sum(len(c.text) for c in parts[first:anchor]) + code_point_offset(
            parts[anchor].text, start) <= derivation.CONTEXT_CHARS:
        first -= 1
    return first, last


def test_a_window_too_small_for_the_context_is_refused():
    parts = chunks("a" * 300, "b" * 10, "c" * 300)

    with pytest.raises(ValueError):
        derive(parts, 1, 0, 2, first=1, last=2)
    assert derive(parts, 1, 0, 2, first=0, last=3).text == "bb"


def test_a_chunk_without_a_stored_position_fails():
    parts = chunks("Jan ", "Novák")
    parts[0].start_word = None

    with pytest.raises(MissingChunkPositions):
        derive(parts, 1, 0, 5)


def test_inconsistent_positions_fail():
    parts = chunks("Jan ", "Novák", " z Brna")
    parts[2].start_char += 1

    with pytest.raises(MissingChunkPositions):
        derive(parts, 1, 0, 5)


def test_the_first_chunk_of_a_document_starts_at_zero():
    parts = chunks("Jan ", "Novák")
    parts[0].start_word = 1
    parts[1].start_word = 2

    with pytest.raises(MissingChunkPositions):
        derive(parts, 1, 0, 5)


def test_vector_input_marks_the_span_and_keeps_braces_in_text():
    derived = derive(chunks("a {text} b"), 0, 2, 8)

    assert render_vector_input("{left}<<<{text}>>>{right}", derived) == "a <<<{text}>>> b"
