"""Rehearsal of annotation tenants on a throwaway Weaviate (#327): mixed tenant sizes,
activation latency, many tenants, and backup/restore of active and inactive tenants.

A controlled measurement, not part of ``make test-integration``. Run it explicitly against
a throwaway store of the deployed Weaviate version (backup module enabled)::

    scripts/with-test-weaviate.sh sh -c 'cd semant_demo_backend && \\
        ../.venv/bin/python -m pytest -m benchmark tests/integration/test_annotation_tenant_rehearsal.py -s'

It prints one JSON report (``SEMANT_REHEARSAL_REPORT`` also writes it to a file) with the
wall-clock phase times, so memory sampled outside (``docker stats``) can be matched to the
phases; ``SEMANT_REHEARSAL_SETTLE_SECONDS`` waits that long after the many tenants were
activated and again after they were deactivated, so a sample falls into each state.
Sizes scale with ``SEMANT_REHEARSAL_SCALE`` (default 1). Correctness is asserted;
times are only recorded: they depend on the machine and are not limits.
"""
import asyncio
import json
import os
import statistics
import time
import uuid
from datetime import datetime, timezone

import pytest
from weaviate.classes.backup import BackupStorage
from weaviate.classes.data import DataObject
from weaviate.classes.tenants import Tenant, TenantActivityStatus

pytestmark = pytest.mark.benchmark

SCALE = float(os.environ.get("SEMANT_REHEARSAL_SCALE", "1"))
SETTLE = float(os.environ.get("SEMANT_REHEARSAL_SETTLE_SECONDS", "0"))
SIZES = [0, 1, 1_000, 10_000, 30_000]
MANY_TENANTS = 1_000
BATCH = 1_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def _timed(coro):
    start = time.perf_counter()
    result = await coro
    return result, round((time.perf_counter() - start) * 1000, 1)


def _span(chunk_id: str, document_id: str, tag_id: str, i: int) -> DataObject:
    return DataObject(properties={"tagId": tag_id, "chunkId": chunk_id, "documentId": document_id, "start": i % 50,
                                  "end": i % 50 + 5, "type": ("pos", "auto", "neg")[i % 3]},
                      references={"text_chunk": chunk_id})


