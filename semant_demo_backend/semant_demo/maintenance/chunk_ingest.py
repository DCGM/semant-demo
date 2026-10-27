"""Import text chunks from JSONL into the existing collections, append-only (#313).

The one supported way to add chunks. The only writes are inserting an absent ``Chunks``
object (with its text, order, document reference, the source fields below and its
absolute position, #463) and, before the first chunk of a new document, inserting an
absent ``Documents`` object without properties. Nothing existing is ever updated or
deleted, and the schema is only read: it is the importer of #128's read-only contract.

Check (read-only, the default)::

    python -m semant_demo.maintenance.chunk_ingest --check check.json FILE.jsonl [...]

Write::

    python -m semant_demo.maintenance.chunk_ingest --write write.json --confirm-endpoint HOST:PORT \\
        (--backup-id BACKUP | --offline-backup NOTE) [--concurrency 8] FILE.jsonl [...]

Input: one JSON object per line and chunk, files read in sorted path order. Required:
``id`` (chunk UUID), ``document`` (document UUID), ``order`` (int) and ``text`` (str, may
be empty). Optional source fields: ``start_page_id``, ``language`` (str), ``from_page``,
``to_page`` (int), ``end_paragraph`` (bool); each must be declared on ``Chunks`` with that
type. The keys of the legacy ``db_insert_jsonl.py`` format that described the document
(``title``, ``year``, ``author``, ...) and precomputed vectors (``vector``,
``vector_index``) are ignored and counted, never written: document metadata comes from
``metadata_sync``, vectors from ``data_tools/embedder``. Any other key, a position
property, an invalid value, a duplicate chunk id or orders that are not consecutive within a
document reject the document (all of its lines).

Each document is planned from what is stored, never from the checkpoint alone:

* ``new``: no chunks stored; its input chunks are inserted from ``DOCUMENT_START``. The first
  order may be any integer. A missing ``Documents`` object is created first, without
  properties (metadata comes later from ``metadata_sync``).
* ``append``: the input continues after the stored chunks ``s..m``: input orders ``a..b``
  with ``s <= a <= m + 1``. The stored part ``a..m`` must equal the input (id, text, source
  fields) and store the positions the calculator gives; the chunks ``m + 1..b`` are inserted
  with positions computed from the stored tail.
* ``replayed``: everything is stored already; nothing is written.
* ``rejected``: reported, nothing of the document is written: a gap or an insert before the
  stored chunks (``gap``, ``before_start``), a difference from what is stored
  (``conflict``), stored orders that are not consecutive (``nonconsecutive_store``), a stored
  tail without positions (``positions_missing``: run ``chunk_positions --write`` first),
  chunks stored for a document object that does not exist (``dangling_document``) or
  invalid input (``invalid_input``).

Writing inserts a document's chunks strictly in order, one at a time, and reads each back
before the next one; documents are written in parallel (``--concurrency``). A failed or
uncertain write blocks the rest of that document only (``blocked``); running the command
again plans it again from what is stored then. A document created by the import whose
chunks did not all arrive is listed as ``incomplete_document`` and never deleted (#281).
Repeating a completed import inserts nothing.

The checkpoint (JSON, replaced atomically after each page of documents) holds the
endpoint, the resolved collections, the mode, the input files (size and SHA-256), the
cursor, the counts and the blocked documents, which a rerun retries first. A finished
checkpoint is refused, as is one for other input: a new run needs a new file name. Every
reported document gets a line in ``CHECKPOINT.manifest.jsonl``.

Afterwards run ``metadata_sync`` (document metadata), then ``chunk_year`` (the year on the
new chunks) and ``data_tools/embedder`` (their vectors; until then they are missing from
vector and hybrid search), see ``docs/DATA_MAINTENANCE.md``.

Exit code 0 when the pass is complete and nothing was rejected, invalid or blocked; 1
otherwise; 2 when refused (endpoint, backup, schema, checkpoint). Run while nothing else
writes chunks. The Weaviate endpoint comes from ``WEAVIATE_HOST`` / ``WEAVIATE_REST_PORT`` /
``WEAVIATE_GRPC_PORT``.
"""
import argparse
import asyncio
import bisect
import hashlib
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID

