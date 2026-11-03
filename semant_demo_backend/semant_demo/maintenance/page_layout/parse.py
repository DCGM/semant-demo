"""PAGE XML parsing with pero-ocr's order (``PageLayout().from_pagexml()``, pero-ocr 0.7.0).

Regions are taken in XML element order: pero-ocr reads ``ReadingOrder`` but applies it only
when the layout is built with ``file=``, which the legacy chunking did not do. Lines are in
XML order (``index`` is ignored); a line without a ``Baseline`` is dropped. The text is
``TextEquiv/Unicode`` verbatim (no stripping); a line without ``TextEquiv`` has no text.
Like pero-ocr, the lines of a region include those of nested regions (reported).
"""
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from uuid import UUID

NAMESPACE = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"
NAMESPACE_PREFIX = "http://schema.primaresearch.org/PAGE/gts/pagecontent/"

Point = tuple[float, float]


class PageXmlError(ValueError):
    """The file is not PAGE XML that can be read (the legacy chunking failed on it)."""


@dataclass(frozen=True)
class Line:
    id: str | None
    text: str | None
    """``TextEquiv/Unicode`` verbatim; None without ``TextEquiv``."""
    conf: float | None
    baseline: tuple[Point, ...]
    heights: tuple[float, float] | None
    """Above and below the baseline, from ``custom``; None when absent."""
    polygon: tuple[Point, ...] = ()


@dataclass(frozen=True)
class Region:
    id: str | None
    lines: tuple[Line, ...]


@dataclass(frozen=True)
class Page:
    page_id: UUID
    width: int | None
    height: int | None
    regions: tuple[Region, ...]
    warnings: tuple[tuple[str, str], ...] = field(default=())
    """``(code, detail)``: ``image_filename_mismatch``, ``page_namespace``, ``nested_region``,
    ``duplicate_line_id``, ``line_without_baseline``, ``invalid_points``."""


def parse_points(text: str | None) -> tuple[Point, ...]:
    """``"x,y x,y ..."`` -> points; raises ``ValueError`` on malformed input."""
    points = []
    for pair in (text or "").split():
        x, y = pair.split(",")
        points.append((float(x), float(y)))
    return tuple(points)


_HEIGHTS = re.compile(r"heights(?:_v2)?\W*\[([^\]]*)\]")


def parse_heights(custom: str | None) -> tuple[float, float] | None:
    """``heights`` (above, below) from a line's ``custom`` attribute: JSON as PERO writes it
    (``{"heights": [18.6, 6.9], ...}``) or the older ``heights_v2:[..]`` form. Read as floats
    (pero-ocr's own regex turns 18.6 into 18 and 6)."""
    if not custom:
        return None
    values = None
    try:
        data = json.loads(custom)
        if isinstance(data, dict):
            values = data.get("heights") or data.get("heights_v2")
    except ValueError:
        pass
    if values is None and (match := _HEIGHTS.search(custom)):
        try:
            values = [float(v) for v in match.group(1).replace(",", " ").split()]
        except ValueError:
            values = None
    if isinstance(values, list) and len(values) == 2 and all(isinstance(v, (int, float)) for v in values):
        return float(values[0]), float(values[1])
    return None


def _int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def parse_page_xml(data: bytes, page_id: UUID) -> Page:
    """The regions and lines of one page (see the module docs). Raises ``PageXmlError`` when
    the file is not well-formed or not PAGE XML."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise PageXmlError(f"not well-formed XML: {e}") from e
    namespace = root.tag[1:].split("}")[0] if root.tag.startswith("{") else ""
    if not namespace.startswith(NAMESPACE_PREFIX) or root.tag != f"{{{namespace}}}PcGts":
        raise PageXmlError(f"not PAGE XML: root element {root.tag}")
    ns = f"{{{namespace}}}"
    page = root.find(ns + "Page")
    if page is None:
        raise PageXmlError("no Page element")
    warnings: list[tuple[str, str]] = []
    if namespace != NAMESPACE:
        warnings.append(("page_namespace", namespace))
    if (name := page.get("imageFilename")) is not None and name.rsplit(".", 1)[0] != str(page_id) \
            and name != str(page_id):
        warnings.append(("image_filename_mismatch", name))

    regions = []
    for region in page.iter(ns + "TextRegion"):
        if region.find(".//" + ns + "TextRegion") is not None:
            warnings.append(("nested_region", region.get("id") or ""))
        lines = []
        for line in region.iter(ns + "TextLine"):
            try:
                baseline_element = line.find(ns + "Baseline")
                if baseline_element is None:
                    warnings.append(("line_without_baseline", line.get("id") or ""))
                    continue
                baseline = parse_points(baseline_element.get("points"))
                coords = line.find(ns + "Coords")
                polygon = parse_points(coords.get("points")) if coords is not None else ()
            except ValueError:
                warnings.append(("invalid_points", line.get("id") or ""))
                continue
            equiv = line.find(ns + "TextEquiv")
            text = conf = None
            if equiv is not None:
                unicode = equiv.find(ns + "Unicode")
                text = (unicode.text if unicode is not None else None) or ""
                try:
                    conf = float(equiv.get("conf")) if equiv.get("conf") is not None else None
                except ValueError:
                    conf = None
            lines.append(Line(id=line.get("id"), text=text, conf=conf, baseline=baseline,
                              heights=parse_heights(line.get("custom")), polygon=polygon))
        regions.append(Region(id=region.get("id"), lines=tuple(lines)))

    ids = Counter(line.id for region in regions for line in region.lines if line.id is not None)
    warnings += [("duplicate_line_id", line_id) for line_id, count in sorted(ids.items()) if count > 1]
    return Page(page_id=page_id, width=_int(page.get("imageWidth")), height=_int(page.get("imageHeight")),
                regions=tuple(regions), warnings=tuple(warnings))