async def test_annotation_tenant_rehearsal(seeded_store, collection_names, ids):
    names = collection_names
    annotations = seeded_store.collections.get(names.annotation_collection_name)
    chunk, document, tag = ids.chunk["chronicle_1"], ids.doc["chronicle"], ids.tag["person"]
    version = (await seeded_store.get_meta())["version"]
    report: dict = {"weaviate": version, "scale": SCALE, "phases": [], "tenants": {}}

    def phase(name: str) -> None:
        report["phases"].append({"phase": name, "at": _now()})

    async def count(tenant: str) -> int:
        return (await annotations.with_tenant(tenant).aggregate.over_all(total_count=True)).total_count

    # Mixed sizes: insert, warm read, cold activation.
    phase("insert_mixed_sizes")
    sized = {}
    for size in SIZES:
        n = int(size * SCALE) if size > 1 else size
        tenant = str(uuid.uuid4())
        _, created_ms = await _timed(annotations.tenants.create([Tenant(name=tenant)]))
        start = time.perf_counter()
        for offset in range(0, n, BATCH):
            result = await annotations.with_tenant(tenant).data.insert_many(
                [_span(chunk, document, tag, i) for i in range(offset, min(n, offset + BATCH))])
            assert not result.has_errors
        insert_s = time.perf_counter() - start
        assert await count(tenant) == n
        sized[tenant] = n
        report["tenants"][tenant] = {"spans": n, "create_ms": created_ms,
                                     "insert_per_s": round(n / insert_s) if n and insert_s else None}

    phase("activation_latency")
    for tenant, n in sized.items():
        warm = [(await _timed(annotations.with_tenant(tenant).query.fetch_objects(limit=50)))[1] for _ in range(3)]
        _, deactivate_ms = await _timed(annotations.tenants.update(
            [Tenant(name=tenant, activity_status=TenantActivityStatus.INACTIVE)]))
        cold_result, cold_ms = await _timed(annotations.with_tenant(tenant).query.fetch_objects(limit=50))
        assert len(cold_result.objects) == min(50, n)
        assert (await annotations.tenants.get_by_name(tenant)).activity_status == TenantActivityStatus.ACTIVE
        report["tenants"][tenant].update({"warm_read_ms": statistics.median(warm), "deactivate_ms": deactivate_ms,
                                          "first_read_after_deactivation_ms": cold_ms})

    # Many small tenants: creation, concurrent activation of inactive ones.
    phase("many_tenants")
    many = [str(uuid.uuid4()) for _ in range(int(MANY_TENANTS * SCALE))]
    start = time.perf_counter()
    for i in range(0, len(many), 100):
        await annotations.tenants.create([Tenant(name=t) for t in many[i:i + 100]])
    create_s = time.perf_counter() - start
    start = time.perf_counter()
    for tenant in many:
        await annotations.with_tenant(tenant).data.insert_many([_span(chunk, document, tag, 0)])
    one_span_s = time.perf_counter() - start
    phase("many_tenants_active")
    await asyncio.sleep(SETTLE)
    await annotations.tenants.update([Tenant(name=t, activity_status=TenantActivityStatus.INACTIVE) for t in many])
    phase("many_tenants_inactive")
    await asyncio.sleep(SETTLE)
    sample = many[:50]
    reads = await asyncio.gather(*(_timed(annotations.with_tenant(t).query.fetch_objects(limit=5)) for t in sample))
    assert all(len(r.objects) == 1 for r, _ in reads)
    latencies = sorted(ms for _, ms in reads)
    report["many_tenants"] = {
        "tenants": len(many), "create_per_s": round(len(many) / create_s),
        "first_insert_per_tenant_ms": round(one_span_s / len(many) * 1000, 1),
        "concurrent_activation_of_50_ms": {"median": statistics.median(latencies), "max": latencies[-1]},
    }

    # Backup and restore with active and inactive tenants of every size.
    phase("backup")
    inactive = list(sized)[::2]
    await annotations.tenants.update([Tenant(name=t, activity_status=TenantActivityStatus.INACTIVE) for t in inactive])
    statuses = {name: t.activity_status for name, t in (await annotations.tenants.get()).items()}
    backup_id = f"rehearsal-{uuid.uuid4().hex[:12]}"
    backup, backup_ms = await _timed(seeded_store.backup.create(
        backup_id=backup_id, backend=BackupStorage.FILESYSTEM,
        include_collections=[names.annotation_collection_name], wait_for_completion=True))
    assert backup.status.value == "SUCCESS"
    assert {name: t.activity_status for name, t in (await annotations.tenants.get()).items()} == statuses
    phase("restore")
    await seeded_store.collections.delete(names.annotation_collection_name)
    restored, restore_ms = await _timed(seeded_store.backup.restore(
        backup_id=backup_id, backend=BackupStorage.FILESYSTEM,
        include_collections=[names.annotation_collection_name], wait_for_completion=True))
    assert restored.status.value == "SUCCESS"
    assert {name: t.activity_status for name, t in (await annotations.tenants.get()).items()} == statuses
    for tenant, n in sized.items():
        assert await count(tenant) == n
    report["backup"] = {"tenants": len(statuses), "inactive": sum(s == TenantActivityStatus.INACTIVE
                                                                  for s in statuses.values()),
                        "spans": sum(sized.values()) + len(many) + 6, "backup_ms": backup_ms,
                        "restore_ms": restore_ms}
    phase("done")

    text = json.dumps(report, indent=2)
    print(text)
    if os.environ.get("SEMANT_REHEARSAL_REPORT"):
        with open(os.environ["SEMANT_REHEARSAL_REPORT"], "w", encoding="utf-8") as f:
            f.write(text)
