"""Recompute, on explicit request, the documents' chunk-value summaries for the whole database (#529).

Document browsing and Analytics filter documents by chunk filters per dimension: a document
matches when, for each filter, some chunk of it has one of the values
(``features/documents/criteria.py``). They read ``Documents.chunk_<dimension>``, the distinct
values of the document's chunks for each dimension (``language`` and the classifications of
``TASK_CLASSES``), and ``Documents.chunk_summaries_computed_at``. This command recomputes them
from the current chunks; ``chunk_summary_schema`` declares the properties first.

Dry run (read-only)::

    python -m semant_demo.maintenance.chunk_summaries --dry-run REPORT.json

Write::

    python -m semant_demo.maintenance.chunk_summaries --write REPORT.json --confirm-endpoint HOST:PORT \\
        [--concurrency 16]

Both read every chunk once in id order (pages of 1000; only the id, the dimension values and
the document reference, never text or vectors) and keep, per document, one bit per distinct
(dimension, value) pair, so memory grows with the number of documents, not of chunks. Then
they read every document in id order with its stored summaries and compare. Writing
**replaces** every document's summaries (values that no longer occur are removed; a document
without chunks or values gets empty summaries) and sets its recomputation time to the start of
the chunk pass; the write is a merge that keeps text, references and other properties, and
every page of writes is read back. Documents whose write failed or did not read back are
listed in ``REPORT.json.manifest.jsonl`` with chunks that reference no document or several
documents (those chunks are not counted for any document).

The run is repeatable: a second run over unchanged chunks reports every document
``unchanged``. An interrupted run is rerun from the start (with a new report). There is no
write-time synchronization: after ingesting, deleting, editing or classifying chunks the
summaries are stale until the next run. Run while nothing else writes chunks.

Counts (``documents``): ``never_computed`` (no recomputation time), ``changed``,
``unchanged``; ``without_values`` (no chunk values at all); ``written`` (verified writes).
Chunks: ``examined``, ``no_document``, ``several_documents``; documents that chunks reference
but that do not exist are ``missing_documents``. Exit code 0 when a dry run finds nothing to
change, or a write completes without failures; 1 otherwise; 2 when refused (missing or
differently declared summary properties when writing, a missing collection, an existing
report, an unconfirmed endpoint).

The Weaviate endpoint comes from ``WEAVIATE_HOST`` / ``WEAVIATE_REST_PORT`` /
``WEAVIATE_GRPC_PORT``.
"""
import argparse
import asyncio
import json
import sys
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from weaviate import WeaviateAsyncClient

from semant_demo.adapters.weaviate import chunk_summaries as store
from semant_demo.adapters.weaviate.document_cleanup import resolve_collection
from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.features.documents.criteria import LANGUAGE_PROPERTY
from semant_demo.features.search.filters import TASK_CLASSES

DIMENSIONS: tuple[str, ...] = (LANGUAGE_PROPERTY, *TASK_CLASSES)
"""The chunk dimensions summarized on documents: chunk language and the classifications."""
PAGE_SIZE = 1000
DOCUMENT_PAGE_SIZE = 200
"""Documents per page: each page is written and read back before the next is read."""
CONCURRENCY = 16
ATTEMPTS = 3
"""Tries of one read or write before the run stops (a read) or the document is reported (a write)."""
BACKOFF = 2.0
QUERY_TIMEOUT = 600


