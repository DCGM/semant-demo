"""Integer line geometry for the page JSON. Positions are pixels of the original scan and
approximate: word starts are estimated from character counts along the baseline."""
import math
from collections.abc import Sequence

from semant_demo.features.documents.positions import word_spans
from semant_demo.maintenance.page_layout.parse import Line, Point


def integer_points(points: Sequence[Point]) -> list[list[int]]:
    return [[round(x), round(y)] for x, y in points]


def baseline_length(points: Sequence[Point]) -> float:
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def line_heights(line: Line) -> list[int] | None:
    """``[above, below]`` the baseline in whole pixels: from ``custom``, else estimated from
    the line polygon's extent around the mean baseline height; None when neither exists."""
    if line.heights is not None:
        return [max(0, round(line.heights[0])), max(0, round(line.heights[1]))]
    if not line.polygon or not line.baseline:
        return None
    y = sum(p[1] for p in line.baseline) / len(line.baseline)
    return [max(0, round(y - min(p[1] for p in line.polygon))), max(0, round(max(p[1] for p in line.polygon) - y))]


def word_starts(text: str, baseline: Sequence[Point]) -> list[int] | None:
    """One integer per word (the #463 word rule): its estimated distance in pixels along the
    baseline from the first baseline point, proportional to the word's first code point in
    the line. None when the line has no text or a baseline of zero length."""
    length = baseline_length(baseline)
    if not text or length <= 0:
        return None
    return [round(start * length / len(text)) for start, _ in word_spans(text)]
