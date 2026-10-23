"""The shared chunk position calculator (#463, features/documents/positions.py).

Every chunk stores where it starts in its document: UTF-16 units and word starts of the
preceding chunks, and whether a word is open at its start. The backfill of existing
chunks and the insertion of new ones use the same ``next_position``.
"""
import random

import pytest

from semant_demo.features.documents.positions import (
    ChunkPosition, chunk_positions, next_position, text_length, word_spans,
)


def test_worked_example_of_the_issue():
    # "hel" + "lo world" is "hello world": the second chunk continues the first word.
    assert list(chunk_positions(["hel", "lo world"])) == [ChunkPosition(0, 0, False), ChunkPosition(3, 1, True)]


@pytest.mark.parametrize("texts, expected", [
    ([], []),
    (["", "abc"], [(0, 0, False), (0, 0, False)]),
    # Empty chunks pass on the open word.
    (["ab", "", "", "c d"], [(0, 0, False), (2, 1, True), (2, 1, True), (2, 1, True)]),
    # A chunk ending in a non-word character closes the word.
    (["ab ", "cd", "-ef", ".", "g"], [(0, 0, False), (3, 1, False), (5, 2, True), (8, 3, True), (9, 3, False)]),
    # Punctuation and whitespace only.
    ([" , ", "!?", "x"], [(0, 0, False), (3, 0, False), (5, 0, False)]),
    # UTF-16 units: the emoji is two, the combining mark one (and part of the word).
    (["Nová", "k 😀", "zde"], [(0, 0, False), (5, 1, True), (9, 1, False)]),
    # Historical letters, digits and the soft hyphen (Cf) are word characters.
    (["ſtará 1848­", "r. "], [(0, 0, False), (11, 2, True)]),
])
def test_positions_of_consecutive_chunks(texts, expected):
    assert list(chunk_positions(texts)) == [ChunkPosition(*e) for e in expected]


def _words_before(document: str, units: int) -> tuple[int, bool]:
    """Word starts and open word before UTF-16 offset ``units`` of the whole text."""
    prefix = document.encode("utf-16-le")[:2 * units].decode("utf-16-le")
    return len(word_spans(prefix)), bool(prefix) and bool(word_spans(prefix[-1]))


def test_positions_equal_counting_the_concatenated_text():
    alphabet = ["a", "ž", "1", " ", "-", ".", "́", "­", "😀", "ſ", ""]
    rng = random.Random(463)
    for _ in range(300):
        texts = ["".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 6))) for _ in range(rng.randrange(1, 8))]
        document = "".join(texts)
        for i, position in enumerate(chunk_positions(texts)):
            start_char = sum(text_length(t) for t in texts[:i])
            assert position == ChunkPosition(start_char, *_words_before(document, start_char)), texts


def test_an_append_continues_from_the_stored_tail():
    texts = ["Roku 18", "48 přijel", " do Brna", ""]
    whole = list(chunk_positions(texts))
    tail = next_position(whole[1], texts[1])

    assert list(chunk_positions(texts[2:], tail)) == whole[2:]
