"""Audit, and on explicit request delete, documents without text chunks (#281).

A document is a removal candidate only if it exists, no ``Chunks.document`` reference
points to it (a successful one-object lookup finds none and an aggregate count agrees: two
independent queries), no other reference in the schema targets it, and it was created at
least ``--min-age-hours`` (default 24) before the audit, so documents whose chunks are still
being ingested are left alone. A lookup that fails after retries makes the document
``unknown_or_error``, never a candidate. Membership in user collections does not protect a
document: deleting it removes its own ``collection`` references, so it leaves the collections'
document lists and counts; the collections, tags, spans and other user data stay.

Audit (read-only, the default)::

    python -m semant_demo.maintenance.document_cleanup --audit audit.json \\
        [--min-age-hours 24] [--limit N] [--concurrency 8] [--rate DOCS_PER_SECOND]

The checkpoint (JSON, replaced atomically after each page of 100 documents) holds the
endpoint, the resolved collection names, the reference schema, the cursor and the counts
(``has_chunks``, ``no_chunks_unreferenced`` and ``no_chunks_collection_member`` - both
removable -, ``unknown_or_error``, ``excluded_recent``, ``excluded_other_reference``); running
the same command again resumes it. Every document but those with chunks gets a line in
``audit.json.candidates.jsonl`` (id, category, creation time, collection ids): the manifest of
original UUIDs for a later reimport. The summary reports counts, percentages, affected
collection memberships (counts only, no names) and example UUIDs. Before the first page the
lookup is validated: documents referenced by a sample of chunks must be found to have chunks.
The total chunk count is read before and after; a change marks the audit unusable for
deletion (ingestion ran).

Delete the audited candidates (back up first)::

    python -m semant_demo.maintenance.document_cleanup --delete audit.json \\
        --confirm-endpoint localhost:8080 --backup-id BACKUP [--limit N] [--concurrency 8] [--rate N]

It refuses to start unless ``--confirm-endpoint`` and the audit's endpoint equal the
configured one, the audit finished with the same collections and reference schema, the total
chunk count still equals the audit's (checked again before every batch), and ``BACKUP`` is a
successful ``backup-filesystem`` backup holding the documents, chunks and user collections.
Immediately before each deletion it reads the document again (an absent one is
``already_absent``), skips it if it was created after the backup started, if a chunk or another
reference now points to it, or if a lookup fails; then deletes it and reads it back. A chunk
that appears between the check and the deletion is reported (``chunk_appeared``), not undone.
Progress goes to ``audit.json.delete.json`` (resumed by running the same command; failed and
unverified ids are retried first) and one line per document to ``audit.json.delete.jsonl``.
After the last batch, every affected user collection's document list is checked not to
contain a deleted document and its document count is compared with the count before. Exit
code 1 while ids remain to retry or the run stopped. Collections and schema are never changed.

A deleted document comes back by importing it again from its source (the JSON metadata and
JSONL chunks, ``weaviate_utils/db_insert_jsonl.py``) with the same UUID, listed in the manifest;
collection memberships are not restored (``collection_ids`` in the manifest records them).

The Weaviate endpoint comes from ``WEAVIATE_HOST`` / ``WEAVIATE_REST_PORT`` /
``WEAVIATE_GRPC_PORT``.
"""
import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from weaviate import WeaviateAsyncClient

from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.adapters.weaviate import document_cleanup as store

PAGE_SIZE = 100
CONCURRENCY = 8
ATTEMPTS = 3
"""Tries of one lookup before the document is ``unknown_or_error`` (or a page read stops the run)."""
BACKOFF = 2.0
PROBE_CHUNKS = 100
EXAMPLES = 5
CHUNK_LINK = "document"
COLLECTION_LINK = "collection"
CANDIDATES = ("no_chunks_unreferenced", "no_chunks_collection_member")
CATEGORIES = ("has_chunks", *CANDIDATES, "unknown_or_error", "excluded_recent", "excluded_other_reference")
OUTCOMES = ("deleted", "already_absent", "skipped_has_chunks", "skipped_other_reference", "skipped_not_in_backup",
            "skipped_error", "failed")
