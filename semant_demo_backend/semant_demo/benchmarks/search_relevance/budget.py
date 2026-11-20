"""``--budget``: an estimate of the model calls, tokens and cost of a generation, without any
model call or store access. Upper bounds before the cache: a rerun asks only what is not cached.
Uses the work directory's outputs where they exist (the real corpus, intents and pools)."""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

from semant_demo.adapters.llm.models import LlmConfigurationError
from semant_demo.benchmarks.search_relevance import prompts
from semant_demo.benchmarks.search_relevance.config import (
    INTENTS_FEATURE, JUDGE_FEATURE, TRANSLATION_FEATURE, GeneratorConfig)
from semant_demo.benchmarks.search_relevance.contracts import CorpusChunk, Intent, iter_jsonl

CHARS_PER_TOKEN = 4
OUTPUT_TOKENS = {INTENTS_FEATURE: 80, TRANSLATION_FEATURE: 40, JUDGE_FEATURE: 2}


def _count_lines(path: Path) -> int | None:
    return sum(1 for line in path.open(encoding="utf-8") if line.strip()) if path.is_file() else None


def estimate(config: GeneratorConfig, work: Path | None = None) -> dict[str, Any]:
    def existing(*parts: str) -> Path | None:
        path = work.joinpath(*parts) if work is not None else None
        return path if path is not None and path.is_file() else None
    corpus_path = existing("sample", "corpus.jsonl")
    chunks = list(iter_jsonl(corpus_path, CorpusChunk)) if corpus_path else []
    passage = mean(len(c.text) for c in chunks) if chunks else config.intents.max_passage_chars / 2
    imported = 0
    if config.intents.imports is not None and config.intents.imports.path.expanduser().is_file():
        imported = _count_lines(config.intents.imports.path.expanduser()) or 0
        if config.intents.imports.limit is not None:
            imported = min(imported, config.intents.imports.limit)
    intents_path = existing("translate", "intents.jsonl") or existing("intents", "intents.jsonl")
    intents = (sum(1 for _ in iter_jsonl(intents_path, Intent)) if intents_path
               else config.intents.count + imported)
    others = len(config.query_languages) - 1
    pools_path = existing("pool", "pools.jsonl")
    if pools_path:
        pairs = sum(len(json.loads(line)["candidates"]) for line in pools_path.open(encoding="utf-8") if line.strip())
    else:
        pairs = intents * config.pooling.max_candidates_per_intent
        if config.pooling.max_judgments is not None:
            pairs = min(pairs, config.pooling.max_judgments)
    judge_calls = round(pairs * (1 + config.judge.per_language_fraction * others))
    # A step whose output is in the work directory needs no more calls: only the rest is estimated.
    done = [step for step, path in (("intents", existing("intents", "intents.jsonl")),
                                    ("translate", existing("translate", "intents.jsonl")),
                                    ("judge", existing("judge", "qrels.jsonl"))) if path]
    to_generate = 0 if "intents" in done else config.intents.count
    calls = {
        INTENTS_FEATURE: {"expected": to_generate,
                          "at_most": round(2 * to_generate * (1 + config.intents.spare))},
        TRANSLATION_FEATURE: {"expected": 0 if "translate" in done else
                              round(intents * others * (1 + config.translation.back_translate_fraction))},
        JUDGE_FEATURE: {"expected": 0 if "judge" in done else judge_calls},
    }
    input_chars = {
        INTENTS_FEATURE: len(prompts.INTENT_SYSTEM) + len(prompts.INTENT_USER) + min(passage,
                                                                                    config.intents.max_passage_chars),
        TRANSLATION_FEATURE: len(prompts.TRANSLATION_SYSTEM) + len(prompts.TRANSLATION_USER) + 300,
        JUDGE_FEATURE: len(prompts.JUDGE_SYSTEM) + len(prompts.JUDGE_USER) + 200 + min(passage, config.judge.max_chars),
    }
    catalog = config.catalog()
    total_cost: float | None = 0.0
    for feature, entry in calls.items():
        n = entry["expected"]
        entry["input_tokens"] = round(n * input_chars[feature] / CHARS_PER_TOKEN)
        entry["output_tokens"] = n * OUTPUT_TOKENS[feature]
        try:
            model = catalog.resolve(feature, None, ())
        except LlmConfigurationError:
            model = None
        cost = model.estimated_cost(entry["input_tokens"], entry["output_tokens"]) if model else None
        entry["model"] = model.model if model else None
        entry["cost_usd"] = round(cost, 4) if cost is not None else None
        total_cost = None if cost is None or total_cost is None else total_cost + cost
    return {"done_steps": done, "intents": intents, "imported": imported, "corpus_chunks": len(chunks) or None,
            "mean_passage_chars": round(passage), "judged_pairs": pairs, "calls": calls,
            "cost_usd": round(total_cost, 4) if total_cost is not None else None,
            "note": "Estimates before the cache (cached calls are free); retries not included."}
