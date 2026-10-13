"""Check, and on explicit request write, the document year copied to text chunks (#153).

The chunk search filters years on ``Chunks.yearIssued`` (an ``int`` with a range index):
range predicates through the ``Chunks.document`` reference give wrong results in Weaviate
1.34. This command keeps every chunk's ``yearIssued`` equal to the ``yearIssued`` of the
document it references:

* a document year (``int``, or a whole ``number``) is copied to its chunks;
* a document without a year leaves its chunks without one: a stored chunk year is removed,
  no year is invented;
* chunks without a resolvable document (no reference, a reference to a missing document,
  several documents) and documents whose year is not a whole number are reported in the
  manifest and left as they are.

Check (read-only, the default)::

    python -m semant_demo.maintenance.chunk_year --check check.json [--limit N]

Write::

    python -m semant_demo.maintenance.chunk_year --write write.json --confirm-endpoint HOST:PORT \\
        [--limit N] [--concurrency 16]

Both read every document's year, then every chunk once in id order (pages of 1000; only the
id, the year and the document reference, never text or vectors). Writing first declares
``Chunks.yearIssued`` (``int``, filterable, range index) if the collection lacks it, then
updates only the chunks whose year differs (a merge: text, vectors, references and other
properties are kept) and reads each page's written chunks back. The checkpoint (JSON,
replaced atomically after each page) holds the endpoint, the resolved collections, the
cursor, the counts, the year histogram and the ids whose write failed or did not read back;
running the same command again resumes it, retrying those ids first. A finished checkpoint
(complete pass, nothing to retry) is refused: a new check or write needs a new file name. Every reported chunk gets
a line in ``CHECKPOINT.manifest.jsonl``. Counts are planned actions: ``consistent``,
``no_year`` (neither has a year), ``set``, ``change`` and ``clear`` (to write);
``no_document``, ``missing_document``, ``several_documents``, ``invalid_year`` (reported).
``written`` counts verified writes.

When the pass is complete (and nothing is left to retry), the summary compares the number
of chunks the search finds for several year ranges (``yearIssued >= first AND <= last``,
the search's own predicates) with the number expected from the documents: the whole range,
1940-1952 (the case of the issue), four ranges with about equal chunk counts and the most
common year. A fresh ``--check`` after writing must report nothing to write and matching
ranges. The summary also lists other chunk properties named like a year (e.g. an unused
``documentYearIssued``); they are neither read nor changed.

A declared ``Chunks.yearIssued`` without a range index is refused by ``--write`` (and fails
``--check``): index settings of a declared property cannot be changed, so it needs a separate,
reviewed schema or collection migration.

Exit code 1 when a check finds chunks to write, a range mismatch or no range index, or a
write leaves ids to retry or a mismatch; 2 when refused. Run while nothing else writes chunks
or document years. A chunk ingested later, or a corrected document year, is reconciled by
running the command again (with a new checkpoint).

The Weaviate endpoint comes from ``WEAVIATE_HOST`` / ``WEAVIATE_REST_PORT`` /
``WEAVIATE_GRPC_PORT``.
"""
import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from weaviate import WeaviateAsyncClient

from semant_demo.adapters.weaviate import chunk_year as store
from semant_demo.adapters.weaviate.document_cleanup import resolve_collection
from semant_demo.adapters.weaviate.names import CollectionNames

PAGE_SIZE = 1000
CONCURRENCY = 16
ATTEMPTS = 3
"""Tries of one read or write before the run stops (a read) or the id is kept to retry (a write)."""
BACKOFF = 2.0
WRITES = ("set", "change", "clear")
REPORTED = ("no_document", "missing_document", "several_documents", "invalid_year")
ACTIONS = ("consistent", "no_year", *WRITES, *REPORTED)
YEAR_TYPES = ("int", "number")
QUERY_TIMEOUT = 600
"""Seconds per query: counting a range of 8 million chunks takes about 40 s on production."""
ISSUE_RANGE = (1940, 1952)
"""The range that found no chunks through the document reference (#153)."""


