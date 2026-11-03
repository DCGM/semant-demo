"""The ``assets`` step: one document's page files, scans, thumbnails, manifest and anchor plan.

Writes only files of the page asset store (#541). The chunks are read by the caller
(read-only) and passed in; nothing here touches a database. Each page is finished on its
own and an interrupted run is simply repeated: a layout file is rewritten only when its
content differs, a scan is copied only when the stored copy is missing or has another size
than the source (copies are atomic, so a stored file is always complete), and a thumbnail is
made only when missing or older than its scan. The manifest and the anchor plan are written
last and describe what exists then.

A page without a ``pageXmlPath`` in the export has no OCR and gets an empty layout. A named
archive that cannot be read (missing, e.g. an unmounted share, or damaged) is different: the
layouts and anchors made without it would be wrong, so the document is ``page_xml_unavailable``
and nothing of it is written; its earlier layouts, manifest and anchor plan stay as they were,
so a later ``anchors --write`` does not clear verified anchors.
"""
import hashlib
import io
import json
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from semant_demo.adapters.filesystem.page_assets import (
    InvalidManifest, ManifestPage, PageAssetStore, PageManifest, write_atomically)
from semant_demo.adapters.weaviate.layout_anchors import AnchoredChunk
from semant_demo.maintenance.page_layout.convert import StoredChunk, convert_document, read_page_xml_zip
from semant_demo.maintenance.page_layout.serialize import Params

PLAN_NAME = "anchors.jsonl"
"""The anchor plan of a document, next to its manifest (never served)."""
THUMBNAIL_WIDTH = 256
THUMBNAIL_QUALITY = 80
SAMPLE = 5


def text_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def plan_path(store: PageAssetStore, document_id: UUID) -> Path:
    return store.document_dir(document_id) / PLAN_NAME


@dataclass
class Issues:
    """Counted problems with a few sample items each."""
    items: dict[str, list[str]] = field(default_factory=dict)

    def add(self, code: str, item: Any = "") -> None:
        self.items.setdefault(code, []).append(str(item))

    def as_json(self) -> list[dict[str, Any]]:
        return [{"code": code, "count": len(items), "sample": sorted({i for i in items if i})[:SAMPLE]}
                for code, items in sorted(self.items.items())]


class CorruptImage(Exception):
    """A source scan that is not a readable JPEG."""


def _jpeg_size(data: bytes) -> tuple[int, int]:
    """The size of a JPEG; raises ``CorruptImage`` for anything else or a damaged file."""
    from PIL import Image  # maintenance dependency (requirements-dev.txt)
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "JPEG":
                raise CorruptImage(image.format or "unknown format")
            size = image.size
            image.load()  # decodes the whole image: a truncated file fails here
    except CorruptImage:
        raise
    except Exception as e:  # Pillow raises many types for damaged data
        raise CorruptImage(type(e).__name__) from e
    return size


def _stored_size(path: Path) -> tuple[int, int] | None:
    from PIL import Image
    try:
        with Image.open(path) as image:
            return image.size
    except Exception:
        return None


