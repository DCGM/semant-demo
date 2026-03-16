"""
Focused benchmarks for Tag ↔ Chunk reference operations.

Measures only what matters:
  - Latency & throughput of adding tag references to chunks
  - Latency & throughput of removing tag references from chunks
  - Speed of loading/querying chunks that carry tag references

Tests are performed with:
  - Varying concurrency (single operations)
  - Batch operations

Efficient flow (minimises setup/teardown overhead):
  0. Validate collections exist and have enough chunks.
  1. Insert tags needed for the whole test.
  2. For each fullness level:
     a. Batch-add references to reach the target fullness.
     b. Concurrent read test (all affected chunks).
     c. Batch read test (batches of READ_BATCH_SIZE chunks).
     d. Concurrent insertion test (OPERATION_COUNT refs).
     e. Concurrent deletion test (remove refs from step d).
     f. Batch insertion test (OPERATION_COUNT refs).
     g. Batch deletion test (remove refs from step f).
  3. Final cleanup — delete all benchmark tags & references.
  4. Render plots, generate report, print result tables.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

import weaviate
from tqdm import tqdm
from weaviate.classes.query import Filter, QueryReference
from weaviate.collections.classes.data import DataObject, DataReference

from . import config as cfg
from .utils import (
    bench_tag_name,
    compute_stats,
    compute_concurrent_stats,
    full_cleanup,
    get_client,
    log,
    run_parallel,
    sample_chunk_uuids,
    save_results,
    timed_call,
    validate_collections,
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


async def _insert_tags(client: weaviate.WeaviateAsyncClient, count: int) -> list[str]:
    """Batch-insert *count* benchmark tags and return their UUIDs."""
    tag_col = client.collections.get(cfg.TAG_COLLECTION)
    objects = []
    for i in range(count):
        uid = uuid.uuid4()
        objects.append(DataObject(properties=_tag_props(bench_tag_name(i)), uuid=uid))
    await tag_col.data.insert_many(objects)
    return [str(o.uuid) for o in objects]


async def _batch_add_refs(
    client: weaviate.WeaviateAsyncClient,
    chunk_uuids: list[str],
    tag_uuids: list[str],
    ref_prop: str = "automaticTag",
):
    """Batch-add tag references from every chunk to every tag."""
    chunks_col = client.collections.get(cfg.CHUNKS_COLLECTION)
    refs = [
        DataReference(from_property=ref_prop, from_uuid=cid, to_uuid=tid)
        for cid in chunk_uuids
        for tid in tag_uuids
    ]
    if refs:
        await chunks_col.data.reference_add_many(refs)


# ── Single-op primitives (used by concurrent tests) ────────────────────────


async def _add_one_ref(client: weaviate.WeaviateAsyncClient, chunk_uuid: str, tag_uuid: str, ref_prop: str = "automaticTag"):
    """Add a single tag reference to a single chunk."""
    chunks_col = client.collections.get(cfg.CHUNKS_COLLECTION)
    await chunks_col.data.reference_add(
        from_uuid=chunk_uuid,
        from_property=ref_prop,
        to=tag_uuid,
    )


async def _remove_one_ref(client: weaviate.WeaviateAsyncClient, chunk_uuid: str, tag_uuid: str, ref_prop: str = "automaticTag"):
    """Remove a single tag reference from a single chunk (read-modify-write)."""
    chunks_col = client.collections.get(cfg.CHUNKS_COLLECTION)
    obj = await chunks_col.query.fetch_object_by_id(
        chunk_uuid,
        return_references=[QueryReference(link_on=ref_prop, return_properties=[])],
    )
    refs = obj.references.get(ref_prop) if obj and obj.references else None
    current = [str(r.uuid) for r in refs.objects] if refs else []
    remaining = [u for u in current if u != tag_uuid]
    await chunks_col.data.reference_replace(
        from_uuid=chunk_uuid,
        from_property=ref_prop,
        to=remaining,
    )


async def _read_chunk_with_refs(client: weaviate.WeaviateAsyncClient, chunk_uuid: str, ref_prop: str = "automaticTag"):
    """Fetch a single chunk including its tag references."""
    chunks_col = client.collections.get(cfg.CHUNKS_COLLECTION)
    await chunks_col.query.fetch_object_by_id(
        chunk_uuid,
        return_references=[QueryReference(link_on=ref_prop, return_properties=["tag_name"])],
    )


# ── Benchmark functions ─────────────────────────────────────────────────────


async def bench_read_concurrent(
    client: weaviate.WeaviateAsyncClient,
    chunk_uuids: list[str],
    fullness: int,
    concurrency: int,
) -> dict:
    """Read all affected chunks concurrently, returning tag references."""
    args = [(client, cid) for cid in chunk_uuids]
    latencies, wall_time = await run_parallel(_read_chunk_with_refs, args, concurrency)
    stats = compute_concurrent_stats(latencies, wall_time)
    return {
        "operation": "read_concurrent",
        "fullness": fullness,
        "concurrency": concurrency,
        "n_chunks": len(chunk_uuids),
        **stats.to_dict(),
    }


async def bench_read_batch(
    client: weaviate.WeaviateAsyncClient,
    chunk_uuids: list[str],
    fullness: int,
    batch_size: int,
) -> dict:
    """Read all chunks in batches of *batch_size* using contains_any ID filter."""
    chunks_col = client.collections.get(cfg.CHUNKS_COLLECTION)
    batch_latencies: list[float] = []
    actual_batch_sizes: list[int] = []
    for i in range(0, len(chunk_uuids), batch_size):
        batch = chunk_uuids[i : i + batch_size]
        t0 = time.perf_counter()
        await chunks_col.query.fetch_objects(
            filters=Filter.by_id().contains_any(batch),
            return_references=[QueryReference(link_on="automaticTag", return_properties=["tag_name"])],
            limit=batch_size,
        )
        batch_latencies.append(time.perf_counter() - t0)
        actual_batch_sizes.append(len(batch))
    # Convert per-batch latencies to per-chunk latencies for meaningful stats
    per_chunk_latencies = [lat / sz for lat, sz in zip(batch_latencies, actual_batch_sizes) if sz > 0]
    stats = compute_stats(per_chunk_latencies)
    # Throughput: total chunks processed divided by total elapsed wall time.
    # This overrides the value produced by compute_stats (which counts batches, not chunks).
    total_time = sum(batch_latencies)
    throughput = len(chunk_uuids) / total_time if total_time > 0 else 0.0
    return {
        "operation": "read_batch",
        "fullness": fullness,
        "batch_size": batch_size,
        "n_chunks": len(chunk_uuids),
        "n_batches": len(batch_latencies),
        **stats.to_dict(),
        "throughput_chunks_sec": round(throughput, 2),
    }


async def bench_ref_add_concurrent(
    client: weaviate.WeaviateAsyncClient,
    chunk_uuids: list[str],
    tag_uuid: str,
    fullness: int,
    concurrency: int,
) -> dict:
    """Add one tag reference to each chunk concurrently."""
    args = [(client, cid, tag_uuid) for cid in chunk_uuids]
    latencies, wall_time = await run_parallel(_add_one_ref, args, concurrency)
    stats = compute_concurrent_stats(latencies, wall_time)
    return {
        "operation": "ref_add_concurrent",
        "fullness": fullness,
        "concurrency": concurrency,
        "n_chunks": len(chunk_uuids),
        **stats.to_dict(),
    }


async def bench_ref_remove_concurrent(
    client: weaviate.WeaviateAsyncClient,
    chunk_uuids: list[str],
    tag_uuid: str,
    fullness: int,
    concurrency: int,
) -> dict:
    """Remove one tag reference from each chunk concurrently."""
    args = [(client, cid, tag_uuid) for cid in chunk_uuids]
    latencies, wall_time = await run_parallel(_remove_one_ref, args, concurrency)
    stats = compute_concurrent_stats(latencies, wall_time)
    return {
        "operation": "ref_remove_concurrent",
        "fullness": fullness,
        "concurrency": concurrency,
        "n_chunks": len(chunk_uuids),
        **stats.to_dict(),
    }


async def bench_ref_add_batch(
    client: weaviate.WeaviateAsyncClient,
    chunk_uuids: list[str],
    tag_uuid: str,
    fullness: int,
) -> dict:
    """Batch-add one tag reference to all chunks (single API call)."""
    chunks_col = client.collections.get(cfg.CHUNKS_COLLECTION)
    refs = [
        DataReference(from_property="automaticTag", from_uuid=cid, to_uuid=tag_uuid)
        for cid in chunk_uuids
    ]
    t0 = time.perf_counter()
    await chunks_col.data.reference_add_many(refs)
    elapsed = time.perf_counter() - t0
    n = len(chunk_uuids)
    return {
        "operation": "ref_add_batch",
        "fullness": fullness,
        "n_chunks": n,
        "total_time_ms": round(elapsed * 1000, 3),
        "throughput_chunks_sec": round(n / elapsed, 2) if elapsed > 0 else 0,
    }


async def bench_ref_remove_batch(
    client: weaviate.WeaviateAsyncClient,
    chunk_uuids: list[str],
    tag_uuid: str,
    fullness: int,
) -> dict:
    """Batch-remove one tag reference from all chunks.

    Each batch targets a single tag across all chunks using reference_replace.
    """
    chunks_col = client.collections.get(cfg.CHUNKS_COLLECTION)
    t0 = time.perf_counter()
    for cid in chunk_uuids:
        obj = await chunks_col.query.fetch_object_by_id(
            cid,
            return_references=[QueryReference(link_on="automaticTag", return_properties=[])],
        )
        refs = obj.references.get("automaticTag") if obj and obj.references else None
        current = [str(r.uuid) for r in refs.objects] if refs else []
        remaining = [u for u in current if u != tag_uuid]
        await chunks_col.data.reference_replace(
            from_uuid=cid,
            from_property="automaticTag",
            to=remaining,
        )
    elapsed = time.perf_counter() - t0
    n = len(chunk_uuids)
    return {
        "operation": "ref_remove_batch",
        "fullness": fullness,
        "n_chunks": n,
        "total_time_ms": round(elapsed * 1000, 3),
        "throughput_chunks_sec": round(n / elapsed, 2) if elapsed > 0 else 0,
    }


# ── Main runner ──────────────────────────────────────────────────────────────


async def run_tag_benchmarks() -> list[dict]:
    """Execute the focused benchmark suite and return results.

    Flow per fullness level:
      1. Batch-add refs to reach target fullness.
      2. Concurrent read test.
      3. Batch read test.
      4. For each concurrency level:
         a. Concurrent ref-add (OPERATION_COUNT tags).
         b. Concurrent ref-remove (same tags).
      5. Batch ref-add (OPERATION_COUNT tags).
      6. Batch ref-remove (same tags).
    """
    client = await get_client()
    all_results: list[dict] = []

    try:
        # 0. Validate
        if not await validate_collections(client):
            return []

        chunk_uuids = await sample_chunk_uuids(client, cfg.CHUNK_SAMPLE_SIZE)
        if not chunk_uuids:
            log.error("No chunks found in database, cannot run benchmarks.")
            return []
        log.info(f"Sampled {len(chunk_uuids)} chunks (shuffled) for benchmarks.")

        # 1. Pre-create all tags we will ever need
        max_fullness = max(cfg.FULLNESS_LEVELS) if cfg.FULLNESS_LEVELS else 0
        total_tags_needed = max_fullness + cfg.OPERATION_COUNT
        log.info(f"Inserting {total_tags_needed} benchmark tags …")
        all_tag_uuids = await _insert_tags(client, total_tags_needed)

        # Split into fullness tags and measurement tags
        fullness_tags = all_tag_uuids[:max_fullness]
        measurement_tags = all_tag_uuids[max_fullness:]

        prev_fullness = 0
        fullness_levels = sorted(cfg.FULLNESS_LEVELS)

        fullness_bar = tqdm(fullness_levels, desc="Fullness levels", unit="lvl")
        for fullness in fullness_bar:
            fullness_bar.set_postfix(fullness=fullness)

            # 2. Add references to reach this fullness level (incremental)
            new_tags_to_add = fullness_tags[prev_fullness:fullness]
            if new_tags_to_add:
                fullness_bar.write(f"  Batch-adding {len(new_tags_to_add)} refs/chunk to reach fullness={fullness}")
                await _batch_add_refs(client, chunk_uuids, new_tags_to_add)
            prev_fullness = fullness

            # 3. Concurrent read test
            for conc in tqdm(cfg.CONCURRENCY_LEVELS, desc=f"  f={fullness} read conc", leave=False):
                result = await bench_read_concurrent(client, chunk_uuids, fullness, conc)
                all_results.append(result)

            # 4. Batch read test
            result = await bench_read_batch(client, chunk_uuids, fullness, cfg.READ_BATCH_SIZE)
            all_results.append(result)

            # 5. Concurrent ref-add / ref-remove for each concurrency level
            for conc in tqdm(cfg.CONCURRENCY_LEVELS, desc=f"  f={fullness} ref add/rm conc", leave=False):
                op_tags = measurement_tags[: cfg.OPERATION_COUNT]

                for tag_uuid in op_tags:
                    result = await bench_ref_add_concurrent(
                        client, chunk_uuids, tag_uuid, fullness, conc,
                    )
                    all_results.append(result)

                for tag_uuid in op_tags:
                    result = await bench_ref_remove_concurrent(
                        client, chunk_uuids, tag_uuid, fullness, conc,
                    )
                    all_results.append(result)

            # 6. Batch ref-add / ref-remove
            op_tags = measurement_tags[: cfg.OPERATION_COUNT]

            for tag_uuid in tqdm(op_tags, desc=f"  f={fullness} ref-add batch", leave=False):
                result = await bench_ref_add_batch(client, chunk_uuids, tag_uuid, fullness)
                all_results.append(result)

            for tag_uuid in tqdm(op_tags, desc=f"  f={fullness} ref-rm batch", leave=False):
                result = await bench_ref_remove_batch(client, chunk_uuids, tag_uuid, fullness)
                all_results.append(result)

        log.info("All fullness levels complete.")

    finally:
        # 9. Final cleanup
        log.info("Final cleanup …")
        await full_cleanup(client)
        await client.close()

    save_results("tag_benchmarks", all_results)
    return all_results


if __name__ == "__main__":
    asyncio.run(run_tag_benchmarks())
