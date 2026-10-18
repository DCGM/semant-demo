"""Copy span annotations into the multi-tenant annotation store, and verify the copy (#327).

The application reads and writes spans in ``Annotation``, one tenant per user collection
(``adapters/weaviate/spans.py``). Existing spans live in the legacy single-tenant ``Span``
collection; this operator-run command copies them, keeping each span's UUID, tag, anchor
chunk, offsets, type and AI metadata. The legacy collection is only read and stays as it
is (for rollback). Nothing here runs at startup or during requests. The cutover procedure
(write pause, backup, rollback) is in docs/DATA_MAINTENANCE.md.

Backfill, a dry run unless ``--execute`` (``STATE`` is the checkpoint and the report)::

    python -m semant_demo.maintenance.annotation_migration backfill --state dry.json
    python -m semant_demo.maintenance.annotation_migration backfill --state run.json --execute \\
        --confirm-endpoint localhost:8080 (--backup-id BACKUP | --offline-backup NOTE)

Verify the copy, and after the cutover list what the new store has that the legacy one
has not (the reconciliation report a rollback needs)::

    python -m semant_demo.maintenance.annotation_migration verify --report verify.json

Each legacy span is validated before it is copied; invalid ones are skipped and counted
by reason, never assigned to a guessed collection: no or several tag references, a
missing tag, a tag with no or several collections, a missing collection, no or several
chunk references, a missing chunk, a chunk without a document, an unknown type or
offsets that are not ``0 <= start < end``. Weaviate 1.40 does not return references to
deleted objects, so the spans of a deleted tag or chunk count as having no reference
and a tag of a deleted collection as having none. Offsets are not re-checked against
the text.
A valid span goes to the tenant of its tag's collection; spans whose anchor chunk is no
longer in that collection are copied and counted (``anchor_not_in_collection``), as the
application keeps them too.

Backfill reads the legacy spans in UUID order, ``--batch-size`` at a time, and after each
batch saves the cursor and the counts to ``STATE``; running the same command again
resumes there. The state names the endpoint, both collections and the mode, and a run
with other ones is refused. Before inserting, each batch reads which ids its tenant
already holds: an identical copy is ``already_present``, a different one a ``conflict``
that is reported and never overwritten (a batch insert would replace it), so repeating a
run, also after a timeout, is safe. ``--execute`` creates the annotation collection when
it is missing (and refuses one without multi-tenancy) and the tenants it needs, and
refuses to run unless ``--confirm-endpoint`` equals the configured endpoint and there is
a backup: ``--backup-id``, a successful ``backup-filesystem`` backup holding the legacy
spans, tags, chunks and user collections (checked), or ``--offline-backup``, the
operator's note (e.g. the path) of an offline copy of the data directory taken with
Weaviate stopped (not checked; the deployed compose files do not enable the backup
module). The backup is recorded in ``STATE``. Exit status 1 when a span failed or
conflicted.

Verify compares every valid legacy span with its tenant's copy (``missing``,
``different``) and lists the tenants' spans without a legacy original (``target_only``)
and tenants of no existing collection (``orphan_tenants``). Before the cutover all
of these must be empty; after it, ``different`` and ``target_only`` are the writes made
in the new store. Reading a tenant activates it. Exit status 1 when anything differs.
"""
import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from semant_demo.adapters.weaviate.annotation_migration import (
    LegacySpan, MigrationStore, SourceChunk, TargetSpan, TARGET_PROPERTIES,
)
from semant_demo.adapters.weaviate.spans import tenant_name
from semant_demo.features.annotations.schemas import SpanType

BATCH_SIZE = 200
SPAN_TYPES = {t.value for t in SpanType}
# Kept in the state file at most; the counts stay complete.
MAX_LISTED = 10_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Validation and conversion ────────────────────────────────────────────