def make_thumbnail(data: bytes, width: int = THUMBNAIL_WIDTH) -> bytes:
    """A JPEG at most ``width`` pixels wide (never enlarged), aspect ratio kept."""
    from PIL import Image
    with Image.open(io.BytesIO(data)) as image:
        image.draft("RGB", (width, max(1, image.height * width // max(1, image.width))))
        image = image.convert("RGB")
        image.thumbnail((width, 1_000_000))
        out = io.BytesIO()
        image.save(out, "JPEG", quality=THUMBNAIL_QUALITY, optimize=True)
    return out.getvalue()


def _layout_bytes(page: dict) -> bytes:
    return json.dumps(page, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _real(path: str | None) -> Path | None:
    return Path(path) if path else None


PAGE_XML_UNAVAILABLE = "page_xml_unavailable"


def _load_page_xml(entry: dict, issues: Issues) -> dict[UUID, bytes] | None:
    """The PAGE XML of the pages by page id; None when a named archive could not be read."""
    xml: dict[UUID, bytes] = {}
    complete = True
    for archive in sorted({p["pageXmlPath"] for p in entry["pages"] if p.get("pageXmlPath")}):
        try:
            pages, unrecognized = read_page_xml_zip(Path(archive))
        except FileNotFoundError:
            issues.add("missing_page_xml_zip", archive)
            complete = False
            continue
        except (OSError, zipfile.BadZipFile):
            issues.add("unreadable_page_xml_zip", archive)
            complete = False
            continue
        for name in unrecognized:
            issues.add("unrecognized_page_xml_file", name)
        xml.update(pages)
    return xml if complete else None


def _stored_chunks(chunks: list[AnchoredChunk], issues: Issues) -> list[StoredChunk] | None:
    """The chunks to anchor, by ``order``; None when the orders are unusable (a chunk without
    one, or a duplicate): such a document gets no anchors."""
    if any(c.order is None for c in chunks):
        issues.add("chunk_without_order", next(c.id for c in chunks if c.order is None))
        return None
    counts = Counter(c.order for c in chunks)
    if duplicated := [o for o, n in counts.items() if n > 1]:
        for order in duplicated[:SAMPLE]:
            issues.add("duplicate_chunk_order", order)
        return None
    return [StoredChunk(str(c.id), c.order, c.text) for c in sorted(chunks, key=lambda c: c.order)]


def _import_image(store: PageAssetStore, document_id: UUID, page: dict, counts: Counter,
                  issues: Issues) -> tuple[int, int] | None:
    """Copy the page's scan when needed; its size, or None when there is no stored scan."""
    page_id = UUID(page["pageId"])
    source = _real(page.get("imagePath"))
    stored = store.asset_path(document_id, page_id, "image")
    if source is None:
        counts["image_none"] += 1
        return _stored_size(stored) if stored.is_file() else None
    try:
        source_size = source.stat().st_size
    except OSError:
        counts["image_missing"] += 1
        issues.add("missing_image", page_id)
        return _stored_size(stored) if stored.is_file() else None
    if stored.is_file() and stored.stat().st_size == source_size and (size := _stored_size(stored)):
        counts["image_kept"] += 1
        return size
    try:
        data = source.read_bytes()
        size = _jpeg_size(data)
    except OSError:
        counts["image_unreadable"] += 1
        issues.add("unreadable_image", page_id)
        return None
    except CorruptImage:
        counts["image_corrupt"] += 1
        issues.add("corrupt_image", page_id)
        return None
    store.write_asset(document_id, page_id, "image", data)
    counts["image_copied"] += 1
    return size


def _import_thumbnail(store: PageAssetStore, document_id: UUID, page_id: UUID, counts: Counter,
                      issues: Issues) -> None:
    image = store.asset_path(document_id, page_id, "image")
    thumbnail = store.asset_path(document_id, page_id, "thumbnail")
    if not image.is_file():
        return
    if thumbnail.is_file() and thumbnail.stat().st_mtime_ns >= image.stat().st_mtime_ns:
        counts["thumbnail_kept"] += 1
        return
    try:
        store.write_asset(document_id, page_id, "thumbnail", make_thumbnail(image.read_bytes()))
        counts["thumbnail_made"] += 1
    except Exception as e:  # a damaged stored scan: reported, the page keeps its other assets
        issues.add("thumbnail_failed", f"{page_id}:{type(e).__name__}")


def _page_metadata(chunks: list[AnchoredChunk], anchors: list[dict], page_index: dict[str, int],
                   issues: Issues) -> Counter:
    """Compare the stored page fields with the verified anchors (report only, never repaired)."""
    by_id = {str(c.id): c for c in chunks}
    counts: Counter = Counter()
    for anchor in anchors:
        start, chunk = anchor["layoutStart"], by_id.get(anchor["chunkId"] or "")
        if start is None or chunk is None:
            continue
        counts["checked"] += 1
        page = page_index.get(start["pageId"])
        if chunk.start_page_id != start["pageId"]:
            counts["start_page_id_differs"] += 1
            issues.add("start_page_id_differs", chunk.id)
        if chunk.from_page != page:
            counts["from_page_differs"] += 1
        if page is None or chunk.from_page is None or chunk.to_page is None \
                or not chunk.from_page <= page <= chunk.to_page:
            counts["outside_page_range"] += 1
            issues.add("anchor_outside_page_range", chunk.id)
    return counts


def import_document(store: PageAssetStore, entry: dict, chunks: list[AnchoredChunk], params: Params,
                    max_edit_ratio: float) -> dict[str, Any]:
    """Import one exported document (a ``page_order`` line) and return its report."""
    document_id = UUID(entry["documentId"])
    issues = Issues()
    counts: Counter = Counter()
    pages = entry["pages"]
    page_ids = [UUID(p["pageId"]) for p in pages]

    xml = _load_page_xml(entry, issues)
    if xml is None:
        return {"documentId": str(document_id), "status": PAGE_XML_UNAVAILABLE, "pages": len(pages),
                "chunks": len(chunks), "assets": {}, "anchors": {}, "pageMetadata": {},
                "warnings": issues.as_json(), "conversionWarnings": []}
    stored = _stored_chunks(chunks, issues)
    result = convert_document(document_id, page_ids, xml, params, stored if stored is not None else [],
                              max_edit_ratio)

    manifest_pages = []
    for index, page in enumerate(pages):
        page_id = page_ids[index]
        layout = result.pages[page_id]
        data = _layout_bytes(layout)
        path = store.asset_path(document_id, page_id, "layout")
        if path.is_file() and path.read_bytes() == data:
            counts["layout_unchanged"] += 1
        else:
            store.write_asset(document_id, page_id, "layout", data)
            counts["layout_written"] += 1
        size = _import_image(store, document_id, page, counts, issues)
        _import_thumbnail(store, document_id, page_id, counts, issues)
        image_size = layout.get("image") or {}
        width, height = size or (image_size.get("width"), image_size.get("height"))
        manifest_pages.append(ManifestPage(
            pageId=page_id, order=index, label=page.get("label"), pageType=page.get("pageType"),
            width=width, height=height,
            image=store.asset_file(document_id, page_id, "image") is not None,
            layout=store.asset_file(document_id, page_id, "layout") is not None,
            thumbnail=store.asset_file(document_id, page_id, "thumbnail") is not None))

    plan = [{**anchor, "textSha256": text_sha(text)}
            for anchor, text in zip(result.anchors, (c.text for c in stored or []))]
    plan_data = "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in plan).encode("utf-8")
    plan_file = plan_path(store, document_id)
    if not plan_file.is_file() or plan_file.read_bytes() != plan_data:
        write_atomically(plan_file, plan_data)
    manifest = PageManifest(documentId=document_id, library=entry.get("library"), params=params.as_json(),
                            pages=manifest_pages)
    try:
        current = store.read_manifest(document_id)
    except InvalidManifest:
        current = None
    if current != manifest:
        store.write_manifest(manifest)

    page_index = {str(p): i for i, p in enumerate(page_ids)}
    matches = Counter(a["layoutStart"]["match"] if a["layoutStart"] else "none" for a in plan)
    reasons = Counter(a["reason"] for a in plan if a["layoutStart"] is None)
    return {
        "documentId": str(document_id),
        "status": "imported" if result.failure is None and stored is not None else (
            "no_anchors" if result.failure is None else result.failure),
        "pages": len(pages),
        "chunks": len(chunks),
        "assets": {key: counts[key] for key in sorted(counts)},
        "anchors": {"exact": matches["exact"], "approximate": matches["approximate"], "none": matches["none"],
                    "reasons": dict(sorted(reasons.items()))},
        "pageMetadata": dict(sorted(_page_metadata(chunks, plan, page_index, issues).items())),
        "warnings": issues.as_json(),
        "conversionWarnings": result.warnings,
    }
