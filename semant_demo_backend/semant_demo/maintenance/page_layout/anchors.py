"""Chunk-start anchors: where each chunk's first character is in the page layout.

The serialized document text is the regenerated chunks concatenated without separators (as
in #463). Chunks are matched to it in ``order``, never before the previous anchor:

``exact``        the chunk text equals the regenerated chunk with the same index (``order``
                 minus the first order), or occurs at the cursor (the end of the previous
                 match) or uniquely near it;
``approximate``  within a window around the cursor the chunk text aligns with at most
                 ``max_edit_ratio`` of its length differing (``difflib`` matching blocks:
                 the larger length minus the matched characters); a warning, and the
                 frontend highlights whole lines. Refused when the text occurs exactly
                 elsewhere (near-duplicate text, e.g. after a page-order error);
none             not found, too different, ambiguous, backwards, or an empty chunk; a
                 reason code.

After a miss (e.g. a chunk missing from the stored list) the cursor is resynchronized on
pieces of the chunk that occur only once ahead.

``layoutStart`` is ``{pageId, lineId, offset, match}``, ``offset`` in UTF-16 units from
the start of the line's transcription. ``replay`` is the walk the frontend does from an
anchor: the line from ``offset``, then each following line of the page files, preceded by
``\\n`` within a region and ``\\n\\n`` between regions and pages.
"""
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any
from uuid import UUID

from semant_demo.features.annotations.offsets import code_point_offset, utf16_offset
from semant_demo.features.documents.positions import text_length
from semant_demo.maintenance.page_layout.serialize import Contribution, Serialization

MAX_EDIT_RATIO = 0.05
CONSECUTIVE_MISSES = 3
"""Misses in a row that add a document warning (often a wrong page order or parameters)."""
_PREFIX = 32
_SOLID = 8
"""Matching blocks shorter than this do not position an approximate match."""


@dataclass(frozen=True)
class Stream:
    """The serialized document text and, per code point, the line it comes from."""
    text: str
    owners: tuple[Contribution | None, ...]
    """The contribution of each code point; None for a separator."""
    offsets: tuple[int, ...]
    """The code point offset in that line."""
    chunk_starts: tuple[int, ...] = ()
    """Where each regenerated chunk starts in ``text``."""


def build_stream(serialization: Serialization) -> Stream:
    text, owners, offsets, starts = [], [], [], []
    for chunk in serialization.chunks:
        starts.append(len(owners))
        raw_owner: list[Contribution | None] = [None] * len(chunk.raw)
        raw_offset = [0] * len(chunk.raw)
        for contribution in chunk.contributions:
            for i in range(len(contribution.text)):
                raw_owner[contribution.start + i] = contribution
                raw_offset[contribution.start + i] = i
        start, end = chunk.lead, chunk.lead + len(chunk.text)
        text.append(chunk.text)
        owners += raw_owner[start:end]
        offsets += raw_offset[start:end]
    return Stream("".join(text), tuple(owners), tuple(offsets), tuple(starts))


@dataclass(frozen=True)
class Anchor:
    page_id: UUID
    line_id: str | None
    offset: int
    """UTF-16 units from the start of the line's transcription."""
    match: str

    def as_json(self) -> dict[str, Any]:
        return {"pageId": str(self.page_id), "lineId": self.line_id, "offset": self.offset, "match": self.match}


@dataclass(frozen=True)
class ChunkMatch:
    anchor: Anchor | None
    reason: str | None = None
    """For no anchor: ``empty_chunk``, ``not_found``, ``start_not_found``, ``too_different``,
    ``ambiguous``, ``backwards``, ``no_line``, ``duplicate_line_id``. For an anchor found away
    from the expected place: ``shifted`` or ``resynced``; for an approximate one: ``edited``
    or ``replay_mismatch``."""
    differences: int | None = None
    position: int | None = None
    """Where the chunk starts in the serialized text."""
    end: int | None = None
    """Where its matched text ends there."""