def target_properties(span: LegacySpan, document_id: UUID) -> dict:
    """The annotation record of a valid legacy span."""
    p = span.properties
    properties: dict[str, Any] = {"tagId": span.tag_ids[0], "chunkId": span.chunk_ids[0], "documentId": document_id,
                                  "start": p["start"], "end": p["end"], "type": p["type"]}
    if p.get("reason") is not None:
        properties["reason"] = p["reason"]
    if p.get("confidence") is not None:
        properties["confidence"] = float(p["confidence"])
    return properties


def _normalized(properties: dict) -> dict:
    """Stored values comparable across reads (UUIDs as strings, absent = None)."""
    result = {}
    for key in TARGET_PROPERTIES:
        value = properties.get(key)
        if key in ("tagId", "chunkId", "documentId") and value is not None:
            value = str(UUID(str(value)))
        elif key == "confidence" and value is not None:
            value = float(value)
        result[key] = value
    return result


def same_record(expected: dict, stored: TargetSpan) -> bool:
    return _normalized(expected) == _normalized(stored.properties)


def _is_offset(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class Lookups:
    """Tags, collections and chunks referenced by the spans, read per batch and cached."""

    def __init__(self, store: MigrationStore):
        self.store = store
        self.tag_owners: dict[UUID, list[UUID] | None] = {}
        self.collections: dict[UUID, bool] = {}

    async def load(self, spans: list[LegacySpan]) -> dict[UUID, SourceChunk]:
        tags = list({t for s in spans for t in s.tag_ids} - self.tag_owners.keys())
        found = await self.store.tag_owners(tags)
        for t in tags:
            self.tag_owners[t] = found.get(t)
        owners = list({c for o in self.tag_owners.values() if o for c in o} - self.collections.keys())
        existing = await self.store.existing_collections(owners)
        for c in owners:
            self.collections[c] = c in existing
        return await self.store.chunks(list({c for s in spans for c in s.chunk_ids}))


def classify(span: LegacySpan, lookups: Lookups, chunks: dict[UUID, SourceChunk]
             ) -> tuple[str | None, UUID | None, UUID | None]:
    """``(reason, collection, document)``: a skip reason, or ``None`` and the span's tenant
    collection and document."""
    p = span.properties
    if p.get("type") not in SPAN_TYPES:
        return "invalid_type", None, None
    if not (_is_offset(p.get("start")) and _is_offset(p.get("end")) and 0 <= p["start"] < p["end"]):
        return "invalid_offsets", None, None
    if not span.tag_ids:
        return "no_tag_reference", None, None
    if len(span.tag_ids) > 1:
        return "several_tag_references", None, None
    owners = lookups.tag_owners.get(span.tag_ids[0])
    if owners is None:
        return "tag_missing", None, None
    if not owners:
        return "tag_without_collection", None, None
    if len(set(owners)) > 1:
        return "tag_in_several_collections", None, None
    collection = owners[0]
    if not lookups.collections.get(collection):
        return "collection_missing", None, None
    if not span.chunk_ids:
        return "no_chunk_reference", None, None
    if len(span.chunk_ids) > 1:
        return "several_chunk_references", None, None
    chunk = chunks.get(span.chunk_ids[0])
    if chunk is None:
        return "chunk_missing", None, None
    if len(set(chunk.document_ids)) != 1:
        return "chunk_without_document", None, None
    return None, collection, chunk.document_ids[0]


# ── State ────────────────────────────────────────────────────────────────


def new_state(endpoint: str, source: str, target: str, execute: bool, batch_size: int) -> dict:
    return {
        "endpoint": endpoint, "source": source, "target": target, "execute": execute, "batch_size": batch_size,
        "started": _now(), "updated": None, "done": False, "after": None, "batches": 0,
        "legacy_total": None, "tags": None,
        "counts": Counter(), "collections": {},
        "skipped": [], "conflicts": [], "failed": [],
    }


def load_state(path: Path, endpoint: str, source: str, target: str, execute: bool) -> dict | None:
    if not path.exists():
        return None
    state = json.loads(path.read_text(encoding="utf-8"))
    expected = {"endpoint": endpoint, "source": source, "target": target, "execute": execute}
    found = {k: state.get(k) for k in expected}
    if found != expected:
        raise LookupError(f"{path} belongs to another run ({found}); expected {expected}. Use a new --state file.")
    state["counts"] = Counter(state["counts"])
    return state


def save_state(path: Path, state: dict) -> None:
    state["updated"] = _now()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True, default=str), encoding="utf-8")
    tmp.replace(path)


