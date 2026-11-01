"""Import text chunks from JSONL into the existing collections, append-only (#313).

The one supported way to add chunks. The only writes are inserting an absent ``Chunks``
object (with its text, order, document reference, the source fields below and its
absolute position, #463) and, before the first chunk of a new document, inserting an
absent ``Documents`` object without properties. Nothing existing is ever updated or
deleted, and the schema is only read: it is the importer of #128's read-only contract.

Check (read-only, the default)::

    python -m semant_demo.maintenance.chunk_ingest --check check.json INPUT [...]

Write::

    python -m semant_demo.maintenance.chunk_ingest --write write.json --confirm-endpoint HOST:PORT \\
        (--backup-id BACKUP | --offline-backup NOTE) [--bulk [--batch 800]] [--page N] [--concurrency 8] \\
        INPUT [...]

An INPUT is a JSONL file or a directory, which stands for its ``*.jsonl`` files (not those of
its subdirectories; other entries are counted and skipped). A file named twice, also through
a directory or a symlink, is read once; a missing file or a directory without ``*.jsonl``
files is refused. Instead of a list file, give a directory of symlinks: it selects files from
anywhere, also more than the command line can hold.

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
before the next one; documents are written in parallel (``--concurrency``). The single-object
insert is refused for an existing id, so nothing stored is ever replaced. ``--bulk`` (only
into a chunk collection that is empty at the start, e.g. a new store) batch-inserts instead:
rounds of one next chunk from each of up to ``--batch`` documents of the page, each round
read back before the next; a document that is finished leaves its place in the next round to
the next document of the page. Documents are always created with the single-object insert.
A batch insert silently replaces an object with the same id, hence the empty-collection
condition; an interrupted bulk run is finished without ``--bulk``. A failed or uncertain
write blocks the rest of that document only (``blocked``); running the command again plans it
again from what is stored then. A document created by the import whose
chunks did not all arrive is listed as ``incomplete_document`` and never deleted (#281).
Repeating a completed import inserts nothing.

Documents are planned, written and checkpointed in pages (``--page``, 100 documents and
2000 with ``--bulk``). A larger page needs more memory and repeats more checks after an
interruption; with ``--bulk`` it keeps the batches full while the short documents finish.

The input is read twice, so that the chunk texts are held for one page only. A first pass
validates every line (including duplicate chunk ids across all files) and keeps only where
each document's lines are, a digest of them and each file's SHA-256 for the checkpoint (about
40 bytes per chunk at its peak). Each page then reads the lines of its documents again; if
they differ from the first pass, the run stops with ``InputChanged`` and writes nothing more.

The checkpoint (JSON, replaced atomically after each page of documents) holds the
endpoint, the resolved collections, the mode, the input files (size and SHA-256), the
cursor, the counts and the blocked documents, which a rerun retries first. A finished
checkpoint is refused, as is one for other input: a new run needs a new file name. Every
write run records its backup, its page and whether it used ``--bulk`` (with its batch) in the
checkpoint (``runs``) before writing; a resumed run may use another page or batch. A
``--backup-id`` is checked (a successful ``backup-filesystem`` backup holding the chunks and
documents collections), an ``--offline-backup`` note is recorded as given and not checked
(an offline copy of the data directory, made with Weaviate stopped). A check takes neither.
Every reported document gets a line in ``CHECKPOINT.manifest.jsonl``.

Afterwards run ``metadata_sync`` (document metadata), then ``chunk_year`` (the year on the
new chunks) and ``data_tools/embedder`` (their vectors; until then they are missing from
vector and hybrid search), see ``docs/DATA_MAINTENANCE.md``.

Exit code 0 when the pass is complete and nothing was rejected, invalid or blocked; 1
otherwise; 2 when refused (endpoint, backup, schema, checkpoint) or an input file changed.
Run while nothing else writes chunks. The Weaviate endpoint comes from ``WEAVIATE_HOST`` /
``WEAVIATE_REST_PORT`` / ``WEAVIATE_GRPC_PORT``.
"""
import argparse
import asyncio
import bisect
import hashlib
import io
import json
import sys
import time
from array import array
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID

import numpy as np
from weaviate import WeaviateAsyncClient

