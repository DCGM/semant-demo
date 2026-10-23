"""Absolute positions of a document's chunks (#463): the one shared calculator.

A document's text is the concatenation of the ``text`` of all its chunks in ``order``,
without separators; its chunk orders are consecutive (each is the previous one + 1, the
first may be any integer). Membership in a user collection does not matter. Every chunk
stores where it starts in that text, so a span's absolute positions are computed from its
anchor chunk and the text after it, never from the chunks before it:

``start_char`` (``Chunks.startChar``)
    UTF-16 code units of all preceding chunks (the browser's ``String.length``, the units
    of span offsets, ``annotations/offsets.py``). 0 for the first chunk.
``start_word`` (``Chunks.startWord``)
    Words that start in the preceding chunks, including one that continues into this
    chunk. 0 for the first chunk.
``word_open_at_start`` (``Chunks.wordOpenAtStart``)
    Whether the last character of the preceding text is a word character. False for the
    first chunk; an empty chunk passes on the state it receives.

A word is a maximal run of letters, combining marks, digits and format characters
(Unicode categories L*, M*, N*, Cf: soft hyphen, zero-width joiners). Everything else
separates words: whitespace, punctuation including hyphens and apostrophes
("Frýdek-Místek" is two words), and symbols. Historical letters (``ſ``) and OCR output
are segmented by the same rule; there is no spelling normalization. A chunk boundary
separates nothing: a word split by one is one word.

``next_position`` is the only implementation of these values: the operator backfill of
existing chunks (``maintenance/chunk_positions.py``) and the insertion of new chunks
(the chunk import of #313, the test and development seed) both use it. Stored values are
never recomputed in place: chunks and their text do not change.
"""
import re
import sys
import unicodedata
from dataclasses import dataclass
from functools import cache
from typing import Iterable, Iterator


@cache
def _word_pattern() -> re.Pattern:
    """Runs of word characters; the class is built once from the Unicode database (~0.3 s)."""
    ranges, first = [], None
    for cp in range(sys.maxunicode + 2):
        cat = unicodedata.category(chr(cp)) if cp <= sys.maxunicode else "Cn"
        word = cat[0] in "LMN" or cat == "Cf"
        if word and first is None:
            first = cp
        elif not word and first is not None:
            ranges.append(f"{re.escape(chr(first))}-{re.escape(chr(cp - 1))}")
            first = None
    return re.compile(f"[{''.join(ranges)}]+")


def word_spans(text: str) -> list[tuple[int, int]]:
    """``(start, end)`` code point ranges of the words of ``text`` (see the module docs)."""
    return [m.span() for m in _word_pattern().finditer(text)]


def is_word(char: str) -> bool:
    """Whether the character belongs to a word."""
    return _word_pattern().fullmatch(char) is not None


def text_length(text: str) -> int:
    """Length of ``text`` in UTF-16 code units, as the browser measures it."""
    return len(text.encode("utf-16-le")) // 2


@dataclass(frozen=True)
class ChunkPosition:
    """Where a chunk starts in its document's text (see the module docs)."""
    start_char: int
    start_word: int
    word_open_at_start: bool


DOCUMENT_START = ChunkPosition(0, 0, False)
"""The position of a document's first chunk."""


def next_position(position: ChunkPosition, text: str) -> ChunkPosition:
    """The position of the chunk that follows a chunk at ``position`` with ``text``.

    A word character after a non-word character starts a word; at the start of ``text``
    it does only when no word is open there.
    """
    words = word_spans(text)
    starts = len(words) - (bool(words) and words[0][0] == 0 and position.word_open_at_start)
    return ChunkPosition(position.start_char + text_length(text), position.start_word + starts,
                         is_word(text[-1]) if text else position.word_open_at_start)


def chunk_positions(texts: Iterable[str], first: ChunkPosition = DOCUMENT_START) -> Iterator[ChunkPosition]:
    """The positions of consecutive chunks with ``texts``, the first at ``first`` (a new
    document starts at ``DOCUMENT_START``, an append at the position after the stored tail)."""
    position = first
    for text in texts:
        yield position
        position = next_position(position, text)
