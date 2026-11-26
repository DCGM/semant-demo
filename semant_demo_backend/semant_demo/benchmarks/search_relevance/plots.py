"""Static report plots (matplotlib, non-interactive Agg backend), saved as PNG and SVG (#728)."""
from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

PRIMARY, SECONDARY = "#2a78d6", "#eb6834"
"""Categorical slots 1 and 2 of the shared chart palette (``dataviz`` skill)."""
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def _pyplot():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": MUTED,
                         "axes.labelcolor": INK, "text.color": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                         "axes.spines.top": False, "axes.spines.right": False, "font.size": 9,
                         "svg.hashsalt": "semant-benchmark", "svg.fonttype": "none"})
    return plt


def _save(fig: Any, out: Path, name: str) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = [out / f"{name}.png", out / f"{name}.svg"]
    fig.savefig(paths[0], dpi=150, bbox_inches="tight", metadata={"Software": None})
    fig.savefig(paths[1], bbox_inches="tight", metadata={"Date": None, "Creator": None})
    fig.clf()
    import matplotlib.pyplot as plt

    plt.close(fig)
    return paths


def _errors(entries: Sequence[dict[str, Any]]) -> tuple[list[float], list[list[float]]]:
    means = [e["mean"] or 0.0 for e in entries]
    low = [0.0 if e["low"] is None else max(0.0, e["mean"] - e["low"]) for e in entries]
    high = [0.0 if e["high"] is None else max(0.0, e["high"] - e["mean"]) for e in entries]
    return means, [low, high]


def metric_bars(labels: Sequence[str], standard: Sequence[dict[str, Any]], condensed: Sequence[dict[str, Any]],
                metric: str, out: Path, name: str) -> list[Path]:
    """Bars of the standard (primary) metric with 95% CIs per configuration, the condensed variant as dots."""
    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(max(4.0, 0.9 * len(labels) + 2), 3.2))
    means, errors = _errors(standard)
    x = range(len(labels))
    ax.bar(x, means, width=0.6, color=PRIMARY, label=f"{metric} (standard, unjudged = not relevant)",
           yerr=errors, error_kw={"ecolor": INK, "elinewidth": 1, "capsize": 3}, zorder=2)
    ax.scatter(x, [e["mean"] if e["mean"] is not None else math.nan for e in condensed], s=40, color=SECONDARY,
               edgecolors=SURFACE, linewidths=2, label=f"{metric} (condensed, unjudged removed)", zorder=3)
    ax.set_xticks(list(x), labels, rotation=30 if len(labels) > 4 else 0, ha="right" if len(labels) > 4 else "center")
    ax.set_ylim(0, 1)
    ax.set_ylabel(metric)
    ax.yaxis.grid(True, color=GRID, zorder=0)
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.18 if len(labels) <= 4 else -0.35), frameon=False, ncol=1)
    ax.set_title(f"{metric} by configuration (95% CI, intents resampled)", loc="left")
    return _save(fig, out, name)


def matrices(titles: Sequence[str], grids: Sequence[list[list[float | None]]], rows: Sequence[str],
             columns: Sequence[str], out: Path, name: str, *, label: str, diverging: bool = False) -> list[Path]:
    """Small multiples of annotated heatmaps (rows: query language, columns: source language)."""
    plt = _pyplot()
    import numpy as np

    n = len(grids)
    cols = min(n, 3)
    nrows = math.ceil(n / cols)
    fig, axes = plt.subplots(nrows, cols, figsize=(3.2 * cols + 0.8, 2.9 * nrows), squeeze=False,
                             layout="constrained")
    values = [v for g in grids for r in g for v in r if v is not None]
    if diverging:
        bound = max([abs(v) for v in values] + [0.05])
        cmap, vmin, vmax = "RdBu", -bound, bound
    else:
        cmap, vmin, vmax = "Blues", 0.0, 1.0
    image = None
    for index, ax in enumerate(axes.flat):
        if index >= n:
            ax.axis("off")
            continue
        data = np.array([[math.nan if v is None else v for v in r] for r in grids[index]], dtype=float)
        image = ax.imshow(data, cmap=cmap, vmin=vmin, vmax=vmax)
        for (i, j), v in np.ndenumerate(data):
            if math.isnan(v):
                ax.text(j, i, "–", ha="center", va="center", color=MUTED)
                continue
            dark = abs(v - vmin) / (vmax - vmin) > 0.6 if not diverging else abs(v) / vmax > 0.6
            ax.text(j, i, f"{v:+.2f}" if diverging else f"{v:.2f}", ha="center", va="center",
                    color=SURFACE if dark else INK)
        ax.set_xticks(range(len(columns)), columns)
        ax.set_yticks(range(len(rows)), rows)
        ax.set_xlabel("source language")
        if index % cols == 0:
            ax.set_ylabel("query language")
        ax.set_title(titles[index], loc="left")
        for spine in ax.spines.values():
            spine.set_visible(False)
    if image is not None:
        fig.colorbar(image, ax=axes.ravel().tolist(), shrink=0.8, label=label)
    return _save(fig, out, name)


def latency(labels: Sequence[str], entries: Sequence[dict[str, Any]], out: Path, name: str) -> list[Path]:
    """p50 bars with a p95 marker of the query embedding and the search time per configuration."""
    plt = _pyplot()
    fig, axes = plt.subplots(1, 2, figsize=(max(6.0, 1.2 * len(labels) + 3), 3.0), sharey=False)
    for ax, (part, title) in zip(axes, (("embed_ms", "query embedding"), ("search_ms", "search"))):
        x = list(range(len(labels)))
        p50 = [e[f"{part}_p50"] if e[f"{part}_p50"] is not None else 0.0 for e in entries]
        p95 = [e[f"{part}_p95"] if e[f"{part}_p95"] is not None else math.nan for e in entries]
        ax.bar(x, p50, width=0.6, color=PRIMARY, label="p50", zorder=2)
        ax.scatter(x, p95, marker="_", s=300, linewidths=2, color=SECONDARY, label="p95", zorder=3)
        for xi, e in zip(x, entries):
            if e[f"{part}_p50"] is None:
                ax.text(xi, 0, "n/a", ha="center", va="bottom", color=MUTED)
        ax.set_xticks(x, labels, rotation=30 if len(labels) > 3 else 0, ha="right" if len(labels) > 3 else "center")
        ax.set_title(f"{title} (ms)", loc="left")
        ax.yaxis.grid(True, color=GRID, zorder=0)
        ax.set_ylim(bottom=0)
    axes[0].legend(frameon=False, loc="upper left")
    return _save(fig, out, name)


def deltas(labels: Sequence[str], entries: Sequence[dict[str, Any]], metric: str, out: Path, name: str) -> list[Path]:
    """Delta (B - A) of a metric per slice with its paired 95% CI, as points on a zero line."""
    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(6.0, 0.32 * len(labels) + 1.2))
    y = list(range(len(labels)))[::-1]
    for yi, e in zip(y, entries):
        if e["delta"] is None:
            continue
        if e["low"] is not None:
            ax.plot([e["low"], e["high"]], [yi, yi], color=MUTED, linewidth=2, zorder=2)
        ax.scatter([e["delta"]], [yi], s=40, color=PRIMARY, edgecolors=SURFACE, linewidths=2, zorder=3)
    ax.axvline(0, color=INK, linewidth=1)
    ax.set_yticks(y, labels)
    ax.set_xlabel(f"Δ {metric} (B − A), paired 95% CI")
    ax.xaxis.grid(True, color=GRID, zorder=0)
    return _save(fig, out, name)