def _anchor_at(stream: Stream, position: int, end: int, match: str) -> tuple[Anchor | None, int]:
    """The anchor of the first line character at or after ``position`` (before ``end``)."""
    while position < end and stream.owners[position] is None:
        position += 1
    if position >= end:
        return None, position
    owner = stream.owners[position]
    return Anchor(owner.page_id, owner.line_id, utf16_offset(owner.text, stream.offsets[position]), match), position


def _occurrences(text: str, needle: str, start: int, end: int) -> int:
    count, index = 0, text.find(needle, start, end)
    while index != -1 and count < 2:
        count += 1
        index = text.find(needle, index + 1, end)
    return count


def match_chunks(stream: Stream, chunks: Sequence[tuple[int, str]],
                 max_edit_ratio: float = MAX_EDIT_RATIO) -> tuple[list[ChunkMatch], list[str]]:
    """One match per ``(order, text)`` chunk, sorted by order, and document warning codes."""
    matches: list[ChunkMatch] = []
    warnings: list[str] = []
    cursor, previous, misses = 0, -1, 0
    base = chunks[0][0] if chunks else 0
    for order, text in chunks:
        if not text:
            matches.append(ChunkMatch(None, "empty_chunk"))
            continue
        result = _by_order(stream, order - base, text, previous, cursor)
        if result is None:
            result = _guarded(stream, text, _match_at(stream, text, cursor, previous, max_edit_ratio), previous)
        if result.anchor is None and result.reason in ("not_found", "too_different", "start_not_found"):
            for resynced in _resync_cursors(stream.text, text, max(previous + 1, 0)):
                retry = _guarded(stream, text, _match_at(stream, text, resynced, previous, max_edit_ratio), previous)
                if retry.anchor is not None:
                    result = ChunkMatch(retry.anchor, "resynced" if retry.reason is None else retry.reason,
                                        retry.differences, retry.position, retry.end)
                    break
        cursor = result.end if result.anchor is not None else cursor + len(text)
        if result.anchor is None:
            misses += 1
            if misses == CONSECUTIVE_MISSES and "consecutive_misses" not in warnings:
                warnings.append("consecutive_misses")
        else:
            misses = 0
            previous = result.position
        matches.append(result)
    return matches, warnings


def _by_order(stream: Stream, index: int, text: str, previous: int, cursor: int) -> ChunkMatch | None:
    """Exact when the regenerated chunk with this index has the same text."""
    if not 0 <= index < len(stream.chunk_starts):
        return None
    start = stream.chunk_starts[index]
    end = stream.chunk_starts[index + 1] if index + 1 < len(stream.chunk_starts) else len(stream.text)
    if start <= previous or stream.text[start:end] != text:
        return None
    anchor, position = _anchor_at(stream, start, end, "exact")
    if anchor is None or position != start:
        return None
    return ChunkMatch(anchor, None if start == cursor else "shifted", 0, start, end)


def _guarded(stream: Stream, text: str, result: ChunkMatch, previous: int) -> ChunkMatch:
    """An approximate match is refused when the text occurs exactly elsewhere: it is then
    placed there if that occurrence is the only one after the previous anchor."""
    if result.anchor is None or result.anchor.match != "approximate" or stream.text.find(text) == -1:
        return result
    index = stream.text.find(text, previous + 1)
    if index != -1 and stream.text.find(text, index + 1) == -1:
        anchor, position = _anchor_at(stream, index, index + len(text), "exact")
        if anchor is not None and position == index:
            return ChunkMatch(anchor, "resynced", 0, index, index + len(text))
    return ChunkMatch(None, "ambiguous", result.differences)


