"""Searchable text, context and positions derived from a span annotation (#328, #463).

The span's anchor chunk, tag and UTF-16 half-open local offsets stay authoritative
(``offsets.py``); everything here is derived from them and the document's canonical
chunk text, never the other way round. Display normalization is not applied: the
stored text is exactly the canonical text the offsets select.

Text model
    A document's text is the concatenation of its chunk texts in ``order``, without
    separators, as the offsets already assume; its chunk orders are consecutive. Chunks
    outside the user collection are part of the text: they keep their place and their
    length counts. Words and chunk positions are defined in
    ``features/documents/positions.py``.

Positions
    Absolute in the document, read from the anchor chunk's stored position (#463), so a
    span is derived from its anchor, the chunks it covers and the few chunks around it
    that its context needs, whatever the length of the document (``SpanSource``).
    ``start_char``/``end_char``: half-open, UTF-16 code units from the document start (the
    units of the stored offsets). ``start_word``/``end_word``: half-open word indexes from
    the document start; the range holds every word the span overlaps, so a span starting
    or ending inside a word includes that word: ``start_word`` is the number of words
    ending at or before the span start, ``end_word`` the number of words starting before
    its end. A span without any word character gets the empty range at the next word.
    Word counts are not language-model token counts.

Context
    ``left_context``/``right_context``: up to ``CONTEXT_CHARS`` code points before and
    after the span within the document, shortened so they do not begin or end inside a
    word (unless the document boundary is reached first). Fixed and independent of any
    display width; a different policy needs a new ``DERIVATION_VERSION`` and a backfill.

Chunks without stored positions, or whose positions do not follow from each other
(``next_position``), raise ``MissingChunkPositions``: an enrichment failure, never a
reason to read the whole document instead.
"""
import bisect
import re
from dataclasses import dataclass
from typing import Sequence

from semant_demo.features.annotations.offsets import check_span_range, code_point_offset
from semant_demo.features.documents.positions import (
    DOCUMENT_START, ChunkPosition, is_word, next_position, word_spans,
)

DERIVATION_VERSION = 1
"""Version of this derivation policy, stored with derived fields (backfill finds older ones)."""

CONTEXT_CHARS = 200
"""Code points of context stored on each side of an annotation (before word trimming)."""


class MissingChunkPositions(Exception):
    """A chunk the derivation reads has no stored position, or one that does not follow
    from the chunk before it (#463: run the chunk position backfill)."""


def position_of(chunk) -> ChunkPosition:
    """The chunk's stored position; raises ``MissingChunkPositions`` when it has none."""
    if chunk.start_char is None or chunk.start_word is None or chunk.word_open_at_start is None:
        raise MissingChunkPositions(f"Chunk {chunk.id} has no stored position")
    return ChunkPosition(chunk.start_char, chunk.start_word, chunk.word_open_at_start)


@dataclass(frozen=True)
class DerivedText:
    text: str
    left_context: str
    right_context: str
    start_char: int
    end_char: int
    start_word: int
    end_word: int


@dataclass(frozen=True)
class SpanSource:
    """The chunks a span's derivation reads: its anchor ``chunks[anchor]`` and the
    consecutive chunks of its document before and after it, in order, each with ``id``,
    ``order``, ``text`` and the stored position (``start_char``, ``start_word``,
    ``word_open_at_start``).

    They must cover the span and ``CONTEXT_CHARS`` + 1 code points on each side of it
    (one more to tell whether the context starts or ends inside a word), unless
    ``at_document_start`` / ``at_document_end`` say that the first / last chunk is the
    document's first / last one.
    """
    chunks: Sequence
    anchor: int
    at_document_start: bool
    at_document_end: bool


def check_positions(chunks: Sequence, at_document_start: bool) -> None:
    """Raise ``MissingChunkPositions`` unless every chunk has a stored position that follows
    from the one before it (and the first chunk of the document is at its start)."""
    positions = [position_of(c) for c in chunks]
    if at_document_start and positions and positions[0] != DOCUMENT_START:
        raise MissingChunkPositions(f"Chunk {chunks[0].id} is the first of its document but starts at {positions[0]}")
    for previous, chunk, position in zip(chunks, chunks[1:], positions[1:]):
        if next_position(position_of(previous), previous.text) != position:
            raise MissingChunkPositions(f"The stored position of chunk {chunk.id} does not follow from "
                                        f"chunk {previous.id}")


def derive(source: SpanSource, start: int, end: int) -> DerivedText:
    """The derived fields of the span anchored on ``source.chunks[source.anchor]`` with local
    ``start``/``end``.

    Raises ``InvalidSpanRange`` (as ``check_span_range``) when the offsets do not describe
    text and ``MissingChunkPositions`` when the chunks' positions are missing or inconsistent.
    """
    chunks, i = source.chunks, source.anchor
    check_span_range(chunks[i:], start, end)
    check_positions(chunks, source.at_document_start)
    anchor = position_of(chunks[i])

    before = "".join(c.text for c in chunks[:i])
    local = "".join(c.text for c in chunks[i:])
    a, b = code_point_offset(local, start), code_point_offset(local, end)

    # Words counted from the anchor: a word open at its start began (and was counted) before it.
    local_words = word_spans(local)
    continued = anchor.word_open_at_start and bool(local) and is_word(local[0])
    start_word = anchor.start_word - continued + sum(e <= a for _, e in local_words)
    end_word = anchor.start_word - continued + sum(s < b for s, _ in local_words)

    # Context in the window ``text``; its start is the document start only when the source says so.
    text = before + local
    a, b = a + len(before), b + len(before)
    words = word_spans(text)
    word_starts, word_ends = [s for s, _ in words], [e for _, e in words]
    if (not source.at_document_start and a <= CONTEXT_CHARS) \
            or (not source.at_document_end and len(text) <= b + CONTEXT_CHARS):
        raise ValueError("The span source does not cover the span's context")
    left = max(0, a - CONTEXT_CHARS)
    if 0 < left < a and is_word(text[left - 1]) and is_word(text[left]):
        left = min(a, word_ends[bisect.bisect_right(word_starts, left) - 1])
    right = min(len(text), b + CONTEXT_CHARS)
    if b < right < len(text) and is_word(text[right - 1]) and is_word(text[right]):
        right = max(b, word_starts[bisect.bisect_right(word_starts, right) - 1])

    return DerivedText(
        text=text[a:b], left_context=text[left:a], right_context=text[b:right],
        start_char=anchor.start_char + start, end_char=anchor.start_char + end,
        start_word=start_word, end_word=end_word)


def render_vector_input(template: str, derived: DerivedText) -> str:
    """The contextual vector's input: ``template`` with ``{left}``, ``{text}`` and ``{right}``
    replaced (literally; braces in the text are kept)."""
    pieces = re.split(r"(\{left\}|\{text\}|\{right\})", template)
    values = {"{left}": derived.left_context, "{text}": derived.text, "{right}": derived.right_context}
    return "".join(values.get(p, p) for p in pieces)
