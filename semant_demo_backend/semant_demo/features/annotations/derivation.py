"""Searchable text, context and positions derived from a span annotation (#328).

The span's anchor chunk, tag and UTF-16 half-open local offsets stay authoritative
(``offsets.py``); everything here is derived from them and the document's canonical
chunk text, never the other way round. Display normalization is not applied: the
stored text is exactly the canonical text the offsets select.

Text model
    A document's text is the concatenation of its chunk texts in ``order``, without
    separators, as the offsets already assume. Chunks outside the user collection are
    part of the text: they keep their place and their length counts.

Segments
    Chunk orders that are not consecutive are a gap: text is missing there and its
    length is unknown. Positions therefore count from the start of a *segment*, the
    maximal run of consecutive chunk orders containing the span. ``segment`` is the
    ``order`` of the segment's first chunk. Positions of two annotations are comparable
    (a distance) only when their document and segment are equal; a document without
    gaps has one segment. Nothing is invented for the missing text.

Positions
    ``start_char``/``end_char``: half-open, UTF-16 code units from the segment start (the
    units of the stored offsets). ``start_word``/``end_word``: half-open word indexes
    from the segment start; the range holds every word the span overlaps, so a span
    starting or ending inside a word includes that word. A span without any word
    character gets the empty range at the next word. Word counts are not language-model
    token counts.

Words
    A word is a maximal run of letters, combining marks, digits and format characters
    (Unicode categories L*, M*, N*, Cf: soft hyphen, zero-width joiners). Everything else
    separates words: whitespace, punctuation including hyphens and apostrophes
    ("Frýdek-Místek" is two words), and symbols. Historical letters (``ſ``) and OCR
    output are segmented by the same rule; there is no spelling normalization. A word
    split only by a chunk boundary is one word.

Context
    ``left_context``/``right_context``: up to ``CONTEXT_CHARS`` code points before and
    after the span within its segment, shortened so they do not begin or end inside a
    word (unless the segment boundary is reached first). Fixed and independent of any
    display width; a different policy needs a new ``DERIVATION_VERSION`` and a backfill.
"""
import bisect
import re
import sys
import unicodedata
from dataclasses import dataclass
from functools import cache
from typing import Sequence
from uuid import UUID

from semant_demo.features.annotations.offsets import InvalidSpanRange, check_span_range, code_point_offset, text_length

DERIVATION_VERSION = 1
"""Version of this derivation policy, stored with derived fields (backfill finds older ones)."""

CONTEXT_CHARS = 200
"""Code points of context stored on each side of an annotation (before word trimming)."""


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


def _is_word(char: str) -> bool:
    return _word_pattern().fullmatch(char) is not None


@dataclass(frozen=True)
class DerivedText:
    text: str
    left_context: str
    right_context: str
    segment: int
    """``order`` of the first chunk of the span's gap-free run of chunks."""
    start_char: int
    end_char: int
    start_word: int
    end_word: int


class DocumentText:
    """The canonical text of one document for deriving its annotations.

    ``chunks`` are all chunks of the document that exist, each with ``id``, ``order`` and
    ``text``, in any order. Segment texts and words are computed once per segment, so
    deriving many annotations of a document (backfill) reads and segments it once.
    """

    def __init__(self, chunks: Sequence):
        self.chunks = sorted(chunks, key=lambda c: c.order)
        self._index = {UUID(str(c.id)): i for i, c in enumerate(self.chunks)}
        self._segments: dict[int, tuple[str, list[int], list[int]]] = {}

    def _segment_first(self, index: int) -> int:
        while index > 0 and self.chunks[index - 1].order == self.chunks[index].order - 1:
            index -= 1
        return index

    def _segment(self, first: int) -> tuple[str, list[int], list[int]]:
        """Text of the segment starting at chunk ``first`` and its word starts and ends."""
        if first not in self._segments:
            last = first
            while last + 1 < len(self.chunks) and self.chunks[last + 1].order == self.chunks[last].order + 1:
                last += 1
            text = "".join(c.text for c in self.chunks[first:last + 1])
            words = word_spans(text)
            self._segments[first] = (text, [s for s, _ in words], [e for _, e in words])
        return self._segments[first]

    def derive(self, chunk_id, start: int, end: int) -> DerivedText:
        """The derived fields of the span anchored on ``chunk_id`` with local ``start``/``end``.

        Raises ``InvalidSpanRange`` (code ``missing_anchor`` for an anchor chunk that does
        not exist, otherwise as ``check_span_range``) when the offsets do not describe text.
        """
        anchor = self._index.get(UUID(str(chunk_id)))
        if anchor is None:
            raise InvalidSpanRange("missing_anchor", "The span's chunk does not exist")
        check_span_range(self.chunks[anchor:], start, end)
        first = self._segment_first(anchor)
        text, word_starts, word_ends = self._segment(first)
        prefix = sum(text_length(c.text) for c in self.chunks[first:anchor])
        start_char, end_char = prefix + start, prefix + end
        a, b = code_point_offset(text, start_char), code_point_offset(text, end_char)

        left = max(0, a - CONTEXT_CHARS)
        if 0 < left < a and _is_word(text[left - 1]) and _is_word(text[left]):
            left = min(a, word_ends[bisect.bisect_right(word_starts, left) - 1])
        right = min(len(text), b + CONTEXT_CHARS)
        if b < right < len(text) and _is_word(text[right - 1]) and _is_word(text[right]):
            right = max(b, word_starts[bisect.bisect_right(word_starts, right) - 1])

        return DerivedText(
            text=text[a:b], left_context=text[left:a], right_context=text[b:right],
            segment=self.chunks[first].order, start_char=start_char, end_char=end_char,
            start_word=bisect.bisect_right(word_ends, a), end_word=bisect.bisect_left(word_starts, b))


def render_vector_input(template: str, derived: DerivedText) -> str:
    """The contextual vector's input: ``template`` with ``{left}``, ``{text}`` and ``{right}``
    replaced (literally; braces in the text are kept)."""
    pieces = re.split(r"(\{left\}|\{text\}|\{right\})", template)
    values = {"{left}": derived.left_context, "{text}": derived.text, "{right}": derived.right_context}
    return "".join(values.get(p, p) for p in pieces)
