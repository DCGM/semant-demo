"""Export the ordered page lists of documents from the Kramerius metadata mirror (#571).

Read-only. For each document it writes one JSON line: the pages of one library in mirror
``order``, with the printed label (``number``), the page type and the stored image and PAGE
XML paths. The PAGE XML converter (#540), the page manifest (#541) and the corpus import
(#542) use it, because PAGE XML zips carry no page order.

The same document id often exists in several libraries, and each library has its own page
UUIDs. The library is chosen, in this order:

1. the one whose page rows have real paths (``image_path`` or ``page_xml_path`` neither empty
   nor the mirror's ``not_found`` marker); among several, the one with more real PAGE XML
   paths, then more pages with a real path (``libraryFrom: paths``);
2. otherwise the one whose page ids contain every supplied PAGE XML file name
   (``page_xml``), or the only library with pages (``only_library``, with a warning).

Supplied PAGE XML file names (``--page-xml-dir``) and, with ``--check-start-pages``, the
chunks' ``start_page_id`` values must belong to the chosen library's pages; otherwise the
document is ``page_xml_conflict`` or ``start_page_conflict`` and no pages are exported. A
document whose library cannot be decided is ``ambiguous``; one without page rows is
``no_pages``. Null or duplicate orders, pages without an image or PAGE XML and unrecognized
file names are reported in ``warnings``, never fixed.

Usage (from ``semant_demo_backend/``)::

    KRAMERIUS_METADATA_DSN=postgresql+psycopg://librarymetadata_all@127.0.0.1:5888/librarymetadata_all \\
    python -m semant_demo.maintenance.page_order --document-ids ids.txt --output pages.jsonl \\
        [--page-xml-dir DIR] [--check-start-pages]

``ids.txt`` has one document UUID per line (``#`` comments allowed); ids may also be given
as arguments. ``--page-xml-dir`` holds ``<document>.page_xml.zip`` files or ``<document>/``
folders of ``<page>.xml`` files; only the file names are read. ``--check-start-pages`` reads
the start pages of up to 1000 chunks per document from the configured Weaviate
(``WEAVIATE_HOST`` / ``WEAVIATE_REST_PORT`` / ``WEAVIATE_GRPC_PORT``), read-only.

The mirror is read in a read-only transaction. Paths are reported as stored, not checked on
disk. Counts per status go to stderr. The exit code is 0 when every document was exported,
1 when any was not, 2 for invalid arguments.
"""
import argparse
import asyncio
import json
import os
import sys
import zipfile
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any
from uuid import UUID

from semant_demo.adapters.sql.kramerius_metadata import PageRow, read_document_pages

DSN_VARIABLE = "KRAMERIUS_METADATA_DSN"
NOT_FOUND = "not_found"
MAX_START_PAGES = 1000
"""Chunks per document whose ``start_page_id`` is checked."""
SAMPLE = 5
EXPORTED = "exported"
STATUSES = (EXPORTED, "ambiguous", "page_xml_conflict", "start_page_conflict", "no_pages")


def real_path(value: str | None) -> str | None:
    """The stored path, or None when it is empty or the mirror's ``not_found`` marker."""
    return value if value and value.strip() and value.strip() != NOT_FOUND else None


def _has_path(row: PageRow) -> bool:
    return bool(real_path(row.image_path) or real_path(row.page_xml_path))


def choose_library(rows: Sequence[PageRow], xml_pages: set[UUID] | None) -> tuple[str | None, str | None]:
    """The library to export and how it was chosen (``paths``, ``page_xml``, ``only_library``),
    or ``(None, None)`` when it cannot be decided. Supplied file names are checked separately."""
    by_library: dict[str, list[PageRow]] = {}
    for row in rows:
        by_library.setdefault(row.library, []).append(row)

    def rank(library: str) -> tuple[int, int]:
        pages = by_library[library]
        return sum(1 for r in pages if real_path(r.page_xml_path)), sum(1 for r in pages if _has_path(r))

    with_paths = [library for library in by_library if rank(library)[1]]
    if with_paths:
        best = max(rank(library) for library in with_paths)
        top = [library for library in with_paths if rank(library) == best]
        if len(top) == 1:
            return top[0], "paths"
        pool = top
    else:
        pool = list(by_library)
    if xml_pages:
        matching = [library for library in pool if xml_pages <= {r.page_id for r in by_library[library]}]
        if len(matching) == 1:
            return matching[0], "page_xml"
    if len(by_library) == 1:
        return next(iter(by_library)), "only_library"
    return None, None


