"""Check, and on explicit request write, the document visibility copied to text chunks (#793).

Unscoped search, RAG and Explore select chunks with ``Chunks.documentPublic == true``
instead of filtering through the ``Chunks.document -> Documents.public`` reference, which
costs over a second per query on 8 million chunks (#279, #789). ``Documents.public`` stays
the source of truth; the chunk flag is derived from it, failing closed:

* ``true`` only when the chunk references exactly one existing document whose ``public`` is
  exactly ``true``;
* ``false`` for a restricted (``false``) or unknown (absent, not a bool) document, and for a
  chunk without a document, with a reference to a document missing from the pass's snapshot
  or with several documents (these are also listed in the manifest). Weaviate resolves no
  reference to a deleted document, so such a chunk reads as without a document.

A chunk without the flag is not public to the search either; a complete pass gives every
chunk an explicit value.

Check (read-only, the default)::

    python -m semant_demo.maintenance.chunk_document_public --check check.json [--limit N]

Write::

    python -m semant_demo.maintenance.chunk_document_public --write write.json --confirm-endpoint HOST:PORT \\
        [--limit N] [--concurrency 16] [--rate N]

Only some documents (one UUID per line, e.g. ``chunk_ingest``'s ``CHECKPOINT.documents.txt``
or the ids ``metadata_sync`` reports as ``chunks_pending``)::

    python -m semant_demo.maintenance.chunk_document_public --write docs.json --confirm-endpoint HOST:PORT \\
        --document-ids ids.txt

The full pass reads every document's ``public``, then every chunk once in id order (pages of
1000; only the id, the flag and the document reference, never text or vectors). Writing first
declares ``Chunks.documentPublic`` (``bool``, filterable) if the collection lacks it, then
updates only the chunks whose flag differs and reads each page's written chunks back. Within
a page, ``false`` is written first; the documents of chunks to become ``true`` are read again
just before, and only a document still ``public=true`` makes its chunks ``true``. ``--rate``
caps the writes per second.

The checkpoint (JSON, replaced atomically after each page) holds the endpoint, the resolved
collections, the mode, the cursor, the counts and the ids whose write failed or did not read
back; running the same command again resumes it, retrying those ids first. A finished
checkpoint is refused: a new check or write needs a new file name. Reported chunks and failed
writes get a line in ``CHECKPOINT.manifest.jsonl``.

Counts: ``reasons`` (why a chunk gets its value: ``public``, ``restricted``, ``unknown``,
``no_document``, ``missing_document``, ``several_documents``) and actions: ``consistent``,
``set`` (no flag stored), ``change`` (the other value stored); ``stale_true`` counts the chunks
storing ``true`` that must not (the leak the order of writes prevents); ``written`` counts
verified writes.

When the pass is complete and nothing is left to retry, the summary compares the chunk counts
the search predicates find (``documentPublic == true``, ``== false``, and all chunks) with
those expected from the pass. A check exits 0 only when nothing is left to write and the
counts match: ``true + false == all`` proves that no chunk lacks the flag. Run it after a
write and before deploying a search that filters on the flag.

The document mode (``--document-ids``) brings the chunks of each listed document to its
value through the ``document`` reference (``sync_document``, which ``metadata_sync`` uses on
a change of ``public``) and verifies the counts of each document. It does not find chunks
without a document; the full pass does.

Exit code 1 when a check finds chunks to write or a count mismatch, or a write leaves ids to
retry or a mismatch; 2 when refused. Run while nothing else changes ``Documents.public``
(``metadata_sync``) or imports chunks; other chunk writes (tags, titles) are kept by the merge.

The Weaviate endpoint comes from ``WEAVIATE_HOST`` / ``WEAVIATE_REST_PORT`` /
``WEAVIATE_GRPC_PORT``.
"""
import argparse
import asyncio
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from weaviate import WeaviateAsyncClient

from semant_demo.adapters.weaviate import chunk_visibility as store
from semant_demo.adapters.weaviate.document_cleanup import resolve_collection
from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.maintenance.chunk_year import _append, _gather, _now, _retrying, _write_json, manifest_path

