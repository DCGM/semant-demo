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
``start_page_id`` values of all the document's chunks must belong to the chosen library's
pages; otherwise the document is ``page_xml_conflict`` or ``start_page_conflict`` and no
pages are exported. When the chunks cannot all be read (a failed query, a chunk without
``order``, a count that changed during the read) the document is ``start_pages_unchecked``,
also without pages. A document whose library cannot be decided is ``ambiguous``; one
without page rows is ``no_pages``. Null or duplicate orders, pages without an image or PAGE XML and unrecognized
file names are reported in ``warnings``, never fixed.

The mirror's ``page_xml_path`` is often null although the archive exists. With
``--source-root`` the pages of an exported document that have no stored PAGE XML path are
looked up in ``<source-root>/<library>/<document>.page_xml.zip`` (the layout of the stored
paths), for the chosen library only. Its file names must all be pages of that library;
otherwise the document is ``page_xml_conflict`` without pages. Pages it contains get that
archive as ``pageXmlPath`` (``page_xml_from_source_root``); a missing or unreadable archive
is reported (``source_page_xml_missing``, ``source_page_xml_unreadable``), never guessed.
Stored paths are kept as they are.

Usage (from ``semant_demo_backend/``)::

    KRAMERIUS_METADATA_DSN=postgresql+psycopg://librarymetadata_all@127.0.0.1:5888/librarymetadata_all \\
    python -m semant_demo.maintenance.page_order --document-ids ids.txt --output pages.jsonl \\
        [--page-xml-dir DIR] [--source-root DIR] [--check-start-pages]