def _listed(state: dict, key: str, item: dict) -> None:
    if len(state[key]) < MAX_LISTED:
        state[key].append(item)


def _bump(state: dict, collection_id: UUID, key: str, n: int = 1) -> None:
    per = state["collections"].setdefault(str(collection_id), {})
    per[key] = per.get(key, 0) + n
    state["counts"][key] += n


def tag_inventory(owners: dict[UUID, list[UUID]]) -> dict:
    """Tags by number of owning collections; the ids of tags without exactly one."""
    none = sorted(str(t) for t, o in owners.items() if not o)
    several = sorted(str(t) for t, o in owners.items() if len(set(o)) > 1)
    return {"total": len(owners), "single_collection": len(owners) - len(none) - len(several),
            "without_collection": none, "several_collections": several}


# ── Backfill ─────────────────────────────────────────────────────────────


async def backfill_batch(store: MigrationStore, lookups: Lookups, state: dict, spans: list[LegacySpan],
                         *, execute: bool, activity=None) -> None:
    chunks = await lookups.load(spans)
    by_collection: dict[UUID, list[tuple[LegacySpan, dict]]] = {}
    for span in spans:
        state["counts"]["read"] += 1
        reason, collection, document = classify(span, lookups, chunks)
        if reason is not None:
            state["counts"][f"skipped:{reason}"] += 1
            _listed(state, "skipped", {"id": str(span.id), "reason": reason})
            continue
        if collection not in chunks[span.chunk_ids[0]].collection_ids:
            _bump(state, collection, "anchor_not_in_collection")
        by_collection.setdefault(collection, []).append((span, target_properties(span, document)))

    for collection, items in by_collection.items():
        existing = await store.target_spans(collection, [s.id for s, _ in items]) if state["target_exists"] else {}
        missing: list[tuple[UUID, dict, UUID]] = []
        for span, properties in items:
            stored = existing.get(span.id)
            if stored is None:
                missing.append((span.id, properties, span.chunk_ids[0]))
            elif same_record(properties, stored):
                _bump(state, collection, "already_present")
            else:
                _bump(state, collection, "conflict")
                _listed(state, "conflicts", {"id": str(span.id), "collection_id": str(collection)})
        if not missing:
            continue
        if not execute:
            _bump(state, collection, "would_copy", len(missing))
            continue
        if activity is not None:
            await activity.touch(collection, force=True)
        try:
            await store.ensure_tenant(collection)
            errors = await store.insert(collection, missing)
        except Exception as e:
            # A timed-out insert may have landed: running again finds what was stored.
            errors = {span_id: f"{type(e).__name__}: {e}"[:300] for span_id, _, _ in missing}
        _bump(state, collection, "copied", len(missing) - len(errors))
        for span_id, message in errors.items():
            _bump(state, collection, "failed")
            _listed(state, "failed", {"id": str(span_id), "collection_id": str(collection), "error": message[:300]})


async def backfill(store: MigrationStore, state: dict, state_path: Path | None, *, execute: bool,
                   activity=None) -> dict:
    """Run (or resume) a backfill until every legacy span was read; returns the state."""
    if state["done"]:
        return state
    if not await store.legacy_exists():
        raise LookupError(f"The legacy collection {state['source']} does not exist")
    state["target_exists"] = await store.target_exists()
    if state["target_exists"] and not await store.target_is_multi_tenant():
        raise LookupError(f"{state['target']} exists without multi-tenancy; refusing to write to it")
    if execute and not state["target_exists"]:
        await store.create_target()
        state["target_exists"] = True
    if state["tags"] is None:
        state["legacy_total"] = await store.legacy_count()
        state["tags"] = tag_inventory(await store.all_tag_owners())
    lookups = Lookups(store)
    after = UUID(state["after"]) if state["after"] else None
    while True:
        page = await store.legacy_page(after, state["batch_size"])
        if not page:
            break
        await backfill_batch(store, lookups, state, page, execute=execute, activity=activity)
        after = page[-1].id
        state["after"] = str(after)
        state["batches"] += 1
        if state_path is not None:
            save_state(state_path, state)
    state["done"] = True
    if state_path is not None:
        save_state(state_path, state)
    return state


