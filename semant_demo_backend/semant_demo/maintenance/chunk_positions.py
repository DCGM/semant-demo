"""Check, and on explicit request write, the absolute position of every existing chunk (#463).

Each chunk stores where it starts in its document's text: ``Chunks.startChar``,
``startWord`` and ``wordOpenAtStart``, defined and computed by the one shared calculator
of ``features/documents/positions.py`` (new chunks get them when they are inserted, #313).
Annotation text, context and positions are derived from them (``annotations/source.py``);
a span on a chunk without them is not derived (``derive_annotation``).

Check (read-only, the default)::

    python -m semant_demo.maintenance.chunk_positions --check check.json [--limit N]

Write::

    python -m semant_demo.maintenance.chunk_positions --write write.json --confirm-endpoint HOST:PORT \\
        [--limit N] [--concurrency 8]

Both go through the documents in id order (pages of ``DOCUMENT_PAGE``). For each document
they count its chunks and their least and greatest ``order`` (one aggregation), then read
its chunks in ``order`` windows of ``WINDOW`` (order, text and the stored position only,
never vectors), check that the orders are consecutive without duplicates, and compute the
positions in order from the first chunk. Only when the whole document is valid are the
missing positions written (writing: a merge of these three properties alone; text,
references, vectors, memberships, annotations and other properties are kept), then read
back. Planned actions per document:

* ``consistent``: every chunk stores the computed position;
* ``missing``: some chunks store none, the others the computed one (written by ``--write``);
* ``conflict``: a chunk stores a different or partial position: reported, nothing of the
  document is written (positions are never overwritten);
* ``nonconsecutive``: a gap or a duplicate ``order``: reported, nothing is written (the
  document violates the text model; it is not renumbered or split);
* ``no_chunks``: a document without chunks.

Writing first declares the missing properties (``startChar``/``startWord`` ``int``,
``wordOpenAtStart`` ``boolean``); a declared property of another type is refused (it needs
a separate, reviewed migration). The checkpoint (JSON, replaced atomically after each page
of documents) holds the endpoint, the resolved collections, the cursor, the counts and the
documents whose read or write failed or did not read back; running the same command again
resumes it, retrying those documents first (planned again from what is stored then). A finished checkpoint is
refused: a new check or write needs a new file name. Every reported document gets a line
in ``CHECKPOINT.manifest.jsonl``. When the pass is complete, the summary compares the
chunks examined with all chunks of the collection: chunks that no document reaches (no or
a dangling ``document`` reference) are not positioned.

Exit code 0 only for a complete pass in which every examined chunk ends with its computed
position (a check: nothing missing) and every chunk was examined; 1 otherwise; 2 when
refused. Run while nothing else writes chunks (no import, #313). Backups and the
rehearsal on a copy are described in ``docs/DATA_MAINTENANCE.md``.

The Weaviate endpoint comes from ``WEAVIATE_HOST`` / ``WEAVIATE_REST_PORT`` /
``WEAVIATE_GRPC_PORT``.
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any
from uuid import UUID

from weaviate import WeaviateAsyncClient

from semant_demo.adapters.weaviate import chunk_positions as store
from semant_demo.adapters.weaviate.document_cleanup import resolve_collection
from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.features.documents.positions import DOCUMENT_START, ChunkPosition, next_position
from semant_demo.maintenance.chunk_year import _append, _now, _retrying, _write_json, manifest_path

DOCUMENT_PAGE = 100
WINDOW = 200
"""Chunk orders read per query."""
CONCURRENCY = 8
"""Documents planned and written in parallel."""
ACTIONS = ("consistent", "missing", "conflict", "nonconsecutive", "no_chunks")
REPORTED = ("conflict", "nonconsecutive")
QUERY_TIMEOUT = 600


class Plan:
    """What one document needs: its action, the positions to write and a reason to report."""

    def __init__(self, action: str, writes: dict[UUID, ChunkPosition] | None = None, chunks: int = 0,
                 reason: str | None = None):
        self.action, self.writes, self.chunks, self.reason = action, writes or {}, chunks, reason


async def plan_document(client: WeaviateAsyncClient, chunks: str, document_id: UUID, with_positions: bool) -> Plan:
    """Read the document's chunks window by window and compute their positions in order."""
    stats = await _retrying(lambda: store.order_stats(client, chunks, document_id))
    if not stats.count:
        return Plan("no_chunks")
    if stats.last - stats.first + 1 != stats.count:
        return Plan("nonconsecutive", chunks=stats.count,
                    reason=f"{stats.count} chunks with orders {stats.first}..{stats.last}")
    position, writes, conflicts = DOCUMENT_START, {}, []
    for first in range(stats.first, stats.last + 1, WINDOW):
        last = min(first + WINDOW - 1, stats.last)
        window = await _retrying(lambda: store.read_order_range(client, chunks, document_id, first, last,
                                                                with_positions))
        if [c.order for c in window] != list(range(first, last + 1)):
            return Plan("nonconsecutive", chunks=stats.count, reason=f"orders {first}..{last} are not consecutive")
        for chunk in window:
            if chunk.position is None and not chunk.partial:
                writes[chunk.id] = position
            elif chunk.position != position:
                conflicts.append(chunk.id)
            position = next_position(position, chunk.text)
    if conflicts:
        return Plan("conflict", chunks=stats.count,
                    reason=f"{len(conflicts)} chunks store another position, e.g. {conflicts[0]}")
    return Plan("missing" if writes else "consistent", writes, stats.count)