def _warning(code: str, items: Iterable[Any]) -> dict[str, Any]:
    items = sorted({str(item) for item in items})
    return {"code": code, "count": len(items), "sample": items[:SAMPLE]}


def export_document(document_id: UUID, rows: Sequence[PageRow], *, xml_pages: set[UUID] | None = None,
                    xml_unrecognized: Sequence[str] = (), start_pages: Sequence[Any] | None = None,
                    start_pages_truncated: bool = False) -> dict[str, Any]:
    """The export entry of one document from its page rows (all libraries).

    ``xml_pages`` are the page ids named by the supplied PAGE XML files (None when none were
    supplied); ``start_pages`` the stored ``start_page_id`` values of its chunks (None when not
    checked). Pages are exported only with status ``exported``."""
    libraries = sorted({row.library for row in rows})
    entry: dict[str, Any] = {"documentId": str(document_id), "status": EXPORTED, "library": None,
                             "libraryFrom": None, "libraries": libraries, "pages": [], "warnings": []}
    warnings = entry["warnings"]
    if xml_unrecognized:
        warnings.append(_warning("unrecognized_page_xml_names", xml_unrecognized))
    if start_pages_truncated:
        warnings.append({"code": "start_pages_truncated", "count": MAX_START_PAGES, "sample": []})
    if not rows:
        entry["status"] = "no_pages"
        return entry

    library, library_from = choose_library(rows, xml_pages)
    if library is None:
        entry["status"] = "ambiguous"
        return entry
    entry["library"], entry["libraryFrom"] = library, library_from
    pages = [row for row in rows if row.library == library]
    page_ids = {row.page_id for row in pages}
    if library_from == "only_library" and not any(_has_path(row) for row in pages):
        warnings.append(_warning("no_real_paths", [library]))

    if xml_pages is not None and (foreign := xml_pages - page_ids):
        entry["status"] = "page_xml_conflict"
        warnings.append(_warning("page_xml_not_in_library", foreign))
        return entry
    if start_pages is not None:
        parsed, invalid = set(), []
        for value in start_pages:
            try:
                parsed.add(value if isinstance(value, UUID) else UUID(str(value)))
            except (TypeError, ValueError):
                invalid.append(value)
        if invalid:
            warnings.append(_warning("invalid_start_page_ids", invalid))
        if foreign := parsed - page_ids:
            entry["status"] = "start_page_conflict"
            warnings.append(_warning("start_pages_not_in_library", foreign))
            return entry

    orders = Counter(row.order for row in pages if row.order is not None)
    if nulls := [row.page_id for row in pages if row.order is None]:
        warnings.append(_warning("null_order", nulls))
    if duplicates := [row.page_id for row in pages if row.order is not None and orders[row.order] > 1]:
        warnings.append(_warning("duplicate_order", duplicates))
    pages.sort(key=lambda row: (row.order is None, row.order or 0, str(row.page_id)))

    for row in pages:
        image, xml = real_path(row.image_path), real_path(row.page_xml_path)
        entry["pages"].append({
            "pageId": str(row.page_id), "order": row.order, "label": row.label, "pageType": row.page_type,
            "imagePath": image, "pageXmlPath": xml, "hasImage": image is not None,
            "hasPageXml": row.page_id in xml_pages if xml_pages is not None else xml is not None})
    if missing := [p["pageId"] for p in entry["pages"] if not p["hasImage"]]:
        warnings.append(_warning("missing_image", missing))
    if missing := [p["pageId"] for p in entry["pages"] if not p["hasPageXml"]]:
        warnings.append(_warning("missing_page_xml", missing))
    return entry


def page_xml_names(directory: Path, document_id: UUID) -> tuple[set[UUID], list[str]] | None:
    """The page ids named by a document's PAGE XML files (``<document>.page_xml.zip`` or a
    ``<document>/`` folder of ``<page>.xml``) and the names that are not ``<uuid>.xml``; None
    when the directory has neither. Only names are read, never file contents."""
    archive, folder = directory / f"{document_id}.page_xml.zip", directory / str(document_id)
    if archive.is_file():
        with zipfile.ZipFile(archive) as zf:
            names = [Path(info.filename).name for info in zf.infolist() if not info.is_dir()]
    elif folder.is_dir():
        names = [path.name for path in folder.iterdir() if path.is_file()]
    else:
        return None
    pages, unrecognized = set(), []
    for name in names:
        stem, dot, suffix = name.rpartition(".")
        try:
            if not dot or suffix.lower() != "xml":
                raise ValueError(name)
            pages.add(UUID(stem))
        except ValueError:
            unrecognized.append(name)
    return pages, unrecognized


