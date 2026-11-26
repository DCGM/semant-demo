"""Step ``judge`` (#726): a 0/1/2 grade of every pooled (intent, chunk) pair.

The judge sees the intent's need, its source-language query, the document title and the chunk
text (cut at ``max_chars``; the prompt says so). Judgements are model calls cached by their
content (need, query, chunk text and title), judge model and prompt version, so a rerun or a
refreshed pool judges only new pairs.

For a seeded share of intents (``per_language_fraction``) every candidate is judged once per
query language (the need with that language's query): ``language_grades`` keeps them, ``grade``
is their aggregate (``aggregation``: the median, the lower one of an even count, by default) and
``consistent`` is false when they differ. Every failed judgement (intent, chunk, language) is
counted by reason (``failed_judgements``). When only some languages of a pair fail,
``language_grades`` holds the judged ones, ``grade`` and ``consistent`` are derived from them and
the pair counts as ``per_language.incomplete``; but with ``aggregation: source`` a pair without
its source-language grade is unjudged (no other language stands in for it). A pair the judge
could not grade is left out of the qrels (``unjudged``, pairs counted by the reason of the
source-language failure, else another one); an intent whose source chunk stays unjudged is dropped,
since the contract requires every source chunk graded. A source chunk graded 0 is flagged.
"""
from __future__ import annotations

import hashlib
import random
from collections import Counter
from typing import Any
from uuid import UUID

from semant_demo.benchmarks.search_relevance import prompts
from semant_demo.benchmarks.search_relevance.calls import CachedModel
from semant_demo.benchmarks.search_relevance.config import GeneratorConfig
from semant_demo.benchmarks.search_relevance.contracts import SOURCE, CorpusChunk, Intent, Qrel, Query, to_json
from semant_demo.benchmarks.search_relevance.llm import gather


def judge_id(model: CachedModel, max_chars: int) -> str:
    """Stable for the same model, prompt and passage cut."""
    key = {**model.identity, **prompts.prompt_provenance({})["judge"], "max_chars": max_chars}
    return "judge-" + hashlib.sha256(to_json(key).encode()).hexdigest()[:12]


def aggregate(grades: dict[str, int], source_language: str, how: str) -> int:
    values = sorted(grades.values())
    if how == "min":
        return values[0]
    if how == "source" and source_language in grades:
        return grades[source_language]
    return values[(len(values) - 1) // 2]


def original_query(queries: list[Query]) -> Query:
    """The intent's query that is not a translation (generated or imported)."""
    return next((q for q in queries if q.origin != "translated"), queries[0])


async def judge_pools(intents: list[Intent], queries: list[Query], pools: dict[str, list[dict[str, Any]]],
                      corpus: dict[UUID, CorpusChunk], config: GeneratorConfig, model: CachedModel
                      ) -> tuple[list[Qrel], list[str], dict[str, Any]]:
    """The qrels, the intents dropped (a source chunk without a grade) and the report."""
    section = config.judge
    judge = judge_id(model, section.max_chars)
    rnd = random.Random(config.seeds.judge)
    by_intent: dict[str, list[Query]] = {}
    for query in queries:
        by_intent.setdefault(query.intent_id, []).append(query)
    per_language = {i.intent_id for i in sorted(intents, key=lambda i: i.intent_id)
                    if rnd.random() < section.per_language_fraction}
    tasks: list[tuple[str, UUID, Query]] = []
    for intent in intents:
        mine = by_intent[intent.intent_id]
        asked = mine if intent.intent_id in per_language else [original_query(mine)]
        for candidate in pools.get(intent.intent_id, []):
            tasks += [(intent.intent_id, UUID(candidate["chunk_id"]), q) for q in asked]
    needs = {i.intent_id: i.need for i in intents}

    async def grade(task: tuple[str, UUID, Query]) -> tuple[int | None, str | None]:
        intent_id, chunk_id, query = task
        chunk = corpus[chunk_id]
        text = f"{chunk.title}\n{chunk.text}" if chunk.title else chunk.text
        return await model.ask(prompts.judge_messages(needs[intent_id], query.text, text, chunk.document.title,
                                                      section.max_chars), prompts.parse_grade)
    results = await gather(tasks, config.concurrency, grade)
    grades: dict[tuple[str, UUID], dict[str, int]] = {}
    reasons: dict[tuple[str, UUID], dict[str, str]] = {}
    failed: Counter[str] = Counter()
    for (intent_id, chunk_id, query), (value, reason) in zip(tasks, results):
        if value is None:
            failed[reason or "unknown"] += 1
            reasons.setdefault((intent_id, chunk_id), {})[query.language] = reason or "unknown"
        else:
            grades.setdefault((intent_id, chunk_id), {})[query.language] = value
    qrels: list[Qrel] = []
    dropped: list[str] = []
    unjudged: Counter[str] = Counter()
    source_zero: list[str] = []
    cut = 0
    for intent in intents:
        source_language = original_query(by_intent[intent.intent_id]).language
        mine: list[Qrel] = []
        for candidate in pools.get(intent.intent_id, []):
            chunk_id = UUID(candidate["chunk_id"])
            found = grades.get((intent.intent_id, chunk_id)) or {}
            missing = reasons.get((intent.intent_id, chunk_id), {})
            if not found or (section.aggregation == "source" and source_language not in found):
                # Unjudged: no grade at all, or no source-language grade to take.
                unjudged[missing.get(source_language) or next(iter(missing.values()), "not_judged")] += 1
                continue
            cut += len(corpus[chunk_id].text) > section.max_chars
            several = intent.intent_id in per_language
            mine.append(Qrel(intent_id=intent.intent_id, chunk_id=chunk_id, grade=aggregate(
                found, source_language, section.aggregation), judge=judge, pooled_by=tuple(candidate["pooled_by"]),
                language_grades=dict(sorted(found.items())) if several else None,
                consistent=not several or len(set(found.values())) == 1))
        graded = {q.chunk_id: q for q in mine}
        if any(c not in graded for c in intent.source_chunk_ids):
            dropped.append(intent.intent_id)
            continue
        if any(graded[c].grade == 0 for c in intent.source_chunk_ids):
            source_zero.append(intent.intent_id)
        qrels += mine
    kept = qrels
    per_language_qrels = [q for q in kept if q.language_grades is not None]
    report = {
        "judge": judge, "pairs": len({(t[0], t[1]) for t in tasks}), "calls": len(tasks), "judged": len(kept),
        "unjudged": dict(unjudged), "failed_judgements": dict(failed), "dropped_intents": dropped,
        "grades": {str(g): n for g, n in sorted(Counter(q.grade for q in kept).items())},
        "source_graded_0": source_zero,
        "per_language": {"intents": len(per_language - set(dropped)), "pairs": len(per_language_qrels),
                         "inconsistent": sum(1 for q in per_language_qrels if not q.consistent),
                         "incomplete": sum(1 for q in per_language_qrels
                                           if len(q.language_grades) < len(by_intent[q.intent_id])),
                         "aggregation": section.aggregation},
        "passages_cut": cut, "max_chars": section.max_chars,
        "pooled_by_grade": {m: {str(g): n for g, n in sorted(Counter(q.grade for q in kept if m in q.pooled_by).items())}
                            for m in sorted({m for q in kept for m in q.pooled_by}, key=lambda m: (m != SOURCE, m))},
        "model_calls": model.report(),
    }
    return kept, dropped, report