from semant_demo.adapters.weaviate import chunk_ingest as store
from semant_demo.adapters.weaviate.chunk_positions import (
    PROPERTY_TYPES as POSITION_TYPES, OrderStats, count_chunks, order_stats,
)
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
"""Documents planned, written and checkpointed together (``--page``)."""
BULK_PAGE = 2000
"""The default page with ``--bulk``: large enough to keep the batches full while short documents finish."""
WINDOW = 200
"""Chunk orders read per query when comparing the stored part of a document."""
CONCURRENCY = 8
BULK_BATCH = 800
"""Chunks per batch insert with ``--bulk`` (``--batch``): one from each of up to this many documents."""
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


class InputChanged(LookupError):
    """An input file changed after the first pass; nothing more is written."""


@dataclass
class _Document:
    """Where the valid input lines of one document are, and what they were."""
    number: int
    """The owner recorded for each of its chunk ids in the duplicate check."""
    ranges: list[tuple[int, int, int, int]] = field(default_factory=list)
    """``(file, start, end, first line number)``: byte ranges of consecutive valid lines."""
    last_order: int | None = None
    digest: bytes = b""
    """Its lines chained through BLAKE2b; ``load`` compares it to detect a changed file."""


@dataclass
class Index:
    """The first pass over the input: everything but the chunks themselves (``load`` reads them)."""
    files: list[Path] = field(default_factory=list)
    """The input files in reading order."""
    fingerprints: list[dict[str, Any]] = field(default_factory=list)
    """Each file's resolved path, size and SHA-256, from the same read as the index."""
    documents: dict[UUID, _Document] = field(default_factory=dict)
    """The documents with valid lines, in order of first appearance."""
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


def _chain(digest: bytes, raw: bytes) -> bytes:
    return hashlib.blake2b(digest + raw, digest_size=16).digest()


def _fold(chunk_id: UUID) -> int:
    return (chunk_id.int >> 64) ^ (chunk_id.int & 0xFFFF_FFFF_FFFF_FFFF)


def index_input(paths: Iterable[Path]) -> Index:
    """Read and validate the input files (sorted by path) once; never touches the store.
    Keeps where each document's lines are instead of its chunks, so memory grows with the
    number of documents and chunks (the duplicate check), not with the texts."""
    index, folds, owners = Index(), array("Q"), array("I")
    for number_of_file, path in enumerate(sorted(paths)):
        index.files.append(path)
        sha, offset = hashlib.sha256(), 0
        with path.open("rb") as file:
            for number, raw in enumerate(file, 1):
                start, offset = offset, offset + len(raw)
                sha.update(raw)
                line = raw.decode("utf-8")
                if not line.strip():
                    continue
                index.lines += 1
                where = f"{path}:{number}"
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as e:
                    index.unattributed.append(f"{where}: not JSON ({e.msg})")
                    continue
                chunk, document, problem = parse_line(record, where, index.ignored)
                if problem:
                    if document is None:
                        index.unattributed.append(problem)
                    else:
                        index.invalid.setdefault(document, problem)
                    continue
                entry = index.documents.get(chunk.document)
                if entry is None:
                    entry = index.documents[chunk.document] = _Document(len(index.documents))
                if entry.last_order is not None and chunk.order != entry.last_order + 1:
                    index.invalid.setdefault(chunk.document, f"{where}: order {chunk.order} follows "
                                                             f"{entry.last_order}; orders must be consecutive in "
                                                             "input order")
                entry.last_order = chunk.order
                last = entry.ranges[-1] if entry.ranges else None
                if last and last[0] == number_of_file and last[2] == start:
                    entry.ranges[-1] = (number_of_file, last[1], offset, last[3])
                else:
                    entry.ranges.append((number_of_file, start, offset, number))
                entry.digest = _chain(entry.digest, raw)
                folds.append(_fold(chunk.id))
                owners.append(entry.number)
        index.fingerprints.append({"path": str(path.resolve()), "size": offset, "sha256": sha.hexdigest()})
    _reject_duplicates(index, folds, owners)
    return index