from weaviate import WeaviateAsyncClient

from semant_demo.adapters.weaviate import chunk_ingest as store
from semant_demo.adapters.weaviate.chunk_positions import PROPERTY_TYPES as POSITION_TYPES, order_stats, OrderStats
from semant_demo.adapters.weaviate.document_cleanup import filesystem_backups, resolve_collection
from semant_demo.adapters.weaviate.documents import POSITION_PROPERTIES
from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.features.documents.positions import ChunkPosition, chunk_positions, next_position
from semant_demo.maintenance.chunk_year import _append, _now, _retrying, _write_json, manifest_path

REQUIRED = {"id": "uuid", "document": "uuid", "order": "int", "text": "text"}
SOURCE_FIELDS = {"start_page_id": "text", "language": "text", "from_page": "int", "to_page": "int",
                 "end_paragraph": "boolean"}
"""Optional chunk properties taken from the input, with their declared type."""
IGNORED = frozenset({
    # the document description of the legacy db_insert_jsonl.py format (and its mapped names)
    "title", "subTitle", "partNumber", "partName", "year", "yearIssued", "date", "dateIssued", "author",
    "authors", "publisher", "description", "url", "public", "documentType", "keywords", "genre", "placeTerm",
    "section", "region", "id_code", "seriesName", "seriesNumber", "edition", "manufacturePublisher",
    "manufacturePlaceTerm", "illustrators", "translators", "editors", "redaktors", "source", "library",
    # precomputed vectors (the embedder computes them)
    "vector", "vector_index"})
"""Input keys that are counted and never written."""
DOCUMENT_PAGE = 100
WINDOW = 200
"""Chunk orders read per query when comparing the stored part of a document."""
CONCURRENCY = 8
ACTIONS = ("new", "append", "replayed", "rejected")
QUERY_TIMEOUT = 600


# ── Input ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class InputChunk:
    id: UUID
    document: UUID
    order: int
    text: str
    fields: dict[str, Any]
    """The source fields given in the input (a subset of ``SOURCE_FIELDS``)."""
    line: str
    """``file:line``, for reports."""


@dataclass
class Input:
    documents: dict[UUID, list[InputChunk]] = field(default_factory=dict)
    """Each document's chunks in input order."""
    invalid: dict[UUID, str] = field(default_factory=dict)
    """Documents rejected for their input, with the first reason."""
    unattributed: list[str] = field(default_factory=list)
    """Invalid lines that name no valid document."""
    ignored: dict[str, int] = field(default_factory=dict)
    lines: int = 0


def _valid(kind: str, value: Any) -> bool:
    if kind == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    return isinstance(value, str)


def _uuid(value: Any) -> UUID | None:
    try:
        return UUID(value) if isinstance(value, str) else None
    except ValueError:
        return None


def parse_line(record: Any, where: str, ignored: dict[str, int]) -> tuple[InputChunk | None, UUID | None, str | None]:
    """The chunk of one input line, or the document it names (if any) and why it is invalid."""
    if not isinstance(record, dict):
        return None, None, f"{where}: not a JSON object"
    document = _uuid(record.get("document"))
    for key in record:
        if key in IGNORED:
            ignored[key] = ignored.get(key, 0) + 1
        elif key in POSITION_PROPERTIES:
            return None, document, f"{where}: positions are computed by the import, not taken from the input ({key})"
        elif key not in REQUIRED and key not in SOURCE_FIELDS:
            return None, document, f"{where}: unknown field {key!r}"
    for key, kind in REQUIRED.items():
        if key not in record:
            return None, document, f"{where}: missing {key!r}"
        if kind == "uuid" and _uuid(record[key]) is None:
            return None, document, f"{where}: {key!r} is not a UUID"
        if kind != "uuid" and not _valid(kind, record[key]):
            return None, document, f"{where}: {key!r} is not {kind}"
    fields = {}
    for key, kind in SOURCE_FIELDS.items():
        if record.get(key) is not None:
            if not _valid(kind, record[key]):
                return None, document, f"{where}: {key!r} is not {kind}"
            fields[key] = record[key]
    return InputChunk(UUID(record["id"]), document, record["order"], record["text"], fields, where), document, None


