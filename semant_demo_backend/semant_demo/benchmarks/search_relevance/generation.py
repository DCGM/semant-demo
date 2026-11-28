"""Steps ``intents`` and ``translate`` (#726): information needs with a query in the source
language, imported intents, and the translations of every query into the other query languages.

Intents are spread evenly over the corpus languages and, within a language, over the configured
styles by their shares. Each is written from one source chunk (one per document where
possible); a reply that is unusable or stays a near-copy of its passage after one regeneration
is dropped and the intent is written from a spare chunk instead.
"""
from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from semant_demo.benchmarks.search_relevance import prompts
from semant_demo.benchmarks.search_relevance.calls import CachedModel
from semant_demo.benchmarks.search_relevance.config import GeneratorConfig, ImportSection
from semant_demo.benchmarks.search_relevance.contracts import CorpusChunk, Intent, Query
from semant_demo.benchmarks.search_relevance.llm import Refused, gather

TWO_LETTER = {"cs": "ces", "en": "eng", "de": "deu", "sk": "slk", "pl": "pol", "fr": "fra", "la": "lat"}


def query_id(intent_id: str, language: str) -> str:
    return f"{intent_id}.{language}"


def split_evenly(total: int, keys: list[str]) -> dict[str, int]:
    base, extra = divmod(total, len(keys)) if keys else (0, 0)
    return {key: base + (1 if i < extra else 0) for i, key in enumerate(keys)}


def style_counts(n: int, shares: dict[str, float]) -> dict[str, int]:
    """``n`` split by ``shares`` (largest remainder; ties in configuration order)."""
    total = sum(shares.values())
    exact = {style: n * share / total for style, share in shares.items()}
    counts = {style: int(value) for style, value in exact.items()}
    order = sorted(shares, key=lambda s: -(exact[s] - counts[s]))
    for style in order[:n - sum(counts.values())]:
        counts[style] += 1
    return counts


def source_candidates(corpus: list[CorpusChunk], language: str, one_per_document: bool, rnd: random.Random
                      ) -> list[CorpusChunk]:
    """The chunks of a language to write intents from, in a seeded order: sampled (not context)
    chunks first, one per document first when ``one_per_document``."""
    chunks = sorted((c for c in corpus if c.language == language), key=lambda c: str(c.chunk_id))
    primary = [c for c in chunks if c.attributes.get("sampled_by") != "context"]
    rest = [c for c in chunks if c.attributes.get("sampled_by") == "context"]
    rnd.shuffle(primary)
    rnd.shuffle(rest)
    if not one_per_document:
        return primary + rest
    first, later, seen = [], [], set()
    for chunk in primary + rest:
        (later if chunk.document_id in seen else first).append(chunk)
        seen.add(chunk.document_id)
    return first + later


@dataclass
class Slot:
    language: str
    style: str
    chunk: CorpusChunk | None = None
    intent: Intent | None = None
    query: Query | None = None
    failures: list[str] | None = None


