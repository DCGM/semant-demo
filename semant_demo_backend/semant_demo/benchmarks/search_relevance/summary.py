"""The short Markdown summary of a dataset (#726, #730): counts, language balance, styles, grades,
candidates per intent, checks, costs and a few examples. Built from the dataset files alone, so
``validate`` prints the same summary the generator writes."""
from __future__ import annotations

from collections import Counter
from statistics import mean, median
from typing import Any

from semant_demo.benchmarks.search_relevance.contracts import Dataset

EXAMPLES = 3
EXAMPLE_CHARS = 160


def _table(header: list[str], rows: list[list[Any]]) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header),
            *("| " + " | ".join(str(v) for v in row) + " |" for row in rows)]


def _short(text: str) -> str:
    text = " ".join(text.split()).replace("|", "\\|")
    return text if len(text) <= EXAMPLE_CHARS else text[:EXAMPLE_CHARS] + " …"


def summarize(dataset: Dataset) -> str:
    m = dataset.manifest
    corpus, intents, queries, qrels = dataset.corpus, dataset.intents, dataset.queries, dataset.qrels
    lines = [f"# Search benchmark dataset `{m.dataset_id}` {m.version}", ""]
    if m.description:
        lines += [m.description, ""]
    lines += [f"Created {m.created.isoformat(timespec='seconds')}; schema `{m.schema_version}`; generator "
              f"`{m.generator.get('tool', '?')}` at `{m.generator.get('git_revision') or 'unknown revision'}`.", ""]
    lines += ["## Counts", ""]
    lines += _table(["Chunks", "Documents", "Intents", "Queries", "Qrels"],
                    [[len(corpus), len({c.document_id for c in corpus.values()}), len(intents), len(queries),
                      len(qrels)]])
    languages = sorted({c.language for c in corpus.values()} | {q.language for q in queries.values()})
    chunk_languages = Counter(c.language for c in corpus.values())
    source_languages = Counter(i.source_language or "(none)" for i in intents.values())
    query_languages = Counter(q.language for q in queries.values())
    lines += ["", "## Language balance", ""]
    lines += _table(["Language", "Chunks", "Intents (source language)", "Queries"],
                    [[lang, chunk_languages[lang], source_languages[lang], query_languages[lang]]
                     for lang in languages])
    sampled = Counter(str(c.attributes.get("sampled_by", "?")) for c in corpus.values())
    lines += ["", "Chunks by how they were sampled: "
              + ", ".join(f"{k} {v}" for k, v in sorted(sampled.items())) + "."]
    near = sum(1 for c in corpus.values() if "near_duplicate_of" in c.attributes)
    if near:
        lines += [f"{near} chunks are near-duplicates of another sampled chunk (kept)."]
    styles = Counter(i.style for i in intents.values())
    origins = Counter(q.origin for q in queries.values())
    lines += ["", "## Intents and queries", ""]
    lines += _table(["Style", "Intents"], [[s, n] for s, n in styles.most_common()])
    lines += ["", "Queries by origin: " + ", ".join(f"{k} {v}" for k, v in sorted(origins.items())) + "."]
    grades = Counter(q.grade for q in qrels)
    per_intent = Counter(q.intent_id for q in qrels)
    sizes = [per_intent[i] for i in intents]
    relevant = Counter(q.intent_id for q in qrels if q.grade == 2)
    lines += ["", "## Judgements", ""]
    lines += _table(["Grade", "Qrels"], [[f"{g} ({['not relevant', 'partly', 'relevant'][g]})", grades[g]]
                                          for g in (0, 1, 2)])
    if sizes:
        lines += ["", f"Judged candidates per intent: mean {mean(sizes):.1f}, median {median(sizes):g}, "
                      f"min {min(sizes)}, max {max(sizes)}. Intents without any chunk graded 2: "
                      f"{sum(1 for i in intents if not relevant[i])}."]
    several = [q for q in qrels if q.language_grades is not None]
    if several:
        lines += [f"Judged per query language: {len(several)} pairs, "
                  f"{sum(1 for q in several if not q.consistent)} inconsistent."]
    pooled = Counter(method for q in qrels for method in q.pooled_by)
    lines += ["", "Candidates by pooling method (a candidate can have several): "
              + ", ".join(f"{k} {v}" for k, v in pooled.most_common()) + "."]
    lines += ["", "## Checks", ""]
    for name, value in m.checks.items():
        lines.append(f"- **{name}**: `{_compact(value)}`")
    usage = m.generator.get("usage")
    if usage:
        lines += ["", "## Model usage", "", "- " + ", ".join(f"{k} {v}" for k, v in usage.items())]
    if m.limitations:
        lines += ["", "## Limitations", "", *(f"- {item}" for item in m.limitations)]
    lines += ["", "## Examples", ""]
    for intent in list(intents.values())[:EXAMPLES]:
        lines += [f"**{intent.intent_id}** ({intent.style}, {intent.origin}): {_short(intent.need)}", ""]
        for query in (q for q in queries.values() if q.intent_id == intent.intent_id):
            lines.append(f"- {query.language} ({query.origin}): {_short(query.text)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _compact(value: Any) -> str:
    if isinstance(value, list) and len(value) > 5:
        return f"{len(value)} items: {value[:5]} …"
    text = str(value)
    return text if len(text) <= 300 else text[:300] + " …"