def read_input(paths: Iterable[Path]) -> Input:
    """Read and validate the input files (sorted by path); never touches the store."""
    result, seen = Input(), {}
    for path in sorted(paths):
        with path.open(encoding="utf-8") as file:
            for number, raw in enumerate(file, 1):
                if not raw.strip():
                    continue
                result.lines += 1
                where = f"{path}:{number}"
                try:
                    record = json.loads(raw)
                except json.JSONDecodeError as e:
                    result.unattributed.append(f"{where}: not JSON ({e.msg})")
                    continue
                chunk, document, problem = parse_line(record, where, result.ignored)
                if problem:
                    if document is None:
                        result.unattributed.append(problem)
                    else:
                        result.invalid.setdefault(document, problem)
                    continue
                if chunk.id in seen:
                    first = seen[chunk.id]
                    for doc in {first.document, chunk.document}:
                        result.invalid.setdefault(doc, f"{where}: chunk {chunk.id} also at {first.line}")
                    continue
                seen[chunk.id] = chunk
                result.documents.setdefault(chunk.document, []).append(chunk)
    for document, chunks in result.documents.items():
        orders = [c.order for c in chunks]
        wrong = next((i for i in range(1, len(orders)) if orders[i] != orders[i - 1] + 1), None)
        if wrong is not None:
            result.invalid.setdefault(document, f"{chunks[wrong].line}: order {orders[wrong]} follows "
                                                f"{orders[wrong - 1]}; orders must be consecutive in input order")
    return result


# ── Plan ─────────────────────────────────────────────────────────────────


@dataclass
class Plan:
    """What one document needs."""
    action: str
    inserts: list[tuple[InputChunk, ChunkPosition]] = field(default_factory=list)
    create_document: bool = False
    replayed: int = 0
    reason: str | None = None


def _rejected(reason: str, kind: str) -> Plan:
    return Plan("rejected", reason=f"{kind}: {reason}")


def _expected_properties(chunk: InputChunk, position: ChunkPosition) -> dict[str, Any]:
    return {"text": chunk.text, "order": chunk.order, **chunk.fields,
            **{name: getattr(position, attr) for name, attr in POSITION_PROPERTIES.items()}}


def matches(stored: store.StoredChunk, chunk: InputChunk, position: ChunkPosition | None) -> str | None:
    """Why a stored chunk differs from the input chunk (and the expected position), None if equal."""
    if stored.document != chunk.document:
        return f"chunk {chunk.id} is stored for document {stored.document}"
    if stored.order != chunk.order:
        return f"chunk {chunk.id} is stored with order {stored.order}, not {chunk.order}"
    if stored.text != chunk.text:
        return f"chunk {chunk.id} (order {chunk.order}) stores another text"
    for name in SOURCE_FIELDS:
        if name in stored.fields and stored.fields[name] != chunk.fields.get(name):
            return f"chunk {chunk.id} (order {chunk.order}) stores {name}={stored.fields[name]!r}, " \
                   f"not {chunk.fields.get(name)!r}"
    if position is not None and stored.position != position:
        return f"chunk {chunk.id} (order {chunk.order}) stores position {stored.position}, not {position}"
    return None