``ids.txt`` has one document UUID per line (``#`` comments allowed); ids may also be given
as arguments. ``--page-xml-dir`` holds ``<document>.page_xml.zip`` files or ``<document>/``
folders of ``<page>.xml`` files; only the file names are read. ``--check-start-pages`` reads
the start pages of every chunk of each document from the configured Weaviate
(``WEAVIATE_HOST`` / ``WEAVIATE_REST_PORT`` / ``WEAVIATE_GRPC_PORT``), read-only, in pages of
1000 chunks.

The mirror is read in a read-only transaction, ``DOCUMENT_BATCH`` documents per query, and
each JSON line is written as soon as its document is done, so memory does not grow with the
number of pages or the output size (only the list of document ids is kept). With
``--output`` the lines go to ``<output>.partial``, renamed to ``<output>`` when the run
completes. Stored paths are reported as stored, not checked on disk. Counts per status go to stderr. The exit code is 0 when every document was exported,
1 when any was not, 2 for invalid arguments.
"""
import argparse
import asyncio
import json
import os
import sys
import zipfile
from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from semant_demo.adapters.sql.kramerius_metadata import PageRow, read_document_pages

DSN_VARIABLE = "KRAMERIUS_METADATA_DSN"
NOT_FOUND = "not_found"
DOCUMENT_BATCH = 100
"""Documents whose page rows are read and exported together."""
SAMPLE = 5
EXPORTED = "exported"
START_PAGES_UNCHECKED = "start_pages_unchecked"
STATUSES = (EXPORTED, "ambiguous", "page_xml_conflict", "start_page_conflict", START_PAGES_UNCHECKED, "no_pages")


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


class _Sample:
    """A count and the ``SAMPLE`` smallest distinct values, in bounded memory."""

    def __init__(self):
        self.count, self.values = 0, set()

    def add(self, value: Any) -> None:
        self.count += 1
        self.values.add(str(value))
        if len(self.values) > SAMPLE:
            self.values.remove(max(self.values))

    def warning(self, code: str) -> dict[str, Any]:
        return {"code": code, "count": self.count, "sample": sorted(self.values)}


@dataclass
class StartPageCheck:
    """The ``start_page_id`` values of a document's chunks checked against its library's pages,
    batch by batch, keeping counts and samples only. ``error`` is set when not every chunk was
    read; the check then proves nothing."""
    page_ids: set[UUID]
    chunks: int = 0
    invalid: _Sample = field(default_factory=_Sample)
    foreign: _Sample = field(default_factory=_Sample)
    error: str | None = None

    def add(self, values: Iterable[Any]) -> None:
        for value in values:
            self.chunks += 1
            try:
                page = value if isinstance(value, UUID) else UUID(str(value))
            except (TypeError, ValueError):
                self.invalid.add(value)
                continue
            if page not in self.page_ids:
                self.foreign.add(page)


StartPageChecker = Callable[[UUID, set[UUID]], Awaitable[StartPageCheck]]
"""Checks all start pages of a document against these page ids."""


def apply_start_page_check(entry: dict[str, Any], check: StartPageCheck) -> dict[str, Any]:
    """The entry after the start-page check: ``start_pages_unchecked`` when the chunks could not
    all be read, ``start_page_conflict`` when one starts on a page of another library; both
    without pages. Counts in these warnings are chunks."""
    if check.invalid.count:
        entry["warnings"].append(check.invalid.warning("invalid_start_page_ids"))
    if check.error is not None:
        entry["status"], entry["pages"] = START_PAGES_UNCHECKED, []
        entry["warnings"].append({"code": "start_pages_incomplete", "count": check.chunks, "sample": [check.error]})
    elif check.foreign.count:
        entry["status"], entry["pages"] = "start_page_conflict", []
        entry["warnings"].append(check.foreign.warning("start_pages_not_in_library"))
    return entry


def export_document(document_id: UUID, rows: Sequence[PageRow], *, xml_pages: set[UUID] | None = None,
                    xml_unrecognized: Sequence[str] = (), start_pages: Iterable[Any] | None = None) -> dict[str, Any]:
    """The export entry of one document from its page rows (all libraries).

    ``xml_pages`` are the page ids named by the supplied PAGE XML files (None when none were
    supplied); ``start_pages`` the stored ``start_page_id`` values of all its chunks (None when
    not checked; ``export`` checks them in batches instead). Pages are exported only with
    status ``exported``."""
    libraries = sorted({row.library for row in rows})
    entry: dict[str, Any] = {"documentId": str(document_id), "status": EXPORTED, "library": None,
                             "libraryFrom": None, "libraries": libraries, "pages": [], "warnings": []}
    warnings = entry["warnings"]
    if xml_unrecognized:
        warnings.append(_warning("unrecognized_page_xml_names", xml_unrecognized))
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
    if start_pages is not None:
        check = StartPageCheck(page_ids)
        check.add(start_pages)
        apply_start_page_check(entry, check)
    return entry


def page_xml_names(directory: Path, document_id: UUID) -> tuple[set[UUID], list[str]] | None:
    """The page ids named by a document's PAGE XML files (``<document>.page_xml.zip`` or a
    ``<document>/`` folder of ``<page>.xml``) and the names that are not ``<uuid>.xml``; None
    when the directory has neither. Only names are read, never file contents."""
    archive, folder = directory / f"{document_id}.page_xml.zip", directory / str(document_id)
    if archive.is_file():
        return archive_page_names(archive)
    if folder.is_dir():
        return _page_names([path.name for path in folder.iterdir() if path.is_file()])
    return None


def archive_page_names(archive: Path) -> tuple[set[UUID], list[str]]:
    """The page ids named in a ``.page_xml.zip`` and its other file names (names only).
    Raises ``OSError`` or ``zipfile.BadZipFile`` for an unreadable archive."""
    with zipfile.ZipFile(archive) as zf:
        return _page_names([Path(info.filename).name for info in zf.infolist() if not info.is_dir()])


def _page_names(names: list[str]) -> tuple[set[UUID], list[str]]:
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


def source_archive(source_root: Path, library: str, document_id: UUID) -> Path:
    """Where the stored paths keep a document's PAGE XML: ``<root>/<library>/<document>.page_xml.zip``."""
    return source_root / library / f"{document_id}.page_xml.zip"