def read_document_ids(path: Path) -> list[UUID]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [UUID(line.strip()) for line in lines if line.strip() and not line.lstrip().startswith("#")]


def export(source, document_ids: Sequence[UUID], *, page_xml_dir: Path | None = None,
           start_pages: dict[UUID, tuple[list[Any], bool]] | None = None) -> list[dict[str, Any]]:
    """The export entries of the documents, in the given order (duplicates removed)."""
    document_ids = list(dict.fromkeys(document_ids))
    rows = read_document_pages(source, document_ids)
    entries = []
    for document_id in document_ids:
        xml = page_xml_names(page_xml_dir, document_id) if page_xml_dir else None
        starts, truncated = start_pages.get(document_id, ([], False)) if start_pages is not None else (None, False)
        entry = export_document(document_id, rows.get(document_id, []),
                                xml_pages=xml[0] if xml else None, xml_unrecognized=xml[1] if xml else (),
                                start_pages=starts, start_pages_truncated=truncated)
        if page_xml_dir and xml is None:
            entry["warnings"].append({"code": "no_page_xml_files", "count": 0, "sample": []})
        entries.append(entry)
    return entries


def summary(entries: Sequence[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(entry["status"] for entry in entries)
    return {"documents": len(entries), "statuses": {s: statuses[s] for s in STATUSES if statuses[s]},
            "libraryFrom": dict(Counter(e["libraryFrom"] for e in entries if e["libraryFrom"])),
            "pages": sum(len(entry["pages"]) for entry in entries),
            "warnings": dict(Counter(w["code"] for entry in entries for w in entry["warnings"]))}


def connect_read_only(engine):
    """A mirror connection whose transactions are read-only on PostgreSQL."""
    return engine.connect().execution_options(postgresql_readonly=True)


async def read_start_pages_of(document_ids: Sequence[UUID]) -> dict[UUID, tuple[list[Any], bool]]:
    from semant_demo.adapters.weaviate.client import connect_weaviate
    from semant_demo.adapters.weaviate.document_metadata import read_start_pages
    from semant_demo.config import Config

    config = Config()
    print(f"Weaviate endpoint (read-only): {config.WEAVIATE_HOST}:{config.WEAVIATE_REST_PORT}", file=sys.stderr)
    client = await connect_weaviate(config)
    try:
        return {document_id: await read_start_pages(client, config.collectionNames, document_id, MAX_START_PAGES)
                for document_id in dict.fromkeys(document_ids)}
    finally:
        await client.close()


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("documents", nargs="*", type=UUID, metavar="DOCUMENT_ID", help="document UUIDs")
    p.add_argument("--document-ids", type=Path, help="file with one document UUID per line")
    p.add_argument("--output", type=Path, help="write the JSON lines here (default: stdout)")
    p.add_argument("--page-xml-dir", type=Path,
                   help="directory of <document>.page_xml.zip files or <document>/ folders; confirms the library")
    p.add_argument("--check-start-pages", action="store_true",
                   help="also check the chunks' start_page_id values (reads the configured Weaviate)")
    return p


async def _main(argv: list[str]) -> int:
    from sqlalchemy import create_engine

    args = _parser().parse_args(argv)
    try:
        document_ids = [*args.documents, *(read_document_ids(args.document_ids) if args.document_ids else [])]
    except (OSError, ValueError) as e:
        print(f"Cannot read document ids: {e}", file=sys.stderr)
        return 2
    if not document_ids:
        print("Give document ids as arguments or with --document-ids", file=sys.stderr)
        return 2
    if args.page_xml_dir and not args.page_xml_dir.is_dir():
        print(f"Not a directory: {args.page_xml_dir}", file=sys.stderr)
        return 2
    dsn = os.environ.get(DSN_VARIABLE)
    if not dsn:
        print(f"Set {DSN_VARIABLE} to the metadata mirror's SQLAlchemy URL", file=sys.stderr)
        return 2

    start_pages = await read_start_pages_of(document_ids) if args.check_start_pages else None
    engine = create_engine(dsn)
    try:
        with connect_read_only(engine) as source:
            entries = export(source, document_ids, page_xml_dir=args.page_xml_dir, start_pages=start_pages)
    finally:
        engine.dispose()

    lines = "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries)
    if args.output:
        args.output.write_text(lines, encoding="utf-8")
    else:
        sys.stdout.write(lines)
    result = summary(entries)
    print(json.dumps(result, indent=2), file=sys.stderr)
    return 0 if result["statuses"].get(EXPORTED, 0) == len(entries) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