RETRIED = ("skipped_error", "failed")
"""Outcomes kept in the retry list: the lookup failed, or the deletion is uncertain."""


@dataclass(frozen=True)
class Targets:
    """Resolved collection names and the references, other than ``Chunks.document``, to documents."""
    documents: str
    chunks: str
    user_collections: str
    dependencies: tuple[tuple[str, str], ...]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _write_json(path: Path, data: Any) -> None:
    """Replace the file atomically, so a crash leaves the previous checkpoint."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _append(path: Path, lines: list[dict[str, Any]]) -> None:
    with path.open("a", encoding="utf-8") as file:
        for line in lines:
            file.write(json.dumps(line) + "\n")


def candidates_path(checkpoint: Path) -> Path:
    return checkpoint.with_name(checkpoint.name + ".candidates.jsonl")


def read_lines(path: Path) -> dict[str, dict[str, Any]]:
    """JSON lines by id; a later line for an id (a page redone after a crash) replaces earlier ones."""
    if not path.exists():
        return {}
    lines = (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return {line["id"]: line for line in lines}


async def resolve_targets(client: WeaviateAsyncClient, names: CollectionNames
                          ) -> tuple[Targets, dict[str, dict[str, list[str]]]]:
    """Raises ``LookupError`` if a collection is missing or ``Chunks.document`` / ``Documents.collection``
    do not target the expected collections."""
    documents, chunks, user_collections = [await store.resolve_collection(client, name) for name in (
        names.document_collection_name, names.chunks_collection_name, names.user_collection_name)]
    schema = await store.reference_schema(client)
    missing = [name for name in (documents, chunks, user_collections) if name not in schema]
    if missing:
        raise LookupError(f"Missing collections: {', '.join(missing)}")
    if schema[chunks].get(CHUNK_LINK) != [documents]:
        raise LookupError(f"{chunks}.{CHUNK_LINK} targets {schema[chunks].get(CHUNK_LINK)}, not [{documents}]")
    if schema[documents].get(COLLECTION_LINK, [user_collections]) != [user_collections]:
        raise LookupError(f"{documents}.{COLLECTION_LINK} targets {schema[documents][COLLECTION_LINK]}, "
                          f"not [{user_collections}]")
    targeting = {documents, names.document_collection_name}
    dependencies = tuple(sorted((collection, link) for collection, refs in schema.items()
                                for link, target in refs.items()
                                if targeting & set(target) and (collection, link) != (chunks, CHUNK_LINK)))
    return Targets(documents, chunks, user_collections, dependencies), schema


def _identity(endpoint: str, targets: Targets, schema: dict) -> dict[str, Any]:
    fingerprint = hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()[:16]
    return {"endpoint": endpoint,
            "collections": {"documents": targets.documents, "chunks": targets.chunks,
                            "user_collections": targets.user_collections},
            "dependencies": [f"{c}.{link}" for c, link in targets.dependencies], "reference_schema": fingerprint}


async def _retrying(call):
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return await call()
        except Exception:
            if attempt == ATTEMPTS:
                raise
            await asyncio.sleep(BACKOFF * attempt)


async def has_chunks(client: WeaviateAsyncClient, targets: Targets, document_id: UUID) -> bool:
    """Raises if a lookup fails or the two lookups disagree: no answer is not "no chunks"."""
    if await store.any_referencing(client, targets.chunks, CHUNK_LINK, document_id):
        return True
    count = await store.count_referencing(client, targets.chunks, CHUNK_LINK, document_id)
    if count:
        raise LookupError(f"chunk lookups disagree: none found, {count} counted")
    return False


async def other_references(client: WeaviateAsyncClient, targets: Targets, document_id: UUID) -> list[str]:
    return [f"{c}.{link}" for c, link in targets.dependencies
            if await store.any_referencing(client, c, link, document_id)]


async def classify(client: WeaviateAsyncClient, targets: Targets, document: store.DocumentLinks,
                   created_before: datetime) -> dict[str, Any]:
    entry: dict[str, Any] = {"id": str(document.id)}
    try:
        if await _retrying(lambda: has_chunks(client, targets, document.id)):
            return {**entry, "category": "has_chunks"}
        dependencies = await _retrying(lambda: other_references(client, targets, document.id))
    except Exception as e:
        return {**entry, "category": "unknown_or_error", "reason": f"{type(e).__name__}: {e}"}
    entry |= {"created": document.created and document.created.isoformat(),
              "collection_ids": [str(i) for i in document.collection_ids]}
    if dependencies:
        return {**entry, "category": "excluded_other_reference", "references": dependencies}
    if document.created is None or document.created > created_before:
        return {**entry, "category": "excluded_recent"}
    return {**entry, "category": "no_chunks_collection_member" if document.collection_ids else "no_chunks_unreferenced"}


async def probe(client: WeaviateAsyncClient, targets: Targets) -> dict[str, int]:
    """Check the lookup on documents known to have chunks (those a sample of chunks references).
    Raises ``LookupError`` if any is not found to have chunks."""
    referenced = await store.sample_referenced(client, targets.chunks, CHUNK_LINK, PROBE_CHUNKS)
    missed = [i for i in referenced if not await has_chunks(client, targets, i)]
    if missed:
        raise LookupError(f"The chunk lookup missed documents that chunks reference: {missed[:EXAMPLES]}")
    return {"documents_checked": len(referenced)}


async def _pace(started: float, items: int, rate: float | None) -> None:
    if rate:
        await asyncio.sleep(max(0.0, items / rate - (time.monotonic() - started)))


def _progress(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


async def _gather(items, concurrency: int, call) -> list:
    semaphore = asyncio.Semaphore(concurrency)

    async def one(item):
        async with semaphore:
            return await call(item)
    return await asyncio.gather(*(one(item) for item in items))


def _membership_counts(state: dict[str, Any]) -> dict[str, int]:
    members = state["members"]
    return {"candidates_in_collections": members["documents"], "memberships": sum(members["collections"].values()),
            "candidates_in_several_collections": members["in_several"],
            "affected_collections": len(members["collections"])}


def audit_summary(state: dict[str, Any], checkpoint: Path) -> dict[str, Any]:
    counts = state["counts"]
    examined = sum(counts.values())
    removable = sum(counts[c] for c in CANDIDATES)
    return {key: state[key] for key in ("endpoint", "collections", "dependencies", "after", "done",
                                        "created_before", "chunk_total_start", "document_total_start")} | {
        "chunk_total_end": state.get("chunk_total_end"),
        "chunks_changed_during_audit": state.get("chunks_changed_during_audit"),
        "examined": examined, "counts": counts, "removable": removable,
        "removable_percent": round(100 * removable / examined, 2) if examined else None,
        "collection_memberships": _membership_counts(state) | {
            "missing_collections": state.get("missing_collections")},
        "examples": state["examples"], "probe": state["probe"],
        "checkpoint": str(checkpoint), "candidates": str(candidates_path(checkpoint))}


async def audit(client: WeaviateAsyncClient, names: CollectionNames, *, checkpoint: Path, endpoint: str,
                min_age: timedelta = timedelta(hours=24), limit: int | None = None,
                concurrency: int = CONCURRENCY, rate: float | None = None, progress=_progress) -> dict[str, Any]:
    """Classify every document (read-only), page by page; resumes an existing checkpoint.
    Raises ``LookupError`` for an unexpected schema, a failed lookup probe or a checkpoint
    of another endpoint, collection or reference schema."""
    targets, schema = await resolve_targets(client, names)
    identity = _identity(endpoint, targets, schema)
    lines = candidates_path(checkpoint)
    if checkpoint.exists():
        state = json.loads(checkpoint.read_text(encoding="utf-8"))
        differing = sorted(key for key, value in identity.items() if state.get(key) != value)
        if differing:
            raise LookupError(f"The checkpoint {checkpoint} has a different {', '.join(differing)}; use a new one")
        progress(f"Resuming {checkpoint} after {state['after']}")
    else:
        checked = await probe(client, targets)
        started = _now()
        state = {**identity, "mode": "audit", "started": started.isoformat(),
                 "created_before": (started - min_age).isoformat(), "probe": checked,
                 "chunk_total_start": await store.total_count(client, targets.chunks),
                 "document_total_start": await store.total_count(client, targets.documents),
                 "after": None, "done": False, "counts": dict.fromkeys(CATEGORIES, 0), "examples": {},
                 "members": {"documents": 0, "in_several": 0, "collections": {}}}
        lines.write_text("", encoding="utf-8")
        _write_json(checkpoint, state)
    created_before = datetime.fromisoformat(state["created_before"])

    examined = 0
    while not state["done"] and (limit is None or examined < limit):
        started = time.monotonic()
        size = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit - examined)
        cursor = UUID(state["after"]) if state["after"] else None
        page = await _retrying(lambda: store.read_document_links_page(
            client, targets.documents, COLLECTION_LINK, cursor, size))
        if not page:
            state["done"] = True
            break
        entries = await _gather(page, concurrency, lambda d: classify(client, targets, d, created_before))
        _append(lines, [e for e in entries if e["category"] != "has_chunks"])
        for entry in entries:
            category = entry["category"]
            state["counts"][category] += 1
            examples = state["examples"].setdefault(category, [])
            if len(examples) < EXAMPLES:
                examples.append(entry["id"])
            if category == "no_chunks_collection_member":
                members = state["members"]
                members["documents"] += 1
                members["in_several"] += len(entry["collection_ids"]) > 1
                for collection_id in entry["collection_ids"]:
                    members["collections"][collection_id] = members["collections"].get(collection_id, 0) + 1
        examined += len(page)
        state["after"] = str(page[-1].id)
        state["done"] = len(page) < size
        state["updated"] = _now().isoformat()
        _write_json(checkpoint, state)
        counts = state["counts"]
        progress(f"examined {sum(counts.values())} has_chunks {counts['has_chunks']} removable "
                 f"{sum(counts[c] for c in CANDIDATES)} unknown {counts['unknown_or_error']} after {state['after']}")
        await _pace(started, len(page), rate)

    if state["done"] and "chunk_total_end" not in state:
        state["chunk_total_end"] = await store.total_count(client, targets.chunks)
        state["chunks_changed_during_audit"] = state["chunk_total_end"] != state["chunk_total_start"]
        affected = [UUID(i) for i in state["members"]["collections"]]
        found = set()
        for start in range(0, len(affected), PAGE_SIZE):
            found |= await store.existing_ids(client, targets.user_collections, affected[start:start + PAGE_SIZE])
        state["missing_collections"] = len(affected) - len(found)
        state["finished"] = _now().isoformat()
    _write_json(checkpoint, state)
    return audit_summary(state, checkpoint)


def audit_exit_code(summary: dict[str, Any]) -> int:
    """1 if any document is ``unknown_or_error`` or ingestion changed the chunks during the audit."""
    return 1 if summary["counts"]["unknown_or_error"] or summary["chunks_changed_during_audit"] else 0


def delete_paths(audit_checkpoint: Path) -> tuple[Path, Path]:
    return (audit_checkpoint.with_name(audit_checkpoint.name + ".delete.json"),
            audit_checkpoint.with_name(audit_checkpoint.name + ".delete.jsonl"))


async def check_backup(client: WeaviateAsyncClient, targets: Targets, backup_id: str) -> store.Backup:
    """Raises ``LookupError`` unless ``backup_id`` is a successful filesystem backup holding the
    documents, chunks and user collections."""
    try:
        backups = await store.filesystem_backups(client)
    except Exception as e:
        raise LookupError(f"Cannot list filesystem backups ({type(e).__name__}: {e})") from e
    backup = next((b for b in backups if b.id == backup_id), None)
    if backup is None or backup.status != "SUCCESS" or backup.started is None:
        raise LookupError(f"No successful filesystem backup {backup_id!r}")
    missing = {targets.documents, targets.chunks, targets.user_collections} - set(backup.collections)
    if missing:
        raise LookupError(f"Backup {backup_id} does not hold {', '.join(sorted(missing))}")
    return backup


async def delete_one(client: WeaviateAsyncClient, targets: Targets, document_id: UUID,
                     backup_started: datetime) -> dict[str, Any]:
    """Recheck one candidate and delete it; the outcome line (``OUTCOMES``)."""
    line: dict[str, Any] = {"id": str(document_id)}
    try:
        document = (await _retrying(lambda: store.read_document_links(
            client, targets.documents, COLLECTION_LINK, [document_id]))).get(document_id)
        if document is None:
            return {**line, "outcome": "already_absent"}
        if document.created is None or document.created >= backup_started:
            return {**line, "outcome": "skipped_not_in_backup"}
        if await _retrying(lambda: has_chunks(client, targets, document_id)):
            return {**line, "outcome": "skipped_has_chunks"}
        dependencies = await _retrying(lambda: other_references(client, targets, document_id))
        if dependencies:
            return {**line, "outcome": "skipped_other_reference", "references": dependencies}
    except Exception as e:
        return {**line, "outcome": "skipped_error", "reason": f"{type(e).__name__}: {e}"}
    line["collection_ids"] = [str(i) for i in document.collection_ids]
    try:
        await store.delete_object(client, targets.documents, document_id)
    except Exception as e:  # the deletion may or may not have happened; a retry reads the document again
        return {**line, "outcome": "failed", "reason": f"{type(e).__name__}: {e}"}
    try:
        remaining = await _retrying(lambda: store.existing_ids(client, targets.documents, [document_id]))
    except Exception as e:
        return {**line, "outcome": "failed", "reason": f"not verified: {type(e).__name__}: {e}"}
    if remaining:
        return {**line, "outcome": "failed", "reason": "still present after deletion"}
    line["outcome"] = "deleted"
    try:  # not atomic with the check above: report a chunk that appeared meanwhile, do not undo
        if await store.any_referencing(client, targets.chunks, CHUNK_LINK, document_id):
            line["chunk_appeared"] = True
    except Exception as e:
        line["chunk_check_error"] = f"{type(e).__name__}: {e}"
    return line


async def _verify_collections(client: WeaviateAsyncClient, targets: Targets, state: dict[str, Any],
                              log: Path) -> dict[str, Any]:
    """Affected collections: none lists a deleted document; document count = before - removed."""
    deleted_by_collection: dict[str, list[UUID]] = {}
    for line in read_lines(log).values():
        if line["outcome"] == "deleted":
            for collection_id in line["collection_ids"]:
                deleted_by_collection.setdefault(collection_id, []).append(UUID(line["id"]))
    ids = [UUID(i) for i in deleted_by_collection]
    existing: set[UUID] = set()
    for start in range(0, len(ids), PAGE_SIZE):
        existing |= await store.existing_ids(client, targets.user_collections, ids[start:start + PAGE_SIZE])
    result = {"affected_collections": len(ids), "missing_collections": len(ids) - len(existing),
              "still_listing_deleted": 0, "count_matches": 0, "count_differs": 0, "count_unknown": 0}
    for collection_id, deleted in deleted_by_collection.items():
        if UUID(collection_id) not in existing:
            continue
        for start in range(0, len(deleted), PAGE_SIZE):
            result["still_listing_deleted"] += len(await store.referencing_among(
                client, targets.documents, COLLECTION_LINK, UUID(collection_id), deleted[start:start + PAGE_SIZE]))
        before = state["collection_counts_before"].get(collection_id)
        after = await store.count_referencing(client, targets.documents, COLLECTION_LINK, UUID(collection_id))
        if before is None:
            result["count_unknown"] += 1
        else:
            result["count_matches" if after == before - len(deleted) else "count_differs"] += 1
    return result


def delete_summary(state: dict[str, Any], state_path: Path, log: Path) -> dict[str, Any]:
    return {key: state.get(key) for key in ("endpoint", "collections", "backup_id", "candidates", "position", "done",
                                            "stopped", "counts", "chunk_appeared", "collections_check")} | {
        "to_retry": len(state["retry"]), "removed_memberships": sum(state["memberships"].values()),
        "affected_collections": len(state["memberships"]), "state": str(state_path), "log": str(log)}


async def delete(client: WeaviateAsyncClient, names: CollectionNames, *, audit_checkpoint: Path,
                 endpoint: str, backup_id: str, limit: int | None = None, concurrency: int = CONCURRENCY,
                 rate: float | None = None, progress=_progress) -> dict[str, Any]:
    """Delete the audit's removable documents after rechecking each; resumable.
    Raises ``LookupError`` before deleting anything if a precondition fails."""
    audited = json.loads(audit_checkpoint.read_text(encoding="utf-8"))
    if audited.get("mode") != "audit" or not audited.get("done") or "chunk_total_end" not in audited:
        raise LookupError(f"{audit_checkpoint} is not a finished audit")
    targets, schema = await resolve_targets(client, names)
    identity = _identity(endpoint, targets, schema)
    differing = sorted(key for key, value in identity.items() if audited.get(key) != value)
    if differing:
        raise LookupError(f"The audit has a different {', '.join(differing)}; audit this endpoint again")
    if audited["chunks_changed_during_audit"]:
        raise LookupError("The chunk count changed during the audit (ingestion?); audit again")
    backup = await check_backup(client, targets, backup_id)

    async def chunks_unchanged() -> bool:
        return await store.total_count(client, targets.chunks) == audited["chunk_total_end"]
    if not await chunks_unchanged():
        raise LookupError("The chunk count changed since the audit (ingestion?); audit again")

    candidates = read_lines(candidates_path(audit_checkpoint))
    ids = sorted(i for i, line in candidates.items() if line["category"] in CANDIDATES)
    state_path, log = delete_paths(audit_checkpoint)
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if (state["audit_started"], state["backup_id"]) != (audited["started"], backup_id):
            raise LookupError(f"{state_path} belongs to another audit or backup")
        progress(f"Resuming {state_path}: {state['position']} of {len(ids)}, {len(state['retry'])} to retry")
    else:
        state = {**identity, "audit_started": audited["started"], "backup_id": backup_id,
                 "backup_started": backup.started.isoformat(), "started": _now().isoformat(),
                 "candidates": len(ids), "position": 0, "retry": {}, "done": False,
                 "counts": dict.fromkeys(OUTCOMES, 0), "chunk_appeared": [], "memberships": {},
                 "collection_counts_before": {}}
        _write_json(state_path, state)
    state.pop("stopped", None)
    backup_started = datetime.fromisoformat(state["backup_started"])

    async def run(batch: list[str], retried: bool) -> bool:
        started = time.monotonic()
        if not await chunks_unchanged():
            state["stopped"] = "the chunk count changed since the audit (ingestion?); audit again"
            return False
        known = {c for i in batch for c in candidates[i].get("collection_ids", [])}
        for collection_id in sorted(known - set(state["collection_counts_before"])):
            state["collection_counts_before"][collection_id] = await store.count_referencing(
                client, targets.documents, COLLECTION_LINK, UUID(collection_id))
        outcomes = await _gather(batch, concurrency,
                                 lambda i: delete_one(client, targets, UUID(i), backup_started))
        _append(log, outcomes)
        for line in outcomes:
            if retried:  # counted at its first attempt; the new outcome replaces it
                state["counts"][state["retry"].pop(line["id"])] -= 1
            state["counts"][line["outcome"]] += 1
            if line["outcome"] in RETRIED:
                state["retry"][line["id"]] = line["outcome"]
            if line["outcome"] == "deleted":
                for collection_id in line["collection_ids"]:
                    state["memberships"][collection_id] = state["memberships"].get(collection_id, 0) + 1
                if line.get("chunk_appeared"):
                    state["chunk_appeared"].append(line["id"])
        state["updated"] = _now().isoformat()
        _write_json(state_path, state)
        counts = state["counts"]
        progress(f"position {state['position']}/{len(ids)} deleted {counts['deleted']} already_absent "
                 f"{counts['already_absent']} skipped {sum(v for k, v in counts.items() if k.startswith('skipped'))} "
                 f"failed {counts['failed']} to retry {len(state['retry'])}")
        await _pace(started, len(batch), rate)
        return True

    processed = 0
    pending = sorted(state["retry"])  # a snapshot: run() rewrites the retry list
    for start in range(0, len(pending), PAGE_SIZE):
        if not await run(pending[start:start + PAGE_SIZE], retried=True):
            break
    while "stopped" not in state and state["position"] < len(ids) and (limit is None or processed < limit):
        size = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit - processed)
        batch = ids[state["position"]:state["position"] + size]
        if not await run(batch, retried=False):
            break
        state["position"] += len(batch)
        processed += len(batch)
        _write_json(state_path, state)

    state["done"] = state["position"] == len(ids) and "stopped" not in state
    if state["done"]:
        state["collections_check"] = await _verify_collections(client, targets, state, log)
        state["finished"] = _now().isoformat()
    _write_json(state_path, state)
    return delete_summary(state, state_path, log)


def delete_exit_code(summary: dict[str, Any]) -> int:
    """0 only when every candidate was processed, nothing remains to retry and the run did not stop."""
    return 0 if summary["done"] and not summary["to_retry"] and not summary["stopped"] else 1


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--audit", type=Path, metavar="CHECKPOINT",
                      help="classify the documents (read-only); an existing checkpoint is resumed")
    mode.add_argument("--delete", type=Path, metavar="AUDIT",
                      help="delete the removable documents of this finished audit checkpoint")
    p.add_argument("--confirm-endpoint", metavar="HOST:PORT", help="with --delete: the configured Weaviate endpoint")
    p.add_argument("--backup-id", help="with --delete: a successful filesystem backup taken before deleting")
    p.add_argument("--min-age-hours", type=float, default=24.0,
                   help="with --audit: documents created more recently are excluded (default 24)")
    p.add_argument("--limit", type=int, help="at most this many documents in this run")
    p.add_argument("--concurrency", type=int, default=CONCURRENCY, help="parallel lookups (default 8)")
    p.add_argument("--rate", type=float, help="at most this many documents per second")
    return p


async def _main(argv: list[str]) -> int:
    from semant_demo.adapters.weaviate.client import connect_weaviate
    from semant_demo.config import Config

    args = _parser().parse_args(argv)
    config = Config()
    endpoint = f"{config.WEAVIATE_HOST}:{config.WEAVIATE_REST_PORT}"
    if args.delete:
        if not args.backup_id:
            print("--delete needs --backup-id", file=sys.stderr)
            return 2
        if args.confirm_endpoint != endpoint:
            print(f"Refusing to delete: configured endpoint {endpoint}, --confirm-endpoint {args.confirm_endpoint}",
                  file=sys.stderr)
            return 2
    print(f"Weaviate endpoint: {endpoint}", file=sys.stderr)
    client = await connect_weaviate(config)
    try:
        if args.delete:
            summary = await delete(client, config.collectionNames, audit_checkpoint=args.delete, endpoint=endpoint,
                                   backup_id=args.backup_id, limit=args.limit, concurrency=args.concurrency,
                                   rate=args.rate)
            print(json.dumps(summary, indent=2))
            return delete_exit_code(summary)
        summary = await audit(client, config.collectionNames, checkpoint=args.audit, endpoint=endpoint,
                              min_age=timedelta(hours=args.min_age_hours), limit=args.limit,
                              concurrency=args.concurrency, rate=args.rate)
        print(json.dumps(summary, indent=2))
        return audit_exit_code(summary)
    except LookupError as e:
        print(e, file=sys.stderr)
        return 2
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
