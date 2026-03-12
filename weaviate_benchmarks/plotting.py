"""
Generate benchmark result plots in PNG and SVG.

Reads JSON result files from the results/ directory and produces:
  - Read latency/throughput vs fullness (concurrent & batch)
  - Ref-add latency/throughput vs fullness (concurrent & batch)
  - Ref-remove latency/throughput vs fullness (concurrent & batch)
  - Concurrency scaling charts
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Any

import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import numpy as np

from . import config as cfg
from .utils import ensure_dirs

# ── Styling ──────────────────────────────────────────────────────────────────

plt.rcParams.update({
    "figure.figsize": (10, 6),
    "axes.grid": True,
    "grid.alpha": 0.3,
    "font.size": 11,
})

COLORS = ["#2196F3", "#FF9800", "#4CAF50", "#E91E63", "#9C27B0", "#00BCD4", "#795548"]


def _save(fig: plt.Figure, name: str):
    ensure_dirs()
    for ext in ("png", "svg"):
        path = os.path.join(cfg.PLOTS_DIR, f"{name}.{ext}")
        fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _load_results(filename: str) -> list[dict]:
    path = os.path.join(cfg.RESULTS_DIR, filename)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


# ── Generic chart builders ──────────────────────────────────────────────────


def _line_chart(
    title: str,
    x_values: list[float],
    y_series: dict[str, list[float]],
    xlabel: str,
    ylabel: str,
    filename: str,
):
    fig, ax = plt.subplots()
    for i, (label, ys) in enumerate(y_series.items()):
        ax.plot(x_values[:len(ys)], ys, marker="o", label=label, color=COLORS[i % len(COLORS)])
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    _save(fig, filename)


def _bar_chart(
    title: str,
    labels: list[str],
    metric_groups: dict[str, list[float]],
    ylabel: str,
    filename: str,
):
    """Grouped bar chart."""
    fig, ax = plt.subplots()
    x = np.arange(len(labels))
    n_groups = len(metric_groups)
    width = 0.8 / max(n_groups, 1)

    for i, (metric_name, values) in enumerate(metric_groups.items()):
        offset = (i - n_groups / 2 + 0.5) * width
        bars = ax.bar(x + offset, values, width, label=metric_name, color=COLORS[i % len(COLORS)])
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{val:.1f}",
                ha="center", va="bottom", fontsize=8,
            )

    ax.set_xlabel("Operation")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.legend()
    fig.tight_layout()
    _save(fig, filename)


# ── Aggregation helpers ─────────────────────────────────────────────────────


def _aggregate_by(results: list[dict], operation: str, group_key: str) -> dict[Any, list[dict]]:
    """Group matching results by a key (e.g. 'fullness' or 'concurrency')."""
    groups: dict[Any, list[dict]] = defaultdict(list)
    for r in results:
        if r["operation"] == operation and group_key in r:
            groups[r[group_key]].append(r)
    return dict(sorted(groups.items()))


def _mean_of(dicts: list[dict], key: str) -> float:
    vals = [d[key] for d in dicts if key in d]
    return sum(vals) / len(vals) if vals else 0.0


# ── Plot generators ─────────────────────────────────────────────────────────


def plot_read_vs_fullness(results: list[dict]):
    """Read throughput & latency vs fullness — concurrent and batch."""
    # Concurrent reads (aggregate across concurrency levels for each fullness)
    conc_by_full = _aggregate_by(results, "read_concurrent", "fullness")
    batch_by_full = _aggregate_by(results, "read_batch", "fullness")

    if not conc_by_full and not batch_by_full:
        return

    x_vals = sorted(set(list(conc_by_full.keys()) + list(batch_by_full.keys())))

    # Throughput
    y_tput: dict[str, list[float]] = {}
    if conc_by_full:
        y_tput["Concurrent (avg)"] = [_mean_of(conc_by_full.get(f, []), "throughput_chunks_sec") for f in x_vals]
    if batch_by_full:
        y_tput["Batch"] = [_mean_of(batch_by_full.get(f, []), "throughput_chunks_sec") for f in x_vals]
    if y_tput:
        _line_chart("Read Throughput vs Fullness", x_vals, y_tput,
                     "Existing refs per chunk (fullness)", "Throughput (chunks/sec)",
                     "read_throughput_vs_fullness")

    # Latency
    y_lat: dict[str, list[float]] = {}
    if conc_by_full:
        y_lat["Concurrent Mean"] = [_mean_of(conc_by_full.get(f, []), "mean_ms") for f in x_vals]
        y_lat["Concurrent P90"] = [_mean_of(conc_by_full.get(f, []), "p90_ms") for f in x_vals]
    if batch_by_full:
        y_lat["Batch Mean"] = [_mean_of(batch_by_full.get(f, []), "mean_ms") for f in x_vals]
    if y_lat:
        _line_chart("Read Latency vs Fullness", x_vals, y_lat,
                     "Existing refs per chunk (fullness)", "Latency (ms)",
                     "read_latency_vs_fullness")


def plot_read_vs_concurrency(results: list[dict]):
    """Read throughput & latency vs concurrency (at each fullness level)."""
    conc_items = [r for r in results if r["operation"] == "read_concurrent"]
    if not conc_items:
        return

    # Group by fullness
    by_full: dict[int, list[dict]] = defaultdict(list)
    for r in conc_items:
        by_full[r["fullness"]].append(r)

    all_conc = sorted(set(r["concurrency"] for r in conc_items))

    # Throughput per fullness
    y_tput: dict[str, list[float]] = {}
    for f in sorted(by_full.keys()):
        by_c = {r["concurrency"]: r for r in by_full[f]}
        y_tput[f"f={f}"] = [by_c.get(c, {}).get("throughput_chunks_sec", 0) for c in all_conc]
    _line_chart("Read Throughput vs Concurrency", all_conc, y_tput,
                "Concurrency", "Throughput (chunks/sec)", "read_throughput_vs_concurrency")


def plot_ref_add_vs_fullness(results: list[dict]):
    """Ref-add throughput & latency vs fullness — concurrent and batch."""
    conc_by_full = _aggregate_by(results, "ref_add_concurrent", "fullness")
    batch_by_full = _aggregate_by(results, "ref_add_batch", "fullness")

    if not conc_by_full and not batch_by_full:
        return

    x_vals = sorted(set(list(conc_by_full.keys()) + list(batch_by_full.keys())))

    # Throughput
    y_tput: dict[str, list[float]] = {}
    if conc_by_full:
        y_tput["Concurrent (avg)"] = [_mean_of(conc_by_full.get(f, []), "throughput_chunks_sec") for f in x_vals]
    if batch_by_full:
        y_tput["Batch"] = [_mean_of(batch_by_full.get(f, []), "throughput_chunks_sec") for f in x_vals]
    if y_tput:
        _line_chart("Ref-Add Throughput vs Fullness", x_vals, y_tput,
                     "Existing refs per chunk (fullness)", "Throughput (chunks/sec)",
                     "ref_add_throughput_vs_fullness")

    # Latency
    y_lat: dict[str, list[float]] = {}
    if conc_by_full:
        y_lat["Concurrent Mean"] = [_mean_of(conc_by_full.get(f, []), "mean_ms") for f in x_vals]
        y_lat["Concurrent P90"] = [_mean_of(conc_by_full.get(f, []), "p90_ms") for f in x_vals]
    if batch_by_full:
        # For batch ops, derive per-chunk latency from total_time_ms / n_chunks
        def _batch_per_chunk(items):
            vals = []
            for r in items:
                n = r.get("n_chunks", 1)
                vals.append(r.get("total_time_ms", 0) / n if n else 0)
            return sum(vals) / len(vals) if vals else 0
        y_lat["Batch Mean (per chunk)"] = [_batch_per_chunk(batch_by_full.get(f, [])) for f in x_vals]
    if y_lat:
        _line_chart("Ref-Add Latency vs Fullness", x_vals, y_lat,
                     "Existing refs per chunk (fullness)", "Latency (ms)",
                     "ref_add_latency_vs_fullness")


def plot_ref_add_vs_concurrency(results: list[dict]):
    """Ref-add throughput vs concurrency (at each fullness level)."""
    conc_items = [r for r in results if r["operation"] == "ref_add_concurrent"]
    if not conc_items:
        return

    by_full: dict[int, list[dict]] = defaultdict(list)
    for r in conc_items:
        by_full[r["fullness"]].append(r)

    all_conc = sorted(set(r["concurrency"] for r in conc_items))

    y_tput: dict[str, list[float]] = {}
    for f in sorted(by_full.keys()):
        by_c = defaultdict(list)
        for r in by_full[f]:
            by_c[r["concurrency"]].append(r.get("throughput_chunks_sec", 0))
        y_tput[f"f={f}"] = [sum(by_c.get(c, [0])) / len(by_c.get(c, [1])) for c in all_conc]
    _line_chart("Ref-Add Throughput vs Concurrency", all_conc, y_tput,
                "Concurrency", "Throughput (chunks/sec)", "ref_add_throughput_vs_concurrency")


def plot_ref_remove_vs_fullness(results: list[dict]):
    """Ref-remove throughput & latency vs fullness — concurrent and batch."""
    conc_by_full = _aggregate_by(results, "ref_remove_concurrent", "fullness")
    batch_by_full = _aggregate_by(results, "ref_remove_batch", "fullness")

    if not conc_by_full and not batch_by_full:
        return

    x_vals = sorted(set(list(conc_by_full.keys()) + list(batch_by_full.keys())))

    # Throughput
    y_tput: dict[str, list[float]] = {}
    if conc_by_full:
        y_tput["Concurrent (avg)"] = [_mean_of(conc_by_full.get(f, []), "throughput_chunks_sec") for f in x_vals]
    if batch_by_full:
        y_tput["Batch"] = [_mean_of(batch_by_full.get(f, []), "throughput_chunks_sec") for f in x_vals]
    if y_tput:
        _line_chart("Ref-Remove Throughput vs Fullness", x_vals, y_tput,
                     "Existing refs per chunk (fullness)", "Throughput (chunks/sec)",
                     "ref_remove_throughput_vs_fullness")

    # Latency
    y_lat: dict[str, list[float]] = {}
    if conc_by_full:
        y_lat["Concurrent Mean"] = [_mean_of(conc_by_full.get(f, []), "mean_ms") for f in x_vals]
        y_lat["Concurrent P90"] = [_mean_of(conc_by_full.get(f, []), "p90_ms") for f in x_vals]
    if batch_by_full:
        def _batch_per_chunk(items):
            vals = []
            for r in items:
                n = r.get("n_chunks", 1)
                vals.append(r.get("total_time_ms", 0) / n if n else 0)
            return sum(vals) / len(vals) if vals else 0
        y_lat["Batch Mean (per chunk)"] = [_batch_per_chunk(batch_by_full.get(f, [])) for f in x_vals]
    if y_lat:
        _line_chart("Ref-Remove Latency vs Fullness", x_vals, y_lat,
                     "Existing refs per chunk (fullness)", "Latency (ms)",
                     "ref_remove_latency_vs_fullness")


def plot_ref_remove_vs_concurrency(results: list[dict]):
    """Ref-remove throughput vs concurrency (at each fullness level)."""
    conc_items = [r for r in results if r["operation"] == "ref_remove_concurrent"]
    if not conc_items:
        return

    by_full: dict[int, list[dict]] = defaultdict(list)
    for r in conc_items:
        by_full[r["fullness"]].append(r)

    all_conc = sorted(set(r["concurrency"] for r in conc_items))

    y_tput: dict[str, list[float]] = {}
    for f in sorted(by_full.keys()):
        by_c = defaultdict(list)
        for r in by_full[f]:
            by_c[r["concurrency"]].append(r.get("throughput_chunks_sec", 0))
        y_tput[f"f={f}"] = [sum(by_c.get(c, [0])) / len(by_c.get(c, [1])) for c in all_conc]
    _line_chart("Ref-Remove Throughput vs Concurrency", all_conc, y_tput,
                "Concurrency", "Throughput (chunks/sec)", "ref_remove_throughput_vs_concurrency")


def plot_all_operations_summary(results: list[dict]):
    """Bar chart comparing mean latency of all operation types at fullness=0."""
    ops = ["read_concurrent", "read_batch", "ref_add_concurrent", "ref_add_batch",
           "ref_remove_concurrent", "ref_remove_batch"]
    labels = []
    means = []
    for op in ops:
        items = [r for r in results if r["operation"] == op and r.get("fullness", 0) == 0]
        if items:
            mean = _mean_of(items, "mean_ms") if "mean_ms" in items[0] else (
                _mean_of(items, "total_time_ms") / max(items[0].get("n_chunks", 1), 1)
            )
            labels.append(op.replace("_", " ").title())
            means.append(mean)

    if not labels:
        return

    _bar_chart("Operation Latency Comparison (fullness=0)", labels,
               {"Mean (ms)": means}, "Latency (ms)", "operation_summary")


# ── Entry point ──────────────────────────────────────────────────────────────


def generate_all_plots():
    """Load results and generate all plots."""
    results = _load_results("tag_benchmarks.json")

    if not results:
        print("No results found. Run benchmarks first.")
        return

    plot_read_vs_fullness(results)
    plot_read_vs_concurrency(results)
    plot_ref_add_vs_fullness(results)
    plot_ref_add_vs_concurrency(results)
    plot_ref_remove_vs_fullness(results)
    plot_ref_remove_vs_concurrency(results)
    plot_all_operations_summary(results)

    print(f"Plots saved to {cfg.PLOTS_DIR}")


if __name__ == "__main__":
    generate_all_plots()