async def _write(client: WeaviateAsyncClient, chunks: str, writes: dict[UUID, ChunkPosition]) -> str | None:
    """Write the positions and read them back; the reason of a failure, None when verified."""
    try:
        for chunk_id, position in writes.items():
            await _retrying(lambda: store.write_position(client, chunks, chunk_id, position))
        ids = list(writes)
        for start in range(0, len(ids), WINDOW):
            part = ids[start:start + WINDOW]
            stored = await _retrying(lambda: store.read_positions(client, chunks, part))
            wrong = [i for i in part if stored.get(i) != writes[i]]
            if wrong:
                return f"{len(wrong)} positions did not read back, e.g. {wrong[0]}"
    except Exception as e:  # the writes may or may not have happened; a retry plans the document again
        return f"{type(e).__name__}: {e}"
    return None


def _counts() -> dict[str, int]:
    return {"documents": 0, **{action: 0 for action in ACTIONS}, "chunks": 0, "chunks_missing": 0,
            "chunks_written": 0}


async def run(client: WeaviateAsyncClient, names: CollectionNames, *, checkpoint: Path, endpoint: str,
              write: bool, limit: int | None = None, concurrency: int = CONCURRENCY,
              progress=lambda line: print(line, file=sys.stderr, flush=True)) -> dict[str, Any]:
    """One pass over the documents (see the module docstring); returns the summary. Raises
    ``LookupError`` before writing if a collection is missing, a position property has
    another type or the checkpoint belongs to another endpoint, collection or mode."""
    chunks = await resolve_collection(client, names.chunks_collection_name)
    documents = await resolve_collection(client, names.document_collection_name)
    for name in (chunks, documents):
        if not await client.collections.exists(name):
            raise LookupError(f"Collection {name} does not exist")
    declared = await store.declared_types(client, chunks)
    wrong = {n: t for n, t in declared.items() if t != store.PROPERTY_TYPES[n].value}
    if wrong:
        raise LookupError(f"{chunks} declares {wrong}; expected {({n: t.value for n, t in store.PROPERTY_TYPES.items()})}. "
                          "Changing a declared type needs a separate, reviewed migration. Nothing was written")

    identity = {"endpoint": endpoint, "chunks": chunks, "documents": documents, "mode": "write" if write else "check"}
    if checkpoint.exists():
        state = json.loads(checkpoint.read_text(encoding="utf-8"))
        differing = sorted(key for key, value in identity.items() if state.get(key) != value)
        if differing:
            raise LookupError(f"The checkpoint {checkpoint} has a different {', '.join(differing)}; use a new checkpoint")
        if state["done"] and not state["retry"]:
            raise LookupError(f"The checkpoint {checkpoint} belongs to a finished run; give a new checkpoint "
                              "file name to check or write again")
        progress(f"Resuming {checkpoint}: after {state['after']}, {len(state['retry'])} to retry")
    else:
        state = {**identity, "started": _now(), "after": None, "done": False, "retry": {}, "counts": _counts()}
        _write_json(checkpoint, state)

    missing = [n for n in store.PROPERTY_TYPES if n not in declared]
    if write and missing:
        await store.add_position_properties(client, chunks, missing)
        state["properties_added"] = {"names": missing, "at": _now()}
        progress(f"Declared {chunks}.{', '.join(missing)}")
        missing = []
    with_positions = not missing
    manifest = manifest_path(checkpoint)
    counts = state["counts"]
    semaphore = asyncio.Semaphore(concurrency)

    async def one(document_id: UUID) -> tuple[UUID, Plan, str | None]:
        async with semaphore:
            try:
                plan = await plan_document(client, chunks, document_id, with_positions)
            except Exception as e:
                return document_id, Plan("failed"), f"read failed: {type(e).__name__}: {e}"
            failure = await _write(client, chunks, plan.writes) if write and plan.writes else None
            return document_id, plan, failure

    def record(results: list[tuple[UUID, Plan, str | None]], counted: dict[str, bool]) -> dict[str, bool]:
        """Count the results (unless ``counted`` says a document was counted before) and
        write their manifest lines; the documents to retry, and whether they are counted."""
        lines, retry = [], {}
        for document_id, plan, failure in results:
            retried = str(document_id) in counted
            if plan.action != "failed" and not counted.get(str(document_id)):
                counts["documents"] += 1
                counts[plan.action] += 1
                counts["chunks"] += plan.chunks
                counts["chunks_missing"] += len(plan.writes)
            if failure is not None:
                retry[str(document_id)] = plan.action != "failed" or counted.get(str(document_id), False)
                lines.append({"document": str(document_id), "status": "failed", "reason": failure})
            else:
                counts["chunks_written"] += len(plan.writes) if write else 0
                if plan.action in REPORTED:
                    lines.append({"document": str(document_id), "status": plan.action, "reason": plan.reason})
                elif retried:
                    lines.append({"document": str(document_id), "status": f"{plan.action}_on_retry"})
        _append(manifest, lines)
        return retry

    def save() -> None:
        state["updated"] = _now()
        _write_json(checkpoint, state)

    if state["retry"]:
        retried = [UUID(d) for d in state["retry"]]
        state["retry"] = record(list(await asyncio.gather(*(one(d) for d in retried))), state["retry"])
        save()

    started, examined = time.monotonic(), 0
    while not state["done"] and (limit is None or examined < limit):
        size = DOCUMENT_PAGE if limit is None else min(DOCUMENT_PAGE, limit - examined)
        after = UUID(state["after"]) if state["after"] else None
        page = await _retrying(lambda: store.read_document_page(client, documents, after, size))
        results = list(await asyncio.gather(*(one(d) for d in page)))
        state["retry"] = state["retry"] | record(results, {})
        examined += len(page)
        if page:
            state["after"] = str(page[-1])
        state["done"] = len(page) < size
        save()
        seconds = max(time.monotonic() - started, 1e-3)
        progress(f"documents {counts['documents']} " + " ".join(f"{a} {counts[a]}" for a in ACTIONS if counts[a])
                 + f" chunks {counts['chunks']} written {counts['chunks_written']} to retry {len(state['retry'])} "
                 f"({examined / seconds:.1f} documents/s this run)")

    if state["done"]:
        state["chunks_total"] = await _retrying(lambda: store.count_chunks(client, chunks))
    state["finished"] = _now()
    save()
    return summary(state, checkpoint, missing)