PAGE_SIZE = 1000
CONCURRENCY = 16
REASONS = ("public", "restricted", "unknown", "no_document", "missing_document", "several_documents")
REPORTED = ("no_document", "missing_document", "several_documents")
ACTIONS = ("consistent", "set", "change")
QUERY_TIMEOUT = 600
"""Seconds per query: counting 8 million chunks by a filter takes tens of seconds."""
DOCUMENT_ROUNDS = 1000
"""Rounds of ``sync_document`` (of up to ``PAGE_SIZE`` chunks each) before it gives up."""


def derive(chunk: store.ChunkVisibility, documents: dict[UUID, Any]) -> tuple[bool, str]:
    """The flag the chunk must store and why (one of ``REASONS``)."""
    if not chunk.document_ids:
        return False, "no_document"
    if len(chunk.document_ids) > 1:
        return False, "several_documents"
    if chunk.document_ids[0] not in documents:
        return False, "missing_document"
    public = documents[chunk.document_ids[0]]
    if public is True:
        return True, "public"
    return False, "restricted" if public is False else "unknown"


def action(stored: Any, expected: bool) -> str:
    if stored is expected:
        return "consistent"
    return "set" if stored is None else "change"


class _Pacer:
    """At most ``rate`` calls per second (none when ``rate`` is None)."""

    def __init__(self, rate: float | None):
        self.interval = 1 / rate if rate else 0.0
        self.next = 0.0
        self.lock = asyncio.Lock()

    async def wait(self) -> None:
        if not self.interval:
            return
        async with self.lock:
            now = time.monotonic()
            delay = self.next - now
            self.next = max(now, self.next) + self.interval
        if delay > 0:
            await asyncio.sleep(delay)


async def _write_values(client: WeaviateAsyncClient, chunks: str, planned: dict[UUID, bool], concurrency: int,
                        pacer: _Pacer) -> dict[UUID, str]:
    """Write the planned flags and read them back; the ids not verified, with the reason."""
    errors: dict[UUID, str] = {}

    async def write(chunk_id: UUID) -> None:
        await pacer.wait()
        try:
            await _retrying(lambda: store.set_chunk_public(client, chunks, chunk_id, planned[chunk_id]))
        except Exception as e:  # the write may or may not have happened; a retry plans it again
            errors[chunk_id] = f"{type(e).__name__}: {e}"
    await _gather(list(planned), concurrency, write)
    written = [i for i in planned if i not in errors]
    try:
        read_back = await _retrying(lambda: store.read_chunks(client, chunks, written))
    except Exception as e:
        read_back = {}
        errors.update({i: f"read back failed: {type(e).__name__}: {e}" for i in written})
    for chunk_id in written:
        if chunk_id not in errors:
            stored = read_back.get(chunk_id)
            if stored is None or stored.public is not planned[chunk_id]:
                errors[chunk_id] = f"read back {stored and stored.public!r}, expected {planned[chunk_id]!r}"
    return errors


async def _apply(client: WeaviateAsyncClient, chunks: str, documents: str, page: list[store.ChunkVisibility],
                 planned: dict[UUID, bool], concurrency: int, pacer: _Pacer) -> tuple[list[UUID], list[dict], int]:
    """Write ``false`` first, then ``true`` for the chunks whose document is still public when
    read again. Returns the ids not verified, their manifest lines and the verified writes."""
    by_id = {c.id: c for c in page}
    lower = {i: v for i, v in planned.items() if v is False}
    errors = await _write_values(client, chunks, lower, concurrency, pacer) if lower else {}
    raise_ = {i: v for i, v in planned.items() if v is True}
    if raise_:
        document_ids = sorted({by_id[i].document_ids[0] for i in raise_})
        try:
            fresh = await _retrying(lambda: store.read_document_public(client, documents, document_ids))
        except Exception as e:  # nothing is raised without a fresh read
            fresh = None
            errors.update({i: f"document reread failed: {type(e).__name__}: {e}" for i in raise_})
        if fresh is not None:
            stale = {i for i in raise_ if fresh.get(by_id[i].document_ids[0]) is not True}
            errors.update({i: "the document is no longer public; planned again" for i in stale})
            errors.update(await _write_values(client, chunks, {i: True for i in raise_ if i not in stale},
                                              concurrency, pacer))
    lines = [{"id": str(i), "status": "failed", "public": planned[i], "reason": reason}
             for i, reason in errors.items()]
    return sorted(errors), lines, len(planned) - len(errors)


