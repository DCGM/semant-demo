"""
Shared utilities: Weaviate connection, timing helpers, statistics, cleanup.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Sequence

import numpy as np
import weaviate
from weaviate.classes.query import Filter, QueryReference

from . import config as cfg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bench")


# ── Weaviate async client helper ────────────────────────────────────────────


async def get_client() -> weaviate.WeaviateAsyncClient:
    """Return a connected async Weaviate client."""
    client = weaviate.use_async_with_custom(
        http_host=cfg.WEAVIATE_HOST,
        http_port=cfg.WEAVIATE_REST_PORT,
        http_secure=False,
        grpc_host=cfg.WEAVIATE_HOST,
        grpc_port=cfg.WEAVIATE_GRPC_PORT,
        grpc_secure=False,
    )
    await client.connect()
    if not await client.is_ready():
        raise RuntimeError("Weaviate is not ready")
    return client


# ── Unique-name helpers ─────────────────────────────────────────────────────


def bench_tag_name(index: int = 0) -> str:
    return f"{cfg.BENCH_PREFIX}tag_{index}_{uuid.uuid4().hex[:8]}"


def bench_collection_name(index: int = 0) -> str:
    return f"{cfg.BENCH_PREFIX}col_{index}_{uuid.uuid4().hex[:8]}"


def bench_user_id() -> str:
    return f"{cfg.BENCH_PREFIX}user_{uuid.uuid4().hex[:8]}"


# ── Timing / statistics ─────────────────────────────────────────────────────


@dataclass
class LatencyStats:
    """Summary statistics for a list of latency samples (seconds)."""
    count: int = 0
    mean: float = 0.0
    median: float = 0.0
    p90: float = 0.0
    p99: float = 0.0
    min_val: float = 0.0
    max_val: float = 0.0
    throughput: float = 0.0  # ops / sec

    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "mean_ms": round(self.mean * 1000, 3),
            "median_ms": round(self.median * 1000, 3),
            "p90_ms": round(self.p90 * 1000, 3),
            "p99_ms": round(self.p99 * 1000, 3),
            "min_ms": round(self.min_val * 1000, 3),
            "max_ms": round(self.max_val * 1000, 3),
            "throughput_ops_sec": round(self.throughput, 2),
        }


def compute_stats(latencies: Sequence[float]) -> LatencyStats:
    """Compute stats from a list of per-operation latency values (seconds)."""
    if not latencies:
        return LatencyStats()
    arr = np.array(latencies)
    total_time = arr.sum()
    return LatencyStats(
        count=len(arr),
        mean=float(np.mean(arr)),
        median=float(np.median(arr)),
        p90=float(np.percentile(arr, 90)),
        p99=float(np.percentile(arr, 99)),
        min_val=float(np.min(arr)),
        max_val=float(np.max(arr)),
        throughput=len(arr) / total_time if total_time > 0 else 0.0,
    )


async def timed_call(coro_fn: Callable[..., Coroutine], *args: Any, **kwargs: Any) -> tuple[Any, float]:
    """Call an async function, returning (result, elapsed_seconds)."""
    t0 = time.perf_counter()
    result = await coro_fn(*args, **kwargs)
    return result, time.perf_counter() - t0


async def run_parallel(coro_fn: Callable[..., Coroutine], arg_list: list[tuple], concurrency: int) -> list[float]:
    """
    Run *coro_fn* for each set of args in *arg_list* with bounded concurrency.
    Returns per-call latencies.
    """
    sem = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    lock = asyncio.Lock()

    async def _worker(args: tuple):
        async with sem:
            _, elapsed = await timed_call(coro_fn, *args)
            async with lock:
                latencies.append(elapsed)

    await asyncio.gather(*[_worker(a) for a in arg_list])
    return latencies


# ── Cleanup ──────────────────────────────────────────────────────────────────


async def cleanup_benchmark_tags(client: weaviate.WeaviateAsyncClient):
    """Remove all Tag objects whose tag_name starts with the benchmark prefix."""
    tag_col = client.collections.get("Tag")
    # Fetch all tags with bench prefix
    # Weaviate text filter with Like operator
    results = await tag_col.query.fetch_objects(
        filters=Filter.by_property("tag_name").like(f"{cfg.BENCH_PREFIX}*"),
        limit=10000,
    )
    if not results.objects:
        log.info("No benchmark tags to clean up.")
        return
    uuids = [str(o.uuid) for o in results.objects]
    log.info(f"Cleaning up {len(uuids)} benchmark tags …")

    # Remove references from Chunks → benchmarked tags
    chunks_col = client.collections.get("Chunks")
    for ref_prop in ("automaticTag", "positiveTag", "negativeTag"):
        try:
            filtered = await chunks_col.query.fetch_objects(
                filters=Filter.by_ref(link_on=ref_prop).by_id().contains_any(uuids),
                return_references=[QueryReference(link_on=ref_prop, return_properties=[])],
                limit=10000,
            )
            for obj in filtered.objects:
                ref_block = obj.references.get(ref_prop) if obj.references else None
                if not ref_block:
                    continue
                current_ids = [str(r.uuid) for r in ref_block.objects]
                remaining = [rid for rid in current_ids if rid not in uuids]
                if len(remaining) != len(current_ids):
                    await chunks_col.data.reference_replace(
                        from_uuid=obj.uuid,
                        from_property=ref_prop,
                        to=remaining,
                    )
        except Exception as e:
            log.warning(f"Cleanup refs {ref_prop}: {e}")

    # Delete tag objects
    await tag_col.data.delete_many(
        where=Filter.by_property("tag_name").like(f"{cfg.BENCH_PREFIX}*"),
    )
    log.info("Benchmark tags cleaned up.")


async def cleanup_benchmark_collections(client: weaviate.WeaviateAsyncClient):
    """Remove all UserCollection objects whose name starts with the benchmark prefix."""
    uc_col = client.collections.get("UserCollection")
    results = await uc_col.query.fetch_objects(
        filters=Filter.by_property("name").like(f"{cfg.BENCH_PREFIX}*"),
        limit=10000,
    )
    if not results.objects:
        log.info("No benchmark user-collections to clean up.")
        return
    uuids = [str(o.uuid) for o in results.objects]
    log.info(f"Cleaning up {len(uuids)} benchmark user-collections …")

    # Remove references from Chunks → benchmark collections
    chunks_col = client.collections.get("Chunks")
    try:
        filtered = await chunks_col.query.fetch_objects(
            filters=Filter.by_ref(link_on="userCollection").by_id().contains_any(uuids),
            return_references=[QueryReference(link_on="userCollection", return_properties=[])],
            limit=10000,
        )
        for obj in filtered.objects:
            ref_block = obj.references.get("userCollection") if obj.references else None
            if not ref_block:
                continue
            current_ids = [str(r.uuid) for r in ref_block.objects]
            remaining = [rid for rid in current_ids if rid not in uuids]
            if len(remaining) != len(current_ids):
                await chunks_col.data.reference_replace(
                    from_uuid=obj.uuid,
                    from_property="userCollection",
                    to=remaining,
                )
    except Exception as e:
        log.warning(f"Cleanup collection refs: {e}")

    await uc_col.data.delete_many(
        where=Filter.by_property("name").like(f"{cfg.BENCH_PREFIX}*"),
    )
    log.info("Benchmark user-collections cleaned up.")


async def full_cleanup(client: weaviate.WeaviateAsyncClient):
    """Run all cleanup routines."""
    await cleanup_benchmark_tags(client)
    await cleanup_benchmark_collections(client)


# ── Result persistence ───────────────────────────────────────────────────────


def ensure_dirs():
    os.makedirs(cfg.RESULTS_DIR, exist_ok=True)
    os.makedirs(cfg.PLOTS_DIR, exist_ok=True)


def save_results(name: str, data: Any):
    ensure_dirs()
    path = os.path.join(cfg.RESULTS_DIR, f"{name}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    log.info(f"Results saved to {path}")


# ── Chunk sampling ──────────────────────────────────────────────────────────


async def sample_chunk_uuids(client: weaviate.WeaviateAsyncClient, n: int) -> list[str]:
    """Return up to *n* random Chunk UUIDs from the database."""
    chunks = client.collections.get("Chunks")
    # Weaviate doesn't have random sampling, but we can grab the first N
    result = await chunks.query.fetch_objects(limit=n)
    return [str(o.uuid) for o in result.objects]