def canonical_year(value: Any) -> int | None:
    """The year as an int, None when absent. Raises ``ValueError`` for a value that is not a
    whole number (a bool, a fraction, text)."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value):
        raise ValueError(f"not a whole year: {value!r}")
    return int(value)


def plan(chunk: store.ChunkYear, years: dict[UUID, Any]) -> tuple[str, int | None]:
    """The action for the chunk and the year it should store (None: none or untouched)."""
    if not chunk.document_ids:
        return "no_document", None
    if len(chunk.document_ids) > 1:
        return "several_documents", None
    if chunk.document_ids[0] not in years:
        return "missing_document", None
    try:
        year = canonical_year(years[chunk.document_ids[0]])
    except ValueError:
        return "invalid_year", None
    if year is None:
        return ("no_year", None) if chunk.year is None else ("clear", None)
    if chunk.year is None:
        return "set", year
    return ("consistent" if chunk.year == year else "change"), year


def expected_year(action: str, year: int | None, chunk: store.ChunkYear) -> int | None:
    """The year the chunk stores after a successful run: reported chunks keep theirs."""
    if action in REPORTED:
        try:
            return canonical_year(chunk.year)
        except ValueError:
            return None
    return year


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, data: Any) -> None:
    """Replace the file atomically, so a crash leaves the previous checkpoint."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def manifest_path(checkpoint: Path) -> Path:
    return checkpoint.with_name(checkpoint.name + ".manifest.jsonl")


def _append(path: Path, lines: list[dict[str, Any]]) -> None:
    if lines:
        with path.open("a", encoding="utf-8") as file:
            for line in lines:
                file.write(json.dumps(line) + "\n")


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


async def _gather(items, concurrency: int, call) -> list:
    semaphore = asyncio.Semaphore(concurrency)

    async def one(item):
        async with semaphore:
            return await call(item)
    return await asyncio.gather(*(one(item) for item in items))


def _counts() -> dict[str, int]:
    return {"examined": 0, **{action: 0 for action in ACTIONS}, "written": 0}


def check_ranges(histogram: dict[int, int]) -> list[tuple[int, int]]:
    """Year ranges to compare: the whole range, the issue's, four with about equal chunk counts
    and the most common year; only ranges that hold chunks, without repeats."""
    if not histogram:
        return []
    years = sorted(histogram)
    ranges = [(years[0], years[-1])]
    if any(ISSUE_RANGE[0] <= y <= ISSUE_RANGE[1] for y in years):
        ranges.append(ISSUE_RANGE)
    total, running, first, quarters = sum(histogram.values()), 0, None, 0
    for year in years:
        first = year if first is None else first
        running += histogram[year]
        if running * 4 >= total * (quarters + 1) or year == years[-1]:
            ranges.append((first, year))
            first, quarters = None, running * 4 // total
    common = max(years, key=lambda y: histogram[y])
    ranges.append((common, common))
    return list(dict.fromkeys(ranges))


async def compare_ranges(client: WeaviateAsyncClient, chunks: str, histogram: dict[int, int]) -> list[dict[str, Any]]:
    """Chunks the search predicates find per range against the expected count; a count that
    fails is reported as a mismatch with its error."""
    result = []
    for first, last in check_ranges(histogram):
        expected = sum(n for year, n in histogram.items() if first <= year <= last)
        try:
            found = await _retrying(lambda: store.count_in_range(client, chunks, first, last))
        except Exception as e:
            result.append({"first": first, "last": last, "expected": expected, "found": None, "match": False,
                           "error": f"{type(e).__name__}: {e}"})
            continue
        result.append({"first": first, "last": last, "expected": expected, "found": found, "match": expected == found})
    return result


async def _apply(client: WeaviateAsyncClient, chunks: str, planned: dict[UUID, int | None],
                 concurrency: int, with_year: bool) -> tuple[list[UUID], list[dict[str, Any]]]:
    """Write the planned years and read them back. The ids not verified, and their manifest lines."""
    errors: dict[UUID, str] = {}

    async def write(chunk_id: UUID) -> None:
        try:
            await _retrying(lambda: store.set_chunk_year(client, chunks, chunk_id, planned[chunk_id]))
        except Exception as e:  # the write may or may not have happened; a retry plans it again
            errors[chunk_id] = f"{type(e).__name__}: {e}"
    await _gather(list(planned), concurrency, write)
    written = [i for i in planned if i not in errors]
    try:
        read_back = await _retrying(lambda: store.read_chunks(client, chunks, written, with_year))
    except Exception as e:
        read_back = {}
        errors.update({i: f"read back failed: {type(e).__name__}: {e}" for i in written})
    for chunk_id in written:
        if chunk_id not in errors:
            stored = read_back.get(chunk_id)
            if stored is None or stored.year != planned[chunk_id]:
                errors[chunk_id] = f"read back {stored and stored.year!r}, expected {planned[chunk_id]!r}"
    lines = [{"id": str(i), "status": "failed", "year": planned[i], "reason": reason} for i, reason in errors.items()]
    return sorted(errors), lines