def _line(chunk: store.ChunkVisibility, reason: str) -> dict[str, Any]:
    return {"id": str(chunk.id), "status": reason, "document_ids": [str(i) for i in chunk.document_ids],
            "stored": chunk.public}


def _counts() -> dict[str, Any]:
    return {"examined": 0, "reasons": {r: 0 for r in REASONS}, **{a: 0 for a in ACTIONS},
            "stale_true": 0, "expected_true": 0, "expected_false": 0, "written": 0}


async def _resolve(client: WeaviateAsyncClient, names: CollectionNames) -> tuple[str, str, Any]:
    chunks = await resolve_collection(client, names.chunks_collection_name)
    documents = await resolve_collection(client, names.document_collection_name)
    for name in (chunks, documents):
        if not await client.collections.exists(name):
            raise LookupError(f"Collection {name} does not exist")
    prop = await store.flag_property(client, chunks)
    if prop is not None and (prop.data_type != "boolean" or not prop.filterable):
        raise LookupError(f"{chunks}.{store.PROPERTY} is declared as {prop.data_type} (filterable: "
                          f"{prop.filterable}); expected a filterable boolean. It needs a separate, reviewed "
                          "schema migration; nothing was written")
    return chunks, documents, prop


async def flag_target(client: WeaviateAsyncClient, names: CollectionNames) -> str | None:
    """The chunks collection (alias resolved) when it declares ``documentPublic``, else None:
    writers of ``Documents.public`` synchronize the chunks only once the flag exists."""
    chunks = await resolve_collection(client, names.chunks_collection_name)
    if not await client.collections.exists(chunks):
        return None
    prop = await store.flag_property(client, chunks)
    return chunks if prop is not None else None


def _load_state(checkpoint: Path, identity: dict[str, Any], progress) -> dict[str, Any]:
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
        return state
    state = {**identity, "started": _now(), "after": None, "done": False, "retry": [], "counts": _counts()}
    _write_json(checkpoint, state)
    return state


async def _declare(client: WeaviateAsyncClient, chunks: str, state: dict[str, Any], progress):
    await store.add_property(client, chunks)
    state["property_added"] = _now()
    progress(f"Declared {chunks}.{store.PROPERTY} (bool, filterable)")
    return await store.flag_property(client, chunks)