def _reject_duplicates(index: Index, folds: array, owners: array) -> None:
    """Reject both documents of every chunk id given on two input lines. The ids are compared
    as 64-bit folds first; the documents of equal folds are read again and compared exactly."""
    values = np.frombuffer(folds, dtype=np.uint64)
    ordered = np.sort(values)
    repeated = np.unique(ordered[1:][ordered[1:] == ordered[:-1]])
    del ordered
    if not len(repeated):
        return
    suspects = set(np.frombuffer(owners, dtype=np.uint32)[np.isin(values, repeated)].tolist())
    names = list(index.documents)
    files = {str(path): n for n, path in enumerate(index.files)}

    def place(chunk: InputChunk) -> tuple[int, int]:
        path, number = chunk.line.rsplit(":", 1)
        return files[path], int(number)
    seen: dict[UUID, InputChunk] = {}
    loaded = load(index, [names[n] for n in sorted(suspects)])
    for chunk in sorted((c for chunks in loaded.values() for c in chunks), key=place):
        first = seen.setdefault(chunk.id, chunk)
        if first is not chunk:
            for document in {first.document, chunk.document}:
                index.invalid.setdefault(document, f"{chunk.line}: chunk {chunk.id} also at {first.line}")


def load(index: Index, documents: Iterable[UUID]) -> dict[UUID, list[InputChunk]]:
    """The chunks of ``documents`` in input order, read again at the ranges of ``index``
    (documents without valid lines are left out). ``InputChanged`` when a document's lines are
    not the ones the first pass read."""
    wanted = {d: index.documents[d] for d in documents if d in index.documents}
    by_file: dict[int, list[tuple[int, int, UUID, int]]] = {}
    for document, entry in wanted.items():
        for n, (number_of_file, start, end, _) in enumerate(entry.ranges):
            by_file.setdefault(number_of_file, []).append((start, end, document, n))
    data: dict[UUID, list[bytes]] = {d: [b""] * len(entry.ranges) for d, entry in wanted.items()}
    for number_of_file, ranges in sorted(by_file.items()):
        with index.files[number_of_file].open("rb") as file:
            for start, end, document, n in sorted(ranges):
                file.seek(start)
                data[document][n] = file.read(end - start)
    result = {}
    for document, entry in wanted.items():
        lines, digest = [], b""
        for (number_of_file, _, _, first), part in zip(entry.ranges, data[document]):
            for number, raw in enumerate(io.BytesIO(part), first):
                digest = _chain(digest, raw)
                lines.append((f"{index.files[number_of_file]}:{number}", raw))
        if digest != entry.digest:
            changed = sorted({str(index.files[r[0]]) for r in entry.ranges})
            raise InputChanged(f"{', '.join(changed)} changed after the input was checked (document {document}); "
                               "nothing more is written. Restore the file, or check the new input with a new "
                               "checkpoint")
        result[document] = [parse_line(json.loads(raw), where, {})[0] for where, raw in lines]
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


async def _create_document(client: WeaviateAsyncClient, target: Target, plan_: Plan) -> Outcome:
    """Insert the plan's document if it needs one (always the single-object insert, which never
    replaces an existing document)."""
    outcome = Outcome()
    if not plan_.create_document:
        return outcome
    document = plan_.inserts[0][0].document
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
    return outcome


async def write(client: WeaviateAsyncClient, target: Target, plan_: Plan) -> Outcome:
    """Insert the plan's document (if needed) and chunks in order, each read back before the next."""
    outcome = await _create_document(client, target, plan_)
    if outcome.failure:
        return outcome
    document = plan_.inserts[0][0].document
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


