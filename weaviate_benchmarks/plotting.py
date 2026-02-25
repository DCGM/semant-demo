"""
Generate benchmark result plots in PNG and SVG.

Reads JSON result files from the results/ directory and produces:
  - Latency comparison bar charts (mean, median, p90, p99)
  - Throughput charts
  - Concurrency scaling charts
  - Fullness impact charts
"""

from __future__ import annotations

import json
import os
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


def _bar_chart(
    title: str,
    labels: list[str],
    metric_groups: dict[str, list[float]],
    ylabel: str,
    filename: str,
):
    """
    Grouped bar chart.
    metric_groups: {"mean": [v1,v2,...], "median": [...], ...}
    """
    fig, ax = plt.subplots()
    x = np.arange(len(labels))
    n_groups = len(metric_groups)
    width = 0.8 / max(n_groups, 1)

    for i, (metric_name, values) in enumerate(metric_groups.items()):
        offset = (i - n_groups / 2 + 0.5) * width
        bars = ax.bar(x + offset, values, width, label=metric_name, color=COLORS[i % len(COLORS)])
        # Value labels on bars
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


# ── Plot generators ─────────────────────────────────────────────────────────


def plot_insertion_latency(results: list[dict], entity: str):
    """Bar chart comparing sequential, batch, and various concurrent insertion latencies."""
    seq = [r for r in results if r["operation"] == f"{entity}_insert_sequential"]
    conc = sorted(
        [r for r in results if r["operation"] == f"{entity}_insert_concurrent"],
        key=lambda r: r.get("concurrency", 0),
    )
    batch = [r for r in results if r["operation"] == f"{entity}_insert_batch"]

    labels = []
    means = []
    medians = []
    p90s = []
    p99s = []

    if seq:
        labels.append("Sequential")
        means.append(seq[0]["mean_ms"])
        medians.append(seq[0]["median_ms"])
        p90s.append(seq[0]["p90_ms"])
        p99s.append(seq[0]["p99_ms"])

    for r in conc:
        labels.append(f"Conc={r['concurrency']}")
        means.append(r["mean_ms"])
        medians.append(r["median_ms"])
        p90s.append(r["p90_ms"])
        p99s.append(r["p99_ms"])

    if not labels:
        return

    _bar_chart(
        title=f"{entity.title()} Insertion Latency",
        labels=labels,
        metric_groups={"Mean": means, "Median": medians, "P90": p90s, "P99": p99s},
        ylabel="Latency (ms)",
        filename=f"{entity}_insertion_latency",
    )

    # Throughput line chart for concurrent insertions
    if conc:
        conc_vals = [r["concurrency"] for r in conc]
        throughputs = [r["throughput_ops_sec"] for r in conc]
        _line_chart(
            title=f"{entity.title()} Insertion Throughput vs Concurrency",
            x_values=conc_vals,
            y_series={"Throughput": throughputs},
            xlabel="Concurrency",
            ylabel="Throughput (ops/sec)",
            filename=f"{entity}_insertion_throughput_vs_concurrency",
        )


def plot_query_latency(results: list[dict], entity: str):
    """Bar chart comparing different query styles."""
    query_ops = [r for r in results if "fetch" in r["operation"] and entity in r["operation"]]
    if not query_ops:
        return

    labels = [r["operation"].replace(f"{entity}_", "") for r in query_ops]
    _bar_chart(
        title=f"{entity.title()} Query Latency",
        labels=labels,
        metric_groups={
            "Mean": [r["mean_ms"] for r in query_ops],
            "Median": [r["median_ms"] for r in query_ops],
            "P90": [r["p90_ms"] for r in query_ops],
            "P99": [r["p99_ms"] for r in query_ops],
        },
        ylabel="Latency (ms)",
        filename=f"{entity}_query_latency",
    )


def plot_ref_add_fullness(results: list[dict], entity: str):
    """Line chart: reference add latency vs fullness level."""
    prefix = f"{entity}_ref_add"
    items = sorted(
        [r for r in results if r["operation"] == prefix and "fullness" in r],
        key=lambda r: r["fullness"],
    )
    if not items:
        return

    fullness = [r["fullness"] for r in items]
    _line_chart(
        title=f"{entity.title()} Ref-Add Latency vs Fullness",
        x_values=fullness,
        y_series={
            "Mean": [r["mean_ms"] for r in items],
            "Median": [r["median_ms"] for r in items],
            "P90": [r["p90_ms"] for r in items],
            "P99": [r["p99_ms"] for r in items],
        },
        xlabel="Existing refs per chunk (fullness)",
        ylabel="Latency (ms)",
        filename=f"{entity}_ref_add_vs_fullness",
    )


def plot_ref_add_concurrency(results: list[dict], entity: str):
    """Line chart: reference add latency & throughput vs concurrency."""
    prefix = f"{entity}_ref_add_concurrent"
    items = sorted(
        [r for r in results if r["operation"] == prefix],
        key=lambda r: r.get("concurrency", 0),
    )
    if not items:
        return

    conc = [r["concurrency"] for r in items]
    _line_chart(
        title=f"{entity.title()} Ref-Add Latency vs Concurrency",
        x_values=conc,
        y_series={
            "Mean": [r["mean_ms"] for r in items],
            "P90": [r["p90_ms"] for r in items],
            "P99": [r["p99_ms"] for r in items],
        },
        xlabel="Concurrency",
        ylabel="Latency (ms)",
        filename=f"{entity}_ref_add_latency_vs_concurrency",
    )

    _line_chart(
        title=f"{entity.title()} Ref-Add Throughput vs Concurrency",
        x_values=conc,
        y_series={"Throughput": [r["throughput_ops_sec"] for r in items]},
        xlabel="Concurrency",
        ylabel="Throughput (ops/sec)",
        filename=f"{entity}_ref_add_throughput_vs_concurrency",
    )