# ── Verify ───────────────────────────────────────────────────────────────


async def verify(store: MigrationStore, batch_size: int = BATCH_SIZE) -> dict:
    """Compare the legacy spans with the tenants' copies (read-only)."""
    report: dict[str, Any] = {"created": _now(), "counts": Counter(), "collections": {},
                              "missing": [], "different": [], "target_only": [], "orphan_tenants": []}
    if not await store.target_exists():
        raise LookupError(f"{store.names.annotation_collection_name} does not exist")
    lookups = Lookups(store)
    expected: dict[str, set[UUID]] = {}

    def bump(tenant: str, key: str, n: int = 1) -> None:
        per = report["collections"].setdefault(tenant, {})
        per[key] = per.get(key, 0) + n
        report["counts"][key] += n

    after = None
    while page := await store.legacy_page(after, batch_size):
        after = page[-1].id
        chunks = await lookups.load(page)
        by_collection: dict[UUID, list[tuple[LegacySpan, dict]]] = {}
        for span in page:
            reason, collection, document = classify(span, lookups, chunks)
            if reason is not None:
                report["counts"][f"skipped:{reason}"] += 1
                continue
            by_collection.setdefault(collection, []).append((span, target_properties(span, document)))
        for collection, items in by_collection.items():
            tenant = tenant_name(collection)
            stored = await store.target_spans(collection, [s.id for s, _ in items])
            for span, properties in items:
                expected.setdefault(tenant, set()).add(span.id)
                copy = stored.get(span.id)
                if copy is None:
                    bump(tenant, "missing")
                    if len(report["missing"]) < MAX_LISTED:
                        report["missing"].append({"id": str(span.id), "collection_id": tenant})
                elif same_record(properties, copy):
                    bump(tenant, "matched")
                else:
                    bump(tenant, "different")
                    if len(report["different"]) < MAX_LISTED:
                        report["different"].append({"id": str(span.id), "collection_id": tenant})

    collections = {str(c) for c in await store.all_collection_ids()}
    for tenant in await store.target_tenants():
        if tenant not in collections:
            report["orphan_tenants"].append(tenant)
        legacy = expected.get(tenant, set())
        async for span in store.iterate_tenant(tenant):
            bump(tenant, "target_total")
            if span.id not in legacy:
                bump(tenant, "target_only")
                if len(report["target_only"]) < MAX_LISTED:
                    report["target_only"].append({"id": str(span.id), "collection_id": tenant})
    report["counts"]["orphan_tenants"] = len(report["orphan_tenants"])
    return report


def verify_ok(report: dict) -> bool:
    counts = report["counts"]
    return not any(counts.get(k) for k in ("missing", "different", "target_only", "orphan_tenants"))


# ── Command line ─────────────────────────────────────────────────────────