def _progress(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


async def compare_counts(client: WeaviateAsyncClient, chunks: str, counts: dict[str, Any]) -> dict[str, Any]:
    """What the search predicates find against what the pass expects; ``match`` only when every
    count is equal (so no chunk lacks the flag)."""
    result: dict[str, Any] = {"expected_true": counts["expected_true"], "expected_false": counts["expected_false"],
                              "expected_all": counts["examined"]}
    try:
        result["true"] = await _retrying(lambda: store.count_flag(client, chunks, True))
        result["false"] = await _retrying(lambda: store.count_flag(client, chunks, False))
        result["all"] = await _retrying(lambda: store.count_flag(client, chunks))
    except Exception as e:
        return result | {"match": False, "error": f"{type(e).__name__}: {e}"}
    result["without_flag"] = result["all"] - result["true"] - result["false"]
    result["match"] = (result["true"], result["false"], result["all"]) == (
        counts["expected_true"], counts["expected_false"], counts["examined"])
    return result


async def run(client: WeaviateAsyncClient, names: CollectionNames, *, checkpoint: Path, endpoint: str,
              write: bool, limit: int | None = None, concurrency: int = CONCURRENCY, rate: float | None = None,
              progress=_progress) -> dict[str, Any]:
    """One pass over the chunks (see the module docstring); returns the summary. Raises
    ``LookupError`` before writing if a collection is missing, the property has another type
    or the checkpoint belongs to another endpoint, collection or mode."""
    chunks, documents, prop = await _resolve(client, names)
    identity = {"endpoint": endpoint, "chunks": chunks, "documents": documents, "mode": "write" if write else "check"}
    state = _load_state(checkpoint, identity, progress)
    if write and prop is None:
        prop = await _declare(client, chunks, state, progress)
    declared = prop is not None
    pacer = _Pacer(rate)

    public = await _retrying(lambda: store.read_all_document_public(client, documents, PAGE_SIZE))
    progress(f"Read the public value of {len(public)} documents")
    manifest = manifest_path(checkpoint)
    counts = state["counts"]
    started, examined = time.monotonic(), 0

    def save() -> None:
        state["updated"] = _now()
        _write_json(checkpoint, state)

    pending = [UUID(i) for i in state["retry"]]
    for start in range(0, len(pending), PAGE_SIZE):
        ids = pending[start:start + PAGE_SIZE]
        stored = await _retrying(lambda: store.read_chunks(client, chunks, ids, declared))
        planned = {}
        for chunk in stored.values():
            expected, _ = derive(chunk, public)
            if action(chunk.public, expected) != "consistent":
                planned[chunk.id] = expected
        failed, lines, written = await _apply(client, chunks, documents, list(stored.values()), planned,
                                              concurrency, pacer)
        retried = {str(i) for i in ids}
        counts["written"] += written
        _append(manifest, lines + [{"id": i, "status": "verified_on_retry" if UUID(i) in stored else "absent_on_retry"}
                                   for i in sorted(retried - {str(f) for f in failed})])
        state["retry"] = sorted((set(state["retry"]) - retried) | {str(f) for f in failed})
        save()

    while not state["done"] and (limit is None or examined < limit):
        size = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit - examined)
        after = UUID(state["after"]) if state["after"] else None
        page = await _retrying(lambda: store.read_chunk_page(client, chunks, after, size, declared))
        planned: dict[UUID, bool] = {}
        lines: list[dict[str, Any]] = []
        for chunk in page:
            expected, reason = derive(chunk, public)
            act = action(chunk.public, expected)
            counts["reasons"][reason] += 1
            counts[act] += 1
            counts["expected_true" if expected else "expected_false"] += 1
            counts["stale_true"] += chunk.public is True and not expected
            if reason in REPORTED:
                lines.append(_line(chunk, reason))
            if act != "consistent" and write:
                planned[chunk.id] = expected
        failed: list[UUID] = []
        if planned:
            failed, failed_lines, written = await _apply(client, chunks, documents, page, planned, concurrency, pacer)
            lines += failed_lines
            counts["written"] += written
        _append(manifest, lines)
        counts["examined"] += len(page)
        examined += len(page)
        state["retry"] = sorted(set(state["retry"]) | {str(f) for f in failed})
        if page:
            state["after"] = str(page[-1].id)
        state["done"] = len(page) < size
        save()
        seconds = max(time.monotonic() - started, 1e-3)
        progress(f"examined {counts['examined']} " + " ".join(f"{a} {counts[a]}" for a in ACTIONS)
                 + f" stale_true {counts['stale_true']} written {counts['written']} to retry {len(state['retry'])}"
                 f" after {state['after']} ({examined / seconds:.0f}/s this run)")

    if state["done"] and not state["retry"] and declared:
        state["search_counts"] = await compare_counts(client, chunks, counts)
    state["finished"] = _now()
    save()
    return summary(state, checkpoint, prop)


def summary(state: dict[str, Any], checkpoint: Path, prop: store.FlagProperty | None) -> dict[str, Any]:
    keys = ("endpoint", "chunks", "documents", "mode", "after", "done", "counts")
    return {key: state[key] for key in keys} | {
        "to_retry": len(state["retry"]), "flag_property": prop and vars(prop),
        "property_added": state.get("property_added"), "search_counts": state.get("search_counts"),
        "checkpoint": str(checkpoint), "manifest": str(manifest_path(checkpoint))}


def exit_code(result: dict[str, Any]) -> int:
    """0 only for a complete pass with matching search counts and, when checking, nothing to write;
    when writing, nothing left to retry."""
    if not result["done"] or result["to_retry"] or not (result["search_counts"] or {}).get("match"):
        return 1
    counts = result["counts"]
    if result["mode"] == "check" and (counts["set"] or counts["change"]):
        return 1
    return 0


# --- one document at a time (--document-ids, metadata_sync) ---


