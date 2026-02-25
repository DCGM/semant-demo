"""
Main entry point — run all Weaviate benchmarks, then generate plots.

Usage:
    python -m weaviate_benchmarks.run_all          # run everything
    python -m weaviate_benchmarks.run_all --tags    # tags only
    python -m weaviate_benchmarks.run_all --cols    # collections only
    python -m weaviate_benchmarks.run_all --plots   # only regenerate plots from existing results
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

from .bench_tags import run_tag_benchmarks
from .bench_collections import run_collection_benchmarks
from .plotting import generate_all_plots
from .utils import ensure_dirs, log, get_client, full_cleanup
from . import config as cfg


def _print_summary(results: list[dict], title: str):
    """Pretty-print a summary table to stdout."""
    if not results:
        return
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}")
    header = f"{'Operation':<45} {'Mean':>8} {'Median':>8} {'P90':>8} {'P99':>8} {'Tput':>10}"
    print(header)
    print("-" * len(header))
    for r in results:
        op = r.get("operation", "?")
        mean = r.get("mean_ms", r.get("total_time_ms", "-"))
        median = r.get("median_ms", "-")
        p90 = r.get("p90_ms", "-")
        p99 = r.get("p99_ms", "-")
        tput = r.get("throughput_ops_sec", "-")

        # Format with concurrency / fullness info
        extra = ""
        if "concurrency" in r:
            extra = f" (c={r['concurrency']})"
        elif "fullness" in r:
            extra = f" (f={r['fullness']})"
        elif "n_ids" in r:
            extra = f" (ids={r['n_ids']})"

        def _fmt(v):
            if isinstance(v, (int, float)):
                return f"{v:>8.2f}"
            return f"{str(v):>8}"

        print(f"{(op + extra):<45} {_fmt(mean)} {_fmt(median)} {_fmt(p90)} {_fmt(p99)} {_fmt(tput)}")


async def _safety_cleanup():
    """Run cleanup against Weaviate to remove any stale benchmark data."""
    try:
        client = await get_client()
        await full_cleanup(client)
        await client.close()
    except Exception as e:
        log.warning(f"Pre-cleanup failed (Weaviate may be unreachable): {e}")


async def main():
    parser = argparse.ArgumentParser(description="Weaviate Benchmark Suite")
    parser.add_argument("--tags", action="store_true", help="Run tag benchmarks only")
    parser.add_argument("--cols", action="store_true", help="Run collection benchmarks only")
    parser.add_argument("--plots", action="store_true", help="Only regenerate plots from existing results")
    parser.add_argument("--cleanup", action="store_true", help="Only run cleanup (remove benchmark data)")
    args = parser.parse_args()

    ensure_dirs()
    run_all = not (args.tags or args.cols or args.plots or args.cleanup)

    if args.cleanup:
        log.info("Running cleanup only …")
        await _safety_cleanup()
        return

    if args.plots:
        generate_all_plots()
        return

    # Pre-run cleanup to remove stale data from aborted runs
    await _safety_cleanup()

    t_start = time.perf_counter()
    tag_results = []
    col_results = []

    if run_all or args.tags:
        log.info("╔══════════════════════════════════════════════╗")
        log.info("║        TAG BENCHMARKS                        ║")
        log.info("╚══════════════════════════════════════════════╝")
        tag_results = await run_tag_benchmarks()
        _print_summary(tag_results, "TAG BENCHMARK RESULTS")

    if run_all or args.cols:
        log.info("╔══════════════════════════════════════════════╗")
        log.info("║        COLLECTION BENCHMARKS                 ║")
        log.info("╚══════════════════════════════════════════════╝")
        col_results = await run_collection_benchmarks()
        _print_summary(col_results, "COLLECTION BENCHMARK RESULTS")

    elapsed = time.perf_counter() - t_start
    log.info(f"All benchmarks completed in {elapsed:.1f}s")

    # Generate plots
    log.info("Generating plots …")
    generate_all_plots()
    log.info("Done.")


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()
