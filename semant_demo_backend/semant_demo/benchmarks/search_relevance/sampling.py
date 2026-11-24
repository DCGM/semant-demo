"""Step ``sample`` (#726): a language-balanced, document-spread sample of the source corpus.

1. **Scan**: one pass over every chunk's id and language (in id order). It counts the
   languages exactly and keeps, per corpus language, a uniform random sample of
   ``oversample`` x its target ids (reservoir sampling with the ``sample`` seed), so a rare
   language is sampled from all its chunks, not from what a batch or a filter happens to reach.
   Languages not configured, mixed and unknown ones are excluded from the balance (counted).
2. **Read**: the sampled ids are read in full (text, title, document, year, type). Chunks that
   are too short or have no document are counted as exclusions.
3. **Selection** per language toward its target: round-robin over (period, document type)
   strata (``balanced``) or in random order (``proportional``), at most ``max_per_document`` per
   document. A language with fewer usable chunks than its target is reported short.
4. **Context**: for a seeded share of the selected chunks, their neighbours in the document
   (``attributes.context_of``), so related passages occur together.
5. **Near-duplicates** are kept (they are realistic) and marked (``attributes.near_duplicate_of``).

Everything random comes from the ``sample`` seed and the scan's order is the ids', so the same
store and configuration give the same sample.
"""
from __future__ import annotations

import hashlib
import math
import random
import re
from itertools import combinations
from collections import Counter, defaultdict, deque
from collections.abc import Iterable, Sequence
from typing import Any
from uuid import UUID

from semant_demo.benchmarks.search_relevance.config import GeneratorConfig
from semant_demo.benchmarks.search_relevance.contracts import LANGUAGE_PATTERN, CorpusChunk, DocumentInfo
from semant_demo.benchmarks.search_relevance.llm import gather
from semant_demo.benchmarks.search_relevance.source import SourceChunk, SourceReader

READ_CONCURRENCY = 8
READ_SLICE = 1000
"""Sampled ids read per task (the source reads them in batches of its own)."""


def period(year: int | None, years: int) -> str:
    if year is None:
        return "unknown"
    start = year - year % years
    return f"{start}-{start + years - 1}"


def stratum(chunk: SourceChunk, years: int) -> str:
    return f"{period(chunk.year, years)}|{chunk.document_type or 'unknown'}"


