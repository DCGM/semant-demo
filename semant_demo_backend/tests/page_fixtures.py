"""Synthetic page scans, layout files and manifests for the fixture corpus (#543).

The browser-test profile (``tests.e2e_server``) and the local development backend
(``tests.local_dev``) serve them from their own ``PAGE_ASSETS_DIR``, so the scan viewer can
be exercised without real scans. Every image is drawn here: paper, a frame and the text of
each layout line, written word by word along its baseline at the layout's approximate word
starts, so the overlay can be compared with what is on the scan.

The documents cover the cases the viewer must handle:

* ``chronicle``: a front cover, two text pages (straight, skewed and curved baselines) whose
  lines hold the text of the corpus chunks, a blank page, a skipped page number, a page with a
  scan but no layout, a page without any asset and a back cover;
* ``gazette``: a long periodical (``GAZETTE_PAGES`` pages) for the thumbnail strip and page jumps,
  whose page 1 holds its two chunks, one line each (exact anchors);
* ``letters`` has no pages: a text-only document.

``fixture_anchors`` gives the chunks the ``layoutStart`` of the import (#542) on these pages,
for the text/scan correspondence (#544). Nothing here is used by the production application.
"""
from __future__ import annotations

import io
import json
import math
import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from uuid import UUID

from semant_demo.adapters.filesystem.page_assets import ManifestPage, PageAssetStore, PageManifest
from semant_demo.maintenance.page_layout.geometry import baseline_length, word_starts

PARAMS = {"lineConfidence": 0.6, "minChunkChars": 768, "maxChunkChars": 1152}
GAZETTE_PAGES = 120
THUMBNAIL_WIDTH = 256
FONT_SIZE = 30
HEIGHTS = [24, 8]
"""[above, below] the baseline of every drawn line."""


@dataclass
class FixtureLine:
    id: str
    text: str
    start: tuple[int, int]
    """The first baseline point."""
    width: int
    skew: float = 0.0
    """Rise of the baseline over its width, in pixels (negative: rising to the right)."""
    curve: float = 0.0
    """Sag of the baseline at its middle, in pixels."""

    def baseline(self, points: int = 8) -> list[list[int]]:
        x0, y0 = self.start
        result = []
        for i in range(points):
            t = i / (points - 1)
            result.append([round(x0 + t * self.width),
                           round(y0 + t * self.skew + self.curve * 4 * t * (1 - t))])
        return result


@dataclass
class FixturePage:
    id: UUID
    label: str | None
    page_type: str
    regions: list[list[FixtureLine]] = field(default_factory=list)
    image: bool = True
    layout: bool = True
    size: tuple[int, int] = (1000, 1400)


def _uuid(suffix: str) -> UUID:
    return UUID(f"5e3a0000-0000-4000-8000-{suffix:0>12}")


def _wrap(text: str, width: int = 34) -> list[str]:
    """``text`` cut at spaces into lines of about ``width`` characters; the spaces stay at
    the line ends, so the lines joined give the text back."""
    lines, current = [], ""
    for word in text.split(" "):
        candidate = f"{current} {word}" if current else word
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    lines.append(current)
    return lines


def _region(prefix: str, texts: list[str], top: int, *, left: int = 90, skew: float = 0.0,
            curve: float = 0.0) -> list[FixtureLine]:
    return [FixtureLine(id=f"{prefix}-l{i + 1:03d}", text=text, start=(left, top + i * 56),
                        width=round(_font().getlength(text)), skew=skew, curve=curve)
            for i, text in enumerate(texts)]


def chronicle_pages(corpus) -> list[FixturePage]:
    chunks = {c["key"]: c["text"] for c in corpus.documents["chronicle"]["chunks"]}
    second = _wrap(chunks["chronicle_2"])
    return [
        FixturePage(_uuid("d1f00"), "[1]", "FrontCover"),
        FixturePage(_uuid("d1f01"), "1", "NormalPage", regions=[
            _region("r001", ["KRONIKA OBCE LHOTA"], 140),
            _region("r002", _wrap(chunks["chronicle_1"]), 300, skew=-18),
            _region("r003", second[:2], 620),
        ]),
        FixturePage(_uuid("d1f02"), "2", "NormalPage", regions=[
            _region("r001", second[2:], 160),
            _region("r002", _wrap(chunks["chronicle_3"], 24), 420, curve=16),
        ]),
        FixturePage(_uuid("d1f03"), "3", "Blank"),
        FixturePage(_uuid("d1f04"), "6", "NormalPage", layout=False),
        FixturePage(_uuid("d1f05"), "7", "NormalPage", image=False, layout=False),
        FixturePage(_uuid("d1f06"), "[8]", "BackCover"),
    ]