def summary(state: dict[str, Any], checkpoint: Path, missing_properties: list[str]) -> dict[str, Any]:
    total = state.get("chunks_total")
    return {key: state[key] for key in ("endpoint", "chunks", "documents", "mode", "after", "done", "counts")} | {
        "to_retry": len(state["retry"]), "missing_properties": missing_properties,
        "properties_added": state.get("properties_added"), "chunks_total": total,
        "chunks_not_reached": None if total is None else total - state["counts"]["chunks"],
        "checkpoint": str(checkpoint), "manifest": str(manifest_path(checkpoint))}


def exit_code(result: dict[str, Any]) -> int:
    """0 only for a complete pass that reached every chunk with nothing left to write, retry
    or report."""
    counts = result["counts"]
    if not result["done"] or result["to_retry"] or result["missing_properties"] or result["chunks_not_reached"]:
        return 1
    if any(counts[a] for a in REPORTED):
        return 1
    if result["mode"] == "check" and counts["missing"]:
        return 1
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", type=Path, metavar="CHECKPOINT",
                      help="compare the stored chunk positions with the computed ones (read-only); resumes a checkpoint")
    mode.add_argument("--write", type=Path, metavar="CHECKPOINT",
                      help="declare the position properties if missing and write the missing positions; "
                           "resumes a checkpoint")
    p.add_argument("--confirm-endpoint", metavar="HOST:PORT", help="with --write: the configured Weaviate endpoint")
    p.add_argument("--limit", type=int, help="at most this many documents in this run")
    p.add_argument("--concurrency", type=int, default=CONCURRENCY,
                   help=f"documents in parallel (default {CONCURRENCY})")
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