def resolve_source_page_xml(entry: dict[str, Any], source_root: Path, *,
                            page_xml_dir_given: bool = False) -> dict[str, Any]:
    """Fill in ``pageXmlPath`` of an exported entry's pages without a stored one from the
    library's archive under ``source_root``, after checking that every page it names belongs
    to the entry's library (otherwise ``page_xml_conflict``, without pages). Stored paths are
    never replaced; a missing or unreadable archive is only reported. ``hasPageXml`` follows
    the resolved path unless ``--page-xml-dir`` decided it."""
    pages = entry["pages"]
    unresolved = [page for page in pages if page["pageXmlPath"] is None]
    if entry["status"] != EXPORTED or not unresolved:
        return entry
    warnings = entry["warnings"]
    archive = source_archive(source_root, entry["library"], UUID(entry["documentId"]))
    try:
        names, _ = archive_page_names(archive)
    except FileNotFoundError:
        warnings.append({"code": "source_page_xml_missing", "count": len(unresolved), "sample": [str(archive)]})
        return entry
    except (OSError, zipfile.BadZipFile) as e:
        warnings.append({"code": "source_page_xml_unreadable", "count": len(unresolved),
                         "sample": [f"{archive}: {type(e).__name__}"]})
        return entry
    if foreign := names - {UUID(page["pageId"]) for page in pages}:
        entry["status"], entry["pages"] = "page_xml_conflict", []
        warnings.append(_warning("source_page_xml_not_in_library", foreign))
        return entry
    resolved = [page for page in unresolved if UUID(page["pageId"]) in names]
    for page in resolved:
        page["pageXmlPath"] = str(archive)
        if not page_xml_dir_given:
            page["hasPageXml"] = True
    if resolved:
        warnings.append(_warning("page_xml_from_source_root", [page["pageId"] for page in resolved]))
        entry["warnings"] = [w for w in warnings if w["code"] != "missing_page_xml"]
        if missing := [page["pageId"] for page in pages if not page["hasPageXml"]]:
            entry["warnings"].append(_warning("missing_page_xml", missing))
    return entry


def read_document_ids(path: Path) -> list[UUID]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [UUID(line.strip()) for line in lines if line.strip() and not line.lstrip().startswith("#")]


async def export(source, document_ids: Iterable[UUID], *, page_xml_dir: Path | None = None,
                 source_root: Path | None = None, check_start_pages: StartPageChecker | None = None,
                 batch_size: int = DOCUMENT_BATCH) -> AsyncIterator[dict[str, Any]]:
    """The export entries of the documents, in the given order (duplicates removed), one at a
    time: page rows are read ``batch_size`` documents at a time and nothing is kept after an
    entry is yielded. Start pages are checked only for documents that would be exported."""
    pending: list[UUID] = []
    seen: set[UUID] = set()
    for document_id in document_ids:
        if document_id not in seen:
            seen.add(document_id)
            pending.append(document_id)
        if len(pending) == batch_size:
            async for entry in _export_batch(source, pending, page_xml_dir, source_root, check_start_pages):
                yield entry
            pending = []
    if pending:
        async for entry in _export_batch(source, pending, page_xml_dir, source_root, check_start_pages):
            yield entry


async def _export_batch(source, document_ids: list[UUID], page_xml_dir: Path | None, source_root: Path | None,
                        check_start_pages: StartPageChecker | None) -> AsyncIterator[dict[str, Any]]:
    rows = read_document_pages(source, document_ids)
    for document_id in document_ids:
        xml = page_xml_names(page_xml_dir, document_id) if page_xml_dir else None
        entry = export_document(document_id, rows.pop(document_id, []),
                                xml_pages=xml[0] if xml else None, xml_unrecognized=xml[1] if xml else ())
        if page_xml_dir and xml is None:
            entry["warnings"].append({"code": "no_page_xml_files", "count": 0, "sample": []})
        if source_root is not None:
            resolve_source_page_xml(entry, source_root, page_xml_dir_given=page_xml_dir is not None)
        if check_start_pages is not None and entry["status"] == EXPORTED:
            page_ids = {UUID(page["pageId"]) for page in entry["pages"]}
            apply_start_page_check(entry, await check_start_pages(document_id, page_ids))
        yield entry


