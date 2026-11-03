"""One document end to end: page files, regenerated chunks and chunk anchors."""
import json
import zipfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from semant_demo.features.documents.positions import text_length
from semant_demo.maintenance.page_layout.anchors import (
    MAX_EDIT_RATIO, Anchor, ChunkMatch, build_stream, match_chunks, replay)
from semant_demo.maintenance.page_layout.page_json import page_json
from semant_demo.maintenance.page_layout.parse import Page, PageXmlError, parse_page_xml
from semant_demo.maintenance.page_layout.serialize import Params, serialize

SAMPLE = 5
CONVERTED = "converted"
LEGACY_FAILURE = "legacy_failure"


@dataclass(frozen=True)
class StoredChunk:
    """A chunk to anchor: a stored one (``id`` set) or one regenerated here."""
    id: str | None
    order: int
    text: str


@dataclass
class DocumentResult:
    document_id: UUID
    status: str
    failure: str | None
    pages: dict[UUID, dict[str, Any]]
    """Page files by page id, in page order."""
    chunks: list[dict[str, Any]]
    """Regenerated chunks: ``order``, ``text``, ``legacyStartPageId``."""
    anchors: list[dict[str, Any]]
    warnings: list[dict[str, Any]] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        found = Counter(a["layoutStart"]["match"] if a["layoutStart"] else "none" for a in self.anchors)
        return {key: found[key] for key in ("exact", "approximate", "none")}


class _Warnings:
    def __init__(self):
        self.items: dict[str, list[str]] = {}

    def add(self, code: str, item: Any = "") -> None:
        self.items.setdefault(code, []).append(str(item))

    def as_json(self) -> list[dict[str, Any]]:
        return [{"code": code, "count": len(items), "sample": sorted(set(i for i in items if i))[:SAMPLE]}
                for code, items in self.items.items()]


def convert_document(document_id: UUID, page_ids: Sequence[UUID], xml: Mapping[UUID, bytes],
                     params: Params = Params(), stored: Sequence[StoredChunk] | None = None,
                     max_edit_ratio: float = MAX_EDIT_RATIO) -> DocumentResult:
    """Parse the pages in ``page_ids`` order (``xml`` by page id; a missing page is skipped as
    the legacy code did), regenerate the chunks and anchor ``stored`` (default: the
    regenerated chunks). Every page in ``page_ids`` gets a page file."""
    warnings = _Warnings()
    parsed: dict[UUID, Page] = {}
    failure = None
    for page_id in page_ids:
        if page_id not in xml:
            warnings.add("missing_page_xml", page_id)
            continue
        try:
            page = parse_page_xml(xml[page_id], page_id)
        except PageXmlError:
            warnings.add("unparseable_page_xml", page_id)
            failure = failure or "unparseable_page_xml"
            continue
        parsed[page_id] = page
        for code, detail in page.warnings:
            warnings.add(code, f"{page_id}:{detail}" if detail else page_id)
    for page_id in sorted(set(xml) - set(page_ids), key=str):
        warnings.add("page_xml_not_in_page_list", page_id)

    serialization = serialize([parsed[p] for p in page_ids if p in parsed], params)
    failure = failure or serialization.failure
    if failure:
        serialization.chunks = []
    contributing: dict[UUID, set[tuple[int, int]]] = {}
    for chunk in serialization.chunks:
        for c in chunk.contributions:
            contributing.setdefault(c.page_id, set()).add((c.region_index, c.line_index))
    pages = {page_id: page_json(page_id, parsed.get(page_id), contributing.get(page_id, set()), params)
             for page_id in page_ids}
    chunks = [{"order": i, "text": c.text, "legacyStartPageId": str(c.legacy_start_page_id)}
              for i, c in enumerate(serialization.chunks)]

    targets = list(stored) if stored is not None else [StoredChunk(None, i, c["text"]) for i, c in enumerate(chunks)]
    matches, document_warnings = match_chunks(build_stream(serialization), [(t.order, t.text) for t in targets],
                                              max_edit_ratio)
    for code in document_warnings:
        warnings.add(code)
    duplicates = {(page_id, detail) for page_id, page in parsed.items()
                  for code, detail in page.warnings if code == "duplicate_line_id"}
    order = [str(p) for p in page_ids]
    files = {str(page_id): data for page_id, data in pages.items()}
    anchors = []
    for target, match in zip(targets, matches):
        match = _checked(match, target, duplicates, files, order)
        if match.anchor is None and match.reason != "empty_chunk":
            warnings.add(f"unanchored_{match.reason}", target.id or target.order)
        elif match.anchor is not None and match.anchor.match == "approximate":
            warnings.add("approximate_anchor", target.id or target.order)
        anchors.append({"documentId": str(document_id), "chunkId": target.id, "order": target.order,
                        "layoutStart": match.anchor.as_json() if match.anchor else None,
                        "reason": match.reason, "differences": match.differences,
                        "params": params.as_json(), "maxEditRatio": max_edit_ratio})
    if failure:
        warnings.add(failure)
    return DocumentResult(document_id, LEGACY_FAILURE if failure else CONVERTED, failure, pages, chunks, anchors,
                          warnings.as_json())