@dataclass
class DocumentSync:
    """The outcome of bringing one document's chunks to ``value``: ``verified`` when every chunk
    of the document stores it afterwards."""
    document_id: UUID
    value: bool
    written: int = 0
    chunks: int = 0
    verified: bool = False
    error: str | None = None


async def sync_document(client: WeaviateAsyncClient, chunks: str, document_id: UUID, value: bool, *,
                        concurrency: int = CONCURRENCY, rate: float | None = None) -> DocumentSync:
    """Set ``documentPublic`` to ``value`` on every chunk referencing the document, then verify
    that all of them store it. Never raises: a failure is returned as ``error`` (the writes so
    far are kept; running it again continues). The caller decides ``value`` and the order with
    the document's own write: ``false`` before the document stops being public, ``true`` only
    after it is verified ``public=true``."""
    result = DocumentSync(document_id, value)
    pacer = _Pacer(rate)
    try:
        for _ in range(DOCUMENT_ROUNDS):
            ids = await _retrying(lambda: store.document_chunks_differing(client, chunks, document_id, value,
                                                                          PAGE_SIZE))
            if not ids:
                break
            errors = await _write_values(client, chunks, dict.fromkeys(ids, value), concurrency, pacer)
            result.written += len(ids) - len(errors)
            if errors:
                result.error = f"{len(errors)} chunk writes not verified, e.g. {next(iter(errors.values()))}"
                return result
        else:
            result.error = f"chunks still differ after {DOCUMENT_ROUNDS} rounds"
            return result
        result.chunks = await _retrying(lambda: store.count_document_chunks(client, chunks, document_id))
        matching = await _retrying(lambda: store.count_document_chunks(client, chunks, document_id, value))
        result.verified = matching == result.chunks
        if not result.verified:
            result.error = f"{result.chunks - matching} of {result.chunks} chunks do not store {value}"
    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
    return result


async def run_documents(client: WeaviateAsyncClient, names: CollectionNames, document_ids: list[UUID], *,
                        checkpoint: Path, endpoint: str, write: bool, concurrency: int = CONCURRENCY,
                        rate: float | None = None, progress=_progress) -> dict[str, Any]:
    """Check or write the chunks of the listed documents (the module docstring's document mode)."""
    chunks, documents, prop = await _resolve(client, names)
    ids = list(dict.fromkeys(document_ids))
    listing = hashlib.sha256("\n".join(map(str, ids)).encode()).hexdigest()[:16]
    identity = {"endpoint": endpoint, "chunks": chunks, "documents": documents,
                "mode": "write-documents" if write else "check-documents", "document_list": listing}
    state = _load_state(checkpoint, identity, progress)
    state.setdefault("finished_documents", 0)
    state.setdefault("document_counts", {"public": 0, "not_public": 0, "missing_document": 0, "verified": 0,
                                         "mismatched": 0, "failed": 0, "written": 0})
    if write and prop is None:
        prop = await _declare(client, chunks, state, progress)
    counts = state["document_counts"]
    manifest = manifest_path(checkpoint)

    async def process(part: list[UUID]) -> list[str]:
        """Check or write the documents; the ids to retry."""
        public = await _retrying(lambda: store.read_document_public(client, documents, part))
        lines, retry = [], []
        for document_id in part:
            if document_id not in public:
                counts["missing_document"] += 1
                lines.append({"id": str(document_id), "status": "missing_document"})
                continue
            value = public[document_id] is True
            counts["public" if value else "not_public"] += 1
            if write:
                outcome = await sync_document(client, chunks, document_id, value, concurrency=concurrency, rate=rate)
                counts["written"] += outcome.written
            elif prop is None:
                outcome = DocumentSync(document_id, value, error=f"{store.PROPERTY} is not declared")
            else:
                total = await _retrying(lambda: store.count_document_chunks(client, chunks, document_id))
                matching = await _retrying(lambda: store.count_document_chunks(client, chunks, document_id, value))
                outcome = DocumentSync(document_id, value, chunks=total, verified=matching == total,
                                       error=None if matching == total else f"{total - matching} of {total} differ")
            if outcome.verified:
                counts["verified"] += 1
                continue
            counts["failed" if write else "mismatched"] += 1
            lines.append({"id": str(document_id), "status": "failed" if write else "mismatched",
                          "public": value, "reason": outcome.error})
            if write:
                retry.append(str(document_id))
        _append(manifest, lines)
        return retry

    def save() -> None:
        state["updated"] = _now()
        _write_json(checkpoint, state)
        progress(f"documents {state['finished_documents']} of {len(ids)} {counts}")

    retried = [UUID(i) for i in state["retry"]]
    for start in range(0, len(retried), PAGE_SIZE):
        part = retried[start:start + PAGE_SIZE]
        failed = await process(part)
        state["retry"] = sorted((set(state["retry"]) - {str(i) for i in part}) | set(failed))
        save()
    while state["finished_documents"] < len(ids):
        part = ids[state["finished_documents"]:state["finished_documents"] + PAGE_SIZE]
        failed = await process(part)
        state["retry"] = sorted(set(state["retry"]) | set(failed))
        state["finished_documents"] += len(part)
        save()
    state["done"] = True
    state["finished"] = _now()
    _write_json(checkpoint, state)
    return {key: state[key] for key in ("endpoint", "chunks", "documents", "mode", "done")} | {
        "documents": len(ids), "counts": counts, "to_retry": len(state["retry"]),
        "flag_property": prop and vars(prop), "property_added": state.get("property_added"),
        "checkpoint": str(checkpoint), "manifest": str(manifest)}