class Summary:
    """Running counts of the exported entries."""

    def __init__(self):
        self.documents, self.pages = 0, 0
        self.statuses, self.library_from, self.warnings = Counter(), Counter(), Counter()

    def add(self, entry: dict[str, Any]) -> None:
        self.documents += 1
        self.pages += len(entry["pages"])
        self.statuses[entry["status"]] += 1
        if entry["libraryFrom"]:
            self.library_from[entry["libraryFrom"]] += 1
        self.warnings.update(warning["code"] for warning in entry["warnings"])

    def as_json(self) -> dict[str, Any]:
        return {"documents": self.documents,
                "statuses": {s: self.statuses[s] for s in STATUSES if self.statuses[s]},
                "libraryFrom": dict(self.library_from), "pages": self.pages, "warnings": dict(self.warnings)}

    @property
    def all_exported(self) -> bool:
        return self.statuses[EXPORTED] == self.documents


def summary(entries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    result = Summary()
    for entry in entries:
        result.add(entry)
    return result.as_json()


def connect_read_only(engine):
    """A mirror connection whose transactions are read-only on PostgreSQL."""
    return engine.connect().execution_options(postgresql_readonly=True)


def weaviate_start_page_checker(client, names) -> StartPageChecker:
    """A checker reading every chunk's ``start_page_id`` from Weaviate (read-only), in batches.
    A failed or incomplete read gives a check with ``error`` set, never a passing one."""
    from weaviate.exceptions import WeaviateBaseError

    from semant_demo.adapters.weaviate.document_metadata import IncompleteRead, iter_start_pages

    async def check(document_id: UUID, page_ids: set[UUID]) -> StartPageCheck:
        result = StartPageCheck(page_ids)
        try:
            async for values in iter_start_pages(client, names, document_id):
                result.add(values)
        except (IncompleteRead, WeaviateBaseError) as e:
            result.error = f"{type(e).__name__}: {e}"[:300]
        return result

    return check


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("documents", nargs="*", type=UUID, metavar="DOCUMENT_ID", help="document UUIDs")
    p.add_argument("--document-ids", type=Path, help="file with one document UUID per line")
    p.add_argument("--output", type=Path, help="write the JSON lines here (default: stdout)")
    p.add_argument("--page-xml-dir", type=Path,
                   help="directory of <document>.page_xml.zip files or <document>/ folders; confirms the library")
    p.add_argument("--source-root", type=Path,
                   help="root of <library>/<document>.page_xml.zip; fills in PAGE XML paths the mirror lacks")
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
    if args.source_root and not args.source_root.is_dir():
        print(f"Not a directory: {args.source_root}", file=sys.stderr)
        return 2
    dsn = os.environ.get(DSN_VARIABLE)
    if not dsn:
        print(f"Set {DSN_VARIABLE} to the metadata mirror's SQLAlchemy URL", file=sys.stderr)
        return 2

    client = None
    engine = create_engine(dsn)
    result = Summary()
    target = args.output.with_name(args.output.name + ".partial") if args.output else None
    try:
        checker = None
        if args.check_start_pages:
            from semant_demo.adapters.weaviate.client import connect_weaviate
            from semant_demo.config import Config

            config = Config()
            print(f"Weaviate endpoint (read-only): {config.WEAVIATE_HOST}:{config.WEAVIATE_REST_PORT}",
                  file=sys.stderr)
            client = await connect_weaviate(config)
            checker = weaviate_start_page_checker(client, config.collectionNames)
        with connect_read_only(engine) as source, \
                (open(target, "w", encoding="utf-8") if target else _stdout()) as out:
            async for entry in export(source, document_ids, page_xml_dir=args.page_xml_dir,
                                      source_root=args.source_root, check_start_pages=checker):
                out.write(json.dumps(entry, ensure_ascii=False) + "\n")
                result.add(entry)
        if target:
            target.replace(args.output)
    finally:
        engine.dispose()
        if client is not None:
            await client.close()
    print(json.dumps(result.as_json(), indent=2), file=sys.stderr)
    return 0 if result.all_exported else 1


def _stdout():
    from contextlib import nullcontext
    return nullcontext(sys.stdout)


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