def _checked(match: ChunkMatch, target: StoredChunk, duplicates: set[tuple[UUID, str]],
             files: Mapping[str, dict], order: list[str]) -> ChunkMatch:
    """No anchor on a line without an id or with a duplicated one (the viewer could not find
    the line); an exact anchor whose replay differs from the chunk text becomes approximate."""
    anchor = match.anchor
    if anchor is None:
        return match
    if not anchor.line_id:
        return ChunkMatch(None, "missing_line_id", match.differences, match.position, match.end)
    if (anchor.page_id, anchor.line_id or "") in duplicates:
        return ChunkMatch(None, "duplicate_line_id", match.differences, match.position, match.end)
    if anchor.match == "exact":
        if replay(files, order, anchor.as_json(), text_length(target.text)) != target.text:
            approximate = Anchor(anchor.page_id, anchor.line_id, anchor.offset, "approximate")
            return ChunkMatch(approximate, "replay_mismatch", match.differences, match.position, match.end)
    return match


# --- inputs -----------------------------------------------------------------------------

def read_page_xml(directory: Path, document_id: UUID) -> tuple[dict[UUID, bytes], list[str]] | None:
    """The PAGE XML files of a document by page id (``<document>.page_xml.zip`` or a
    ``<document>/`` folder of ``<page>.xml``) and the names that are not ``<uuid>.xml``;
    None when the directory has neither. Archives are read in memory, never extracted."""
    archive, folder = directory / f"{document_id}.page_xml.zip", directory / str(document_id)
    files: list[tuple[str, bytes]] = []
    if archive.is_file():
        with zipfile.ZipFile(archive) as zf:
            files = [(Path(i.filename).name, zf.read(i)) for i in zf.infolist() if not i.is_dir()]
    elif folder.is_dir():
        files = [(p.name, p.read_bytes()) for p in sorted(folder.iterdir()) if p.is_file()]
    else:
        return None
    pages, unrecognized = {}, []
    for name, data in files:
        stem, dot, suffix = name.rpartition(".")
        try:
            if not dot or suffix.lower() != "xml":
                raise ValueError(name)
            pages[UUID(stem)] = data
        except ValueError:
            unrecognized.append(name)
    return pages, unrecognized


def documents_in(directory: Path) -> list[UUID]:
    """Document ids with PAGE XML in the directory, sorted."""
    found = set()
    for path in directory.iterdir():
        name = path.name.removesuffix(".page_xml.zip") if path.is_file() else path.name
        try:
            if path.is_dir() or path.name.endswith(".page_xml.zip"):
                found.add(UUID(name))
        except ValueError:
            pass
    return sorted(found, key=str)


def read_page_order(path: Path) -> dict[UUID, list[UUID]]:
    """Page lists from a ``page_order`` export (#571): exported documents only."""
    orders = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entry = json.loads(line)
            if entry.get("status") == "exported":
                orders[UUID(entry["documentId"])] = [UUID(p["pageId"]) for p in entry["pages"]]
    return orders


def read_chunks(path: Path) -> dict[UUID, list[StoredChunk]]:
    """Chunks to anchor (JSON lines ``id``, ``document`` or ``documentId``, ``order``, ``text``;
    this command's ``chunks.jsonl`` works too) by document,
    sorted by ``order``. Raises ``ValueError`` on a malformed line or a duplicate order."""
    by_document: dict[UUID, list[StoredChunk]] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            order = entry["order"]
            if not isinstance(order, int) or isinstance(order, bool) or not isinstance(entry["text"], str):
                raise ValueError("order must be an integer and text a string")
            chunk = StoredChunk(str(entry["id"]) if entry.get("id") is not None else None, order, entry["text"])
            document = entry["document"] if "document" in entry else entry["documentId"]
            by_document.setdefault(UUID(str(document)), []).append(chunk)
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"{path}:{number}: {e}") from e
    for document_id, chunks in by_document.items():
        chunks.sort(key=lambda c: c.order)
        if len({c.order for c in chunks}) != len(chunks):
            raise ValueError(f"{path}: duplicate order in document {document_id}")
    return by_document
