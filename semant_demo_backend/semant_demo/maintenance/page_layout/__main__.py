"""Convert PERO PAGE XML to per-page layout JSON and chunk-start anchors (#540).

Offline: reads files, writes files, no database or network access. From
``semant_demo_backend/``::

    python -m semant_demo.maintenance.page_layout --page-xml-dir DIR --output OUT \\
        [DOCUMENT_ID ... | --document-ids ids.txt] [--page-order pages.jsonl] [--chunks chunks.jsonl] \\
        [--line-confidence 0.6] [--min-chunk-chars 768] [--max-chunk-chars 1152] [--max-edit-ratio 0.05] \\
        [--overwrite]

``DIR`` holds ``<document>.page_xml.zip`` files or ``<document>/`` folders of
``<page>.xml``; without document ids every document there is converted. ``--page-order`` is
a ``page_order`` export (#571); a document without an exported page list uses the file
names' order, with a ``file_name_order`` warning (often wrong). ``--chunks`` gives the
chunks to anchor (JSON lines ``id``, ``document``, ``order``, ``text``); without it, the
regenerated chunks are anchored, which checks the converter against itself.

Output in ``OUT`` (refused when it is not empty, unless ``--overwrite``; then each converted
document's page folder is replaced as a whole, other documents' folders are kept, and the
JSON lines files and the report cover this run only):

- ``pages/<document>/<page>.json``: one versioned page file per page (``docs/PAGE_LAYOUT.md``);
- ``chunks.jsonl``: the regenerated chunks (``documentId``, ``order``, ``text``,
  ``legacyStartPageId``);
- ``anchors.jsonl``: per chunk ``layoutStart`` (``{pageId, lineId, offset, match}`` or null),
  ``reason``, ``differences`` (Levenshtein distance) and the ``params`` and
  ``maxEditRatio`` it was made with (they must match the page files');
- ``report.json``: parameters, totals and per-document status, counts and warnings.

The exit code is 0 when every document converted and every non-empty chunk has an exact
anchor, 1 otherwise, 2 for invalid arguments.
"""
import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from uuid import UUID

from semant_demo.maintenance.page_layout.anchors import MAX_EDIT_RATIO
from semant_demo.maintenance.page_layout.convert import (
    CONVERTED, convert_document, documents_in, read_chunks, read_page_order, read_page_xml)
from semant_demo.maintenance.page_layout.serialize import Params