async def check_backup(client, names, backup_id: str) -> None:
    """Raises ``LookupError`` unless ``backup_id`` is a successful filesystem backup of the
    legacy spans, tags, chunks and user collections."""
    from semant_demo.adapters.weaviate.document_cleanup import filesystem_backups
    try:
        backups = await filesystem_backups(client)
    except Exception as e:
        raise LookupError(f"Cannot list filesystem backups ({type(e).__name__}: {e})") from e
    backup = next((b for b in backups if b.id == backup_id), None)
    if backup is None or backup.status != "SUCCESS":
        raise LookupError(f"No successful filesystem backup {backup_id!r}")
    needed = {names.span_collection_name, names.tag_collection_name, names.chunks_collection_name,
              names.user_collection_name}
    missing = needed - set(backup.collections)
    if missing:
        raise LookupError(f"Backup {backup_id} does not hold {', '.join(sorted(missing))}")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("backfill", help="copy legacy spans into the tenants (dry run unless --execute)")
    b.add_argument("--state", type=Path, required=True, help="checkpoint and report (JSON); resumed when it exists")
    b.add_argument("--execute", action="store_true", help="write: create the collection, tenants and copies")
    b.add_argument("--confirm-endpoint", metavar="HOST:PORT", help="with --execute: the configured Weaviate endpoint")
    backup = b.add_mutually_exclusive_group()
    backup.add_argument("--backup-id", help="with --execute: a successful backup-filesystem backup of the source data")
    backup.add_argument("--offline-backup", metavar="NOTE",
                        help="with --execute: where the offline copy of the data directory is (not checked)")
    b.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    v = sub.add_parser("verify", help="compare the legacy spans with the tenants (read-only)")
    v.add_argument("--report", type=Path, help="write the full report (JSON) to this file")
    v.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    return p


def _summary(state: dict) -> dict:
    return {k: state.get(k) for k in ("endpoint", "execute", "done", "batches", "legacy_total")} | {
        "counts": dict(sorted(state["counts"].items())),
        "tags": {k: (len(v) if isinstance(v, list) else v) for k, v in (state.get("tags") or {}).items()}}


async def _main(argv: list[str]) -> int:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from semant_demo.adapters.sql.tables import create_tables
    from semant_demo.adapters.sql.tenant_activity import TenantActivity
    from semant_demo.adapters.weaviate.client import connect_weaviate
    from semant_demo.config import Config

    args = _parser().parse_args(argv)
    if args.batch_size < 1:
        print("--batch-size must be positive", file=sys.stderr)
        return 2
    config = Config()
    names = config.collectionNames
    endpoint = f"{config.WEAVIATE_HOST}:{config.WEAVIATE_REST_PORT}"
    print(f"Weaviate endpoint: {endpoint}", file=sys.stderr)

    if args.command == "backfill" and args.execute:
        if args.confirm_endpoint != endpoint:
            print(f"Refusing to write: configured endpoint {endpoint}, --confirm-endpoint {args.confirm_endpoint}",
                  file=sys.stderr)
            return 2
        if not (args.backup_id or (args.offline_backup or "").strip()):
            print("Refusing to write without --backup-id or --offline-backup", file=sys.stderr)
            return 2

    client = await connect_weaviate(config, query_timeout=300)
    engine = None
    try:
        store = MigrationStore(client, names)
        if args.command == "verify":
            report = await verify(store, args.batch_size)
            if args.report:
                args.report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
            print(json.dumps({"endpoint": endpoint, "counts": dict(sorted(report["counts"].items()))}, indent=2))
            return 0 if verify_ok(report) else 1

        try:
            state = load_state(args.state, endpoint, names.span_collection_name, names.annotation_collection_name,
                               args.execute)
            activity = None
            if args.execute:
                if args.backup_id:
                    await check_backup(client, names, args.backup_id)
                # Recorded as in use, so the idle deactivation leaves the tenants alone.
                engine = create_async_engine(config.SQL_DB_URL)
                await create_tables(engine)
                activity = TenantActivity(async_sessionmaker(engine, expire_on_commit=False),
                                          config.ANNOTATION_TENANT_TOUCH_SECONDS)
            if state is None:
                state = new_state(endpoint, names.span_collection_name, names.annotation_collection_name,
                                  args.execute, args.batch_size)
            if args.execute:
                state.setdefault("backups", []).append(
                    {"at": _now(), "backup_id": args.backup_id, "offline_backup": args.offline_backup})
            state = await backfill(store, state, args.state, execute=args.execute, activity=activity)
        except LookupError as e:
            print(f"Refusing: {e}", file=sys.stderr)
            return 2
        print(json.dumps(_summary(state), indent=2, default=str))
        return 1 if state["counts"].get("failed") or state["counts"].get("conflict") else 0
    finally:
        await client.close()
        if engine is not None:
            await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
