"""Relevance metrics of one ranked result list and their uncertainty (#728, docs/SEARCH_BENCHMARK.md#reports).

Pure functions over chunk ids and the graded qrels of one intent (``grades``: chunk id -> 0, 1, 2).
A chunk without a qrel is **unjudged**. Two variants handle it:

* ``standard`` (primary): an unjudged chunk counts as not relevant, so a score is a lower bound
  when pooling missed relevant chunks;
* ``condensed``: unjudged chunks are removed from the ranking before scoring (the chunks below
  move up), which ignores them instead of penalising them.

A metric is None when it is undefined for the intent (no relevant qrel, no source chunk, nothing
returned); means leave such values out and say how many values they average.
"""
from __future__ import annotations

import math
import zlib
from collections.abc import Hashable, Iterable, Mapping, Sequence
from typing import Any

import numpy as np

K = 10
RECALL_KS = (20, 50)
STANDARD, CONDENSED = "standard", "condensed"
VARIANTS = (STANDARD, CONDENSED)
RELEVANCE_METRICS = ("ndcg@10", "p@10", "p2@10", "hit@10", "recall@20", "recall@50")
"""Computed in both variants; the condensed one is named ``<metric>_condensed``."""
COVERAGE_METRIC = "unjudged@10"
"""Only meaningful for the standard ranking (a condensed ranking has no unjudged chunk)."""
METRICS = (*RELEVANCE_METRICS, *(f"{m}_condensed" for m in RELEVANCE_METRICS), COVERAGE_METRIC)


def gain(grade: int) -> float:
    return 2.0 ** grade - 1


def dcg(grades: Iterable[int]) -> float:
    """Discounted cumulative gain with graded gains ``2^g - 1`` and a ``log2(rank + 1)`` discount."""
    return sum(gain(g) / math.log2(rank + 2) for rank, g in enumerate(grades))


def ndcg(ranked: Sequence[Hashable], grades: Mapping[Hashable, int], k: int = K) -> float | None:
    """nDCG@k against the ideal ranking of **all** the intent's qrels (not only the retrieved ones);
    None when the intent has no relevant qrel."""
    ideal = dcg(sorted(grades.values(), reverse=True)[:k])
    if ideal == 0:
        return None
    return dcg(grades.get(c, 0) for c in ranked[:k]) / ideal


def precision(ranked: Sequence[Hashable], grades: Mapping[Hashable, int], k: int = K,
              minimum: int = 1) -> float | None:
    """Share of the k slots holding a chunk graded at least ``minimum``; empty slots (fewer than k
    hits) count as misses. None when the intent has no chunk graded at least ``minimum``."""
    if not any(g >= minimum for g in grades.values()):
        return None
    return sum(1 for c in ranked[:k] if grades.get(c, 0) >= minimum) / k


def hit(ranked: Sequence[Hashable], sources: Iterable[Hashable], k: int = K) -> float | None:
    """1 when a known source chunk of the intent is in the top k, else 0; None without source chunks."""
    sources = set(sources)
    if not sources:
        return None
    return 1.0 if sources.intersection(ranked[:k]) else 0.0


def recall(ranked: Sequence[Hashable], grades: Mapping[Hashable, int], k: int) -> float | None:
    """Share of the intent's relevant qrels (grade >= 1) in the top k; None when it has none.
    Pooled qrels are incomplete, so this is recall of the *judged* relevant chunks."""
    relevant = {c for c, g in grades.items() if g >= 1}
    if not relevant:
        return None
    return len(relevant.intersection(ranked[:k])) / len(relevant)


def unjudged_rate(ranked: Sequence[Hashable], grades: Mapping[Hashable, int], k: int = K) -> float | None:
    """Share of the returned top-k chunks without a qrel for the intent; None when nothing was returned."""
    top = ranked[:k]
    if not top:
        return None
    return sum(1 for c in top if c not in grades) / len(top)


def condensed(ranked: Sequence[Hashable], grades: Mapping[Hashable, int]) -> list[Hashable]:
    """The ranking without its unjudged chunks."""
    return [c for c in ranked if c in grades]


def query_metrics(ranked: Sequence[Hashable], grades: Mapping[Hashable, int],
                  sources: Iterable[Hashable]) -> dict[str, float | None]:
    """Every metric of ``METRICS`` for one successful search."""
    sources = tuple(sources)
    found: dict[str, float | None] = {}
    for variant, ranking in ((STANDARD, list(ranked)), (CONDENSED, condensed(ranked, grades))):
        suffix = "" if variant == STANDARD else "_condensed"
        found[f"ndcg@{K}{suffix}"] = ndcg(ranking, grades, K)
        found[f"p@{K}{suffix}"] = precision(ranking, grades, K, 1)
        found[f"p2@{K}{suffix}"] = precision(ranking, grades, K, 2)
        found[f"hit@{K}{suffix}"] = hit(ranking, sources, K)
        for k in RECALL_KS:
            found[f"recall@{k}{suffix}"] = recall(ranking, grades, k)
    found[COVERAGE_METRIC] = unjudged_rate(ranked, grades, K)
    return found


def percentile(values: Iterable[float | None], q: float) -> float | None:
    """The q-th percentile (linear interpolation) of the values that are not None."""
    present = [v for v in values if v is not None]
    return float(np.percentile(present, q)) if present else None


# ---- uncertainty --------------------------------------------------------------------------

BOOTSTRAP_SAMPLES = 2000
SEED = 728


def stable_seed(seed: int, *key: Any) -> int:
    """A seed derived from ``seed`` and a key, the same in every process (unlike ``hash``)."""
    return zlib.crc32(repr((seed, *key)).encode("utf-8"))


def _clusters(values: Iterable[tuple[Hashable, float | None]]) -> tuple[np.ndarray, np.ndarray]:
    sums: dict[Hashable, float] = {}
    counts: dict[Hashable, int] = {}
    for cluster, value in values:
        if value is None:
            continue
        sums[cluster] = sums.get(cluster, 0.0) + value
        counts[cluster] = counts.get(cluster, 0) + 1
    keys = sorted(sums, key=repr)
    return np.array([sums[c] for c in keys]), np.array([counts[c] for c in keys], dtype=float)


def clustered_mean(values: Iterable[tuple[Hashable, float | None]], *, seed: int = SEED,
                   samples: int = BOOTSTRAP_SAMPLES, level: float = 0.95) -> dict[str, Any]:
    """Mean of the (cluster, value) pairs whose value is not None, with a percentile-bootstrap CI
    that resamples **clusters** (intents) with replacement, keeping each cluster's values together:
    the translations of one intent are not independent.

    Returns ``mean``, ``low``, ``high`` (None with fewer than two clusters), ``n`` (values) and
    ``clusters``. The same seed and input give the same interval.
    """
    sums, counts = _clusters(values)
    n = len(sums)
    if n == 0:
        return {"mean": None, "low": None, "high": None, "n": 0, "clusters": 0}
    mean = float(sums.sum() / counts.sum())
    if n < 2 or samples <= 0:
        return {"mean": mean, "low": None, "high": None, "n": int(counts.sum()), "clusters": n}
    rng = np.random.default_rng(seed)
    weights = rng.multinomial(n, np.full(n, 1.0 / n), size=samples)
    means = (weights @ sums) / (weights @ counts)
    tail = (1 - level) / 2 * 100
    low, high = np.percentile(means, [tail, 100 - tail])
    return {"mean": mean, "low": float(low), "high": float(high), "n": int(counts.sum()), "clusters": n}
