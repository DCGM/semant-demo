"""Per-query scores of saved runs and their aggregation into slices (#728).

Reads only a dataset and runs (``contracts``). Every query of the dataset gets one row per
configuration: ``scored`` (its metrics), ``failed`` (``RunResult.error``) or ``missing`` (no result).
Failed and missing searches are counted and left out of the means.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from .contracts import CorpusChunk, Dataset, Intent, Run, RunConfiguration
from .metrics import (BOOTSTRAP_SAMPLES, METRICS, SEED, clustered_mean, percentile,
                      query_metrics, stable_seed)

SCORED, FAILED, MISSING = "scored", "failed", "missing"
MAX_GROUPS = 12
"""A chunk attribute with more distinct values than this (an id, a year) is not used as a slice."""
SAME, CROSS, UNKNOWN = "same language", "cross language", "unknown"


@dataclass(frozen=True)
class Configuration:
    """A configuration of a run, labelled uniquely across the runs of one report."""
    label: str
    run_id: str
    config: RunConfiguration


@dataclass
class Row:
    configuration: str
    query_id: str
    intent_id: str
    query_language: str
    source_language: str | None
    style: str
    status: str
    ranked: list[UUID] = field(default_factory=list)
    metrics: dict[str, float | None] = field(default_factory=dict)
    embed_ms: float | None = None
    search_ms: float | None = None
    error: str | None = None
    slices: dict[str, str] = field(default_factory=dict)
    """Slice name -> this query's group in it (language pair, style, source attributes, …)."""


def configurations(runs: Sequence[Run]) -> list[Configuration]:
    """The configurations of the runs, labelled by their id, or ``run_id/id`` when an id repeats."""
    ids = Counter(c.configuration_id for run in runs for c in run.manifest.configurations)
    found = []
    for run in runs:
        for c in run.manifest.configurations:
            label = c.configuration_id if ids[c.configuration_id] == 1 else f"{run.manifest.run_id}/{c.configuration_id}"
            found.append(Configuration(label, run.manifest.run_id, c))
    labels = [c.label for c in found]
    if len(set(labels)) != len(labels):
        raise ValueError("a run is given twice")
    return found


def inconsistent_intents(dataset: Dataset) -> set[str]:
    """Intents with at least one qrel whose per-language grades disagree (``consistent: false``)."""
    return {q.intent_id for q in dataset.qrels if not q.consistent}


def _value(values: set[Any]) -> str:
    if not values:
        return "none"
    if len(values) > 1:
        return "mixed"
    value = next(iter(values))
    return "none" if value is None else str(value)


def source_slices(dataset: Dataset) -> dict[str, dict[str, str]]:
    """Intent id -> slice -> group from its source chunks: each chunk attribute with at most
    ``MAX_GROUPS`` values, the document type and whether the chunk has a title ("mixed" when the
    source chunks of one intent differ, "none" without a value)."""
    def sources(intent: Intent) -> list[CorpusChunk]:
        return [dataset.corpus[c] for c in intent.source_chunk_ids]

    keys = sorted({k for chunk in dataset.corpus.values() for k in chunk.attributes})
    found: dict[str, dict[str, str]] = {i: {} for i in dataset.intents}
    candidates: dict[str, dict[str, str]] = {}
    for intent in dataset.intents.values():
        chunks = sources(intent)
        groups = {f"source {k}": _value({c.attributes.get(k) for c in chunks}) for k in keys}
        groups["source document type"] = _value({c.document.document_type for c in chunks})
        groups["source title"] = _value({"with title" if c.title else "without title" for c in chunks})
        candidates[intent.intent_id] = groups
    names = {name for groups in candidates.values() for name in groups}
    for name in sorted(names):
        values = {groups[name] for groups in candidates.values()}
        if 1 < len(values) <= MAX_GROUPS:
            for intent_id, groups in candidates.items():
                found[intent_id][name] = groups[name]
    return found


def score(dataset: Dataset, runs: Sequence[Run], exclude_inconsistent: bool = False
          ) -> tuple[list[Configuration], list[Row]]:
    """One row per (configuration, query) of the dataset, in the order of the configurations and
    query ids; the intents with inconsistent qrels are left out when asked."""
    configs = configurations(runs)
    grades = dataset.grades()
    skipped = inconsistent_intents(dataset) if exclude_inconsistent else set()
    attributes = source_slices(dataset)
    results = {}
    for run, config in ((r, c) for r in runs for c in configs if c.run_id == r.manifest.run_id):
        for result in run.results:
            if result.configuration_id == config.config.configuration_id:
                results[config.label, result.query_id] = result
    rows = []
    for config in configs:
        for query in sorted(dataset.queries.values(), key=lambda q: q.query_id):
            intent = dataset.intents[query.intent_id]
            if intent.intent_id in skipped:
                continue
            source = intent.source_language
            slices = {"language pair": f"{query.language}→{source or UNKNOWN}",
                      "query language": query.language, "source language": source or UNKNOWN,
                      "language match": UNKNOWN if source is None else SAME if query.language == source else CROSS,
                      "style": intent.style, **attributes[intent.intent_id]}
            row = Row(config.label, query.query_id, intent.intent_id, query.language, source, intent.style,
                      MISSING, slices=slices)
            result = results.get((config.label, query.query_id))
            if result is not None:
                row.embed_ms, row.search_ms, row.error = result.embed_ms, result.search_ms, result.error
                if result.error is not None:
                    row.status = FAILED
                else:
                    row.status = SCORED
                    row.ranked = [h.chunk_id for h in result.hits]
                    row.metrics = query_metrics(row.ranked, grades.get(intent.intent_id, {}), intent.source_chunk_ids)
            rows.append(row)
    return configs, rows