def _match_at(stream: Stream, text: str, cursor: int, previous: int, max_edit_ratio: float) -> ChunkMatch:
    """Exact at ``cursor``, else approximate in the window around it."""
    full = stream.text
    candidates = [cursor] if full.startswith(text, cursor) else []
    if not candidates:
        # the text unchanged but slightly off the cursor (e.g. after an approximate match)
        margin = max(64, len(text) // 10)
        low, high = max(0, cursor - margin), min(len(full), cursor + len(text) + margin)
        index = full.find(text, low, high)
        if index != -1 and full.find(text, index + 1, high) == -1:
            candidates = [index]
    for start in candidates:
        if start <= previous:
            continue
        anchor, position = _anchor_at(stream, start, start + len(text), "exact")
        if anchor is not None and position == start:
            return ChunkMatch(anchor, None if start == cursor else "shifted", 0, start, start + len(text))
    return _approximate(stream, text, cursor, previous, max_edit_ratio)


def _resync_cursors(full: str, text: str, start: int) -> list[int]:
    """Candidate cursors after a miss (e.g. a chunk missing from the stored list): for a few
    pieces of the chunk, the place the chunk would start if the piece's only occurrence after
    ``start`` is where it belongs. Pieces that occur twice are skipped."""
    cursors = []
    for k in dict.fromkeys((0, len(text) // 4, len(text) // 2, 3 * len(text) // 4)):
        piece = text[k:k + _PREFIX]
        if len(piece) < _PREFIX // 2:
            continue
        index = full.find(piece, start)
        if index != -1 and full.find(piece, index + 1) == -1 and (cursor := max(start, index - k)) not in cursors:
            cursors.append(cursor)
    return cursors


def _approximate(stream: Stream, text: str, cursor: int, previous: int, max_edit_ratio: float) -> ChunkMatch:
    full = stream.text
    margin = max(64, len(text) // 10)
    low, high = max(0, cursor - margin), min(len(full), cursor + len(text) + margin)
    window = full[low:high]
    if not window:
        return ChunkMatch(None, "not_found")
    blocks = [b for b in SequenceMatcher(None, text, window, autojunk=False).get_matching_blocks() if b.size]
    if not blocks:
        return ChunkMatch(None, "not_found")
    matched = sum(b.size for b in blocks)
    # position the chunk by its first and last solid blocks: short blocks match by accident
    solid = [b for b in blocks if b.size >= _SOLID] or blocks
    first, last = solid[0], solid[-1]
    if low + first.b - first.a < low or first.a > _SOLID:
        # the chunk's first characters are not in the window (or come from elsewhere, e.g. a page
        # out of order): a start derived from later text would point into the wrong line
        return ChunkMatch(None, "start_not_found")
    start = low + first.b - first.a
    end = min(len(full), max(start, low + last.b + last.size + len(text) - last.a - last.size))
    differences = max(len(text), end - start) - matched
    if differences > max_edit_ratio * len(text):
        return ChunkMatch(None, "too_different", differences)
    prefix = text[:_PREFIX]
    if len(prefix) >= 8 and _occurrences(full, prefix, low, high) > 1:
        return ChunkMatch(None, "ambiguous", differences)
    if start <= previous:
        return ChunkMatch(None, "backwards", differences)
    anchor, position = _anchor_at(stream, start, max(end, start + 1), "approximate")
    if anchor is None:
        return ChunkMatch(None, "no_line", differences)
    return ChunkMatch(anchor, "edited" if differences else "shifted", differences, position, max(end, position))


def replay(pages: Mapping[str, Mapping[str, Any]], page_order: Sequence[str], anchor: Mapping[str, Any],
           length: int) -> str | None:
    """The ``length`` UTF-16 units of text from ``anchor`` (a ``layoutStart``) through the page
    files in ``page_order``; None when the anchor's page or line is not there."""
    if anchor["pageId"] not in page_order:
        return None
    parts: list[str] = []
    units, started = 0, False
    for page_id in page_order[page_order.index(anchor["pageId"]):]:
        for region in (pages.get(page_id) or {}).get("regions", []):
            for i, line in enumerate(region["lines"]):
                text = line["text"] or ""
                if not started:
                    if page_id != anchor["pageId"] or line["id"] != anchor["lineId"]:
                        continue
                    started = True
                    piece = text[code_point_offset(text, anchor["offset"]):]
                else:
                    piece = ("\n" if i else "\n\n") + text
                parts.append(piece)
                units += text_length(piece)
                if units >= length:
                    joined = "".join(parts)
                    return joined[:code_point_offset(joined, length)]
    return "".join(parts) if started else None