def _line(chunk: store.ChunkYear, action: str) -> dict[str, Any]:
    return {"id": str(chunk.id), "status": action, "document_ids": [str(i) for i in chunk.document_ids],
            "stored_year": chunk.year}


async def run(client: WeaviateAsyncClient, names: CollectionNames, *, checkpoint: Path, endpoint: str,
              write: bool, limit: int | None = None, concurrency: int = CONCURRENCY,
              progress=_progress) -> dict[str, Any]:
    """One pass over the chunks (see the module docstring); returns the summary. Raises
    ``LookupError`` before writing if a collection is missing, ``Chunks.yearIssued`` has
    another type or the checkpoint belongs to another endpoint, collection or mode."""
    chunks = await resolve_collection(client, names.chunks_collection_name)
    documents = await resolve_collection(client, names.document_collection_name)
    for name in (chunks, documents):
        if not await client.collections.exists(name):
            raise LookupError(f"Collection {name} does not exist")
    prop = await store.year_property(client, chunks)
    if prop is not None and (prop.data_type not in YEAR_TYPES or not prop.filterable):
        raise LookupError(f"{chunks}.{store.YEAR} is declared as {prop.data_type} (filterable: {prop.filterable}); "
                          f"expected a filterable {' or '.join(YEAR_TYPES)}")
    if write and prop is not None and not prop.range_index:
        raise LookupError(f"{chunks}.{store.YEAR} is declared without a range index (indexRangeFilters). Index "
                          "settings of a declared property cannot be changed: adding it needs a separate, reviewed "
                          "schema or collection migration. Nothing was written")

    identity = {"endpoint": endpoint, "chunks": chunks, "documents": documents, "mode": "write" if write else "check"}
    if checkpoint.exists():
        state = json.loads(checkpoint.read_text(encoding="utf-8"))
        differing = sorted(key for key, value in identity.items() if state.get(key) != value)
        if differing:
            raise LookupError(f"The checkpoint {checkpoint} has a different {', '.join(differing)}; "
                              "use a new checkpoint")
        if state["done"] and not state["retry"]:
            raise LookupError(f"The checkpoint {checkpoint} belongs to a finished run; give a new checkpoint "
                              "file name to check or write again")
        progress(f"Resuming {checkpoint}: after {state['after']}, {len(state['retry'])} to retry")
    else:
        state = {**identity, "started": _now(), "after": None, "done": False, "retry": [],
                 "counts": _counts(), "histogram": {}}
        _write_json(checkpoint, state)

    if write and prop is None:
        await store.add_year_property(client, chunks)
        prop = await store.year_property(client, chunks)
        state["property_added"] = _now()
        progress(f"Declared {chunks}.{store.YEAR} (int, range index)")
    with_year = prop is not None

    years = await _retrying(lambda: store.read_document_years(client, documents, PAGE_SIZE))
    progress(f"Read the years of {len(years)} documents")
    manifest = manifest_path(checkpoint)
    counts, histogram = state["counts"], state["histogram"]
    started, examined = time.monotonic(), 0

    def save() -> None:
        state["updated"] = _now()
        _write_json(checkpoint, state)

    # ids whose write failed or did not read back: planned again from what is stored now
    pending = [UUID(i) for i in state["retry"]]
    for start in range(0, len(pending), PAGE_SIZE):
        ids = pending[start:start + PAGE_SIZE]
        stored = await _retrying(lambda: store.read_chunks(client, chunks, ids, with_year))
        planned = {}
        for chunk in stored.values():
            action, year = plan(chunk, years)
            if action in WRITES:
                planned[chunk.id] = year
        failed, lines = await _apply(client, chunks, planned, concurrency, with_year)
        retried = {str(i) for i in ids}
        counts["written"] += len(planned) - len(failed)
        _append(manifest, lines + [{"id": i, "status": "verified_on_retry" if UUID(i) in stored else "absent_on_retry"}
                                   for i in sorted(retried - {str(f) for f in failed})])
        state["retry"] = sorted((set(state["retry"]) - retried) | {str(f) for f in failed})
        save()

    while not state["done"] and (limit is None or examined < limit):
        size = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit - examined)
        after = UUID(state["after"]) if state["after"] else None
        page = await _retrying(lambda: store.read_chunk_page(client, chunks, after, size, with_year))
        planned: dict[UUID, int | None] = {}
        lines: list[dict[str, Any]] = []
        for chunk in page:
            action, year = plan(chunk, years)
            counts[action] += 1
            final = expected_year(action, year, chunk)
            if final is not None:
                histogram[str(final)] = histogram.get(str(final), 0) + 1
            if action in REPORTED:
                lines.append(_line(chunk, action))
            elif action in WRITES and write:
                planned[chunk.id] = year
        failed: list[UUID] = []
        if planned:
            failed, failed_lines = await _apply(client, chunks, planned, concurrency, with_year)
            lines += failed_lines
            counts["written"] += len(planned) - len(failed)
        _append(manifest, lines)
        counts["examined"] += len(page)
        examined += len(page)
        state["retry"] = sorted(set(state["retry"]) | {str(f) for f in failed})
        if page:
            state["after"] = str(page[-1].id)
        state["done"] = len(page) < size
        save()
        seconds = max(time.monotonic() - started, 1e-3)
        progress(f"examined {counts['examined']} " + " ".join(f"{a} {counts[a]}" for a in ACTIONS if counts[a])
                 + f" written {counts['written']} to retry {len(state['retry'])} after {state['after']} "
                 f"({examined / seconds:.0f}/s this run)")

    if state["done"] and not state["retry"] and with_year:
        state["ranges"] = await compare_ranges(client, chunks, {int(y): n for y, n in histogram.items()})
    state["finished"] = _now()
    save()
    return summary(state, checkpoint, prop, await store.property_names(client, chunks))


