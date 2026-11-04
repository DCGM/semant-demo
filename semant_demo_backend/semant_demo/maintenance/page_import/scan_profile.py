"""Import profile v1 of the stored page scans (#594): the size of the derived viewing JPEG
and the layout geometry scaled to it.

The stored scan is a **derived viewing asset**, made from the original source JPEG (never
from an already derived one): scans whose small print is large are reduced so that the 10th
percentile of the line heights becomes ``TARGET_LINE_HEIGHT``, at most ``MAX_REDUCTION``
times; every scan is re-encoded as JPEG quality ``QUALITY``. The layout file of the page then
describes the derived JPEG's pixels. The originals stay in source storage.
"""
import io
import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

PERCENTILE = 10
MIN_RESIZED_LINE_HEIGHT = 20
"""A 10th-percentile line height (``above + below``) below this keeps the original size."""
TARGET_LINE_HEIGHT = 18
MAX_REDUCTION = 3
QUALITY = 85

PROFILE: dict[str, Any] = {
    "name": "page-scan", "version": 1, "percentile": PERCENTILE, "minResizedLineHeight": MIN_RESIZED_LINE_HEIGHT,
    "targetLineHeight": TARGET_LINE_HEIGHT, "maxReduction": MAX_REDUCTION, "resample": "lanczos",
    "format": "JPEG", "quality": QUALITY, "optimize": True}
"""Everything the derived scan depends on besides its source and the layout's line heights.
A stored scan made with another profile is regenerated."""


def line_heights(layout: dict) -> list[int]:
    """``above + below`` of every layout line with valid heights (two non-negative integers
    with a positive sum); other lines are ignored."""
    found = []
    for region in layout.get("regions") or []:
        for line in region.get("lines") or []:
            h = line.get("heights")
            if (isinstance(h, list) and len(h) == 2 and all(isinstance(v, int) and not isinstance(v, bool) for v in h)
                    and min(h) >= 0 and sum(h) > 0):
                found.append(h[0] + h[1])
    return found


def percentile(values: Iterable[float], p: float = PERCENTILE) -> float | None:
    """The ``p``-th percentile with linear interpolation between closest ranks (numpy's default)."""
    ordered = sorted(values)
    if not ordered:
        return None
    k = (len(ordered) - 1) * p / 100
    low = math.floor(k)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (k - low)


def reduction(line_height: float | None) -> float:
    """How many times smaller the derived scan is in each dimension (1: original size)."""
    if line_height is None or line_height < MIN_RESIZED_LINE_HEIGHT:
        return 1.0
    return min(MAX_REDUCTION, line_height / TARGET_LINE_HEIGHT)


def output_size(width: int, height: int, factor: float) -> tuple[int, int]:
    """The derived size: aspect ratio kept, never enlarged, never more than ``MAX_REDUCTION``
    times smaller in either dimension (after rounding)."""
    if factor <= 1:
        return width, height

    def side(n: int) -> int:
        return min(n, max(1, math.ceil(n / MAX_REDUCTION), round(n / factor)))
    return side(width), side(height)


def source_line_height(layout: dict, source_size: tuple[int, int]) -> float | None:
    """The 10th-percentile line height in source-JPEG pixels. Layout heights are in the PAGE
    XML's pixels; when the PAGE XML names another image size, they are converted."""
    h10 = percentile(line_heights(layout))
    image = layout.get("image") or {}
    if h10 is None:
        return None
    if image.get("height") and image["height"] != source_size[1]:
        h10 = h10 * source_size[1] / image["height"]
    return h10


@dataclass(frozen=True)
class Derived:
    data: bytes
    size: tuple[int, int]


def derive_scan(source: bytes, size: tuple[int, int]) -> Derived:
    """Resize (Lanczos) the source JPEG to ``size`` when it differs, and encode as JPEG
    ``QUALITY`` with ``optimize``. Grayscale stays grayscale; the colour profile is kept."""
    from PIL import Image  # maintenance dependency (requirements-dev.txt)
    with Image.open(io.BytesIO(source)) as image:
        icc = image.info.get("icc_profile")
        image = image.convert("L" if image.mode in ("L", "1", "I;16") else "RGB")
        if image.size != size:
            image = image.resize(size, Image.Resampling.LANCZOS)
        out = io.BytesIO()
        options: dict[str, Any] = {"quality": QUALITY, "optimize": True}
        if icc:
            options["icc_profile"] = icc
        image.save(out, "JPEG", **options)
        return Derived(out.getvalue(), image.size)


def _clamp(value: int, top: int) -> int:
    return max(0, min(top, value))


def _length(points: list[list[int]]) -> float:
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def scale_layout(layout: dict, size: tuple[int, int]) -> dict:
    """The layout with its pixel geometry in a ``size`` image: ``image``, baselines (rounded,
    clamped to the image), heights (by the vertical scale) and word starts (by the change of
    the baseline's length; the horizontal scale for a zero-length one). Ids, text and order
    are unchanged. A layout without an image size, or of this size already, is returned as is."""
    image = layout.get("image")
    if not image or (image.get("width"), image.get("height")) == size:
        return layout
    width, height = size
    sx, sy = width / image["width"], height / image["height"]
    regions = []
    for region in layout.get("regions") or []:
        lines = []
        for line in region.get("lines") or []:
            entry = dict(line)
            baseline = [[_clamp(round(x * sx), width), _clamp(round(y * sy), height)] for x, y in line["baseline"]]
            entry["baseline"] = baseline
            if line.get("heights") is not None:
                entry["heights"] = [max(0, round(v * sy)) for v in line["heights"]]
            if line.get("wordStarts") is not None:
                before = _length(line["baseline"])
                ratio = _length(baseline) / before if before > 0 else sx
                entry["wordStarts"] = [max(0, round(v * ratio)) for v in line["wordStarts"]]
            lines.append(entry)
        regions.append({**region, "lines": lines})
    return {**layout, "image": {"width": width, "height": height}, "regions": regions}