def plan(chunks: list[InputChunk], stats: OrderStats, by_id: dict[UUID, store.StoredChunk],
         stored: list[store.StoredChunk], document_exists: bool) -> Plan:
    """The plan of a document from its input chunks (valid, consecutive orders ``a..b``), its
    stored order statistics ``s..m``, the stored chunks with the input ids (``by_id``), its
    stored chunks with orders ``max(a, s)..m`` or the tail ``m..m`` (``stored``, in order) and
    whether the document object exists. Pure: the caller reads, this decides."""
    a, b = chunks[0].order, chunks[-1].order
    for chunk in chunks:
        other = by_id.get(chunk.id)
        if other is not None and (other.document != chunk.document or other.order != chunk.order):
            return _rejected(matches(other, chunk, None), "conflict")
    if not stats.count:
        if by_id:
            return _rejected(f"{len(by_id)} input chunks are stored without the document's chunks", "conflict")
        return Plan("new", list(zip(chunks, chunk_positions(c.text for c in chunks))),
                    create_document=not document_exists)
    if not document_exists:
        return _rejected(f"{stats.count} chunks reference document {chunks[0].document}, which does not exist",
                         "dangling_document")
    s, m = stats.first, stats.last
    if stats.count != m - s + 1:
        return _rejected(f"{stats.count} chunks stored with orders {s}..{m}", "nonconsecutive_store")
    if a < s:
        return _rejected(f"the input starts at order {a}, before the stored chunks {s}..{m}", "before_start")
    if a > m + 1:
        return _rejected(f"the input starts at order {a}; the stored chunks end at {m}", "gap")
    expected_orders = list(range(min(a, m), m + 1))
    if [c.order for c in stored] != expected_orders:
        return _rejected(f"stored orders {min(a, m)}..{m} are not consecutive", "nonconsecutive_store")
    if stored[0].position is None:
        return _rejected(f"chunk {stored[0].id} (order {stored[0].order}) stores no position; run "
                         "chunk_positions --write first", "positions_missing")
    position = stored[0].position
    by_order = {c.order: c for c in chunks}
    for current in stored:
        if current.order >= a:
            problem = matches(current, by_order[current.order], position)
            if problem:
                return _rejected(problem, "conflict")
        elif current.position != position:
            return _rejected(f"chunk {current.id} (order {current.order}) stores position {current.position}",
                             "positions_missing")
        position = next_position(position, current.text)
    new = [c for c in chunks if c.order > m]
    replayed = len(chunks) - len(new)
    if not new:
        return Plan("replayed", replayed=replayed)
    return Plan("append", list(zip(new, chunk_positions((c.text for c in new), position))), replayed=replayed)


# ── Store side ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Target:
    chunks: str
    documents: str
    fields: tuple[str, ...]
    """The source fields declared on the chunks collection."""


async def preflight(client: WeaviateAsyncClient, names: CollectionNames) -> Target:
    """Resolve the collections and check the schema read-only; ``LookupError`` before any write."""
    chunks = await resolve_collection(client, names.chunks_collection_name)
    documents = await resolve_collection(client, names.document_collection_name)
    for name in (chunks, documents):
        if not await client.collections.exists(name):
            raise LookupError(f"Collection {name} does not exist. The import never creates collections (#128)")
    declared = await store.schema(client, chunks)
    required = {"text": "text", "order": "int", **{n: t.value for n, t in POSITION_TYPES.items()}}
    problems = [f"{n} is {declared.properties.get(n, 'missing')}, expected {t}" for n, t in required.items()
                if declared.properties.get(n) != t]
    problems += [f"{n} is {declared.properties[n]}, expected {t}" for n, t in SOURCE_FIELDS.items()
                 if n in declared.properties and declared.properties[n] != t]
    targets = declared.references.get("document")
    if targets != (documents,):
        problems.append(f"the document reference targets {targets}, expected ({documents},)")
    if problems:
        raise LookupError(f"{chunks}: {'; '.join(problems)}. The import never changes the schema; nothing was written")
    return Target(chunks, documents, tuple(n for n in SOURCE_FIELDS if n in declared.properties))