class Sampler:
    def __init__(self, source: SourceReader, config: GeneratorConfig):
        self.source, self.config, self.s = source, config, config.sample
        self.rnd = random.Random(config.seeds.sample)
        self.targets = {language: config.target(language) for language in config.languages}
        self.languages = set(config.languages)
        self.candidates: dict[str, dict[UUID, SourceChunk]] = {language: {} for language in self.targets}
        self.seen: set[UUID] = set()
        self.exclusions: Counter[str] = Counter()

    def _consider(self, chunk: SourceChunk) -> None:
        """Records a chunk read in full as a candidate of its language, or why it is not one."""
        if chunk.document_id is None:
            self.exclusions["no_document"] += 1
        elif len(chunk.text) < self.s.min_chars:
            self.exclusions["too_short"] += 1
        elif chunk.language in self.targets:
            self.candidates[chunk.language][chunk.id] = chunk

    async def _scan(self) -> tuple[Counter[str], dict[str, list[UUID]]]:
        """Exact language counts and, per corpus language, a uniform random sample of
        ``oversample`` x target ids (reservoir sampling, Algorithm R, in the scan's id order)."""
        counts: Counter[str] = Counter()
        size = {lang: math.ceil(target * self.s.oversample) for lang, target in self.targets.items()}
        reservoirs: dict[str, list[UUID]] = {lang: [] for lang in self.targets}
        async for chunk_id, language in self.source.scan(self.s.scan_batch):
            counts[language] += 1
            reservoir = reservoirs.get(language)
            if reservoir is None:
                continue
            if len(reservoir) < size[language]:
                reservoir.append(chunk_id)
            else:
                j = self.rnd.randrange(counts[language])
                if j < size[language]:
                    reservoir[j] = chunk_id
        return counts, reservoirs

    async def _read(self, ids: Sequence[UUID]) -> list[SourceChunk]:
        slices = [list(ids[i:i + READ_SLICE]) for i in range(0, len(ids), READ_SLICE)]
        return [chunk for found in await gather(slices, READ_CONCURRENCY, self.source.read) for chunk in found]

    def _select(self, language: str, target: int) -> list[SourceChunk]:
        pool = sorted(self.candidates[language].values(), key=lambda c: c.id)
        self.rnd.shuffle(pool)
        per_document: Counter[UUID] = Counter()
        chosen: list[SourceChunk] = []

        def take(chunk: SourceChunk) -> bool:
            if per_document[chunk.document_id] >= self.s.max_per_document:
                return False
            per_document[chunk.document_id] += 1
            chosen.append(chunk)
            return True

        if self.s.strata == "proportional":
            for chunk in pool:
                if len(chosen) >= target:
                    break
                take(chunk)
            return chosen
        groups: dict[str, deque[SourceChunk]] = defaultdict(deque)
        for chunk in pool:
            groups[stratum(chunk, self.s.period_years)].append(chunk)
        order = sorted(groups)
        self.rnd.shuffle(order)
        while len(chosen) < target and any(groups[key] for key in order):
            for key in order:
                group = groups[key]
                while group:
                    if take(group.popleft()):
                        break
                if len(chosen) >= target:
                    break
        return chosen

    async def _context(self, selected: list[SourceChunk], have: set[UUID]) -> tuple[list[tuple[SourceChunk, UUID]],
                                                                                    Counter[str]]:
        count = round(self.s.context_fraction * len(selected))
        if not count or not self.s.context_neighbours:
            return [], Counter()
        anchors = sorted(self.rnd.sample(sorted(selected, key=lambda c: c.id), count), key=lambda c: c.id)
        k = self.s.context_neighbours

        async def read(anchor: SourceChunk) -> list[SourceChunk]:
            orders = [o for o in range(anchor.order - k, anchor.order + k + 1) if o >= 0 and o != anchor.order]
            found = await self.source.neighbours(anchor.document_id, orders)
            return sorted(found, key=lambda c: (c.order, c.id))
        added: list[tuple[SourceChunk, UUID]] = []
        skipped: Counter[str] = Counter()
        for anchor, found in zip(anchors, await gather(anchors, READ_CONCURRENCY, read)):
            for chunk in found:
                if chunk.id in have:
                    continue
                if not re.fullmatch(LANGUAGE_PATTERN, chunk.language):
                    skipped["no_single_language"] += 1
                    continue
                if not self.s.other_languages and chunk.language not in self.languages:
                    skipped["other_language"] += 1
                    continue
                if not chunk.text:
                    skipped["empty"] += 1
                    continue
                have.add(chunk.id)
                added.append((chunk, anchor.id))
        return added, skipped

    async def run(self, extra_ids: Iterable[UUID] = ()) -> tuple[list[CorpusChunk], dict[str, Any]]:
        counts, reservoirs = await self._scan()
        inventory = dict(counts)
        excluded_languages = {lang: n for lang, n in sorted(inventory.items()) if lang not in self.targets}
        sampled = sorted((i for ids in reservoirs.values() for i in ids), key=str)
        read = await self._read(sampled)
        if len(read) < len(sampled):
            self.exclusions["gone_since_the_scan"] += len(sampled) - len(read)
        for chunk in read:
            self._consider(chunk)
        selected: dict[str, list[SourceChunk]] = {lang: self._select(lang, target)
                                                  for lang, target in self.targets.items()}
        methods = {lang: "random" for lang in self.targets}
        records: dict[UUID, CorpusChunk] = {}
        for language, chunks in selected.items():
            for chunk in chunks:
                records[chunk.id] = self._record(chunk, methods[language])
        all_selected = [c for chunks in selected.values() for c in chunks]
        context, context_skipped = await self._context(all_selected, set(records))
        for chunk, anchor in context:
            records[chunk.id] = self._record(chunk, "context", context_of=anchor)
        extra = sorted(set(extra_ids) - set(records))
        imported_missing: list[str] = []
        if extra:
            found = {c.id: c for c in await self.source.read(extra)}
            for chunk_id in extra:
                chunk = found.get(chunk_id)
                if (chunk is None or not chunk.text or chunk.document_id is None
                        or not re.fullmatch(LANGUAGE_PATTERN, chunk.language)
                        or (not self.s.other_languages and chunk.language not in self.languages)):
                    imported_missing.append(str(chunk_id))
                else:
                    records[chunk_id] = self._record(chunk, "imported")
        corpus = mark_near_duplicates(sorted(records.values(), key=lambda c: (c.language, str(c.document_id),
                                                                              c.order, str(c.chunk_id))))
        report = {
            "inventory": dict(sorted(inventory.items(), key=lambda item: -item[1])),
            "excluded_languages": excluded_languages,
            "targets": self.targets,
            "scanned": sum(counts.values()), "method": "scan + reservoir sample",
            "sampled_ids": {lang: len(ids) for lang, ids in reservoirs.items()},
            "candidates": {lang: len(c) for lang, c in self.candidates.items()},
            "read_exclusions": dict(sorted(self.exclusions.items())),
            "selected": {lang: len(c) for lang, c in selected.items()},
            "short": {lang: {"target": t, "selected": len(selected[lang])}
                      for lang, t in self.targets.items() if len(selected[lang]) < t},
            "context_added": len(context), "context_skipped": dict(context_skipped),
            "imported_sources": len(extra) - len(imported_missing), "imported_sources_missing": imported_missing,
            "documents": len({c.document_id for c in corpus}),
            "max_per_document": max(Counter(c.document_id for c in corpus
                                            if c.attributes.get("sampled_by") != "context").values(), default=0),
            "strata": {lang: dict(sorted(Counter(stratum(c, self.s.period_years) for c in chunks).items()))
                       for lang, chunks in selected.items()},
            "near_duplicates": sum(1 for c in corpus if "near_duplicate_of" in c.attributes),
        }
        return corpus, report

    def _record(self, chunk: SourceChunk, sampled_by: str, context_of: UUID | None = None) -> CorpusChunk:
        attributes: dict[str, Any] = {"stratum": stratum(chunk, self.s.period_years),
                                      "period": period(chunk.year, self.s.period_years), "sampled_by": sampled_by}
        if context_of is not None:
            attributes["context_of"] = str(context_of)
        return CorpusChunk(chunk_id=chunk.id, document_id=chunk.document_id, order=chunk.order,
                           language=chunk.language, text=chunk.text, title=chunk.title,
                           document=DocumentInfo(title=chunk.document_title, year=chunk.year,
                                                 document_type=chunk.document_type),
                           attributes=attributes)