# ---- aggregation --------------------------------------------------------------------------

def summarize(rows: Iterable[Row], *, key: tuple[Any, ...], seed: int = SEED,
              samples: int = BOOTSTRAP_SAMPLES, metrics: Sequence[str] = METRICS) -> dict[str, Any]:
    """Counts and the mean of every metric with its intent-bootstrap CI over the scored rows.
    One bootstrap seed per ``key`` and metric, so a cell does not depend on the others."""
    rows = list(rows)
    scored = [r for r in rows if r.status == SCORED]
    summary: dict[str, Any] = {
        "queries": len(rows), "scored": len(scored), "failed": sum(r.status == FAILED for r in rows),
        "missing": sum(r.status == MISSING for r in rows), "intents": len({r.intent_id for r in scored}),
        "no_relevant": sum(1 for r in scored if r.metrics.get("ndcg@10") is None), "metrics": {}}
    for metric in metrics:
        summary["metrics"][metric] = clustered_mean(((r.intent_id, r.metrics.get(metric)) for r in scored),
                                                    seed=stable_seed(seed, *key, metric), samples=samples)
    return summary


def slice_names(rows: Iterable[Row]) -> list[str]:
    seen: dict[str, None] = {}
    for row in rows:
        for name in row.slices:
            seen.setdefault(name, None)
    return list(seen)


def aggregate(configs: Sequence[Configuration], rows: Sequence[Row], *, seed: int = SEED,
              samples: int = BOOTSTRAP_SAMPLES) -> list[dict[str, Any]]:
    """Summaries per configuration: overall and each group of each slice."""
    found = []
    for config in configs:
        mine = [r for r in rows if r.configuration == config.label]
        found.append({"configuration": config.label, "slice": "overall", "group": "all",
                      **summarize(mine, key=(config.label, "overall"), seed=seed, samples=samples)})
        for name in slice_names(mine):
            groups: dict[str, list[Row]] = {}
            for row in mine:
                groups.setdefault(row.slices[name], []).append(row)
            for group in sorted(groups):
                found.append({"configuration": config.label, "slice": name, "group": group,
                              **summarize(groups[group], key=(config.label, name, group), seed=seed,
                                          samples=samples)})
    return found


def latency(configs: Sequence[Configuration], rows: Sequence[Row]) -> list[dict[str, Any]]:
    """p50 and p95 of the query embedding, the search and their sum over the successful searches."""
    found = []
    for config in configs:
        mine = [r for r in rows if r.configuration == config.label and r.status == SCORED]
        total = [None if r.search_ms is None else (r.embed_ms or 0.0) + r.search_ms for r in mine]
        entry: dict[str, Any] = {"configuration": config.label, "searches": len(mine)}
        for name, values in (("embed_ms", [r.embed_ms for r in mine]), ("search_ms", [r.search_ms for r in mine]),
                             ("total_ms", total)):
            entry[f"{name}_n"] = sum(v is not None for v in values)
            entry[f"{name}_p50"] = percentile(values, 50)
            entry[f"{name}_p95"] = percentile(values, 95)
        found.append(entry)
    return found


def intent_means(rows: Iterable[Row], metric: str = "ndcg@10") -> dict[str, float]:
    """Intent id -> mean of a metric over its scored queries (intents without a value left out)."""
    values: dict[str, list[float]] = {}
    for row in rows:
        value = row.metrics.get(metric) if row.status == SCORED else None
        if value is not None:
            values.setdefault(row.intent_id, []).append(value)
    return {i: sum(v) / len(v) for i, v in values.items()}


def paired(rows_a: Iterable[Row], rows_b: Iterable[Row], metric: str, *, key: tuple[Any, ...],
           seed: int = SEED, samples: int = BOOTSTRAP_SAMPLES,
           where: Callable[[Row], bool] = lambda row: True) -> dict[str, Any]:
    """A and B means and the delta B - A over the queries both scored with a value of the metric,
    with an intent-bootstrap CI of the delta (the same intents resampled for both)."""
    by_query = {r.query_id: r for r in rows_a if r.status == SCORED and where(r)}
    pairs = []
    for b in rows_b:
        a = by_query.get(b.query_id)
        if a is None or b.status != SCORED or a.metrics.get(metric) is None or b.metrics.get(metric) is None:
            continue
        pairs.append((b.intent_id, a.metrics[metric], b.metrics[metric]))
    stable = stable_seed(seed, *key, metric)
    a_mean = clustered_mean(((i, a) for i, a, _ in pairs), seed=stable, samples=0)
    b_mean = clustered_mean(((i, b) for i, _, b in pairs), seed=stable, samples=0)
    delta = clustered_mean(((i, b - a) for i, a, b in pairs), seed=stable, samples=samples)
    return {"metric": metric, "a": a_mean["mean"], "b": b_mean["mean"], "delta": delta["mean"],
            "low": delta["low"], "high": delta["high"], "n": delta["n"], "clusters": delta["clusters"]}