def summary(state: dict[str, Any], checkpoint: Path, prop: store.YearProperty | None,
            chunk_properties: list[str]) -> dict[str, Any]:
    histogram = {int(y): n for y, n in state["histogram"].items()}
    return {key: state[key] for key in ("endpoint", "chunks", "documents", "mode", "after", "done", "counts")} | {
        "to_retry": len(state["retry"]),
        "year_property": prop and {"data_type": prop.data_type, "range_index": prop.range_index},
        "property_added": state.get("property_added"),
        "other_year_properties": [p for p in chunk_properties if "year" in p.lower() and p != store.YEAR],
        "years": {"first": min(histogram, default=None), "last": max(histogram, default=None),
                  "chunks_with_year": sum(histogram.values())},
        "ranges": state.get("ranges"),
        "checkpoint": str(checkpoint), "manifest": str(manifest_path(checkpoint))}


def exit_code(result: dict[str, Any]) -> int:
    """0 only for a complete pass with matching ranges on a range-indexed property and, when
    checking, nothing to write; when writing, nothing left to retry."""
    counts = result["counts"]
    if not result["done"] or result["to_retry"] or result["ranges"] is None:
        return 1
    if not (result["year_property"] or {}).get("range_index"):
        return 1
    if any(not r["match"] for r in result["ranges"]):
        return 1
    if result["mode"] == "check" and any(counts[a] for a in WRITES):
        return 1
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", type=Path, metavar="CHECKPOINT",
                      help="compare the chunk years with the document years (read-only); resumes a checkpoint")
    mode.add_argument("--write", type=Path, metavar="CHECKPOINT",
                      help="declare Chunks.yearIssued if missing and write the differing years; resumes a checkpoint")
    p.add_argument("--confirm-endpoint", metavar="HOST:PORT", help="with --write: the configured Weaviate endpoint")
    p.add_argument("--limit", type=int, help="at most this many chunks in this run")
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
        result = await run(client, config.collectionNames, checkpoint=args.write or args.check, endpoint=endpoint,
                           write=bool(args.write), limit=args.limit, concurrency=args.concurrency)
        print(json.dumps(result, indent=2))
        return exit_code(result)
    except LookupError as e:
        print(e, file=sys.stderr)
        return 2
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
