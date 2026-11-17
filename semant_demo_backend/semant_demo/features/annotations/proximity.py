"""Proximity of annotations (#333): which annotations have a neighbor annotation in a relation.

Compares the stored document-relative intervals of annotations (#463), never chunk text. Both
sides are read as projected positions of at most ``MAX_NEAR_ANNOTATIONS`` annotations each,
restricted to the documents that hold a neighbor; every document is matched on its own by a
window over its neighbors sorted by start (``match``), so the work is bounded by the number of
neighbors whose start can satisfy the relation, not by all pairs of a document.

Intervals are half-open, ``[start, end)``. The gap of two spans is ``max(0, sB - eA, sA - eB)``
in the chosen unit, so adjacent and overlapping spans both have gap 0. Overlap and containment
compare characters. Annotations whose positions are not current (``enrichment.text_current``:
not derived for their revision, or a document whose chunk order is malformed, #463) are never
compared: they neither match nor prove that no neighbor exists.

Word example: a span over words ``[100, 110)`` and a neighbor over ``[140, 145)`` have a gap of
30 words (the neighbor is after); a neighbor over ``[105, 115)`` overlaps (gap 0). A word only
partly covered by a span counts as covered (#463), so two spans inside one word have gap 0.
"""
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from uuid import UUID

from semant_demo.features.annotations.enrichment import text_current
from semant_demo.features.annotations.schemas import (
    MAX_NEAR_EXPLAINED, AnnotationRow, DistanceUnit, NearDirection, NearFilter, NearRelation,
)

MAX_NEAR_ANNOTATIONS = 10_000
"""Annotations one side of a proximity filter may compare at most (one Weaviate read each); more
is refused, never truncated."""
MAX_NEAR_COMPARISONS = 5_000_000
"""Interval comparisons one proximity filter may make; more is refused (e.g. a large distance
over a dense document)."""


class TooManyComparisons(Exception):
    pass


@dataclass(frozen=True)
class Interval:
    id: UUID
    document: UUID
    start_char: int
    end_char: int
    start_word: int
    end_word: int

    def start(self, unit: DistanceUnit) -> int:
        return self.start_word if unit == DistanceUnit.words else self.start_char

    def end(self, unit: DistanceUnit) -> int:
        return self.end_word if unit == DistanceUnit.words else self.end_char


def interval(row: AnnotationRow) -> Interval | None:
    """The row's document interval, or ``None`` when its positions are not current or missing."""
    values = (row.documentId, row.documentStartChar, row.documentEndChar, row.documentStartWord, row.documentEndWord)
    if not text_current(row) or any(v is None for v in values):
        return None
    return Interval(row.id, *values)  # type: ignore[arg-type]


def gap(a: Interval, b: Interval, unit: DistanceUnit) -> int:
    return max(0, b.start(unit) - a.end(unit), a.start(unit) - b.end(unit))


def related(a: Interval, b: Interval, near: NearFilter) -> bool:
    """Whether ``b`` (a neighbor) lies in ``near.relation`` to ``a`` (same document assumed)."""
    if a.id == b.id:
        return False
    match near.relation:
        case NearRelation.within:
            if near.direction == NearDirection.after and b.start_char < a.end_char:
                return False
            if near.direction == NearDirection.before and b.end_char > a.start_char:
                return False
            return gap(a, b, near.unit) <= near.distance
        case NearRelation.overlaps:
            return b.start_char < a.end_char and a.start_char < b.end_char
        case NearRelation.contains:
            return a.start_char <= b.start_char and b.end_char <= a.end_char
        case NearRelation.contained_by:
            return b.start_char <= a.start_char and a.end_char <= b.end_char
        case NearRelation.same_document:
            return True


class _Neighbors:
    """The neighbors of one document, sorted by start in one unit, for windowed lookups."""

    def __init__(self, items: list[Interval], unit: DistanceUnit):
        self.unit = unit
        self.items = sorted(items, key=lambda b: (b.start(unit), b.end(unit), str(b.id)))
        self.starts = [b.start(unit) for b in self.items]
        self.longest = max((b.end(unit) - b.start(unit) for b in self.items), default=0)

    def window(self, low: int, high: int) -> list[Interval]:
        """The neighbors starting in ``[low, high]``."""
        return self.items[bisect_left(self.starts, low):bisect_right(self.starts, high)]


def _candidates(a: Interval, chars: _Neighbors, units: _Neighbors, near: NearFilter) -> list[Interval]:
    """Neighbors that may relate to ``a``: every neighbor that does starts in the window."""
    match near.relation:
        case NearRelation.within:
            s, e = a.start(near.unit), a.end(near.unit)
            return units.window(s - near.distance - units.longest, e + near.distance)
        case NearRelation.overlaps:
            return chars.window(a.start_char - chars.longest, a.end_char - 1)
        case NearRelation.contains:
            return chars.window(a.start_char, a.end_char)
        case NearRelation.contained_by:
            return chars.window(a.start_char - chars.longest, a.start_char)
        case NearRelation.same_document:
            # Existence needs one other neighbor; the explanation names those starting nearest.
            i = bisect_left(chars.starts, a.start_char)
            return chars.items[max(0, i - MAX_NEAR_EXPLAINED - 1):i + MAX_NEAR_EXPLAINED + 1]


@dataclass
class Matched:
    """The outcome of matching primary annotations against neighbors."""
    ids: list[UUID] = field(default_factory=list)
    """Primary annotations that match (``absent``: that provably have no such neighbor)."""
    neighbors: dict[UUID, list[UUID]] = field(default_factory=dict)
    """Matching primary annotation -> its nearest related neighbors (not with ``absent``)."""
    primary: int = 0
    unknown: int = 0
    neighbors_found: int = 0
    neighbors_unpositioned: int = 0


def match(primary: list[AnnotationRow], neighbors: list[AnnotationRow], near: NearFilter) -> Matched:
    """Which ``primary`` annotations have (``near.absent``: provably have not) a neighbor of
    ``neighbors`` in ``near.relation``, document by document. Raises ``TooManyComparisons``
    beyond ``MAX_NEAR_COMPARISONS``."""
    out = Matched(primary=len(primary), neighbors_found=len(neighbors))
    by_document: dict[UUID, list[Interval]] = {}
    blind: set[UUID] = set()  # documents with a neighbor whose position is unknown
    for row in neighbors:
        found = interval(row)
        if found is None:
            out.neighbors_unpositioned += 1
            if row.documentId is not None:
                blind.add(row.documentId)
        else:
            by_document.setdefault(found.document, []).append(found)
    indexes: dict[UUID, tuple[_Neighbors, _Neighbors]] = {}
    comparisons = 0
    for row in primary:
        a = interval(row)
        if a is None or (near.absent and a.document in blind):
            out.unknown += 1
            continue
        items = by_document.get(a.document, [])
        if a.document not in indexes:
            chars = _Neighbors(items, DistanceUnit.chars)
            indexes[a.document] = (chars, chars if near.unit == DistanceUnit.chars else
                                   _Neighbors(items, near.unit))
        window = _candidates(a, *indexes[a.document], near)
        comparisons += len(window)
        if comparisons > MAX_NEAR_COMPARISONS:
            raise TooManyComparisons()
        hits = [b for b in window if related(a, b, near)]
        if near.absent:
            if not hits:
                out.ids.append(a.id)
        elif hits:
            hits.sort(key=lambda b: (gap(a, b, near.unit), abs(b.start_char - a.start_char), str(b.id)))
            out.ids.append(a.id)
            out.neighbors[a.id] = [b.id for b in hits[:MAX_NEAR_EXPLAINED]]
    return out
