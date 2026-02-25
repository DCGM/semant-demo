"""
Benchmarks for Tag operations:
  - insert (single, batch, concurrent)
  - query / search (fetch_objects with filters, fetch by ID, iterator)
  - add tag references to chunks (under varying fullness)
  - remove tag references from chunks
  - delete tags

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
    bench_tag_name,
    bench_collection_name,
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


def _tag_props(name: str) -> dict:
    return {
        "tag_name": name,
        "tag_shorthand": name[:10],
        "tag_color": "#FF0000",
        "tag_pictogram": "star",
        "tag_definition": "Benchmark tag for latency measurement",
        "tag_examples": ["example_a", "example_b"],
        "collection_name": f"{cfg.BENCH_PREFIX}col",
    }


async def _insert_tag(client: weaviate.WeaviateAsyncClient, name: str | None = None) -> str:
    """Insert a single benchmark tag and return its UUID."""
    name = name or bench_tag_name()
    tag_col = client.collections.get("Tag")
    uid = await tag_col.data.insert(properties=_tag_props(name))
    return str(uid)


async def _insert_tag_batch(client: weaviate.WeaviateAsyncClient, names: list[str]) -> list[str]:
    """Insert tags using batch API."""
    tag_col = client.collections.get("Tag")
    uuids = []
    async with tag_col.batch.dynamic() as batch:
        for name in names:
            uid = uuid.uuid4()
            batch.add_object(properties=_tag_props(name), uuid=uid)
            uuids.append(str(uid))
    return uuids


# ── 1. Tag insertion benchmarks ─────────────────────────────────────────────


async def bench_tag_insert_sequential(client: weaviate.WeaviateAsyncClient, n: int) -> dict:
    """Insert *n* tags one-by-one sequentially."""
    latencies = []
    created_uuids = []
    for i in range(n):
        name = bench_tag_name(i)
        uid, elapsed = await timed_call(_insert_tag, client, name)
        latencies.append(elapsed)
        created_uuids.append(uid)
    stats = compute_stats(latencies)
    return {"operation": "tag_insert_sequential", "n": n, **stats.to_dict()}


async def bench_tag_insert_concurrent(client: weaviate.WeaviateAsyncClient, n: int, concurrency: int) -> dict:
    """Insert *n* tags with bounded *concurrency*."""
    names = [bench_tag_name(i) for i in range(n)]
    args = [(client, name) for name in names]
    latencies = await run_parallel(_insert_tag, args, concurrency)
    stats = compute_stats(latencies)
    return {"operation": "tag_insert_concurrent", "n": n, "concurrency": concurrency, **stats.to_dict()}


async def bench_tag_insert_batch(client: weaviate.WeaviateAsyncClient, n: int) -> dict:
    """Insert *n* tags via the batch API (single call)."""
    names = [bench_tag_name(i) for i in range(n)]
    t0 = time.perf_counter()
    uuids = await _insert_tag_batch(client, names)
    elapsed = time.perf_counter() - t0
    return {
        "operation": "tag_insert_batch",
        "n": n,
        "total_time_ms": round(elapsed * 1000, 3),
        "throughput_ops_sec": round(n / elapsed, 2) if elapsed > 0 else 0,
    }


# ── 2. Tag query / search benchmarks ────────────────────────────────────────


async def bench_tag_fetch_all(client: weaviate.WeaviateAsyncClient, iterations: int) -> dict:
    """Measure fetch_objects for all benchmark tags."""
    tag_col = client.collections.get("Tag")
    latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        await tag_col.query.fetch_objects(
            filters=Filter.by_property("tag_name").like(f"{cfg.BENCH_PREFIX}*"),
            limit=10000,
        )
        latencies.append(time.perf_counter() - t0)
    stats = compute_stats(latencies)
    return {"operation": "tag_fetch_all", "iterations": iterations, **stats.to_dict()}


async def bench_tag_fetch_by_id(client: weaviate.WeaviateAsyncClient, tag_uuids: list[str]) -> dict:
    """Measure fetch_object_by_id for each tag."""
    tag_col = client.collections.get("Tag")
    latencies = []
    for uid in tag_uuids:
        t0 = time.perf_counter()
        await tag_col.query.fetch_object_by_id(uid)
        latencies.append(time.perf_counter() - t0)
    stats = compute_stats(latencies)
    return {"operation": "tag_fetch_by_id", "n": len(tag_uuids), **stats.to_dict()}


async def bench_tag_fetch_filtered(client: weaviate.WeaviateAsyncClient, iterations: int) -> dict:
    """Fetch tags with a compound property filter."""
    tag_col = client.collections.get("Tag")
    latencies = []
    for _ in range(iterations):
        filters = (
            Filter.by_property("tag_name").like(f"{cfg.BENCH_PREFIX}*")
            & Filter.by_property("tag_color").equal("#FF0000")
        )
        t0 = time.perf_counter()
        await tag_col.query.fetch_objects(filters=filters, limit=10000)
        latencies.append(time.perf_counter() - t0)
    stats = compute_stats(latencies)
    return {"operation": "tag_fetch_filtered", "iterations": iterations, **stats.to_dict()}


async def bench_tag_fetch_contains_any(client: weaviate.WeaviateAsyncClient, tag_uuids: list[str], iterations: int) -> dict:
    """Fetch tags via contains_any (ID filter), varying batch sizes."""
    tag_col = client.collections.get("Tag")
    latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        await tag_col.query.fetch_objects(
            filters=Filter.by_id().contains_any(tag_uuids),
            limit=10000,
        )
        latencies.append(time.perf_counter() - t0)
    stats = compute_stats(latencies)
    return {"operation": "tag_fetch_contains_any", "n_ids": len(tag_uuids), "iterations": iterations, **stats.to_dict()}


# ── 3. Reference addition benchmarks (varying fullness) ─────────────────────


async def _add_tag_ref(client: weaviate.WeaviateAsyncClient, chunk_uuid: str, tag_uuid: str, ref_prop: str = "automaticTag"):
    """Add a single tag reference to a chunk."""
    chunks_col = client.collections.get("Chunks")
    await chunks_col.data.reference_add(
        from_uuid=chunk_uuid,
        from_property=ref_prop,
        to=tag_uuid,
    )


async def _remove_tag_ref(client: weaviate.WeaviateAsyncClient, chunk_uuid: str, tag_uuids_to_remove: list[str], ref_prop: str = "automaticTag"):
    """Remove given tag references from a chunk via replace (keep others intact)."""
    chunks_col = client.collections.get("Chunks")
    obj = await chunks_col.query.fetch_object_by_id(
        chunk_uuid,
        return_references=[QueryReference(link_on=ref_prop, return_properties=[])],
    )
    refs = obj.references.get(ref_prop) if obj and obj.references else None
    current = [str(r.uuid) for r in refs.objects] if refs else []
    remove_set = set(tag_uuids_to_remove)
    remaining = [u for u in current if u not in remove_set]
    await chunks_col.data.reference_replace(
        from_uuid=chunk_uuid,
        from_property=ref_prop,
        to=remaining,
    )


async def bench_tag_ref_add_varying_fullness(
    client: weaviate.WeaviateAsyncClient,
    chunk_uuids: list[str],
    fullness_levels: list[int],
) -> list[dict]:
    """
    For each fullness level, pre-fill chunks with that many tag refs,
    then measure adding one more.
    """
    results = []
    tag_col = client.collections.get("Tag")

    for fullness in fullness_levels:
        log.info(f"  Tag ref add — fullness={fullness}")
        # Pre-create tags for pre-fill + 1 measurement tag per chunk
        prefill_tags = []
        for i in range(fullness):
            uid = await _insert_tag(client, bench_tag_name(i))
            prefill_tags.append(uid)

        # Pre-fill
        for cid in chunk_uuids:
            for tid in prefill_tags:
                await _add_tag_ref(client, cid, tid)

        # Create the measurement tag
        measure_tag = await _insert_tag(client, bench_tag_name(9000 + fullness))

        # Measure adding the measurement tag
        latencies = []
        for cid in chunk_uuids:
            _, elapsed = await timed_call(_add_tag_ref, client, cid, measure_tag)
            latencies.append(elapsed)

        stats = compute_stats(latencies)
        results.append({
            "operation": "tag_ref_add",
            "fullness": fullness,
            "n_chunks": len(chunk_uuids),
            **stats.to_dict(),
        })

        # Cleanup: remove measurement tag + prefill tags from chunks
        all_bench_tags = prefill_tags + [measure_tag]
        for cid in chunk_uuids:
            await _remove_tag_ref(client, cid, all_bench_tags)

        # Delete tag objects
        await tag_col.data.delete_many(
            where=Filter.by_id().contains_any(all_bench_tags)
        )

    return results


async def bench_tag_ref_add_concurrent(
    client: weaviate.WeaviateAsyncClient,
    chunk_uuids: list[str],
    concurrency_levels: list[int],
) -> list[dict]:
    """Measure adding one tag ref per chunk at various concurrency levels."""
    results = []
    tag_col = client.collections.get("Tag")

    for conc in concurrency_levels:
        log.info(f"  Tag ref add — concurrency={conc}")
        tag_uuid = await _insert_tag(client, bench_tag_name(8000 + conc))
        args = [(client, cid, tag_uuid) for cid in chunk_uuids]
        latencies = await run_parallel(_add_tag_ref, args, conc)
        stats = compute_stats(latencies)
        results.append({
            "operation": "tag_ref_add_concurrent",
            "concurrency": conc,
            "n_chunks": len(chunk_uuids),
            **stats.to_dict(),
        })
        # Cleanup
        for cid in chunk_uuids:
            await _remove_tag_ref(client, cid, [tag_uuid])
        await tag_col.data.delete_many(where=Filter.by_id().contains_any([tag_uuid]))

    return results


# ── 4. Reference removal benchmarks ─────────────────────────────────────────


async def bench_tag_ref_remove(
    client: weaviate.WeaviateAsyncClient,
    chunk_uuids: list[str],
) -> dict:
    """Measure removing a single tag ref from each chunk (via replace)."""
    tag_col = client.collections.get("Tag")
    tag_uuid = await _insert_tag(client, bench_tag_name(7000))

    # Pre-add
    for cid in chunk_uuids:
        await _add_tag_ref(client, cid, tag_uuid)

    # Measure removal
    latencies = []
    for cid in chunk_uuids:
        _, elapsed = await timed_call(_remove_tag_ref, client, cid, [tag_uuid])
        latencies.append(elapsed)

    stats = compute_stats(latencies)

    # Delete tag object
    await tag_col.data.delete_many(where=Filter.by_id().contains_any([tag_uuid]))

    return {"operation": "tag_ref_remove", "n_chunks": len(chunk_uuids), **stats.to_dict()}


# ── 5. Tag deletion benchmarks ──────────────────────────────────────────────


async def bench_tag_delete_single(client: weaviate.WeaviateAsyncClient, n: int) -> dict:
    """Create *n* tags then delete them one-by-one."""
    tag_col = client.collections.get("Tag")
    uuids = []
    for i in range(n):
        uid = await _insert_tag(client, bench_tag_name(i))
        uuids.append(uid)

    latencies = []
    for uid in uuids:
        t0 = time.perf_counter()
        await tag_col.data.delete_by_id(uid)
        latencies.append(time.perf_counter() - t0)

    stats = compute_stats(latencies)
    return {"operation": "tag_delete_single", "n": n, **stats.to_dict()}


async def bench_tag_delete_batch(client: weaviate.WeaviateAsyncClient, n: int) -> dict:
    """Create *n* tags then delete them in one delete_many call."""
    uuids = []
    for i in range(n):
        uid = await _insert_tag(client, bench_tag_name(i))
        uuids.append(uid)

    tag_col = client.collections.get("Tag")
    t0 = time.perf_counter()
    await tag_col.data.delete_many(where=Filter.by_id().contains_any(uuids))
    elapsed = time.perf_counter() - t0

    return {
        "operation": "tag_delete_batch",
        "n": n,
        "total_time_ms": round(elapsed * 1000, 3),
        "throughput_ops_sec": round(n / elapsed, 2) if elapsed > 0 else 0,
    }


# ── 6. Query with tag reference filter (on Chunks) ─────────────────────────


async def bench_chunk_query_by_tag_ref(
    client: weaviate.WeaviateAsyncClient,
    chunk_uuids: list[str],
    iterations: int = 20,
) -> list[dict]:
    """
    Benchmark querying Chunks filtered by a tag reference,
    using different query styles: fetch_objects, bm25, near_vector placeholder.
    """
    tag_col = client.collections.get("Tag")
    chunks_col = client.collections.get("Chunks")

    # Create and attach a tag
    tag_uuid = await _insert_tag(client, bench_tag_name(6000))
    for cid in chunk_uuids:
        await _add_tag_ref(client, cid, tag_uuid)

    results = []

    # Style 1: fetch_objects with ref filter
    latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        await chunks_col.query.fetch_objects(
            filters=Filter.by_ref(link_on="automaticTag").by_id().contains_any([tag_uuid]),
            return_references=[QueryReference(link_on="automaticTag", return_properties=[])],
            limit=100,
        )
        latencies.append(time.perf_counter() - t0)
    stats = compute_stats(latencies)
    results.append({"operation": "chunk_query_by_tag_fetch_objects", "iterations": iterations, **stats.to_dict()})

    # Style 2: fetch_objects with ID filter (chunks that we know have the tag)
    latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        await chunks_col.query.fetch_objects(
            filters=(
                Filter.by_id().contains_any(chunk_uuids)
                & Filter.by_ref(link_on="automaticTag").by_id().contains_any([tag_uuid])
            ),
            return_references=[QueryReference(link_on="automaticTag", return_properties=["tag_name"])],
            limit=100,
        )
        latencies.append(time.perf_counter() - t0)
    stats = compute_stats(latencies)
    results.append({"operation": "chunk_query_by_tag_id_and_ref", "iterations": iterations, **stats.to_dict()})

    # Style 3: bm25 with tag ref filter
    latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        await chunks_col.query.bm25(
            query="benchmark",
            filters=Filter.by_ref(link_on="automaticTag").by_id().contains_any([tag_uuid]),
            return_references=[QueryReference(link_on="automaticTag", return_properties=[])],
            limit=100,
        )
        latencies.append(time.perf_counter() - t0)
    stats = compute_stats(latencies)
    results.append({"operation": "chunk_query_by_tag_bm25", "iterations": iterations, **stats.to_dict()})

    # Cleanup
    for cid in chunk_uuids:
        await _remove_tag_ref(client, cid, [tag_uuid])
    await tag_col.data.delete_many(where=Filter.by_id().contains_any([tag_uuid]))

    return results


# ── Main runner ──────────────────────────────────────────────────────────────


async def run_tag_benchmarks() -> list[dict]:
    """Execute the full tag benchmark suite and return results."""
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
        log.info("=== Tag insertion benchmarks ===")
        all_results.append(await bench_tag_insert_sequential(client, n))
        # Cleanup inserted tags
        await full_cleanup(client)

        for conc in cfg.CONCURRENCY_LEVELS:
            all_results.append(await bench_tag_insert_concurrent(client, n, conc))
            await full_cleanup(client)

        all_results.append(await bench_tag_insert_batch(client, n))
        await full_cleanup(client)

        # 2. Query (need some tags first)
        log.info("=== Tag query benchmarks ===")
        tag_uuids = []
        for i in range(n):
            uid = await _insert_tag(client, bench_tag_name(i))
            tag_uuids.append(uid)

        all_results.append(await bench_tag_fetch_all(client, 30))
        all_results.append(await bench_tag_fetch_by_id(client, tag_uuids[:20]))
        all_results.append(await bench_tag_fetch_filtered(client, 30))
        all_results.append(await bench_tag_fetch_contains_any(client, tag_uuids[:10], 30))
        all_results.append(await bench_tag_fetch_contains_any(client, tag_uuids, 30))
        await full_cleanup(client)

        # 3. Reference add (fullness)
        log.info("=== Tag reference addition (fullness) benchmarks ===")
        fullness_results = await bench_tag_ref_add_varying_fullness(
            client, chunk_uuids, cfg.FULLNESS_LEVELS,
        )
        all_results.extend(fullness_results)

        # 4. Reference add (concurrency)
        log.info("=== Tag reference addition (concurrency) benchmarks ===")
        conc_results = await bench_tag_ref_add_concurrent(
            client, chunk_uuids, cfg.CONCURRENCY_LEVELS,
        )
        all_results.extend(conc_results)

        # 5. Reference removal
        log.info("=== Tag reference removal benchmarks ===")
        all_results.append(await bench_tag_ref_remove(client, chunk_uuids))

        # 6. Deletion
        log.info("=== Tag deletion benchmarks ===")
        all_results.append(await bench_tag_delete_single(client, n))
        all_results.append(await bench_tag_delete_batch(client, n))

        # 7. Chunk query by tag ref
        log.info("=== Chunk query by tag reference benchmarks ===")
        query_results = await bench_chunk_query_by_tag_ref(client, chunk_uuids)
        all_results.extend(query_results)

    finally:
        # Final safety cleanup
        await full_cleanup(client)
        await client.close()

    save_results("tag_benchmarks", all_results)
    return all_results


if __name__ == "__main__":
    asyncio.run(run_tag_benchmarks())
