"""Running the two steps over many documents, with streamed reports.

Each run writes ``REPORT.documents.jsonl`` (one line per document, appended as it is done)
and ``REPORT`` (the totals, replaced after every document), so an interrupted run leaves a
usable record. Documents are processed one at a time, in input order.
"""
import json
import sys
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import Any
from uuid import UUID

from semant_demo.adapters.filesystem.page_assets import PageAssetStore, write_atomically
from semant_demo.adapters.weaviate.layout_anchors import AnchoredChunk
from semant_demo.maintenance.page_import.anchors import AnchorStore, apply_plan, plan_document
from semant_demo.maintenance.page_import.assets import import_document
from semant_demo.maintenance.page_layout.serialize import Params

ChunkReader = Callable[[UUID], Awaitable[list[AnchoredChunk]]]


class Report:
    def __init__(self, path: Path, header: dict[str, Any]):
        self.path, self.header = path, header
        self.totals: Counter = Counter()
        self.statuses: Counter = Counter()
        self.lines_path = path.with_name(path.name + ".documents.jsonl")
        self.lines_path.write_text("", encoding="utf-8")
        self.started = time.time()

    def add(self, entry: dict[str, Any], counts: dict[str, int]) -> None:
        with self.lines_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self.statuses[entry["status"]] += 1
        self.totals.update(counts)
        self.save(complete=False)

    def save(self, complete: bool) -> dict[str, Any]:
        summary = {**self.header, "complete": complete, "seconds": round(time.time() - self.started, 1),
                   "documents": sum(self.statuses.values()), "statuses": dict(sorted(self.statuses.items())),
                   "totals": dict(sorted(self.totals.items())), "documentReports": self.lines_path.name}
        write_atomically(self.path, json.dumps(summary, indent=2, ensure_ascii=False).encode("utf-8"))
        return summary


def _flat(prefix: str, values: dict[str, Any]) -> dict[str, int]:
    return {f"{prefix}{key}": value for key, value in values.items() if isinstance(value, int)}


def read_exports(path: Path, wanted: Iterable[UUID] | None) -> list[dict[str, Any]]:
    """The ``page_order`` export lines, in file order or in the order of ``wanted``."""
    entries = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entry = json.loads(line)
                entries.setdefault(UUID(entry["documentId"]), entry)
    if wanted is None:
        return list(entries.values())
    return [entries.get(d, {"documentId": str(d), "status": "not_in_export", "pages": []}) for d in wanted]


async def run_assets(store: PageAssetStore, exports: list[dict[str, Any]], read_chunks: ChunkReader,
                     params: Params, max_edit_ratio: float, report_path: Path,
                     progress=lambda message: print(message, file=sys.stderr)) -> dict[str, Any]:
    report = Report(report_path, {"step": "assets", "assetsDir": str(store.root), "params": params.as_json(),
                                  "maxEditRatio": max_edit_ratio})
    for n, entry in enumerate(exports, 1):
        document_id = UUID(entry["documentId"])
        if entry.get("status", "exported") != "exported" or not entry.get("pages"):
            line = {"documentId": str(document_id), "status": "not_exported",
                    "exportStatus": entry.get("status")}
            report.add(line, {})
        else:
            try:
                chunks = await read_chunks(document_id)
            except Exception as e:  # a failed read: reported, the next document goes on
                report.add({"documentId": str(document_id), "status": "chunk_read_failed",
                            "error": type(e).__name__}, {})
                continue
            line = import_document(store, entry, chunks, params, max_edit_ratio)
            report.add(line, {"pages": line["pages"], "chunks": line["chunks"], **_flat("", line["assets"]),
                              **_flat("anchors_", line["anchors"]), **_flat("pageMetadata_", line["pageMetadata"])})
        progress(f"[{n}/{len(exports)}] {document_id} {line['status']}")
    return report.save(complete=True)


async def run_anchors(store: PageAssetStore, document_ids: list[UUID], anchors: AnchorStore, write: bool,
                      concurrency: int, report_path: Path, endpoint: str,
                      progress=lambda message: print(message, file=sys.stderr)) -> dict[str, Any]:
    report = Report(report_path, {"step": "anchors", "mode": "write" if write else "check", "endpoint": endpoint,
                                  "assetsDir": str(store.root)})
    for n, document_id in enumerate(document_ids, 1):
        try:
            chunks = await anchors.read_chunks(document_id)
        except Exception:
            chunks = None
        plan = plan_document(store, document_id, chunks)
        counts = Counter(plan.counts)
        if write and plan.status == "planned" and plan.actions:
            counts.update(await apply_plan(anchors, plan, concurrency))
        report.add({"documentId": str(document_id), "status": plan.status, "counts": dict(sorted(counts.items())),
                    "issues": plan.issues.as_json()}, dict(counts))
        progress(f"[{n}/{len(document_ids)}] {document_id} {plan.status} {dict(sorted(counts.items()))}")
    return report.save(complete=True)


def assets_exit_code(summary: dict[str, Any]) -> int:
    """0 when every document was imported; source gaps are reported, not failures."""
    return 0 if set(summary["statuses"]) <= {"imported"} else 1


def anchors_exit_code(summary: dict[str, Any]) -> int:
    """0 when every document was planned and nothing is left to write (check) or every write
    read back (write), and no chunk text changed since planning."""
    totals = summary["totals"]
    if set(summary["statuses"]) - {"planned"} or totals.get("text_changed") or totals.get("chunk_missing"):
        return 1
    if summary["mode"] == "check":
        return 1 if totals.get("set") or totals.get("clear") else 0
    pending = totals.get("set", 0) + totals.get("clear", 0)
    return 0 if totals.get("written", 0) == pending else 1