async def write_bulk(client: WeaviateAsyncClient, target: Target, plans: dict[UUID, Plan],
                     batch: int = BULK_BATCH, concurrency: int = CONCURRENCY) -> dict[UUID, Outcome]:
    """``--bulk``: the documents first (single inserts), then the chunks in rounds of batch
    inserts holding at most one chunk from each of the first ``batch`` unfinished documents,
    each round read back before the next. A chunk refused, missing or different after its
    round blocks the rest of its document."""
    semaphore = asyncio.Semaphore(concurrency)

    async def create(plan_: Plan) -> Outcome:
        async with semaphore:
            try:
                return await _create_document(client, target, plan_)
            except Exception as e:
                return Outcome(failure=f"{type(e).__name__}: {e}")
    outcomes = dict(zip(plans, await asyncio.gather(*(create(p) for p in plans.values()))))
    pending = {d: list(p.inserts) for d, p in plans.items() if not outcomes[d].failure}
    while pending:
        round_ = [(d, *queue[0]) for d, queue in pending.items()][:batch]
        try:
            errors = await store.insert_chunks(client, target.chunks, [
                (chunk.id, d, _expected_properties(chunk, position)) for d, chunk, position in round_])
        except Exception as e:  # uncertain: what arrived is decided by the read-back
            errors = {chunk.id: f"{type(e).__name__}: {e}" for _, chunk, _ in round_}
        try:
            stored = await _retrying(lambda: store.read_chunks(client, target.chunks, [c.id for _, c, _ in round_],
                                                              target.fields))
        except Exception as e:
            for d, _, _ in round_:
                outcomes[d].failure = f"read back failed: {type(e).__name__}: {e}"
                del pending[d]
            continue
        for d, chunk, position in round_:
            row = stored.get(chunk.id)
            problem = (f"chunk {chunk.id} (order {chunk.order}) is not stored" if row is None
                       else matches(row, chunk, position))
            if problem:
                outcomes[d].failure = f"{problem}; {errors[chunk.id]}" if chunk.id in errors else f"read back: {problem}"
                del pending[d]
                continue
            outcomes[d].inserted += 1
            pending[d].pop(0)
            if not pending[d]:
                del pending[d]
    return outcomes


# ── Run ──────────────────────────────────────────────────────────────────


def _counts() -> dict[str, int]:
    return {"documents": 0, **{a: 0 for a in ACTIONS}, "documents_created": 0,
            "chunks_inserted": 0, "chunks_to_insert": 0, "chunks_replayed": 0}


