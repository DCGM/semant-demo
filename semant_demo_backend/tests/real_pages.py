"""Real PERO OCR pages and stored legacy chunks as regression fixtures (#546).

``tests/fixtures/real_pages/`` holds excerpts of six public documents of the digitized
library corpus (``README.md`` there says where they come from and what each one covers):

* ``documents.json``: per document its pages (in page-list order) and the stored chunks whose
  text lies on them (id, ``order``, page fields, text), with the ``layoutStart`` the
  whole-document import gave them (``fullRunLayoutStart``);
* ``page_xml/<document>.page_xml.zip``: the PERO PAGE XML of those pages;
* ``scans/<document>/<page>.jpg``: two downscaled grayscale scans, for the browser test;
* ``generated/``: what the converter (#540) makes of them, the input of the frontend tests:
  ``pages/<document>/<page>.json`` (the page files) and ``anchors.jsonl``.

``generated/`` is the converter's output and must stay so: ``tests/test_real_pages.py``
regenerates it and fails on any difference. After an intended converter change, rewrite it
from ``semant_demo_backend/`` with ``python -m tests.real_pages --write`` and review the diff.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any
from uuid import UUID

from semant_demo.maintenance.page_import.assets import _layout_bytes
from semant_demo.maintenance.page_layout.convert import (
    DocumentResult, StoredChunk, convert_document, read_page_xml_zip)

FIXTURE = Path(__file__).parent / "fixtures" / "real_pages"
GENERATED = FIXTURE / "generated"


@dataclass(frozen=True)
class RealDocument:
    id: UUID
    entry: dict[str, Any]

    @property
    def page_ids(self) -> list[UUID]:
        return [UUID(p["pageId"]) for p in self.entry["pages"]]

    @property
    def chunks(self) -> list[dict[str, Any]]:
        return self.entry["chunks"]

    def xml(self) -> dict[UUID, bytes]:
        pages, unrecognized = read_page_xml_zip(FIXTURE / "page_xml" / f"{self.id}.page_xml.zip")
        assert not unrecognized, unrecognized
        return pages

    def scan(self, page_id: UUID) -> Path | None:
        path = FIXTURE / "scans" / str(self.id) / f"{page_id}.jpg"
        return path if path.is_file() else None


@cache
def documents() -> dict[UUID, RealDocument]:
    entries = json.loads((FIXTURE / "documents.json").read_text(encoding="utf-8"))["documents"]
    return {UUID(e["documentId"]): RealDocument(UUID(e["documentId"]), e) for e in entries}


def convert(document: RealDocument) -> DocumentResult:
    """The converter on the document's pages, anchoring its stored chunks."""
    stored = [StoredChunk(c["id"], c["order"], c["text"]) for c in document.chunks]
    return convert_document(document.id, document.page_ids, document.xml(), stored=stored)


def page_file_bytes(page: dict[str, Any]) -> bytes:
    """A page file as the import (#542) stores it."""
    return _layout_bytes(page)


def generate() -> dict[Path, bytes]:
    """Every file of ``generated/``, by path relative to it."""
    files: dict[Path, bytes] = {}
    anchors = []
    for document in documents().values():
        result = convert(document)
        assert result.status == "converted", (document.id, result.failure)
        for page_id, page in result.pages.items():
            files[Path("pages") / str(document.id) / f"{page_id}.json"] = page_file_bytes(page)
        anchors.extend(result.anchors)
    files[Path("anchors.jsonl")] = "".join(json.dumps(a, ensure_ascii=False) + "\n" for a in anchors).encode("utf-8")
    return files


def write_generated() -> None:
    files = generate()
    for path in sorted(GENERATED.rglob("*"), reverse=True):
        if path.is_file() and path.relative_to(GENERATED) not in files:
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    for relative, data in files.items():
        target = GENERATED / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true", help="rewrite tests/fixtures/real_pages/generated/")
    args = parser.parse_args()
    if not args.write:
        parser.error("nothing to do without --write")
    write_generated()
    print(f"wrote {GENERATED}")


if __name__ == "__main__":
    main()