def plot_deletion_latency(results: list[dict], entity: str):
    """Bar chart comparing single vs batch deletion."""
    ops = [r for r in results if "delete" in r["operation"] and entity in r["operation"]]
    if not ops:
        return

    labels = [r["operation"].replace(f"{entity}_", "") for r in ops]
    # Some ops (batch) may lack per-item stats — use total_time_ms where available
    means = []
    throughputs = []
    for r in ops:
        means.append(r.get("mean_ms", r.get("total_time_ms", 0)))
        throughputs.append(r.get("throughput_ops_sec", 0))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    x = np.arange(len(labels))
    ax1.bar(x, means, color=COLORS[:len(labels)])
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)
    ax1.set_ylabel("Latency (ms)")
    ax1.set_title(f"{entity.title()} Deletion Latency")
    for i, v in enumerate(means):
        ax1.text(i, v, f"{v:.1f}", ha="center", va="bottom", fontsize=9)

    ax2.bar(x, throughputs, color=COLORS[:len(labels)])
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels)
    ax2.set_ylabel("Throughput (ops/sec)")
    ax2.set_title(f"{entity.title()} Deletion Throughput")
    for i, v in enumerate(throughputs):
        ax2.text(i, v, f"{v:.1f}", ha="center", va="bottom", fontsize=9)

    fig.tight_layout()
    _save(fig, f"{entity}_deletion")


def plot_chunk_query_styles(results: list[dict], entity: str):
    """Bar chart comparing different chunk query styles (by tag/collection ref)."""
    prefix = "chunk_query_by_"
    ops = [r for r in results if r["operation"].startswith(prefix) and entity in r["operation"]]
    if not ops:
        return

    labels = [r["operation"].replace(prefix, "").replace(f"{entity}_", "") for r in ops]
    _bar_chart(
        title=f"Chunk Query (by {entity.title()} ref) — Style Comparison",
        labels=labels,
        metric_groups={
            "Mean": [r["mean_ms"] for r in ops],
            "Median": [r["median_ms"] for r in ops],
            "P90": [r["p90_ms"] for r in ops],
            "P99": [r["p99_ms"] for r in ops],
        },
        ylabel="Latency (ms)",
        filename=f"chunk_query_by_{entity}_styles",
    )


def plot_ref_remove(results: list[dict], entity: str):
    """Bar chart for reference removal."""
    ops = [r for r in results if r["operation"] == f"{entity}_ref_remove"]
    if not ops:
        return
    r = ops[0]
    labels = ["Ref Remove"]
    _bar_chart(
        title=f"{entity.title()} Reference Removal Latency",
        labels=labels,
        metric_groups={
            "Mean": [r["mean_ms"]],
            "Median": [r["median_ms"]],
            "P90": [r["p90_ms"]],
            "P99": [r["p99_ms"]],
        },
        ylabel="Latency (ms)",
        filename=f"{entity}_ref_remove_latency",
    )


# ── Combined summary plot ───────────────────────────────────────────────────


def plot_combined_summary(tag_results: list[dict], col_results: list[dict]):
    """Side-by-side summary of tag vs collection operations."""
    # Pick representative operations
    op_pairs = [
        ("tag_insert_sequential", "col_insert_sequential", "Insert (seq)"),
        ("tag_ref_remove", "col_ref_remove", "Ref remove"),
        ("tag_delete_single", "col_delete_single", "Delete (single)"),
    ]

    tag_map = {r["operation"]: r for r in tag_results}
    col_map = {r["operation"]: r for r in col_results}

    labels = []
    tag_means = []
    col_means = []

    for t_op, c_op, label in op_pairs:
        t = tag_map.get(t_op)
        c = col_map.get(c_op)
        if t and c:
            labels.append(label)
            tag_means.append(t["mean_ms"])
            col_means.append(c["mean_ms"])

    if not labels:
        return

    fig, ax = plt.subplots()
    x = np.arange(len(labels))
    w = 0.35
    ax.bar(x - w / 2, tag_means, w, label="Tag", color=COLORS[0])
    ax.bar(x + w / 2, col_means, w, label="Collection", color=COLORS[1])
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Mean Latency (ms)")
    ax.set_title("Tag vs Collection — Operation Comparison")
    ax.legend()
    fig.tight_layout()
    _save(fig, "combined_summary")


# ── Entry point ──────────────────────────────────────────────────────────────


def generate_all_plots():
    """Load results and generate all plots."""
    tag_results = _load_results("tag_benchmarks.json")
    col_results = _load_results("collection_benchmarks.json")

    if tag_results:
        plot_insertion_latency(tag_results, "tag")
        plot_query_latency(tag_results, "tag")
        plot_ref_add_fullness(tag_results, "tag")
        plot_ref_add_concurrency(tag_results, "tag")
        plot_ref_remove(tag_results, "tag")
        plot_deletion_latency(tag_results, "tag")
        plot_chunk_query_styles(tag_results, "tag")

    if col_results:
        plot_insertion_latency(col_results, "col")
        plot_query_latency(col_results, "col")
        plot_ref_add_fullness(col_results, "col")
        plot_ref_add_concurrency(col_results, "col")
        plot_ref_remove(col_results, "col")
        plot_deletion_latency(col_results, "col")
        plot_chunk_query_styles(col_results, "col")

    if tag_results and col_results:
        plot_combined_summary(tag_results, col_results)

    print(f"Plots saved to {cfg.PLOTS_DIR}")


if __name__ == "__main__":
    generate_all_plots()