def gazette_pages(corpus) -> list[FixturePage]:
    chunks = corpus.documents["gazette"]["chunks"]
    first_page = chunks[0]["start_page_id"]
    pages = []
    for order in range(GAZETTE_PAGES):
        page_id = UUID(first_page) if order == 1 else _uuid(f"d3{order:06x}0")
        size = (600, 840)
        if order == 0:
            regions = []
        elif order == 1:
            # The page of both gazette chunks, one line each: their text is exactly the
            # serialized lines, so their anchors are exact (#544). Wider, for the long lines.
            size = (1000, 840)
            regions = [_region("r001", ["VĚSTNÍK — strana 1"], 120, left=60),
                       _region("r002", [chunks[0]["text"]], 240, left=60),
                       _region("r003", [chunks[1]["text"]], 360, left=60)]
        else:
            regions = [
                _region("r001", [f"VĚSTNÍK — strana {order}"], 120, left=60),
                _region("r002", [f"Zpráva {order}.{i}: trh a divadlo." for i in range(1, 5)], 240, left=60),
            ]
        pages.append(FixturePage(page_id, "[1]" if order == 0 else str(order),
                                 "FrontCover" if order == 0 else "NormalPage", regions=regions,
                                 size=size))
    return pages


def fixture_documents(corpus) -> dict[UUID, list[FixturePage]]:
    return {UUID(corpus.documents["chronicle"]["id"]): chronicle_pages(corpus),
            UUID(corpus.documents["gazette"]["id"]): gazette_pages(corpus)}


def fixture_anchors(corpus) -> dict[str, dict]:
    """The ``layoutStart`` of each fixture chunk on the fixture pages (#544), by chunk key, as
    the import (#542) stores them. The gazette chunks are single lines, so their anchors are
    ``exact``. The chronicle lines are the chunk text cut at spaces, the spaces kept at the
    line ends, so the serialized text has a line break more per line: ``approximate``
    anchors, one of a chunk continuing from page 1 onto page 2. The letters have no pages, so
    no anchors. ``tests/test_page_fixtures.py`` replays every anchor."""
    chronicle = [str(p.id) for p in chronicle_pages(corpus)]
    gazette = corpus.documents["gazette"]["chunks"][0]["start_page_id"]

    def anchor(page_id: str, line_id: str, match: str) -> dict:
        return {"pageId": page_id, "lineId": line_id, "offset": 0, "match": match}

    return {
        "chronicle_1": anchor(chronicle[1], "r002-l001", "approximate"),
        "chronicle_2": anchor(chronicle[1], "r003-l001", "approximate"),
        "chronicle_3": anchor(chronicle[2], "r002-l001", "approximate"),
        "gazette_1": anchor(gazette, "r002-l001", "exact"),
        "gazette_2": anchor(gazette, "r003-l001", "exact"),
    }


async def seed_layout_anchors(client, chunks_collection: str, corpus) -> None:
    """Declare ``Chunks.layoutStart`` on a freshly seeded test-owned store and store the
    fixture anchors. Only for the stores of the browser-test profile and the local
    development backend, which serve the page fixtures."""
    from semant_demo.adapters.weaviate.layout_anchors import declare_layout_start, write_layout_start

    await declare_layout_start(client, chunks_collection)
    for key, value in fixture_anchors(corpus).items():
        await write_layout_start(client, chunks_collection, UUID(corpus.chunks[key]["id"]), value)


