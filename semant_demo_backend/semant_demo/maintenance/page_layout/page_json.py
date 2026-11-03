"""The versioned per-page layout file (``docs/PAGE_LAYOUT.md``)."""
from collections.abc import Collection
from typing import Any
from uuid import UUID

from semant_demo.maintenance.page_layout.geometry import integer_points, line_heights, word_starts
from semant_demo.maintenance.page_layout.parse import Page
from semant_demo.maintenance.page_layout.serialize import Params

SCHEMA = "semant.page-layout"
VERSION = 1


def page_json(page_id: UUID, page: Page | None, contributing: Collection[tuple[int, int]],
              params: Params) -> dict[str, Any]:
    """The page file: only lines that contribute to canonical text (``(region_index,
    line_index)`` in ``contributing``), in serialization order; regions without such lines
    are left out. A page without XML (``page`` None) has ``image`` None."""
    regions = []
    if page is not None:
        for region_index, region in enumerate(page.regions):
            lines = []
            for line_index, line in enumerate(region.lines):
                if (region_index, line_index) not in contributing:
                    continue
                entry: dict[str, Any] = {"id": line.id, "text": line.text,
                                         "baseline": integer_points(line.baseline),
                                         "heights": line_heights(line)}
                if (starts := word_starts(line.text or "", line.baseline)) is not None:
                    entry["wordStarts"] = starts
                lines.append(entry)
            if lines:
                regions.append({"id": region.id, "lines": lines})
    image = ({"width": page.width, "height": page.height}
             if page is not None and page.width is not None and page.height is not None else None)
    return {"schema": SCHEMA, "version": VERSION, "pageId": str(page_id), "params": params.as_json(),
            "image": image, "regions": regions}