async def run(client: WeaviateAsyncClient, names: CollectionNames, inputs: list[Path], *, checkpoint: Path,
              endpoint: str, write_: bool, backup: dict[str, str] | None = None, bulk: bool = False,
              page: int | None = None, batch: int | None = None, concurrency: int = CONCURRENCY,
              progress=lambda line: print(line, file=sys.stderr, flush=True)) -> dict[str, Any]:
    """One pass over the input documents (see the module docstring); returns the summary.
    ``backup`` (``{"backup_id": ...}`` or ``{"offline_backup": ...}``) is required for a write,
    refused for a check, and recorded in the checkpoint (``runs``) before anything is written.
    ``bulk`` batch-inserts the chunks and is refused unless the chunk collection is empty at the
    start. ``page`` defaults to ``DOCUMENT_PAGE`` (``BULK_PAGE`` with ``bulk``); ``batch``
    (default ``BULK_BATCH``) belongs to ``bulk``. Raises ``LookupError`` before writing for a
    backup, bulk, page, batch, schema or checkpoint problem, and ``InputChanged`` (after the
    pages before it are checkpointed) when an input file changes during the run."""
    if write_ and not backup:
        raise LookupError("A write needs a backup (--backup-id or --offline-backup, docs/DATA_MAINTENANCE.md)")
    if not write_ and (backup or bulk):
        raise LookupError("A check writes nothing and takes no backup or --bulk")
    if batch is not None and not bulk:
        raise LookupError("--batch belongs to --bulk")
    if (page is not None and page < 1) or (batch is not None and batch < 1):
        raise LookupError("--page and --batch must be positive")
    page = page or (BULK_PAGE if bulk else DOCUMENT_PAGE)
    batch = batch or BULK_BATCH
    if bulk and batch > page:
        progress(f"--batch {batch} exceeds --page {page}: a batch holds at most one chunk from each document of a page")
    target = await preflight(client, names)
    if bulk:
        stored = await _retrying(lambda: count_chunks(client, target.chunks))
        if stored:
            raise LookupError(f"--bulk needs an empty {target.chunks} ({stored} chunks stored): a batch insert would "
                              "silently replace a chunk with the same id. Run without --bulk; nothing was written")
    index = index_input(inputs)
    identity = {"endpoint": endpoint, "chunks": target.chunks, "documents": target.documents,
                "mode": "write" if write_ else "check", "inputs": index.fingerprints}
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
                 "lines": index.lines, "ignored_fields": index.ignored, "invalid_lines": index.unattributed}
        _write_json(checkpoint, state)
        _append(manifest_path(checkpoint), [{"status": "invalid_line", "reason": r} for r in index.unattributed])
    if write_:
        state.setdefault("runs", []).append({"at": _now(), "bulk": bulk, "page": page,
                                              **({"batch": batch} if bulk else {}), **backup})
        _write_json(checkpoint, state)
    counts, manifest = state["counts"], manifest_path(checkpoint)
    semaphore = asyncio.Semaphore(concurrency)

    async def one(document: UUID, chunks: list[InputChunk]) -> tuple[UUID, Plan, Outcome | None]:
        async with semaphore:
            if document in index.invalid:
                return document, _rejected(index.invalid[document], "invalid_input"), None
            try:
                plan_ = await examine(client, target, chunks)
            except Exception as e:
                return document, Plan("failed"), Outcome(failure=f"read failed: {type(e).__name__}: {e}")
            if not write_ or not plan_.inserts or bulk:
                return document, plan_, None
            try:
                return document, plan_, await write(client, target, plan_)
            except Exception as e:  # a read-back failed; the next run plans the document again
                return document, plan_, Outcome(failure=f"{type(e).__name__}: {e}")

    async def each(documents_: list[str]) -> list[tuple[UUID, Plan, Outcome | None]]:
        """Plan (and without ``bulk`` write) these documents, reading only their input lines."""
        ids = [UUID(d) for d in documents_]
        chunks = load(index, (d for d in ids if d not in index.invalid))
        return list(await asyncio.gather(*(one(d, chunks.get(d, [])) for d in ids)))

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
                    if plan_.action == "new" and (outcome.created_document or not plan_.create_document):
                        lines.append({"document": str(document), "status": "incomplete_document",
                                      "reason": f"{outcome.inserted} of {len(plan_.inserts)} chunks inserted"})
        _append(manifest, lines)
        return blocked

    async def process(documents_: list[str]) -> list[str]:
        """Plan and write one page; returns its blocked documents. Its chunks are freed on return,
        before the next page is read."""
        results = await each(documents_)
        if bulk:
            writes = {d: p for d, p, o in results if o is None and p.inserts}
            outcomes = (await write_bulk(client, target, writes, batch=batch, concurrency=concurrency)
                        if writes else {})
            results = [(d, p, outcomes.get(d, o)) for d, p, o in results]
        return record(results, set())

    def save() -> None:
        state["updated"] = _now()
        _write_json(checkpoint, state)

    documents = sorted(str(d) for d in set(index.documents) | set(index.invalid))
    if state["blocked"]:
        retried = set(state["blocked"])
        state["blocked"] = record(await each(state["blocked"]), retried)
        save()
    started = time.monotonic()
    while not state["done"]:
        start = bisect.bisect_right(documents, state["after"]) if state["after"] else 0
        current = documents[start:start + page]
        state["blocked"] += await process(current)
        if current:
            state["after"] = current[-1]
        state["done"] = len(current) < page
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
        "runs": state.get("runs", []),
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


def input_files(inputs: Iterable[Path]) -> tuple[list[Path], dict[Path, int]]:
    """The files of the command line's inputs and, per directory, how many of its entries were
    skipped. ``LookupError`` for a missing file (also a broken symlink) or a directory without
    ``*.jsonl`` files."""
    files, seen, skipped, missing, empty = [], set(), {}, [], []
    for given in inputs:
        if given.is_dir():
            entries = sorted(given.iterdir())
            candidates = [e for e in entries if e.suffix == ".jsonl" and not e.is_dir()]
            skipped[given] = len(entries) - len(candidates)
            if not candidates:
                empty.append(str(given))
        else:
            candidates = [given]
        for path in candidates:
            if not path.is_file():
                missing.append(str(path))
            elif (real := path.resolve()) not in seen:
                seen.add(real)
                files.append(path)
    if missing:
        more = f" and {len(missing) - 10} more" if len(missing) > 10 else ""
        raise LookupError(f"No such input file: {', '.join(missing[:10])}{more}")
    if empty:
        raise LookupError(f"No *.jsonl files in {', '.join(empty)}")
    return files, skipped