async def generate_intents(corpus: list[CorpusChunk], config: GeneratorConfig, model: CachedModel
                           ) -> tuple[list[Intent], list[Query], dict[str, Any]]:
    section = config.intents
    descriptions = section.descriptions()
    rnd = random.Random(config.seeds.intents)
    per_language = split_evenly(section.count, list(config.languages))
    slots: list[Slot] = []
    queues: dict[str, list[CorpusChunk]] = {}
    for language in config.languages:
        counts = style_counts(per_language[language], section.styles)
        styles = [style for style, n in counts.items() for _ in range(n)]
        rnd.shuffle(styles)
        queues[language] = source_candidates(corpus, language, section.one_per_document, rnd)
        limit = len(styles) + int(len(styles) * section.spare + 0.999)
        queues[language] = queues[language][:limit]
        slots += [Slot(language, style, failures=[]) for style in styles]
    reasons: Counter[str] = Counter()
    near_copies = regenerated = 0

    async def write(slot: Slot) -> None:
        nonlocal near_copies, regenerated
        chunk = slot.chunk
        text = chunk.text[:section.max_passage_chars]
        avoid = None
        for attempt in range(2):
            messages = prompts.intent_messages(text, chunk.document.title, slot.style, descriptions[slot.style],
                                               slot.language, avoid)
            reply, reason = await model.ask(messages, prompts.parse_intent)
            if reply is None:
                slot.failures.append(reason)
                return
            avoid = prompts.is_near_copy(reply["query"], chunk.text, section.max_copied_words)
            if avoid is None:
                digest = hashlib.sha256(f"{chunk.chunk_id}|{slot.style}".encode()).hexdigest()[:12]
                intent_id = f"{slot.language}-{slot.style}-{digest}"
                slot.intent = Intent(intent_id=intent_id, style=slot.style, need=reply["need"],
                                     source_chunk_ids=(chunk.chunk_id,), source_language=chunk.language)
                slot.query = Query(query_id=query_id(intent_id, slot.language), intent_id=intent_id,
                                   language=slot.language, text=reply["query"])
                regenerated += attempt
                return
            near_copies += 1
        slot.failures.append("near_copy")

    pending = list(slots)
    while pending:
        for slot in pending:  # in slot order: the same chunks for the same slots on every run
            queue = queues[slot.language]
            slot.chunk = queue.pop(0) if queue else None
        ready = [slot for slot in pending if slot.chunk is not None]
        if not ready:
            break
        await gather(ready, config.concurrency, write)
        for slot in ready:
            if slot.intent is None:
                reasons[slot.failures[-1]] += 1
        pending = [slot for slot in ready if slot.intent is None]
    done = [slot for slot in slots if slot.intent is not None]
    report = {
        "requested": len(slots), "generated": len(done),
        "short": {lang: n - sum(1 for s in done if s.language == lang) for lang, n in per_language.items()
                  if n > sum(1 for s in done if s.language == lang)},
        "by_language": dict(Counter(s.language for s in done)), "by_style": dict(Counter(s.style for s in done)),
        "failed_attempts": dict(reasons), "near_copy_replies": near_copies, "regenerated_after_near_copy": regenerated,
        "model_calls": model.report(),
    }
    return [s.intent for s in done], [s.query for s in done], report


# ---- imported intents ---------------------------------------------------------------------