class Refused(LookupError):
    """The run cannot start; nothing was written."""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _progress(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


async def _retrying(call):
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return await call()
        except Exception:
            if attempt == ATTEMPTS:
                raise
            await asyncio.sleep(BACKOFF * attempt)


def manifest_path(report: Path) -> Path:
    return report.with_name(report.name + ".manifest.jsonl")


class Summaries:
    """Per document, the distinct (dimension, value) pairs of its chunks, one bit each."""

    def __init__(self, dimensions: Sequence[str]):
        self.dimensions = tuple(dimensions)
        self.bits: dict[tuple[str, str], int] = {}
        self.pairs: list[tuple[str, str]] = []
        self.masks: dict[UUID, int] = {}

    def add(self, document_id: UUID, values: dict[str, tuple[str, ...]]) -> None:
        mask = self.masks.get(document_id, 0)
        for dimension, dimension_values in values.items():
            for value in dimension_values:
                bit = self.bits.get((dimension, value))
                if bit is None:
                    bit = self.bits[(dimension, value)] = len(self.pairs)
                    self.pairs.append((dimension, value))
                mask |= 1 << bit
        self.masks[document_id] = mask

    def pop(self, document_id: UUID) -> dict[str, tuple[str, ...]]:
        """The document's values per dimension, sorted (empty for a document without chunks)."""
        mask = self.masks.pop(document_id, 0)
        values: dict[str, list[str]] = {d: [] for d in self.dimensions}
        while mask:
            lowest = mask & -mask
            dimension, value = self.pairs[lowest.bit_length() - 1]
            values[dimension].append(value)
            mask ^= lowest
        return {d: tuple(sorted(v)) for d, v in values.items()}

    def distinct_values(self) -> dict[str, int]:
        counts = {d: 0 for d in self.dimensions}
        for dimension, _ in self.bits:
            counts[dimension] += 1
        return counts


def _counts() -> dict[str, dict[str, int]]:
    return {"chunks": {"examined": 0, "no_document": 0, "several_documents": 0},
            "documents": {"examined": 0, "never_computed": 0, "changed": 0, "unchanged": 0, "without_values": 0,
                          "written": 0, "failed": 0, "missing_documents": 0}}


def _append(path: Path, lines: list[dict[str, Any]]) -> None:
    if lines:
        with path.open("a", encoding="utf-8") as file:
            for line in lines:
                file.write(json.dumps(line) + "\n")


def property_status(declared: dict[str, store.DeclaredProperty],
                    dimensions: Sequence[str]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """The expected summary properties that are not declared, and those declared differently."""
    missing, different = [], {}
    for name, expected in store.expected_properties(dimensions).items():
        found = declared.get(name)
        if found is None:
            missing.append(name)
        elif found != expected:
            different[name] = {"declared": vars(found), "expected": vars(expected)}
    return missing, different


async def _write_page(client: WeaviateAsyncClient, documents: str, planned: dict[UUID, dict[str, tuple[str, ...]]],
                      computed_at: datetime, dimensions: Sequence[str], concurrency: int) -> dict[UUID, str]:
    """Write the planned summaries and read them back; the documents not verified, with the reason."""
    errors: dict[UUID, str] = {}
    semaphore = asyncio.Semaphore(concurrency)

    async def write(document_id: UUID) -> None:
        async with semaphore:
            try:
                await _retrying(lambda: store.write_summaries(client, documents, document_id, planned[document_id],
                                                              computed_at))
            except Exception as e:
                errors[document_id] = f"{type(e).__name__}: {e}"
    await asyncio.gather(*(write(i) for i in planned))
    written = [i for i in planned if i not in errors]
    try:
        stored = await _retrying(lambda: store.read_documents(client, documents, written, dimensions))
    except Exception as e:
        return errors | {i: f"read back failed: {type(e).__name__}: {e}" for i in written}
    for document_id in written:
        found = stored.get(document_id)
        if found is None:
            errors[document_id] = "absent on read back"
        elif found.values != planned[document_id] or found.computed_at != computed_at:
            errors[document_id] = f"read back {found.values} at {found.computed_at}, expected {planned[document_id]}"
    return errors


async def run(client: WeaviateAsyncClient, names: CollectionNames, *, report: Path, endpoint: str, write: bool,
              dimensions: Sequence[str] = DIMENSIONS, concurrency: int = CONCURRENCY,
              progress: Callable[[str], None] = _progress, now: Callable[[], datetime] = _now) -> dict[str, Any]:
    """One full recomputation (see the module docstring); returns the summary, also saved to
    ``report``. Raises ``Refused`` before reading chunks when it cannot run."""
    if report.exists() or manifest_path(report).exists():
        raise Refused(f"The report {report} exists; give a new report file name")
    chunks = await resolve_collection(client, names.chunks_collection_name)
    documents = await resolve_collection(client, names.document_collection_name)
    for name in (chunks, documents):
        if not await client.collections.exists(name):
            raise Refused(f"Collection {name} does not exist")
    missing, different = property_status(await store.declared_properties(client, documents), dimensions)
    if write and (missing or different):
        raise Refused(f"{documents} does not declare the chunk-value summaries as expected (missing: "
                      f"{', '.join(missing) or 'none'}; declared differently: {', '.join(different) or 'none'}). "
                      "Run python -m semant_demo.maintenance.chunk_summary_schema --apply first; nothing was written")
    declared = not missing and not different
    chunk_properties = await store.declared_properties(client, chunks)
    chunk_dimensions = [d for d in dimensions if d in chunk_properties]

    manifest = manifest_path(report)
    manifest.touch()
    counts = _counts()
    computed_at = now()
    summaries = Summaries(dimensions)
    started = time.monotonic()
    after = None
    while True:
        page = await _retrying(lambda: store.read_chunk_page(client, chunks, after, PAGE_SIZE, chunk_dimensions))
        lines = []
        for chunk in page:
            if len(chunk.document_ids) != 1:
                status = "no_document" if not chunk.document_ids else "several_documents"
                counts["chunks"][status] += 1
                lines.append({"id": str(chunk.id), "kind": "chunk", "status": status,
                              "document_ids": [str(i) for i in chunk.document_ids]})
                continue
            summaries.add(chunk.document_ids[0], chunk.values)
        _append(manifest, lines)
        counts["chunks"]["examined"] += len(page)
        if counts["chunks"]["examined"] % (PAGE_SIZE * 100) < len(page) or len(page) < PAGE_SIZE:
            progress(f"chunks examined {counts['chunks']['examined']}, documents {len(summaries.masks)} "
                     f"({counts['chunks']['examined'] / max(time.monotonic() - started, 1e-3):.0f}/s)")
        if len(page) < PAGE_SIZE:
            break
        after = page[-1].id
    chunk_seconds = time.monotonic() - started

    started = time.monotonic()
    with_values = {d: 0 for d in dimensions}
    after = None
    document_counts = counts["documents"]
    while True:
        page = await _retrying(lambda: store.read_document_page(client, documents, after, DOCUMENT_PAGE_SIZE,
                                                                dimensions, declared))
        planned: dict[UUID, dict[str, tuple[str, ...]]] = {}
        for document in page:
            values = summaries.pop(document.id)
            planned[document.id] = values
            if document.computed_at is None:
                document_counts["never_computed"] += 1
            elif document.values != values:
                document_counts["changed"] += 1
            else:
                document_counts["unchanged"] += 1
            if not any(values.values()):
                document_counts["without_values"] += 1
            for dimension, dimension_values in values.items():
                with_values[dimension] += bool(dimension_values)
        if write and planned:
            failed = await _write_page(client, documents, planned, computed_at, dimensions, concurrency)
            document_counts["written"] += len(planned) - len(failed)
            document_counts["failed"] += len(failed)
            _append(manifest, [{"id": str(i), "kind": "document", "status": "failed", "reason": reason}
                               for i, reason in failed.items()])
        document_counts["examined"] += len(page)
        if document_counts["examined"] % (DOCUMENT_PAGE_SIZE * 100) < len(page) or len(page) < DOCUMENT_PAGE_SIZE:
            progress(f"documents examined {document_counts['examined']}, written {document_counts['written']}, "
                     f"failed {document_counts['failed']}")
        if len(page) < DOCUMENT_PAGE_SIZE:
            break
        after = page[-1].id
    document_counts["missing_documents"] = len(summaries.masks)
    _append(manifest, [{"id": str(i), "kind": "document", "status": "missing_document"} for i in summaries.masks])

    result = {
        "endpoint": endpoint, "chunks": chunks, "documents": documents, "mode": "write" if write else "dry_run",
        "computed_at": computed_at.isoformat(), "counts": counts,
        "missing_properties": missing, "different_properties": different,
        "chunk_dimensions_not_declared": [d for d in dimensions if d not in chunk_dimensions],
        "documents_with_values": with_values, "distinct_values": summaries.distinct_values(),
        "seconds": {"chunks": round(chunk_seconds, 1), "documents": round(time.monotonic() - started, 1)},
        "report": str(report), "manifest": str(manifest)}
    report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def exit_code(result: dict[str, Any]) -> int:
    """0 for a dry run with nothing to change on declared properties, or a write without failures."""
    documents = result["counts"]["documents"]
    if result["mode"] == "write":
        return 1 if documents["failed"] else 0
    if result["missing_properties"] or result["different_properties"]:
        return 1
    return 1 if documents["never_computed"] or documents["changed"] else 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", type=Path, metavar="REPORT",
                      help="recompute and compare with the stored summaries (read-only)")
    mode.add_argument("--write", type=Path, metavar="REPORT", help="recompute and replace every document's summaries")
    p.add_argument("--confirm-endpoint", metavar="HOST:PORT", help="with --write: the configured Weaviate endpoint")
    p.add_argument("--concurrency", type=int, default=CONCURRENCY, help=f"parallel writes (default {CONCURRENCY})")
    return p


async def _main(argv: list[str]) -> int:
    from semant_demo.adapters.weaviate.client import connect_weaviate
    from semant_demo.config import Config

    args = _parser().parse_args(argv)
    config = Config()
    endpoint = f"{config.WEAVIATE_HOST}:{config.WEAVIATE_REST_PORT}"
    if args.write and args.confirm_endpoint != endpoint:
        print(f"Refusing to write: configured endpoint {endpoint}, --confirm-endpoint {args.confirm_endpoint}",
              file=sys.stderr)
        return 2
    print(f"Weaviate endpoint: {endpoint}", file=sys.stderr)
    client = await connect_weaviate(config, query_timeout=QUERY_TIMEOUT)
    try:
        result = await run(client, config.collectionNames, report=args.write or args.dry_run, endpoint=endpoint,
                           write=bool(args.write), concurrency=args.concurrency)
        print(json.dumps(result, indent=2))
        return exit_code(result)
    except Refused as e:
        print(e, file=sys.stderr)
        return 2
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
