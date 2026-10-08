"""Span coordinates (ADR 0006), the backend twin of ``src/utils/spanOffsets.ts``.

Characterized from the current code, not redefined (#206):

- A span is stored on the chunk where it starts (its anchor) with ``start``/``end``
  relative to the start of that chunk's text, half-open (``end`` is exclusive).
- Units are UTF-16 code units: the document view measures chunk text with JavaScript
  ``String.length`` and sends those offsets. They equal Python ``len`` (code points)
  only for text without characters outside the Basic Multilingual Plane; a combining
  mark counts as its own unit in both.
- ``end`` may exceed the anchor chunk's length: the span then continues into the
  following chunks of the same document, measured as if their texts were concatenated.
  Chunks are consecutive when their ``order`` values differ by one; membership in a
  collection does not matter. A span cannot continue across a gap in ``order``.

``tests/fixtures/text_offsets.json`` holds the cases both implementations must agree on.
"""
from dataclasses import dataclass
from typing import Sequence

from semant_demo.core.errors import InvalidRequestError


def text_length(text: str) -> int:
    """Length of ``text`` in UTF-16 code units, as the browser measures it."""
    return len(text.encode("utf-16-le")) // 2


@dataclass(frozen=True)
class ChunkSpan:
    """The part of a span inside one chunk, in that chunk's coordinates."""
    index: int
    start: int
    end: int


class InvalidSpanRange(InvalidRequestError):
    """The span's offsets do not describe text of its document (400)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _run(chunks: Sequence, anchor: int):
    """(index, length) of the anchor chunk and the consecutive chunks after it."""
    for i in range(anchor, len(chunks)):
        if i > anchor and chunks[i].order != chunks[i - 1].order + 1:
            return
        yield i, text_length(chunks[i].text)


def project_span(chunks: Sequence, anchor: int, start: int, end: int) -> list[ChunkSpan]:
    """The parts of a span anchored on ``chunks[anchor]`` in each chunk it covers.

    ``chunks`` are in document order and have ``order`` and ``text``. Parts are clipped
    to each chunk; nothing is projected across a gap or into earlier chunks.
    """
    parts: list[ChunkSpan] = []
    offset = 0
    for i, length in _run(chunks, anchor):
        local_start, local_end = max(0, start - offset), min(length, end - offset)
        if local_end > local_start:
            parts.append(ChunkSpan(i, local_start, local_end))
        offset += length
        if end <= offset:
            break
    return parts


def check_span_range(chunks: Sequence, start: int, end: int) -> None:
    """Raise ``InvalidSpanRange`` unless ``[start, end)`` lies within the chunks' text.

    ``chunks[0]`` is the anchor chunk; the rest are the following chunks of its document
    in order (they may contain gaps). Only as many following chunks as ``end`` needs
    have to be given.
    """
    if start < 0:
        raise InvalidSpanRange("negative_start", "Span start must not be negative")
    if end <= start:
        raise InvalidSpanRange("empty", "Span end must be greater than its start")
    if start >= text_length(chunks[0].text):
        raise InvalidSpanRange("start_outside_anchor", "Span start must lie within the span's chunk")
    covered, last = 0, 0
    for last, length in _run(chunks, 0):
        covered += length
        if end <= covered:
            return
    if last + 1 < len(chunks):
        raise InvalidSpanRange("gap", "Span crosses a gap between the document's chunks")
    raise InvalidSpanRange("past_end", "Span ends after the end of the document's text")