def documents_exit_code(result: dict[str, Any]) -> int:
    counts = result["counts"]
    return 1 if result["to_retry"] or counts["mismatched"] or counts["failed"] or counts["missing_document"] else 0


def read_document_ids(path: Path) -> list[UUID]:
    return [UUID(line.strip()) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", type=Path, metavar="CHECKPOINT",
                      help="compare the chunk flags with the documents (read-only); resumes a checkpoint")
    mode.add_argument("--write", type=Path, metavar="CHECKPOINT",
                      help="declare Chunks.documentPublic if missing and write the differing flags; resumes")
    p.add_argument("--confirm-endpoint", metavar="HOST:PORT", help="with --write: the configured Weaviate endpoint")
    p.add_argument("--document-ids", type=Path, metavar="FILE",
                   help="only the chunks of these documents (one UUID per line), through the document reference")
    p.add_argument("--limit", type=int, help="at most this many chunks in this run (full pass only)")
    p.add_argument("--concurrency", type=int, default=CONCURRENCY, help=f"parallel writes (default {CONCURRENCY})")
    p.add_argument("--rate", type=float, help="at most this many chunk writes per second (default: unlimited)")
    return p


async def _main(argv: list[str]) -> int:
    from semant_demo.adapters.weaviate.client import connect_weaviate
    from semant_demo.config import Config

    args = _parser().parse_args(argv)
    if args.document_ids and args.limit:
        print("--limit applies to the full pass only", file=sys.stderr)
        return 2
    config = Config()
    endpoint = f"{config.WEAVIATE_HOST}:{config.WEAVIATE_REST_PORT}"
    if args.write and args.confirm_endpoint != endpoint:
        print(f"Refusing to write: configured endpoint {endpoint}, --confirm-endpoint {args.confirm_endpoint}",
              file=sys.stderr)
        return 2
    print(f"Weaviate endpoint: {endpoint}", file=sys.stderr)
    client = await connect_weaviate(config, query_timeout=QUERY_TIMEOUT)
    try:
        checkpoint = args.write or args.check
        if args.document_ids:
            result = await run_documents(client, config.collectionNames, read_document_ids(args.document_ids),
                                         checkpoint=checkpoint, endpoint=endpoint, write=bool(args.write),
                                         concurrency=args.concurrency, rate=args.rate)
            print(json.dumps(result, indent=2))
            return documents_exit_code(result)
        result = await run(client, config.collectionNames, checkpoint=checkpoint, endpoint=endpoint,
                           write=bool(args.write), limit=args.limit, concurrency=args.concurrency, rate=args.rate)
        print(json.dumps(result, indent=2))
        return exit_code(result)
    except LookupError as e:
        print(e, file=sys.stderr)
        return 2
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