def layout_json(page: FixturePage) -> dict:
    regions = []
    for r_index, lines in enumerate(page.regions):
        entries = []
        for line in lines:
            baseline = line.baseline()
            entry = {"id": line.id, "text": line.text, "baseline": baseline, "heights": HEIGHTS}
            if (starts := word_starts(line.text, baseline)) is not None:
                entry["wordStarts"] = starts
            entries.append(entry)
        regions.append({"id": lines[0].id.split("-")[0] if lines else f"r{r_index:03d}", "lines": entries})
    width, height = page.size
    return {"schema": "semant.page-layout", "version": 1, "pageId": str(page.id), "params": PARAMS,
            "image": {"width": width, "height": height}, "regions": regions}


FONT_FILES = ("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "DejaVuSerif.ttf")
"""A font with Czech letters where installed; Pillow's own (no diacritics) otherwise. The
images only illustrate the layout: the tests read the layout files, not the pixels."""


@cache
def _font():
    from PIL import ImageFont
    for name in FONT_FILES:
        try:
            return ImageFont.truetype(name, FONT_SIZE)
        except OSError:
            continue
    return ImageFont.load_default(size=FONT_SIZE)


def _point_along(baseline: list[list[int]], distance: float) -> tuple[float, float]:
    for (x1, y1), (x2, y2) in zip(baseline, baseline[1:]):
        step = math.dist((x1, y1), (x2, y2))
        if distance <= step or (x2, y2) == tuple(baseline[-1]):
            t = 0 if step == 0 else min(1.0, distance / step)
            return x1 + t * (x2 - x1), y1 + t * (y2 - y1)
        distance -= step
    return tuple(baseline[-1])  # pragma: no cover - the loop returns at the last segment


def scan_jpeg(page: FixturePage, layout: dict) -> bytes:
    from PIL import Image, ImageDraw

    width, height = page.size
    image = Image.new("RGB", page.size, (244, 236, 214))
    draw = ImageDraw.Draw(image)
    draw.rectangle([24, 24, width - 25, height - 25], outline=(170, 150, 120), width=3)
    if page.page_type in ("FrontCover", "BackCover"):
        draw.rectangle([60, 60, width - 61, height - 61], fill=(120, 72, 48))
        draw.text((width / 2, height / 2), page.label or "", fill=(240, 220, 170), font=_font(), anchor="mm")
    for region in layout["regions"]:
        for line in region["lines"]:
            # Each token where the layout's character-proportional estimate puts it.
            text, scale = line["text"], baseline_length(line["baseline"]) / max(1, len(line["text"]))
            for token in re.finditer(r"\S+", text):
                x, y = _point_along(line["baseline"], token.start() * scale)
                draw.text((x, y), token.group(), fill=(40, 32, 24), font=_font(), anchor="ls")
    if page.label and page.page_type == "NormalPage":
        draw.text((width / 2, height - 60), page.label, fill=(90, 80, 70), font=_font(), anchor="ms")
    out = io.BytesIO()
    image.save(out, "JPEG", quality=70)
    return out.getvalue()


def thumbnail_jpeg(scan: bytes) -> bytes:
    from PIL import Image

    image = Image.open(io.BytesIO(scan))
    image.thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_WIDTH * 4))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=70)
    return out.getvalue()


def write_page_fixtures(root: Path, corpus) -> PageAssetStore:
    """Write the fixture documents' page assets and manifests under ``root`` (replacing
    earlier copies) and return the store."""
    store = PageAssetStore(root)
    for document_id, pages in fixture_documents(corpus).items():
        manifest_pages = []
        for order, page in enumerate(pages):
            layout = layout_json(page)
            if page.image:
                scan = scan_jpeg(page, layout)
                store.write_asset(document_id, page.id, "image", scan)
                store.write_asset(document_id, page.id, "thumbnail", thumbnail_jpeg(scan))
            if page.layout:
                store.write_asset(document_id, page.id, "layout", json.dumps(layout, ensure_ascii=False).encode())
            width, height = page.size if page.image else (None, None)
            manifest_pages.append(ManifestPage(pageId=page.id, order=order, label=page.label,
                                               pageType=page.page_type, width=width, height=height,
                                               image=page.image, layout=page.layout, thumbnail=page.image))
        store.write_manifest(PageManifest(documentId=document_id, library="fixture", params=PARAMS,
                                          pages=manifest_pages))
    return store
