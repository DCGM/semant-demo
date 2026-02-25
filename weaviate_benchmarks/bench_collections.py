"""
Benchmarks for UserCollection operations:
  - insert (single, concurrent, batch)
  - query / search (by user_id, by id, filtered)
  - add chunk → collection references (under varying fullness)
  - remove chunk → collection references
  - delete collections

All created objects use the benchmark prefix and are cleaned up at the end.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

import weaviate
from weaviate.classes.query import Filter, QueryReference

from . import config as cfg
from .utils import (
    bench_collection_name,
    bench_user_id,
    compute_stats,
    full_cleanup,
    get_client,
    log,
    run_parallel,
    sample_chunk_uuids,
    save_results,
    timed_call,
)

# ── Helpers ──────────────────────────────────────────────────────────────────

_BENCH_USER = bench_user_id()


def _col_props(name: str, user_id: str | None = None) -> dict:
    return {
        "name": name,
        "user_id": user_id or _BENCH_USER,
    }


async def _insert_collection(client: weaviate.WeaviateAsyncClient, name: str | None = None) -> str:
    """Insert a single benchmark UserCollection and return its UUID."""
    name = name or bench_collection_name()
    uc = client.collections.get("UserCollection")
    uid = await uc.data.insert(properties=_col_props(name))
    return str(uid)


async def _insert_collection_batch(client: weaviate.WeaviateAsyncClient, names: list[str]) -> list[str]:
    """Insert UserCollections using batch API."""
    uc = client.collections.get("UserCollection")
    uuids = []
    async with uc.batch.dynamic() as batch:
        for name in names:
            uid = uuid.uuid4()
            batch.add_object(properties=_col_props(name), uuid=uid)
            uuids.append(str(uid))
    return uuids


# ── Reference helpers ────────────────────────────────────────────────────────


async def _add_col_ref(client: weaviate.WeaviateAsyncClient, chunk_uuid: str, col_uuid: str):
    """Add a single userCollection reference from Chunk to UserCollection."""
    chunks = client.collections.get("Chunks")
    await chunks.data.reference_add(
        from_uuid=chunk_uuid,
        from_property="userCollection",
        to=col_uuid,
    )


async def _remove_col_ref(client: weaviate.WeaviateAsyncClient, chunk_uuid: str, col_uuids_to_remove: list[str]):
    """Remove given collection refs from a chunk via replace."""
    chunks = client.collections.get("Chunks")
    obj = await chunks.query.fetch_object_by_id(
        chunk_uuid,
        return_references=[QueryReference(link_on="userCollection", return_properties=[])],
    )
    refs = obj.references.get("userCollection") if obj and obj.references else None
    current = [str(r.uuid) for r in refs.objects] if refs else []
    remove_set = set(col_uuids_to_remove)
    remaining = [u for u in current if u not in remove_set]
    await chunks.data.reference_replace(
        from_uuid=chunk_uuid,
        from_property="userCollection",
        to=remaining,
    )


# ── 1. Collection insertion benchmarks ───────────────────────────────────────


async def bench_col_insert_sequential(client: weaviate.WeaviateAsyncClient, n: int) -> dict:
    latencies = []
    for i in range(n):
        name = bench_collection_name(i)
        _, elapsed = await timed_call(_insert_collection, client, name)
        latencies.append(elapsed)
    stats = compute_stats(latencies)
    return {"operation": "col_insert_sequential", "n": n, **stats.to_dict()}


async def bench_col_insert_concurrent(client: weaviate.WeaviateAsyncClient, n: int, concurrency: int) -> dict:
    names = [bench_collection_name(i) for i in range(n)]
    args = [(client, name) for name in names]
    latencies = await run_parallel(_insert_collection, args, concurrency)
    stats = compute_stats(latencies)
    return {"operation": "col_insert_concurrent", "n": n, "concurrency": concurrency, **stats.to_dict()}


async def bench_col_insert_batch(client: weaviate.WeaviateAsyncClient, n: int) -> dict:
    names = [bench_collection_name(i) for i in range(n)]
    t0 = time.perf_counter()
    await _insert_collection_batch(client, names)
    elapsed = time.perf_counter() - t0
    return {
        "operation": "col_insert_batch",
        "n": n,
        "total_time_ms": round(elapsed * 1000, 3),
        "throughput_ops_sec": round(n / elapsed, 2) if elapsed > 0 else 0,
    }


# ── 2. Collection query benchmarks ──────────────────────────────────────────


async def bench_col_fetch_by_user(client: weaviate.WeaviateAsyncClient, iterations: int) -> dict:
    uc = client.collections.get("UserCollection")
    latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        await uc.query.fetch_objects(
            filters=Filter.by_property("user_id").equal(_BENCH_USER),
            limit=10000,
        )
        latencies.append(time.perf_counter() - t0)
    stats = compute_stats(latencies)
    return {"operation": "col_fetch_by_user", "iterations": iterations, **stats.to_dict()}


async def bench_col_fetch_by_id(client: weaviate.WeaviateAsyncClient, col_uuids: list[str]) -> dict:
    uc = client.collections.get("UserCollection")
    latencies = []
    for uid in col_uuids:
        t0 = time.perf_counter()
        await uc.query.fetch_object_by_id(uid)
        latencies.append(time.perf_counter() - t0)
    stats = compute_stats(latencies)
    return {"operation": "col_fetch_by_id", "n": len(col_uuids), **stats.to_dict()}


async def bench_col_fetch_by_name_filter(client: weaviate.WeaviateAsyncClient, iterations: int) -> dict:
    uc = client.collections.get("UserCollection")
    latencies = []
    for _ in range(iterations):
        filters = (
            Filter.by_property("name").like(f"{cfg.BENCH_PREFIX}*")
            & Filter.by_property("user_id").equal(_BENCH_USER)
        )
        t0 = time.perf_counter()
        await uc.query.fetch_objects(filters=filters, limit=10000)
        latencies.append(time.perf_counter() - t0)
    stats = compute_stats(latencies)
    return {"operation": "col_fetch_by_name_filter", "iterations": iterations, **stats.to_dict()}


async def bench_col_fetch_contains_any(client: weaviate.WeaviateAsyncClient, col_uuids: list[str], iterations: int) -> dict:
    uc = client.collections.get("UserCollection")
    latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        await uc.query.fetch_objects(
            filters=Filter.by_id().contains_any(col_uuids),
            limit=10000,
        )
        latencies.append(time.perf_counter() - t0)
    stats = compute_stats(latencies)
    return {"operation": "col_fetch_contains_any", "n_ids": len(col_uuids), "iterations": iterations, **stats.to_dict()}


# ── 3. Reference addition (fullness) ────────────────────────────────────────


async def bench_col_ref_add_varying_fullness(
    client: weaviate.WeaviateAsyncClient,
    chunk_uuids: list[str],
    fullness_levels: list[int],
) -> list[dict]:
    results = []
    uc_col = client.collections.get("UserCollection")

    for fullness in fullness_levels:
        log.info(f"  Collection ref add — fullness={fullness}")
        prefill = []
        for i in range(fullness):
            uid = await _insert_collection(client, bench_collection_name(i))
            prefill.append(uid)

        for cid in chunk_uuids:
            for col_id in prefill:
                await _add_col_ref(client, cid, col_id)

        measure_col = await _insert_collection(client, bench_collection_name(9000 + fullness))

        latencies = []
        for cid in chunk_uuids:
            _, elapsed = await timed_call(_add_col_ref, client, cid, measure_col)
            latencies.append(elapsed)

        stats = compute_stats(latencies)
        results.append({
            "operation": "col_ref_add",
            "fullness": fullness,
            "n_chunks": len(chunk_uuids),
            **stats.to_dict(),
        })

        # Cleanup
        all_cols = prefill + [measure_col]
        for cid in chunk_uuids:
            await _remove_col_ref(client, cid, all_cols)
        await uc_col.data.delete_many(where=Filter.by_id().contains_any(all_cols))

    return results


# ── 4. Reference addition (concurrency) ─────────────────────────────────────


async def bench_col_ref_add_concurrent(
    client: weaviate.WeaviateAsyncClient,
    chunk_uuids: list[str],
    concurrency_levels: list[int],
) -> list[dict]:
    results = []
    uc_col = client.collections.get("UserCollection")

    for conc in concurrency_levels:
        log.info(f"  Collection ref add — concurrency={conc}")
        col_uuid = await _insert_collection(client, bench_collection_name(8000 + conc))
        args = [(client, cid, col_uuid) for cid in chunk_uuids]
        latencies = await run_parallel(_add_col_ref, args, conc)
        stats = compute_stats(latencies)
        results.append({
            "operation": "col_ref_add_concurrent",
            "concurrency": conc,
            "n_chunks": len(chunk_uuids),
            **stats.to_dict(),
        })
        for cid in chunk_uuids:
            await _remove_col_ref(client, cid, [col_uuid])
        await uc_col.data.delete_many(where=Filter.by_id().contains_any([col_uuid]))

    return results


# ── 5. Reference removal ────────────────────────────────────────────────────


async def bench_col_ref_remove(client: weaviate.WeaviateAsyncClient, chunk_uuids: list[str]) -> dict:
    uc_col = client.collections.get("UserCollection")
    col_uuid = await _insert_collection(client, bench_collection_name(7000))

    for cid in chunk_uuids:
        await _add_col_ref(client, cid, col_uuid)

    latencies = []
    for cid in chunk_uuids:
        _, elapsed = await timed_call(_remove_col_ref, client, cid, [col_uuid])
        latencies.append(elapsed)

    stats = compute_stats(latencies)
    await uc_col.data.delete_many(where=Filter.by_id().contains_any([col_uuid]))
    return {"operation": "col_ref_remove", "n_chunks": len(chunk_uuids), **stats.to_dict()}


# ── 6. Collection deletion ──────────────────────────────────────────────────


async def bench_col_delete_single(client: weaviate.WeaviateAsyncClient, n: int) -> dict:
    uc = client.collections.get("UserCollection")
    uuids = []
    for i in range(n):
        uid = await _insert_collection(client, bench_collection_name(i))
        uuids.append(uid)

    latencies = []
    for uid in uuids:
        t0 = time.perf_counter()
        await uc.data.delete_by_id(uid)
        latencies.append(time.perf_counter() - t0)

    stats = compute_stats(latencies)
    return {"operation": "col_delete_single", "n": n, **stats.to_dict()}


async def bench_col_delete_batch(client: weaviate.WeaviateAsyncClient, n: int) -> dict:
    uuids = []
    for i in range(n):
        uid = await _insert_collection(client, bench_collection_name(i))
        uuids.append(uid)

    uc = client.collections.get("UserCollection")
    t0 = time.perf_counter()
    await uc.data.delete_many(where=Filter.by_id().contains_any(uuids))
    elapsed = time.perf_counter() - t0

    return {
        "operation": "col_delete_batch",
        "n": n,
        "total_time_ms": round(elapsed * 1000, 3),
        "throughput_ops_sec": round(n / elapsed, 2) if elapsed > 0 else 0,
    }


# ── 7. Chunk query filtered by collection ref ───────────────────────────────


async def bench_chunk_query_by_col_ref(
    client: weaviate.WeaviateAsyncClient,
    chunk_uuids: list[str],
    iterations: int = 20,
) -> list[dict]:
    uc_col = client.collections.get("UserCollection")
    chunks_col = client.collections.get("Chunks")

    col_uuid = await _insert_collection(client, bench_collection_name(6000))
    for cid in chunk_uuids:
        await _add_col_ref(client, cid, col_uuid)

    results = []

    # Style 1: fetch_objects with ref filter
    latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        await chunks_col.query.fetch_objects(
            filters=Filter.by_ref(link_on="userCollection").by_id().contains_any([col_uuid]),
            return_references=[QueryReference(link_on="userCollection", return_properties=[])],
            limit=100,
        )
        latencies.append(time.perf_counter() - t0)
    stats = compute_stats(latencies)
    results.append({"operation": "chunk_query_by_col_fetch_objects", "iterations": iterations, **stats.to_dict()})

    # Style 2: fetch_objects with name property filter on nested ref
    latencies = []
    col_name = bench_collection_name(6000)
    for _ in range(iterations):
        t0 = time.perf_counter()
        await chunks_col.query.fetch_objects(
            filters=Filter.by_ref(link_on="userCollection").by_property("name").like(f"{cfg.BENCH_PREFIX}*"),
            return_references=[QueryReference(link_on="userCollection", return_properties=["name"])],
            limit=100,
        )
        latencies.append(time.perf_counter() - t0)
    stats = compute_stats(latencies)
    results.append({"operation": "chunk_query_by_col_name_filter", "iterations": iterations, **stats.to_dict()})

    # Style 3: ID+ref compound filter
    latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        await chunks_col.query.fetch_objects(
            filters=(
                Filter.by_id().contains_any(chunk_uuids)
                & Filter.by_ref(link_on="userCollection").by_id().contains_any([col_uuid])
            ),
            return_references=[QueryReference(link_on="userCollection", return_properties=[])],
            limit=100,
        )
        latencies.append(time.perf_counter() - t0)
    stats = compute_stats(latencies)
    results.append({"operation": "chunk_query_by_col_id_and_ref", "iterations": iterations, **stats.to_dict()})

    # Cleanup
    for cid in chunk_uuids:
        await _remove_col_ref(client, cid, [col_uuid])
    await uc_col.data.delete_many(where=Filter.by_id().contains_any([col_uuid]))

    return results


# ── Main runner ──────────────────────────────────────────────────────────────


async def run_collection_benchmarks() -> list[dict]:
    """Execute the full UserCollection benchmark suite and return results."""
    client = await get_client()
    all_results: list[dict] = []

    try:
        n = cfg.OPS_PER_MEASUREMENT
        chunk_uuids = await sample_chunk_uuids(client, cfg.CHUNK_SAMPLE_SIZE)
        if not chunk_uuids:
            log.error("No chunks found in database, cannot run benchmarks.")
            return []

        log.info(f"Sampled {len(chunk_uuids)} chunks for reference benchmarks.")

        # 1. Insertion
        log.info("=== Collection insertion benchmarks ===")
        all_results.append(await bench_col_insert_sequential(client, n))
        await full_cleanup(client)

        for conc in cfg.CONCURRENCY_LEVELS:
            all_results.append(await bench_col_insert_concurrent(client, n, conc))
            await full_cleanup(client)

        all_results.append(await bench_col_insert_batch(client, n))
        await full_cleanup(client)

        # 2. Query
        log.info("=== Collection query benchmarks ===")
        col_uuids = []
        for i in range(n):
            uid = await _insert_collection(client, bench_collection_name(i))
            col_uuids.append(uid)

        all_results.append(await bench_col_fetch_by_user(client, 30))
        all_results.append(await bench_col_fetch_by_id(client, col_uuids[:20]))
        all_results.append(await bench_col_fetch_by_name_filter(client, 30))
        all_results.append(await bench_col_fetch_contains_any(client, col_uuids[:10], 30))
        all_results.append(await bench_col_fetch_contains_any(client, col_uuids, 30))
        await full_cleanup(client)

        # 3. Reference add (fullness)
        log.info("=== Collection reference addition (fullness) benchmarks ===")
        fullness_results = await bench_col_ref_add_varying_fullness(
            client, chunk_uuids, cfg.FULLNESS_LEVELS,
        )
        all_results.extend(fullness_results)

        # 4. Reference add (concurrency)
        log.info("=== Collection reference addition (concurrency) benchmarks ===")
        conc_results = await bench_col_ref_add_concurrent(
            client, chunk_uuids, cfg.CONCURRENCY_LEVELS,
        )
        all_results.extend(conc_results)

        # 5. Reference removal
        log.info("=== Collection reference removal benchmarks ===")
        all_results.append(await bench_col_ref_remove(client, chunk_uuids))

        # 6. Deletion
        log.info("=== Collection deletion benchmarks ===")
        all_results.append(await bench_col_delete_single(client, n))
        all_results.append(await bench_col_delete_batch(client, n))

        # 7. Chunk query by collection ref
        log.info("=== Chunk query by collection reference benchmarks ===")
        query_results = await bench_chunk_query_by_col_ref(client, chunk_uuids)
        all_results.extend(query_results)

    finally:
        await full_cleanup(client)
        await client.close()

    save_results("collection_benchmarks", all_results)
    return all_results


if __name__ == "__main__":
    asyncio.run(run_collection_benchmarks())