def read_imports(section: ImportSection) -> list[dict[str, Any]]:
    found = []
    with section.path.expanduser().open(encoding="utf-8") as f:
        for number, line in enumerate(f, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise Refused(f"{section.path.name}:{number}: not a JSON object")
            found.append(record)
    return found


def _import_chunk(record: dict[str, Any]) -> UUID | None:
    value = record.get("corpus_id") or record.get("chunk_id")
    try:
        return UUID(str(value)) if value else None
    except ValueError:
        return None


def import_source_ids(config: GeneratorConfig) -> list[UUID]:
    """The source chunks of the imported intents (the sample adds them to the corpus)."""
    section = config.intents.imports
    if section is None or not config.sample.include_import_sources:
        return []
    return sorted({c for r in select_imports(read_imports(section), config)[0] if (c := _import_chunk(r))}, key=str)


def select_imports(records: list[dict[str, Any]], config: GeneratorConfig) -> tuple[list[dict[str, Any]], Counter]:
    """Usable records (a text and a query language), at most ``limit``, round-robin over languages."""
    skipped: Counter[str] = Counter()
    by_language: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        text = record.get("question") or record.get("query")
        language = str(record.get("language") or "").lower()
        language = TWO_LETTER.get(language, language)
        if not isinstance(text, str) or not text.strip():
            skipped["no_text"] += 1
        elif language not in config.query_languages:
            skipped["language_not_queried"] += 1
        else:
            by_language[language].append({**record, "language": language, "text": " ".join(text.split())})
    rnd = random.Random(config.seeds.intents)
    for language in by_language:
        rnd.shuffle(by_language[language])
    limit = config.intents.imports.limit if config.intents.imports else None
    chosen: list[dict[str, Any]] = []
    languages = sorted(by_language)
    while any(by_language.values()) and (limit is None or len(chosen) < limit):
        for language in languages:
            if by_language[language] and (limit is None or len(chosen) < limit):
                chosen.append(by_language[language].pop(0))
    skipped["over_limit"] += sum(len(v) for v in by_language.values())
    return chosen, skipped


def imported_intents(corpus: list[CorpusChunk], config: GeneratorConfig
                     ) -> tuple[list[Intent], list[Query], dict[str, Any]]:
    section = config.intents.imports
    if section is None:
        return [], [], {}
    chosen, skipped = select_imports(read_imports(section), config)
    in_corpus = {c.chunk_id: c for c in corpus}
    intents, queries, ids = [], [], set()
    outside = 0
    for record in chosen:
        chunk_id = _import_chunk(record)
        source = in_corpus.get(chunk_id) if chunk_id else None
        outside += chunk_id is not None and source is None
        digest = hashlib.sha256(f"{record['language']}|{record['text']}".encode()).hexdigest()[:12]
        intent_id = str(record.get("intent_id") or f"imported-{digest}")
        if intent_id in ids:
            skipped["duplicate"] += 1
            continue
        try:
            intent = Intent(intent_id=intent_id, style=str(record.get("style") or "question"),
                            need=" ".join(str(record.get("need") or record["text"]).split()),
                            source_chunk_ids=(source.chunk_id,) if source else (),
                            source_language=source.language if source else None, origin="imported")
            query = Query(query_id=query_id(intent_id, record["language"]), intent_id=intent_id,
                          language=record["language"], text=record["text"], origin="imported")
        except ValueError:
            skipped["invalid"] += 1
            continue
        ids.add(intent_id)
        intents.append(intent)
        queries.append(query)
    return intents, queries, {"imported": len(intents), "skipped": dict(skipped),
                              "source_outside_corpus": outside, "path": Path(section.path).name}


# ---- translations -------------------------------------------------------------------------

async def translate(intents: list[Intent], queries: list[Query], config: GeneratorConfig, model: CachedModel
                    ) -> tuple[list[Intent], list[Query], dict[str, Any]]:
    """Every intent's query in every query language; checks recorded in the report."""
    section = config.translation
    rnd = random.Random(config.seeds.intents + 1)
    originals = {q.intent_id: q for q in queries}
    intent_by_id = {i.intent_id: i for i in intents}
    tasks = [(originals[i.intent_id], language) for i in intents for language in config.query_languages
             if language != originals[i.intent_id].language]
    back = {task for task in tasks if rnd.random() < section.back_translate_fraction}
    results: dict[tuple[str, str], Query] = {}
    flags: dict[str, list[str]] = defaultdict(list)
    overlaps: list[float] = []
    failures: Counter[str] = Counter()

    async def one(task: tuple[Query, str]) -> None:
        source, language = task
        intent = intent_by_id[source.intent_id]
        text, reason = await model.ask(prompts.translation_messages(intent.need, intent.style, source.text,
                                                                    source.language, language),
                                       prompts.parse_translation)
        if text is None:
            failures[reason] += 1
            return
        query = Query(query_id=query_id(intent.intent_id, language), intent_id=intent.intent_id, language=language,
                      text=text, origin="translated", translated_from=source.query_id)
        results[(intent.intent_id, language)] = query
        if " ".join(prompts.words(text)) == " ".join(prompts.words(source.text)):
            flags["same_as_source"].append(query.query_id)
        if prompts.language_doubtful(text, language):
            flags["language_doubtful"].append(query.query_id)
        if task in back:
            again, _ = await model.ask(prompts.translation_messages(intent.need, intent.style, text, language,
                                                                    source.language), prompts.parse_translation)
            if again is not None:
                overlap = prompts.word_overlap(again, source.text)
                overlaps.append(overlap)
                if overlap < section.min_back_overlap:
                    flags["back_translation_low_overlap"].append(query.query_id)
    await gather(tasks, config.concurrency, one)
    kept_intents, kept_queries, dropped = [], [], []
    for intent in intents:
        original = originals[intent.intent_id]
        mine = [original] + [results[(intent.intent_id, lang)] for lang in config.query_languages
                             if (intent.intent_id, lang) in results]
        if section.require_all_languages and set(config.query_languages) - {q.language for q in mine}:
            dropped.append(intent.intent_id)
            continue
        kept_intents.append(intent)
        kept_queries += sorted(mine, key=lambda q: config.query_languages.index(q.language)
                               if q.language in config.query_languages else len(config.query_languages))
    dropped_ids = set(dropped)
    report = {
        "requested": len(tasks), "translated": len(results), "failed": dict(failures),
        "dropped_intents": dropped,
        "flags": {name: sorted(q for q in ids if q.rsplit(".", 1)[0] not in dropped_ids)
                  for name, ids in sorted(flags.items())},
        "back_translation": {"checked": len(overlaps),
                             "mean_overlap": round(sum(overlaps) / len(overlaps), 3) if overlaps else None},
        "model_calls": model.report(),
    }
    return kept_intents, kept_queries, report