def _parser() -> argparse.ArgumentParser:
    defaults = Params()
    p = argparse.ArgumentParser(prog="python -m semant_demo.maintenance.page_layout", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("documents", nargs="*", type=UUID, metavar="DOCUMENT_ID")
    p.add_argument("--document-ids", type=Path, help="file with one document UUID per line")
    p.add_argument("--page-xml-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--page-order", type=Path, help="page_order export (#571)")
    p.add_argument("--chunks", type=Path, help="chunks to anchor (JSON lines)")
    p.add_argument("--line-confidence", type=float, default=defaults.line_confidence)
    p.add_argument("--min-chunk-chars", type=int, default=defaults.min_chunk_chars)
    p.add_argument("--max-chunk-chars", type=int, default=defaults.max_chunk_chars)
    p.add_argument("--max-edit-ratio", type=float, default=MAX_EDIT_RATIO)
    p.add_argument("--overwrite", action="store_true", help="write into a non-empty output directory")
    return p


def _ids(path: Path) -> list[UUID]:
    return [UUID(line.strip()) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def main(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    params = Params(args.line_confidence, args.min_chunk_chars, args.max_chunk_chars)
    if not args.page_xml_dir.is_dir():
        print(f"Not a directory: {args.page_xml_dir}", file=sys.stderr)
        return 2
    if args.output.exists() and any(args.output.iterdir()) and not args.overwrite:
        print(f"{args.output} is not empty (use --overwrite)", file=sys.stderr)
        return 2
    if not 0 <= args.max_edit_ratio < 1 or not 0 < params.min_chunk_chars <= params.max_chunk_chars:
        print("Need 0 <= --max-edit-ratio < 1 and 0 < --min-chunk-chars <= --max-chunk-chars", file=sys.stderr)
        return 2
    try:
        document_ids = [*args.documents, *(_ids(args.document_ids) if args.document_ids else [])]
        orders = read_page_order(args.page_order) if args.page_order else {}
        stored = read_chunks(args.chunks) if args.chunks else None
    except (OSError, ValueError, KeyError) as e:
        print(f"Cannot read input: {e}", file=sys.stderr)
        return 2
    document_ids = list(dict.fromkeys(document_ids)) or documents_in(args.page_xml_dir)

    args.output.mkdir(parents=True, exist_ok=True)
    documents, totals = [], Counter()
    with open(args.output / "chunks.jsonl", "w", encoding="utf-8") as chunks_file, \
            open(args.output / "anchors.jsonl", "w", encoding="utf-8") as anchors_file:
        for document_id in document_ids:
            entry = _convert(args, document_id, orders, stored, params, chunks_file, anchors_file)
            documents.append(entry)
            totals.update({"documents": 1, entry["status"]: 1, "pages": entry["pages"], "chunks": entry["chunks"],
                           **{f"anchors_{k}": v for k, v in entry["anchors"].items()}})
    report = {"params": params.as_json(), "maxEditRatio": args.max_edit_ratio,
              "pageOrder": str(args.page_order) if args.page_order else None,
              "chunks": str(args.chunks) if args.chunks else "regenerated", "totals": dict(totals),
              "documents": documents}
    (args.output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"totals": dict(totals)}, indent=2), file=sys.stderr)
    clean = all(d["status"] == CONVERTED and d["anchors"]["approximate"] == 0
                and d["anchors"]["none"] == d["emptyChunks"] for d in documents)
    return 0 if clean else 1


def _convert(args, document_id, orders, stored, params, chunks_file, anchors_file) -> dict:
    files = read_page_xml(args.page_xml_dir, document_id)
    xml, unrecognized = files if files is not None else ({}, [])
    extra = []
    if document_id in orders:
        page_ids, order_from = orders[document_id], "page_order"
    else:
        page_ids, order_from = sorted(xml, key=str), "file_names"
        extra.append({"code": "file_name_order", "count": 0, "sample": []})
    if files is None:
        extra.append({"code": "no_page_xml_files", "count": 0, "sample": []})
    if unrecognized:
        extra.append({"code": "unrecognized_page_xml_names", "count": len(unrecognized), "sample": unrecognized[:5]})
    targets = stored.get(document_id, []) if stored is not None else None
    result = convert_document(document_id, page_ids, xml, params, targets, args.max_edit_ratio)

    _write_pages(args.output / "pages", document_id, result.pages)
    for chunk in result.chunks:
        chunks_file.write(json.dumps({"documentId": str(document_id), **chunk}, ensure_ascii=False) + "\n")
    for anchor in result.anchors:
        anchors_file.write(json.dumps(anchor, ensure_ascii=False) + "\n")
    return {"documentId": str(document_id), "status": result.status, "failure": result.failure,
            "pageOrderFrom": order_from, "pages": len(result.pages), "chunks": len(result.chunks),
            "emptyChunks": sum(1 for a in result.anchors if a["reason"] == "empty_chunk"),
            "anchors": result.counts(), "warnings": extra + result.warnings}


def _write_pages(root: Path, document_id: UUID, pages: dict) -> None:
    """Replace the document's page folder with exactly these pages: written to a new folder,
    swapped in, the old one removed. Other documents' folders are not touched."""
    final = root / str(document_id)
    fresh, old = root / f".{document_id}.new", root / f".{document_id}.old"
    for leftover in (fresh, old):
        if leftover.exists():
            shutil.rmtree(leftover)
    fresh.mkdir(parents=True)
    for page_id, data in pages.items():
        (fresh / f"{page_id}.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                                               encoding="utf-8")
    if final.exists():
        final.rename(old)
    fresh.rename(final)
    if old.exists():
        shutil.rmtree(old)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