async def examine(client: WeaviateAsyncClient, target: Target, chunks: list[InputChunk]) -> Plan:
    """Read what ``plan`` needs about one document."""
    document = chunks[0].document
    undeclared = sorted({k for c in chunks for k in c.fields} - set(target.fields))
    if undeclared:
        return _rejected(f"{', '.join(undeclared)} not declared on {target.chunks}", "invalid_input")
    stats = await _retrying(lambda: order_stats(client, target.chunks, document))
    ids = [c.id for c in chunks]
    by_id = {}
    for start in range(0, len(ids), WINDOW):
        part = ids[start:start + WINDOW]
        by_id |= await _retrying(lambda: store.read_chunks(client, target.chunks, part, target.fields))
    exists = bool(await _retrying(lambda: store.existing_documents(client, target.documents, [document])))
    stored = []
    if stats.count and stats.count == stats.last - stats.first + 1 and stats.first <= chunks[0].order <= stats.last + 1:
        first = min(chunks[0].order, stats.last)
        for low in range(first, stats.last + 1, WINDOW):
            high = min(low + WINDOW - 1, stats.last)
            stored += await _retrying(lambda: store.read_order_range(client, target.chunks, document, low, high,
                                                                     target.fields))
    return plan(chunks, stats, by_id, stored, exists)


@dataclass
class Outcome:
    inserted: int = 0
    created_document: bool = False
    failure: str | None = None


async def _verify(client, target: Target, chunk: InputChunk, position: ChunkPosition) -> str | None:
    stored = (await _retrying(lambda: store.read_chunks(client, target.chunks, [chunk.id], target.fields))).get(chunk.id)
    if stored is None:
        return f"chunk {chunk.id} (order {chunk.order}) is not stored"
    return matches(stored, chunk, position)


async def write(client: WeaviateAsyncClient, target: Target, plan_: Plan) -> Outcome:
    """Insert the plan's document (if needed) and chunks in order, each read back before the next."""
    outcome = Outcome()
    document = plan_.inserts[0][0].document
    if plan_.create_document:
        try:
            await store.insert_document(client, target.documents, document)
            outcome.created_document = True
        except store.AlreadyExists:
            pass  # created meanwhile, or by an earlier uncertain attempt; it exists either way
        except Exception as e:
            if not await _retrying(lambda: store.existing_documents(client, target.documents, [document])):
                outcome.failure = f"creating document {document} failed: {type(e).__name__}: {e}"
                return outcome
            outcome.created_document = True  # the uncertain write arrived
    for chunk, position in plan_.inserts:
        properties = _expected_properties(chunk, position)
        try:
            await store.insert_chunk(client, target.chunks, chunk.id, document, properties)
        except store.AlreadyExists:
            pass  # verified below: equal is fine (an earlier uncertain write), different is a conflict
        except Exception as e:
            if await _verify(client, target, chunk, position):  # the write may or may not have arrived
                outcome.failure = f"inserting chunk {chunk.id} (order {chunk.order}) failed: {type(e).__name__}: {e}"
                return outcome
        problem = await _verify(client, target, chunk, position)
        if problem:
            outcome.failure = f"read back: {problem}"
            return outcome
        outcome.inserted += 1
    return outcome


# ── Run ──────────────────────────────────────────────────────────────────


def _counts() -> dict[str, int]:
    return {"documents": 0, **{a: 0 for a in ACTIONS}, "documents_created": 0,
            "chunks_inserted": 0, "chunks_to_insert": 0, "chunks_replayed": 0}


def _fingerprint(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1 << 20), b""):
            digest.update(block)
    return {"path": str(path.resolve()), "size": path.stat().st_size, "sha256": digest.hexdigest()}


