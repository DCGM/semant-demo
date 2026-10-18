"""Annotation tenants: status, and deactivation of idle tenants (#327).

Each user collection's spans are one tenant of the ``Annotation`` collection. An inactive
tenant keeps its data on disk and uses no memory; the next read or write activates it
again (``auto_tenant_activation``), at the cost of that request's latency. The backend
and the maintenance commands record every use of a tenant in the application database
(``adapters/sql/tenant_activity.py``); a tenant counts as idle when its last recorded
use is older than the idle time. A tenant without a record gets one now, so it becomes
idle only one idle time later.

Status (read-only; ``--counts`` also counts each tenant's spans, which activates it)::

    python -m semant_demo.maintenance.annotation_tenants status [--counts]

Deactivate idle tenants (a dry run lists them; run periodically, e.g. from a timer)::

    python -m semant_demo.maintenance.annotation_tenants deactivate-idle [--idle-seconds N]
    python -m semant_demo.maintenance.annotation_tenants deactivate-idle --execute \\
        --confirm-endpoint localhost:8080

Deactivation is disabled until ``ANNOTATION_TENANT_DEACTIVATION_ENABLED=true``: enable
it only after backup and restore of active and inactive tenants have been rehearsed on
the deployed Weaviate version (docs/DATA_MAINTENANCE.md). The idle time
(``ANNOTATION_TENANT_IDLE_SECONDS``, default 3600) must be at least three times
``ANNOTATION_TENANT_TOUCH_SECONDS``, the interval in which running operations record
themselves. Each candidate's record is read again right before it is deactivated; a
request that starts in between may still find its tenant being deactivated (it then
fails or waits for the activation, and can be repeated). Records of tenants that no
longer exist are dropped.
"""
import argparse
import asyncio
import json
import sys
from datetime import timedelta

from weaviate.classes.tenants import TenantActivityStatus

from semant_demo.adapters.sql.tenant_activity import TenantActivity
from semant_demo.adapters.weaviate.spans import SpanRepository

MIN_IDLE_FACTOR = 3


async def tenant_status(spans: SpanRepository, activity: TenantActivity, collection_ids: set[str],
                        *, counts: bool = False) -> list[dict]:
    tenants = await spans.list_tenants()
    last = await activity.last_used(tenants)
    now = activity.now()
    rows = []
    for name, status in sorted(tenants.items()):
        row = {"tenant": name, "status": status.value, "orphan": name not in collection_ids,
               "last_used_at": last[name].isoformat() if name in last else None,
               "idle_seconds": round((now - last[name]).total_seconds()) if name in last else None}
        if counts:
            row["spans"] = len(await spans.read_by_collection(name))
        rows.append(row)
    return rows


async def deactivate_idle(spans: SpanRepository, activity: TenantActivity, idle_seconds: float,
                          *, execute: bool) -> dict:
    """Deactivate (or, without ``execute``, list) active tenants idle for ``idle_seconds``."""
    tenants = await spans.list_tenants()
    recorded = await activity.last_used()
    await activity.forget(set(recorded) - set(tenants))
    await activity.record_unseen(set(tenants) - set(recorded))
    last = await activity.last_used(tenants)
    cutoff = activity.now() - timedelta(seconds=idle_seconds)
    candidates = sorted(n for n, s in tenants.items()
                        if s == TenantActivityStatus.ACTIVE and n in last and last[n] < cutoff)
    result: dict = {"tenants": len(tenants), "active": sum(s == TenantActivityStatus.ACTIVE for s in tenants.values()),
                    "idle": candidates, "deactivated": [], "skipped_in_use": [], "failed": []}
    if not execute:
        return result
    for name in candidates:
        # Read again: a use recorded since the listing keeps the tenant active.
        fresh = (await activity.last_used([name])).get(name)
        if fresh is None or fresh >= activity.now() - timedelta(seconds=idle_seconds):
            result["skipped_in_use"].append(name)
            continue
        try:
            await spans.deactivate_tenant(name)
            result["deactivated"].append(name)
        except Exception as e:
            result["failed"].append({"tenant": name, "error": f"{type(e).__name__}: {e}"[:300]})
    return result


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("status", help="list the tenants, their status and last use (read-only)")
    s.add_argument("--counts", action="store_true", help="also count each tenant's spans (activates them)")
    d = sub.add_parser("deactivate-idle", help="deactivate idle tenants (dry run unless --execute)")
    d.add_argument("--idle-seconds", type=float, help="default: ANNOTATION_TENANT_IDLE_SECONDS")
    d.add_argument("--execute", action="store_true")
    d.add_argument("--confirm-endpoint", metavar="HOST:PORT", help="with --execute: the configured Weaviate endpoint")
    return p


async def _main(argv: list[str]) -> int:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from semant_demo.adapters.sql.tables import create_tables
    from semant_demo.adapters.weaviate.annotation_migration import MigrationStore
    from semant_demo.adapters.weaviate.client import connect_weaviate
    from semant_demo.config import Config

    args = _parser().parse_args(argv)
    config = Config()
    endpoint = f"{config.WEAVIATE_HOST}:{config.WEAVIATE_REST_PORT}"
    if args.command == "deactivate-idle":
        idle = args.idle_seconds if args.idle_seconds is not None else config.ANNOTATION_TENANT_IDLE_SECONDS
        if idle < MIN_IDLE_FACTOR * config.ANNOTATION_TENANT_TOUCH_SECONDS:
            print(f"Refusing: the idle time ({idle} s) must be at least {MIN_IDLE_FACTOR} x "
                  f"ANNOTATION_TENANT_TOUCH_SECONDS ({config.ANNOTATION_TENANT_TOUCH_SECONDS} s)", file=sys.stderr)
            return 2
        if args.execute and not config.ANNOTATION_TENANT_DEACTIVATION_ENABLED:
            print("Refusing: tenant deactivation is disabled (ANNOTATION_TENANT_DEACTIVATION_ENABLED)",
                  file=sys.stderr)
            return 2
        if args.execute and args.confirm_endpoint != endpoint:
            print(f"Refusing to write: configured endpoint {endpoint}, --confirm-endpoint {args.confirm_endpoint}",
                  file=sys.stderr)
            return 2
    print(f"Weaviate endpoint: {endpoint}", file=sys.stderr)

    engine = create_async_engine(config.SQL_DB_URL)
    client = await connect_weaviate(config)
    try:
        await create_tables(engine)
        activity = TenantActivity(async_sessionmaker(engine, expire_on_commit=False),
                                  config.ANNOTATION_TENANT_TOUCH_SECONDS)
        spans = SpanRepository(client, config.collectionNames)
        if args.command == "status":
            ids = {str(c) for c in await MigrationStore(client, config.collectionNames).all_collection_ids()}
            print(json.dumps(await tenant_status(spans, activity, ids, counts=args.counts), indent=2))
            return 0
        result = await deactivate_idle(spans, activity, idle, execute=args.execute)
        print(json.dumps(result, indent=2))
        return 1 if result["failed"] else 0
    finally:
        await client.close()
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