def _positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError(f"{value} is not a positive number")
    return number


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", type=Path, metavar="CHECKPOINT", help="validate and plan the import (read-only)")
    mode.add_argument("--write", type=Path, metavar="CHECKPOINT", help="insert the new documents and chunks")
    p.add_argument("--confirm-endpoint", metavar="HOST:PORT", help="with --write: the configured Weaviate endpoint")
    backup = p.add_mutually_exclusive_group()
    backup.add_argument("--backup-id", help="with --write: a successful backup-filesystem backup of chunks and documents")
    backup.add_argument("--offline-backup", metavar="NOTE",
                        help="with --write: where an offline copy of the store is (recorded in the checkpoint, "
                             "not checked)")
    p.add_argument("--bulk", action="store_true",
                   help="with --write into an empty chunk collection only: batch-insert the chunks (faster; refused "
                        "when any chunk is stored, because a batch insert replaces an object with the same id)")
    p.add_argument("--batch", type=_positive, metavar="N",
                   help=f"with --bulk: chunks per batch insert, one from each of up to N documents of the page "
                        f"(default {BULK_BATCH})")
    p.add_argument("--page", type=_positive, metavar="N",
                   help=f"documents planned, written and checkpointed together (default {DOCUMENT_PAGE}, with --bulk "
                        f"{BULK_PAGE}); a larger page needs more memory and repeats more checks after an interruption")
    p.add_argument("--concurrency", type=int, default=CONCURRENCY, help=f"documents in parallel (default {CONCURRENCY})")
    p.add_argument("inputs", nargs="+", type=Path, metavar="INPUT",
                   help="a JSONL file, or a directory standing for its *.jsonl files; instead of a list file, "
                        "give a directory of symlinks (any files, also more than the command line can hold)")
    return p


async def _main(argv: list[str]) -> int:
    from semant_demo.adapters.weaviate.client import connect_weaviate
    from semant_demo.config import Config

    args = _parser().parse_args(argv)
    if args.check and (args.backup_id or args.offline_backup or args.bulk):
        print("--backup-id, --offline-backup and --bulk belong to --write; a check writes nothing", file=sys.stderr)
        return 2
    if args.batch and not args.bulk:
        print("--batch belongs to --bulk", file=sys.stderr)
        return 2
    backup = {"backup_id": args.backup_id} if args.backup_id else (
        {"offline_backup": args.offline_backup} if args.offline_backup else None)
    config = Config()
    endpoint = f"{config.WEAVIATE_HOST}:{config.WEAVIATE_REST_PORT}"
    if args.write and args.confirm_endpoint != endpoint:
        print(f"Refusing to write: configured endpoint {endpoint}, --confirm-endpoint {args.confirm_endpoint}",
              file=sys.stderr)
        return 2
    if args.write and not backup:
        print("Refusing to write without --backup-id or --offline-backup (docs/DATA_MAINTENANCE.md)", file=sys.stderr)
        return 2
    try:
        inputs, skipped = input_files(args.inputs)
    except LookupError as e:
        print(e, file=sys.stderr)
        return 2
    for directory, count in skipped.items():
        if count:
            print(f"Skipped {count} entries of {directory} that are not *.jsonl files", file=sys.stderr)
    print(f"Weaviate endpoint: {endpoint}", file=sys.stderr)
    client = await connect_weaviate(config, query_timeout=QUERY_TIMEOUT)
    try:
        if args.write and args.backup_id:
            await check_backup(client, await preflight(client, config.collectionNames), args.backup_id)
        result = await run(client, config.collectionNames, inputs, checkpoint=args.write or args.check,
                           endpoint=endpoint, write_=bool(args.write), backup=backup, bulk=args.bulk,
                           page=args.page, batch=args.batch, concurrency=args.concurrency)
        print(json.dumps(result, indent=2))
        return exit_code(result)
    except LookupError as e:
        print(e, file=sys.stderr)
        return 2
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