async def run(client: WeaviateAsyncClient, names: CollectionNames, inputs: list[Path], *, checkpoint: Path,
              endpoint: str, write_: bool, concurrency: int = CONCURRENCY,
              progress=lambda line: print(line, file=sys.stderr, flush=True)) -> dict[str, Any]:
    """One pass over the input documents (see the module docstring); returns the summary.
    Raises ``LookupError`` before writing for a schema or checkpoint problem."""
    target = await preflight(client, names)
    data = read_input(inputs)
    identity = {"endpoint": endpoint, "chunks": target.chunks, "documents": target.documents,
                "mode": "write" if write_ else "check", "inputs": [_fingerprint(p) for p in sorted(inputs)]}
    if checkpoint.exists():
        state = json.loads(checkpoint.read_text(encoding="utf-8"))
        differing = sorted(key for key, value in identity.items() if state.get(key) != value)
        if differing:
            raise LookupError(f"The checkpoint {checkpoint} has a different {', '.join(differing)}; use a new checkpoint")
        if state["done"] and not state["blocked"]:
            raise LookupError(f"The checkpoint {checkpoint} belongs to a finished run; give a new checkpoint file name")
        progress(f"Resuming {checkpoint}: after {state['after']}, {len(state['blocked'])} blocked to retry")
    else:
        state = {**identity, "started": _now(), "after": None, "done": False, "blocked": [], "counts": _counts(),
                 "lines": data.lines, "ignored_fields": data.ignored, "invalid_lines": data.unattributed}
        _write_json(checkpoint, state)
        _append(manifest_path(checkpoint), [{"status": "invalid_line", "reason": r} for r in data.unattributed])
    counts, manifest = state["counts"], manifest_path(checkpoint)
    semaphore = asyncio.Semaphore(concurrency)

    async def one(document: UUID) -> tuple[UUID, Plan, Outcome | None]:
        async with semaphore:
            if document in data.invalid:
                return document, _rejected(data.invalid[document], "invalid_input"), None
            try:
                plan_ = await examine(client, target, data.documents[document])
            except Exception as e:
                return document, Plan("failed"), Outcome(failure=f"read failed: {type(e).__name__}: {e}")
            if not write_ or not plan_.inserts:
                return document, plan_, None
            try:
                return document, plan_, await write(client, target, plan_)
            except Exception as e:  # a read-back failed; the next run plans the document again
                return document, plan_, Outcome(failure=f"{type(e).__name__}: {e}")

    def record(results: list[tuple[UUID, Plan, Outcome | None]], retried: set[str]) -> list[str]:
        lines, blocked = [], []
        for document, plan_, outcome in results:
            if plan_.action != "failed" and str(document) not in retried:
                counts["documents"] += 1
                counts[plan_.action] += 1
                counts["chunks_replayed"] += plan_.replayed
            counts["chunks_to_insert"] += len(plan_.inserts) if not write_ else 0
            if plan_.action == "rejected":
                lines.append({"document": str(document), "status": "rejected", "reason": plan_.reason})
            if outcome is not None:
                counts["chunks_inserted"] += outcome.inserted
                counts["documents_created"] += outcome.created_document
                if outcome.failure:
                    blocked.append(str(document))
                    lines.append({"document": str(document), "status": "blocked", "reason": outcome.failure,
                                  "inserted": outcome.inserted})
                    if plan_.action == "new":
                        lines.append({"document": str(document), "status": "incomplete_document",
                                      "reason": f"{outcome.inserted} of {len(plan_.inserts)} chunks inserted"})
        _append(manifest, lines)
        return blocked

    def save() -> None:
        state["updated"] = _now()
        _write_json(checkpoint, state)

    documents = sorted(str(d) for d in set(data.documents) | set(data.invalid))
    if state["blocked"]:
        retried = set(state["blocked"])
        state["blocked"] = record(list(await asyncio.gather(*(one(UUID(d)) for d in state["blocked"]))), retried)
        save()
    started = time.monotonic()
    while not state["done"]:
        start = bisect.bisect_right(documents, state["after"]) if state["after"] else 0
        page = documents[start:start + DOCUMENT_PAGE]
        results = list(await asyncio.gather(*(one(UUID(d)) for d in page)))
        state["blocked"] += record(results, set())
        if page:
            state["after"] = page[-1]
        state["done"] = len(page) < DOCUMENT_PAGE
        save()
        seconds = max(time.monotonic() - started, 1e-3)
        progress(f"documents {counts['documents']} " + " ".join(f"{a} {counts[a]}" for a in ACTIONS if counts[a])
                 + f" inserted {counts['chunks_inserted']} blocked {len(state['blocked'])} "
                 f"({counts['documents'] / seconds:.1f} documents/s)")
    state["finished"] = _now()
    save()
    return summary(state, checkpoint)


