"""Step ``pool`` (#726): candidate chunks per intent from several retrieval methods.

The sampled corpus is loaded into the benchmark store (``store_api``), the vectors of the
pooling methods are ensured, and every query of an intent (all its languages) is searched with
every method. An intent's pool is the union of those hits and its source chunks
(``pooled_by: source``), each candidate recording the methods that proposed it. The pool is
capped per intent (source chunks always kept; then by best rank over methods and queries, then
by the number of methods) and, with ``max_judgments``, the per-intent cap is lowered until the
total fits the budget. What the caps leave out is counted: pooling is incomplete by design.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any
from uuid import UUID

from semant_demo.benchmarks.search_relevance.config import GeneratorConfig
from semant_demo.benchmarks.search_relevance.contracts import SOURCE, Dataset, Intent, Query
from semant_demo.benchmarks.search_relevance.llm import gather
from semant_demo.benchmarks.search_relevance.store_api import BenchmarkStore


@dataclass
class Candidate:
    chunk_id: UUID
    methods: set[str] = field(default_factory=set)
    best_rank: int | None = None
    """1-based best rank over methods and queries; None for a source chunk no method found."""
    methods_order: tuple[str, ...] = ()
    """``methods`` with ``source`` first, then in configuration order (``pooled_by``)."""

    def record(self) -> dict[str, Any]:
        return {"chunk_id": str(self.chunk_id), "pooled_by": list(self.methods_order), "best_rank": self.best_rank}


def order_methods(methods: set[str], configured: list[str]) -> tuple[str, ...]:
    return tuple(m for m in [SOURCE, *configured] if m in methods)


def cap_pools(pools: dict[str, list[Candidate]], per_intent: int, budget: int | None
              ) -> tuple[dict[str, list[Candidate]], int]:
    """Pools cut to ``per_intent`` candidates (source chunks first and always), lowered until the
    total is within ``budget``; and the cap used."""
    def cut(cap: int) -> dict[str, list[Candidate]]:
        found = {}
        for intent_id, candidates in pools.items():
            sources = [c for c in candidates if SOURCE in c.methods]
            others = sorted((c for c in candidates if SOURCE not in c.methods),
                            key=lambda c: (c.best_rank or 0, -len(c.methods), str(c.chunk_id)))
            found[intent_id] = sources + others[:max(cap - len(sources), 0)]
        return found
    cap = per_intent
    capped = cut(cap)
    while budget is not None and cap > 1 and sum(map(len, capped.values())) > budget:
        cap -= 1
        capped = cut(cap)
    return capped, cap


async def pool_candidates(store: BenchmarkStore, dataset: Dataset, intents: list[Intent], queries: list[Query],
                          config: GeneratorConfig, embedding_cache: Path
                          ) -> tuple[dict[str, list[Candidate]], dict[str, Any]]:
    section = config.pooling
    load = await store.load(dataset)
    vectors: dict[str, Any] = {}
    for method in section.methods:
        if method.vector is not None and method.vector.id not in vectors:
            report = await store.ensure_vector(method.vector, method.endpoint.endpoint(), embedding_cache)
            vectors[method.vector.id] = vars(report)
    searchers = {m.id: store.searcher(m.configuration(), m.endpoint.endpoint() if m.endpoint else None)
                 for m in section.methods}
    tasks = [(method.id, query) for method in section.methods for query in queries]
    failures: dict[str, Counter[str]] = defaultdict(Counter)
    outside = 0

    async def search(task: tuple[str, Query]) -> list[tuple[UUID, float | None]] | None:
        method, query = task
        try:
            return (await searchers[method](query.text)).hits
        except Exception as e:  # reported per method; the class only (a message may hold the query)
            failures[method][type(e).__name__] += 1
            return None
    results = await gather(tasks, section.concurrency, search)
    configured = [m.id for m in section.methods]
    pools: dict[str, dict[UUID, Candidate]] = {i.intent_id: {} for i in intents}
    for intent in intents:
        for chunk_id in intent.source_chunk_ids:
            pools[intent.intent_id][chunk_id] = Candidate(chunk_id, {SOURCE})
    for (method, query), hits in zip(tasks, results):
        for rank, (chunk_id, _score) in enumerate(hits or [], 1):
            if chunk_id not in dataset.corpus:
                outside += 1
                continue
            candidate = pools[query.intent_id].setdefault(chunk_id, Candidate(chunk_id))
            candidate.methods.add(method)
            candidate.best_rank = rank if candidate.best_rank is None else min(candidate.best_rank, rank)
    for candidates in pools.values():
        for candidate in candidates.values():
            candidate.methods_order = order_methods(candidate.methods, configured)
    full = {intent_id: list(c.values()) for intent_id, c in pools.items()}
    capped, cap = cap_pools(full, section.max_candidates_per_intent, section.max_judgments)
    sizes = [len(c) for c in capped.values()]
    before = sum(map(len, full.values()))
    after = sum(sizes)
    contributes = Counter(m for cands in capped.values() for c in cands for m in c.methods)
    only = Counter(next(iter(c.methods)) for cands in capped.values() for c in cands if len(c.methods) == 1)
    source_found = Counter(m for cands in capped.values() for c in cands if SOURCE in c.methods
                           for m in c.methods if m != SOURCE)
    report = {
        "load": vars(load), "vectors": vectors,
        "methods": [{"id": m.id, "description": m.description, **m.configuration().model_dump(
            mode="json", exclude_none=True, exclude={"configuration_id"})} for m in section.methods],
        "searches": len(tasks), "failed_searches": {m: dict(c) for m, c in failures.items()},
        "hits_outside_corpus": outside,
        "candidates_before_cap": before, "candidates": after, "left_out_by_cap": before - after,
        "cap_per_intent": cap, "budget": section.max_judgments,
        "per_intent": {"mean": round(mean(sizes), 2) if sizes else 0, "min": min(sizes, default=0),
                       "max": max(sizes, default=0)},
        "proposed_by": dict(contributes), "proposed_only_by": dict(only),
        "sources_found_by": dict(source_found),
    }
    return capped, report