async def sample_corpus(source: SourceReader, config: GeneratorConfig, extra_ids: Iterable[UUID] = ()
                        ) -> tuple[list[CorpusChunk], dict[str, Any]]:
    return await Sampler(source, config).run(extra_ids)


# ---- near-duplicates ----------------------------------------------------------------------

SHINGLE = 5
HASHES, ROWS = 16, 2
NEAR_DUPLICATE = 0.8
"""Word 5-gram Jaccard similarity from which two chunks are near-duplicates."""
_PRIME = (1 << 61) - 1
_PARAMS = [(1 + 2 * i * 7919 % _PRIME, 31 * i + 17) for i in range(HASHES)]


def _shingles(text: str) -> set[int]:
    tokens = re.findall(r"\w+", text.lower())
    grams = [" ".join(tokens[i:i + SHINGLE]) for i in range(max(len(tokens) - SHINGLE + 1, 1))]
    return {int.from_bytes(hashlib.blake2b(g.encode(), digest_size=8).digest(), "big") for g in grams}


def mark_near_duplicates(corpus: list[CorpusChunk]) -> list[CorpusChunk]:
    """The corpus with ``attributes.near_duplicate_of`` (the group's smallest chunk id) on every
    chunk of a group of near-duplicates but that one (MinHash banding, then exact Jaccard)."""
    shingles = [_shingles(c.text) for c in corpus]
    buckets: dict[tuple, list[int]] = defaultdict(list)
    for index, items in enumerate(shingles):
        if not items:
            continue
        signature = [min((a * x + b) % _PRIME for x in items) for a, b in _PARAMS]
        for band in range(HASHES // ROWS):
            buckets[(band, *signature[band * ROWS:(band + 1) * ROWS])].append(index)
    parent = list(range(len(corpus)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for members in buckets.values():
        # Every pair of a bucket: two near-duplicates may both differ from the bucket's first member.
        for i, j in combinations(members, 2):
            if root(i) != root(j):
                a, b = shingles[i], shingles[j]
                if len(a & b) / len(a | b) >= NEAR_DUPLICATE:
                    parent[root(i)] = root(j)
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(corpus)):
        groups[root(i)].append(i)
    marked = list(corpus)
    for members in groups.values():
        if len(members) < 2:
            continue
        first = min((corpus[i].chunk_id for i in members), key=str)
        for i in members:
            if corpus[i].chunk_id != first:
                marked[i] = corpus[i].model_copy(update={"attributes": {**corpus[i].attributes,
                                                                        "near_duplicate_of": str(first)}})
    return marked