def summary(state: dict[str, Any], checkpoint: Path) -> dict[str, Any]:
    return {key: state[key] for key in ("endpoint", "chunks", "documents", "mode", "done", "counts", "lines",
                                        "ignored_fields")} | {
        "invalid_lines": len(state["invalid_lines"]), "blocked": len(state["blocked"]),
        "checkpoint": str(checkpoint), "manifest": str(manifest_path(checkpoint)),
        "next": "metadata_sync, then chunk_year and data_tools/embedder (docs/DATA_MAINTENANCE.md)"}


def exit_code(result: dict[str, Any]) -> int:
    """0 only for a complete pass in which nothing was rejected, invalid or blocked."""
    if not result["done"] or result["blocked"] or result["invalid_lines"] or result["counts"]["rejected"]:
        return 1
    return 0


async def check_backup(client: WeaviateAsyncClient, target: Target, backup_id: str) -> None:
    """``LookupError`` unless ``backup_id`` is a successful filesystem backup holding the chunks
    and documents collections themselves."""
    try:
        backups = await filesystem_backups(client)
    except Exception as e:
        raise LookupError(f"Cannot list filesystem backups ({type(e).__name__}: {e})") from e
    backup = next((b for b in backups if b.id == backup_id), None)
    if backup is None or backup.status != "SUCCESS":
        raise LookupError(f"No successful filesystem backup {backup_id!r}")
    missing = {target.chunks, target.documents} - set(backup.collections)
    if missing:
        raise LookupError(f"Backup {backup_id} does not hold {', '.join(sorted(missing))}")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", type=Path, metavar="CHECKPOINT", help="validate and plan the import (read-only)")
    mode.add_argument("--write", type=Path, metavar="CHECKPOINT", help="insert the new documents and chunks")
    p.add_argument("--confirm-endpoint", metavar="HOST:PORT", help="with --write: the configured Weaviate endpoint")
    backup = p.add_mutually_exclusive_group()
    backup.add_argument("--backup-id", help="with --write: a successful backup-filesystem backup of chunks and documents")
    backup.add_argument("--offline-backup", metavar="NOTE",
                        help="with --write: where an offline copy of the store is (recorded, not checked)")
    p.add_argument("--concurrency", type=int, default=CONCURRENCY, help=f"documents in parallel (default {CONCURRENCY})")
    p.add_argument("inputs", nargs="+", type=Path, metavar="FILE.jsonl")
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
    if args.write and not (args.backup_id or args.offline_backup):
        print("Refusing to write without --backup-id or --offline-backup (docs/DATA_MAINTENANCE.md)", file=sys.stderr)
        return 2
    missing = [str(p) for p in args.inputs if not p.is_file()]
    if missing:
        print(f"No such input file: {', '.join(missing)}", file=sys.stderr)
        return 2
    print(f"Weaviate endpoint: {endpoint}", file=sys.stderr)
    client = await connect_weaviate(config, query_timeout=QUERY_TIMEOUT)
    try:
        if args.write and args.backup_id:
            await check_backup(client, await preflight(client, config.collectionNames), args.backup_id)
        result = await run(client, config.collectionNames, args.inputs, checkpoint=args.write or args.check,
                           endpoint=endpoint, write_=bool(args.write), concurrency=args.concurrency)
        if args.write:
            result["backup"] = args.backup_id or {"offline": args.offline_backup}
        print(json.dumps(result, indent=2))
        return exit_code(result)
    except LookupError as e:
        print(e, file=sys.stderr)
        return 2
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
