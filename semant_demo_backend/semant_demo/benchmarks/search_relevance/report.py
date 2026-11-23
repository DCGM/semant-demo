"""Offline relevance reports of saved runs (#728, docs/SEARCH_BENCHMARK.md#reports).

Reads a dataset and runs through ``contracts``; no Weaviate, model or network::

    python -m semant_demo.benchmarks.search_relevance.report report --dataset DIR --run RUN [--run RUN2 ...] --out OUT
    python -m semant_demo.benchmarks.search_relevance.report compare --dataset DIR --run RUN [--run RUN2] \\
        --a CONFIG --b CONFIG --out OUT

``report`` writes ``report.md`` with its plots (``plots/*.png``, ``*.svg``), ``report.json`` and CSV
tables; ``compare`` writes ``comparison.md``, ``comparison.json``, ``comparison.csv`` and plots.
A configuration is named by its id, or ``run_id/configuration_id`` when several runs share it.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from uuid import UUID

from . import plots
from .analysis import (CROSS, SAME, SCORED, UNKNOWN, Configuration, Row, aggregate, inconsistent_intents,
                       intent_means, latency, paired, query_grades, rows_by_configuration, score, slice_names)
from .contracts import ContractError, Dataset, Run, load_dataset, load_run
from .metrics import BOOTSTRAP_SAMPLES, COVERAGE_METRIC, METRICS, RELEVANCE_METRICS, SEED

PRIMARY = "ndcg@10"
LABELS = {"ndcg@10": "nDCG@10", "p@10": "P@10", "p2@10": "P@10 (grade 2)", "hit@10": "Hit@10 (source)",
          "recall@20": "Recall@20", "recall@50": "Recall@50", COVERAGE_METRIC: "unjudged@10"}
REPORT_SECTIONS = ("Summary", "Conclusions", "Dataset and runs", "Configurations", "Metrics and unjudged results",
                   "Overall", "Query language × source language", "Same language and cross language",
                   "Query style", "Source chunk properties", "Latency", "Examples", "Limitations", "Files")
COMPARE_SECTIONS = ("Summary", "Conclusions", "Dataset and runs", "Configurations", "Overall",
                    "Sample sizes and judged coverage", "Query language × source language", "Slices",
                    "Latency trade-off", "Limitations", "Files")
SNIPPET = 160
TOP = 10
MISSED = 5
SLICE_SECTIONS = {"language match": "Same language and cross language", "style": "Query style"}
LANGUAGE_SLICES = ("language pair", "query language", "source language")


def label(metric: str) -> str:
    if metric.endswith("_condensed"):
        return f"{LABELS[metric.removesuffix('_condensed')]} condensed"
    return LABELS[metric]


MODE_NAMES = {"text": "BM25", "vector": "Vector", "hybrid": "Hybrid"}
"""Readable search modes; ``text`` is the application's name of BM25 keyword search."""


def display_name(config: Any) -> str:
    """A configuration's readable name, e.g. ``Hybrid bge-m3, α=0.75, relativeScore fusion``."""
    vector = config.vector
    head = MODE_NAMES.get(config.mode, config.mode)
    parts = [f"{head} {vector.model.rsplit('/', 1)[-1]}" if vector else head]
    if config.alpha is not None:
        parts.append(f"α={config.alpha:g}")
    if config.fusion:
        parts.append(f"{config.fusion} fusion")
    if vector and vector.query_prefix:
        parts.append("query prefix")
    if config.properties is not None and config.mode != "vector":
        parts.append("fields " + " ".join(f"{k}×{v:g}" for k, v in config.properties.items()))
    return ", ".join(parts)


def display_names(configs: Sequence[Configuration]) -> dict[str, str]:
    """Configuration label -> readable name, the label added where two names coincide."""
    names = {c.label: display_name(c.config) for c in configs}
    counts = Counter(names.values())
    return {k: v if counts[v] == 1 else f"{v} ({k})" for k, v in names.items()}


CONFIGURATION_TEXT = (
    "**BM25** is keyword search (the application's `text` mode). **Vector** ranks by the similarity of the query's "
    "and the chunks' embeddings from the named model. **Hybrid** combines both in Weaviate: **α** is the weight of "
    "the vector part (0 = BM25 only, 1 = vector only; the application uses 0.5) and the **fusion** combines the two "
    "result lists either by normalised scores (`relativeScore`) or by rank (`ranked`). **Query prefix**: an "
    "instruction put before the query when it is embedded (listed below the table). **Fields**: the fields BM25 "
    "searches, with their weights (`title×2` counts a title match twice); without it, the application's default "
    "fields. The **id** names "
    "the configuration in `compare`, `report.json` and the CSV files.")


# ---- loading ------------------------------------------------------------------------------

def load(dataset_dir: Path, run_dirs: Sequence[Path]) -> tuple[Dataset, list[Run]]:
    """The dataset and the runs, each verified to be of exactly this dataset (refused otherwise)."""
    dataset = load_dataset(dataset_dir)
    runs = [load_run(d, dataset) for d in run_dirs]
    ids = [r.manifest.run_id for r in runs]
    if len(set(ids)) != len(ids):
        raise ContractError(f"a run is given twice: {', '.join(sorted(i for i in set(ids) if ids.count(i) > 1))}")
    return dataset, runs


# ---- formatting ---------------------------------------------------------------------------

def number(value: float | None, digits: int = 3) -> str:
    return "–" if value is None else f"{value:.{digits}f}"


def with_ci(entry: dict[str, Any], digits: int = 3) -> str:
    if entry["mean"] is None:
        return "–"
    if entry["low"] is None:
        return number(entry["mean"], digits)
    return f"{entry['mean']:.{digits}f} [{entry['low']:.{digits}f}, {entry['high']:.{digits}f}]"


def signed(value: float | None) -> str:
    return "–" if value is None else f"{value:+.3f}"


def delta_ci(entry: dict[str, Any]) -> str:
    return "–" if entry["low"] is None else f"[{signed(entry['low'])}, {signed(entry['high'])}]"


def cell(text: Any) -> str:
    return str(text).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def table(head: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    return ["| " + " | ".join(cell(h) for h in head) + " |", "|" + "---|" * len(head),
            *("| " + " | ".join(cell(c) for c in row) + " |" for row in rows)]


def snippet(text: str, limit: int = SNIPPET) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def json_default(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (set, tuple)):
        return list(value)
    return str(value)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=1, ensure_ascii=False, default=json_default) + "\n", encoding="utf-8")


def write_csv(path: Path, head: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(head)
        writer.writerows(["" if v is None else v for v in row] for row in rows)


# ---- shared sections ----------------------------------------------------------------------

def languages(dataset: Dataset) -> tuple[list[str], list[str]]:
    """Query languages (rows) and source languages (columns) of the language matrix, in the
    manifest's order, then any other found."""
    order = list(dataset.manifest.languages)
    queries = {q.language for q in dataset.queries.values()}
    sources = {i.source_language or UNKNOWN for i in dataset.intents.values()}

    def ordered(found: set[str]) -> list[str]:
        return [lang for lang in order if lang in found] + sorted(found - set(order))
    return ordered(queries), ordered(sources)


def provenance(dataset: Dataset, runs: Sequence[Run]) -> list[str]:
    m = dataset.manifest
    lines = [f"- Dataset `{m.dataset_id}` version `{m.version}`, created {m.created.isoformat()}, manifest SHA-256 "
             f"`{dataset.manifest_sha256()}`: {len(dataset.corpus)} chunks, {len(dataset.intents)} intents, "
             f"{len(dataset.queries)} queries, {len(dataset.qrels)} qrels."]
    if m.description:
        lines.append(f"- Description: {m.description}")
    for judge in m.judges:
        p = judge.provenance
        details = ", ".join(f"{k} `{p[k]}`" for k in ("model", "prompt_version", "max_input_tokens") if p.get(k))
        lines.append(f"- Judge `{judge.id}` (the model that graded the qrels): {details or 'no details recorded'}.")
    if m.pooling:
        lines.append("- Searches that proposed the chunks to grade (pooling): "
                     + "; ".join(f"`{p.id}` ({p.description or 'no description'})" for p in m.pooling) + ".")
    for run in runs:
        r = run.manifest
        env = r.environment if isinstance(r.environment, dict) else {}
        store = env.get("store") if isinstance(env.get("store"), dict) else {}
        git = env.get("git") if isinstance(env.get("git"), dict) else {}
        facts = [f"{len(run.results)} searches", f"started {env.get('started') or r.created.isoformat()}"]
        if env.get("finished"):
            facts.append(f"finished {env['finished']}")
        if git.get("revision"):
            facts.append(f"code `{str(git['revision'])[:12]}`" + (" (with uncommitted changes)" if git.get("dirty") else ""))
        if store.get("weaviate_version"):
            facts.append(f"Weaviate {store['weaviate_version']}")
        lines.append(f"- Run `{r.run_id}`: {', '.join(facts)}.")
    lines.append("- Every setting (store schema, endpoints, budgets) is in `report.json` under `dataset` and `runs`.")
    return lines


def configuration_table(configs: Sequence[Configuration], names: dict[str, str] | None = None) -> list[str]:
    names = names or display_names(configs)
    prefixes = list(dict.fromkeys(c.config.vector.query_prefix for c in configs
                                  if c.config.vector and c.config.vector.query_prefix))
    marks = {p: "yes" if len(prefixes) == 1 else f"P{n}" for n, p in enumerate(prefixes, 1)}
    rows = []
    for c in configs:
        x = c.config
        vector = x.vector
        props = "default" if x.properties is None else " ".join(f"{k}×{v:g}" for k, v in x.properties.items())
        rows.append([names[c.label], f"`{c.label}`", vector.model if vector else "–",
                     marks[vector.query_prefix] if vector and vector.query_prefix else "–",
                     "–" if x.alpha is None else f"{x.alpha:g}", x.fusion or "–",
                     props if x.mode != "vector" else "–"])
    runs = sorted({c.run_id for c in configs})
    return [CONFIGURATION_TEXT, "",
            *table(["name", "id", "embedding model", "query prefix", "α", "fusion", "fields"], rows), "",
            *(f"- Query prefix{'' if len(prefixes) == 1 else ' ' + marks[p]}: `{repr(p)}`" for p in prefixes),
            "", f"Run{'s' if len(runs) > 1 else ''}: {', '.join(f'`{r}`' for r in runs)}; each search keeps the top "
            f"{', '.join(sorted({str(c.config.depth) for c in configs}))} chunks."]


def limitations(dataset: Dataset, configs: Sequence[Configuration], unjudged: dict[str, dict[str, Any]],
                excluded: int, inconsistent: int) -> list[str]:
    judges = ", ".join(f"`{j.id}`" for j in dataset.manifest.judges) or "(none declared)"
    pools = ", ".join(f"`{p.id}`" for p in dataset.manifest.pooling) or "(none declared)"
    lines = [
        f"- **The qrels are judged by an LLM ({judges}) and pooled** (from the source chunks and {pools}). They are "
        "not exhaustive: a relevant chunk that no pooling method proposed is unjudged. The standard metrics count it "
        "as not relevant, so they are **lower bounds**, and recall is recall of the *judged* relevant chunks. A "
        "configuration unlike the pooling methods retrieves more unjudged chunks and is penalised more; read its "
        "standard score with its unjudged rate and its condensed score.",
        f"- How much this matters: the share of unjudged chunks in the top 10 is {unjudged_range(configs, unjudged)} "
        "(the report's \"Effect of unjudged results\" shows how it moves each configuration).",
        "- **The LLM grades are not verified by people**; the judge can be wrong or biased (e.g. towards one "
        "language).",
        "- Latency is measured on the benchmark's isolated, smaller store; it does not predict production-scale "
        "latency or memory (#374, #394).",
        f"- Intents with qrels whose per-language grades disagree (`consistent: false`): {inconsistent}; a query "
        f"is scored with its own language's grade where one was judged, otherwise with the intent's `grade`. "
        f"Left out of this report: {excluded}.",
        "- Searches that ended in an error, and queries a run did not search, are left out of the means (see "
        "\"Queries\" under Overall).",
    ]
    shallow = [c.label for c in configs if c.config.depth < 50]
    if shallow:
        lines.append(f"- Depth below 50 ({', '.join(shallow)}): these configurations keep too few chunks for "
                     "Recall@50, which is not shown for them (likewise Recall@20 below depth 20).")
    lines += [f"- Dataset: {text}" for text in dataset.manifest.limitations]
    return lines


# ---- report -------------------------------------------------------------------------------

def find(aggregates: Sequence[dict[str, Any]], config: str, slice_: str, group: str) -> dict[str, Any] | None:
    for entry in aggregates:
        if (entry["configuration"], entry["slice"], entry["group"]) == (config, slice_, group):
            return entry
    return None


def unjudged_range(configs: Sequence[Configuration], unjudged: dict[str, dict[str, Any]]) -> str:
    rates = [unjudged[c.label]["mean"] for c in configs if unjudged[c.label]["mean"] is not None]
    if not rates:
        return "not known (no scored query)"
    return number(rates[0]) if len(rates) == 1 else f"{number(min(rates))} to {number(max(rates))}"


def query_counts(configs: Sequence[Configuration], aggregates: Sequence[dict[str, Any]],
                 names: dict[str, str]) -> list[str]:
    """How many queries each configuration searched and scored, in words when they are all alike."""
    overall = {c.label: find(aggregates, c.label, "overall", "all") for c in configs}
    first = next(iter(overall.values()))
    lines = []
    unscored = {k: e for k, e in overall.items() if e["failed"] or e["missing"]}
    if not unscored:
        lines.append(f"- Every configuration searched all {first['queries']} queries ({first['intents']} intents) "
                     "without an error.")
    else:
        lines += ["- Some searches have no result. A **search error** is a search that failed in the run (for "
                  "example a timeout of the embedding model); **not searched** is a query of the dataset that the "
                  "run has no result for (an interrupted run, or one limited to some queries). Both are left out "
                  "of the means:", "",
                  *table(["configuration", "queries", "search errors", "not searched"],
                         [[names[k], e["queries"], e["failed"], e["missing"]] for k, e in unscored.items()]), ""]
    no_relevant = max(e["no_relevant"] for e in overall.values())
    if no_relevant:
        lines.append(f"- {no_relevant} queries belong to intents with no chunk judged relevant (grade ≥ 1), so "
                     "they have no nDCG@10, P@10 or recall; they are left out of those means (Hit@10 and "
                     "unjudged@10 still count them).")
    return lines


def overall_tables(configs: Sequence[Configuration], aggregates: Sequence[dict[str, Any]],
                   names: dict[str, str] | None = None) -> list[str]:
    names = names or display_names(configs)
    head = ["configuration", *(label(m) for m in RELEVANCE_METRICS), label(COVERAGE_METRIC)]
    standard, condensed_rows = [], []
    for c in configs:
        e = find(aggregates, c.label, "overall", "all")
        standard.append([names[c.label], *(with_ci(e["metrics"][m]) for m in RELEVANCE_METRICS),
                         with_ci(e["metrics"][COVERAGE_METRIC])])
        condensed_rows.append([names[c.label], *(with_ci(e["metrics"][f"{m}_condensed"]) for m in RELEVANCE_METRICS)])
    return ["**Queries.**", "", *query_counts(configs, aggregates, names), "",
            "**Standard scores** (primary): an unjudged chunk counts as not relevant. Mean with its 95% CI.", "",
            *table(head, standard), "",
            "**Condensed scores**: unjudged chunks are removed from each ranking before scoring.", "",
            *table(["configuration", *(label(m) for m in RELEVANCE_METRICS)], condensed_rows), "",
            "### Effect of unjudged results", "", *unjudged_effect(configs, aggregates, names)]


def unjudged_effect(configs: Sequence[Configuration], aggregates: Sequence[dict[str, Any]],
                    names: dict[str, str]) -> list[str]:
    """How the unjudged chunks move each configuration: its unjudged share, its standard and condensed
    nDCG@10 and its rank by each, with the rank correlation of the two orders."""
    overall = {c.label: find(aggregates, c.label, "overall", "all")["metrics"] for c in configs}
    scored = [c.label for c in configs if overall[c.label][PRIMARY]["mean"] is not None
              and overall[c.label][f"{PRIMARY}_condensed"]["mean"] is not None]
    if len(scored) < 2:
        return []
    standard = sorted(scored, key=lambda c: (-overall[c][PRIMARY]["mean"], c))
    condensed = sorted(scored, key=lambda c: (-overall[c][f"{PRIMARY}_condensed"]["mean"], c))
    rank_s = {c: n for n, c in enumerate(standard, 1)}
    rank_c = {c: n for n, c in enumerate(condensed, 1)}
    n = len(scored)
    rho = 1 - 6 * sum((rank_s[c] - rank_c[c]) ** 2 for c in scored) / (n * (n * n - 1))
    shift = max(abs(rank_s[c] - rank_c[c]) for c in scored)
    rows = [[names[c], number(overall[c][COVERAGE_METRIC]["mean"]), number(overall[c][PRIMARY]["mean"]), rank_s[c],
             number(overall[c][f"{PRIMARY}_condensed"]["mean"]), rank_c[c],
             signed(overall[c][f"{PRIMARY}_condensed"]["mean"] - overall[c][PRIMARY]["mean"])] for c in standard]
    return ["A chunk in a top 10 that no pooling search proposed has no grade. The standard score counts it as not "
            "relevant (a lower bound); the condensed score drops it (closer to an upper bound). A configuration "
            "unlike the pooling searches returns more unjudged chunks, so its standard score is pulled down more. "
            "Where the two orders of the configurations agree, the conclusions about which is better do not depend "
            "on the missing grades; the absolute scores do.", "",
            f"- Rank correlation (Spearman) of the standard and the condensed order: {rho:.2f}; the largest move "
            f"is {shift} place{'s' if shift != 1 else ''}.", "",
            *table(["configuration", "unjudged@10", "nDCG@10 standard", "rank", "nDCG@10 condensed", "rank",
                    "condensed − standard"], rows)]


def slice_table(configs: Sequence[Configuration], aggregates: Sequence[dict[str, Any]], slice_: str,
                names: dict[str, str] | None = None) -> list[str]:
    names = names or display_names(configs)
    entries = [e for c in configs for e in aggregates if e["configuration"] == c.label and e["slice"] == slice_]
    errors = any(e["failed"] for e in entries)
    rows = []
    for e in entries:
        m = e["metrics"]
        rows.append([names[e["configuration"]], e["group"], e["scored"], e["intents"],
                     *([e["failed"]] if errors else []), with_ci(m[PRIMARY]),
                     with_ci(m[f"{PRIMARY}_condensed"]), number(m["p@10"]["mean"]),
                     number(m["hit@10"]["mean"]), number(m[COVERAGE_METRIC]["mean"])])
    return table(["configuration", slice_, "queries", "intents", *(["search errors"] if errors else []),
                  "nDCG@10 [95% CI]", "nDCG@10 condensed", "P@10", "Hit@10", "unjudged@10"], rows)


def language_grid(dataset: Dataset, aggregates: Sequence[dict[str, Any]], config: str,
                  metric: str = PRIMARY) -> tuple[list[list[dict[str, Any] | None]], list[str], list[str]]:
    rows, columns = languages(dataset)
    grid = []
    for q in rows:
        line = []
        for s in columns:
            e = find(aggregates, config, "language pair", f"{q}→{s}")
            line.append(None if e is None else {**e["metrics"][metric], "scored": e["scored"],
                                                 "unscored": e["failed"] + e["missing"]})
        grid.append(line)
    return grid, rows, columns


def grid_markdown(grid: list[list[dict[str, Any] | None]], rows: list[str], columns: list[str],
                  render) -> list[str]:
    return table(["query ↓ / source →", *columns],
                 [[q, *("–" if v is None else render(v) for v in line)] for q, line in zip(rows, grid)])


def chunk_line(dataset: Dataset, chunk_id: UUID, grades: dict[UUID, int], sources: set[UUID], rank: Any) -> list[Any]:
    chunk = dataset.corpus.get(chunk_id)
    grade = grades.get(chunk_id)
    marks = " (source)" if chunk_id in sources else ""
    return [rank, f"`{chunk_id}`{marks}", chunk.language if chunk else "–",
            "unjudged" if grade is None else grade, snippet(chunk.text) if chunk else "–"]


def examples(dataset: Dataset, rows: Sequence[Row], config: str, count: int,
             name: str | None = None) -> tuple[list[str], list[dict[str, Any]]]:
    """The ``count`` best and worst intents of a configuration by mean nDCG@10, each with its
    best (or worst) query: top hits with grades and the relevant chunks it missed. ``rows`` may be
    the configuration's own (``rows_by_configuration``) or all."""
    mine = [r for r in rows if r.configuration == config]
    means = intent_means(mine)
    order = sorted(means, key=lambda i: (means[i], i))
    worst = order[:count]
    best = [i for i in reversed(order) if i not in worst][:count]
    grades_of = query_grades(dataset)
    lines: list[str] = []
    found = []
    for kind, intents in (("Best", best), ("Worst", worst)):
        for n, intent_id in enumerate(intents, 1):
            intent = dataset.intents[intent_id]
            sources = set(intent.source_chunk_ids)
            queries = [r for r in mine if r.intent_id == intent_id and r.status == SCORED
                       and r.metrics.get(PRIMARY) is not None]
            queries.sort(key=lambda r: (r.metrics[PRIMARY], r.query_id), reverse=kind == "Best")
            row = queries[0]
            query = dataset.queries[row.query_id]
            grades = grades_of(intent_id, query.language)  # the grades the query's metrics used
            top = row.ranked[:TOP]
            relevant = sorted((c for c, g in grades.items() if g >= 1), key=lambda c: (-grades[c], str(c)))
            missed = [c for c in relevant if c not in top]
            others = ", ".join(f"{r.query_language} {number(r.metrics[PRIMARY], 2)}" for r in
                               sorted(queries, key=lambda r: r.query_language))
            failed = [r.query_language for r in mine if r.intent_id == intent_id and r.status != SCORED]
            lines += [f"#### {name or config}: {kind.lower()} {n}, intent `{intent_id}` "
                      f"(mean nDCG@10 {number(means[intent_id])})",
                      "",
                      f"- Need: {cell(intent.need)}",
                      f"- Style `{intent.style}`, source language `{intent.source_language or UNKNOWN}`, "
                      f"source chunks {', '.join(f'`{c}`' for c in intent.source_chunk_ids) or '–'}",
                      f"- Query `{query.query_id}` ({query.language}): “{cell(query.text)}”, nDCG@10 "
                      f"{number(row.metrics[PRIMARY])}, unjudged@10 {number(row.metrics[COVERAGE_METRIC])}",
                      f"- nDCG@10 by query language: {others}" + (f"; not scored: {', '.join(failed)}" if failed else ""),
                      "", f"Top {TOP} results:", "",
                      *table(["rank", "chunk", "language", "grade", "text"],
                             [chunk_line(dataset, c, grades, sources, rank) for rank, c in enumerate(top, 1)]
                             or [["–", "no results", "", "", ""]]),
                      ""]
            if missed:
                lines += [f"Relevant chunks it missed ({len(missed)}, the first {min(len(missed), MISSED)}):", "",
                          *table(["rank", "chunk", "language", "grade", "text"],
                                 [chunk_line(dataset, c, grades, sources,
                                             row.ranked.index(c) + 1 if c in row.ranked else "not retrieved")
                                  for c in missed[:MISSED]]), ""]
            else:
                lines += ["It missed no judged relevant chunk.", ""]
            found.append({"configuration": config, "kind": kind.lower(), "intent_id": intent_id,
                          "intent_mean": means[intent_id], "query_id": query.query_id,
                          "ndcg@10": row.metrics[PRIMARY], "top": [str(c) for c in top],
                          "missed": [str(c) for c in missed]})
    return lines, found


SUMMARY_TOP = 5
"""Configurations the summary shows; the full ranking is in the Overall section."""


def report_summary(dataset: Dataset, configs: Sequence[Configuration], aggregates: Sequence[dict[str, Any]],
                   inconsistent: int, excluded: bool, names: dict[str, str] | None = None) -> list[str]:
    names = names or display_names(configs)
    overall = {c.label: find(aggregates, c.label, "overall", "all") for c in configs}
    lines = [f"- {len(configs)} configuration(s) on dataset `{dataset.manifest.dataset_id}` "
             f"`{dataset.manifest.version}` ({len(dataset.intents)} intents, {len(dataset.queries)} queries). "
             f"Primary metric: nDCG@10, standard variant (unjudged = not relevant); 95% CIs resample intents."]
    ranked = sorted((c.label for c in configs if overall[c.label]["metrics"][PRIMARY]["mean"] is not None),
                    key=lambda c: -overall[c]["metrics"][PRIMARY]["mean"])

    def language_match(label: str, group: str) -> float | None:
        found = find(aggregates, label, "language match", group)
        return found["metrics"][PRIMARY]["mean"] if found else None
    if ranked:
        best = overall[ranked[0]]["metrics"][PRIMARY]
        rows = []
        for rank, label in enumerate(ranked[:SUMMARY_TOP], 1):
            same, cross = language_match(label, SAME), language_match(label, CROSS)
            gap = same - cross if same is not None and cross is not None else None
            rows.append([str(rank), names[label], with_ci(overall[label]["metrics"][PRIMARY]), number(same),
                         number(cross), signed(gap) if gap is not None else "–"])
        lines += ["", f"The {len(rows)} configurations with the highest nDCG@10 (of {len(ranked)}; the full ranking "
                  "and every configuration's same/cross-language scores are in the sections below). Same language: "
                  "the query is in the language of the chunk it was written from; cross language: it is not; "
                  "gap = same − cross.", "",
                  *table(["#", "configuration", "nDCG@10 [95% CI]", "same language", "cross language", "gap"], rows),
                  ""]
        if len(ranked) > SUMMARY_TOP:
            worst = ranked[-1]
            lines.append(f"- Lowest nDCG@10: {names[worst]} — {with_ci(overall[worst]['metrics'][PRIMARY])}.")
        if best["low"] is not None:
            overlapping = [c for c in ranked[1:] if overall[c]["metrics"][PRIMARY]["high"] is not None
                           and overall[c]["metrics"][PRIMARY]["high"] >= best["low"]]
            if overlapping:
                named = "; ".join(names[c] for c in overlapping[:SUMMARY_TOP])
                more = f" and {len(overlapping) - SUMMARY_TOP} more" if len(overlapping) > SUMMARY_TOP else ""
                lines.append(f"- The best's CI overlaps those of {len(overlapping)} configuration(s) ({named}{more}): "
                             "use `compare` (with the ids of the Configurations section) for a paired test before "
                             "calling it better.")
    rates = [overall[c.label]["metrics"][COVERAGE_METRIC]["mean"] for c in configs]
    rates = [r for r in rates if r is not None]
    if rates:
        lines.append(f"- Unjudged share of the top 10: {number(min(rates))} to {number(max(rates))} across "
                     "configurations; the standard scores count these as not relevant (see Limitations).")
    failed = {c.label: overall[c.label]["failed"] + overall[c.label]["missing"] for c in configs}
    if any(failed.values()):
        lines.append("- Queries without a result (a search error or not searched; left out of the means): "
                     + ", ".join(f"{names[c]} {n}" for c, n in failed.items() if n) + ".")
    no_relevant = max(overall[c.label]["no_relevant"] for c in configs)
    if no_relevant:
        lines.append(f"- Queries whose intent has no chunk judged relevant (no nDCG, P or recall): {no_relevant}.")
    lines.append(f"- Intents with inconsistent per-language grades: {inconsistent} "
                 f"({'left out' if excluded else 'included'}).")
    return lines


CONCLUSIONS = ("_To be written by the reviewer from the numbers above: which configuration to recommend for general "
               "search, what the cross-language results show and which follow-up experiments are worth running. "
               "This report states measurements only._")


def build_report(dataset: Dataset, runs: Sequence[Run], out: Path, *, exclude_inconsistent: bool = False,
                 samples: int = BOOTSTRAP_SAMPLES, seed: int = SEED, example_count: int = 2,
                 conclusions: str | None = None) -> dict[str, Any]:
    """Writes the report; ``conclusions`` is the reviewer's Markdown for the Conclusions section
    (a placeholder without it)."""
    out.mkdir(parents=True, exist_ok=True)
    configs, rows = score(dataset, runs, exclude_inconsistent)
    aggregates = aggregate(configs, rows, seed=seed, samples=samples)
    times = latency(configs, rows)
    inconsistent = len(inconsistent_intents(dataset))
    excluded = inconsistent if exclude_inconsistent else 0
    labels = [c.label for c in configs]
    names = display_names(configs)
    shown = [names[c] for c in labels]
    overall = {c: find(aggregates, c, "overall", "all") for c in labels}
    plot_dir = out / "plots"
    images = {"ndcg": plots.metric_bars(shown, [overall[c]["metrics"][PRIMARY] for c in labels],
                                        [overall[c]["metrics"][f"{PRIMARY}_condensed"] for c in labels],
                                        "nDCG@10", plot_dir, "ndcg_by_configuration")}
    grids = [language_grid(dataset, aggregates, c) for c in labels]
    query_langs, source_langs = languages(dataset)
    images["matrix"] = plots.matrices(shown, [[[None if v is None else v["mean"] for v in line] for line in g[0]]
                                               for g in grids], query_langs, source_langs, plot_dir,
                                      "language_matrix", label="nDCG@10")
    images["latency"] = plots.latency(shown, [{**t, "configuration": names.get(t["configuration"], t["configuration"])}
                                              for t in times], plot_dir, "latency")

    def rel(path: Path) -> str:
        return path.relative_to(out).as_posix()

    md = ["# Search relevance report", "", "## Summary", "",
          *report_summary(dataset, configs, aggregates, inconsistent, exclude_inconsistent, names), "",
          "## Conclusions", "", conclusions.strip() if conclusions and conclusions.strip() else CONCLUSIONS, "",
          "## Dataset and runs", "", *provenance(dataset, runs), "",
          "## Configurations", "", *configuration_table(configs, names), "",
          "## Metrics and unjudged results", "", *METRIC_TEXT, "",
          "## Overall", "", *overall_tables(configs, aggregates, names), "",
          f"![nDCG@10 by configuration]({rel(images['ndcg'][0])})", "",
          "## Query language × source language", "",
          "nDCG@10 by the query's language (rows) and the language of the intent's source chunk (columns), with "
          "its 95% CI and the number of scored queries. The diagonal is same-language search.", ""]
    for c, (grid, qrows, scols) in zip(labels, grids):
        md += [f"### {names[c]}", "", *grid_markdown(grid, qrows, scols, lambda v: f"{with_ci(v, 2)} (n={v['scored']}"
                                                + (f", {v['unscored']} without a result)" if v["unscored"] else ")")), ""]
    md += [f"![nDCG@10 by language pair]({rel(images['matrix'][0])})", "",
           "Marginals by query language and by source language:", "",
           *slice_table(configs, aggregates, "query language", names), "",
           *slice_table(configs, aggregates, "source language", names),
           ""]
    for slice_, title in SLICE_SECTIONS.items():
        md += [f"## {title}", "", *slice_table(configs, aggregates, slice_, names), ""]
    md += ["## Source chunk properties", "",
           "Slices by properties of the intent's source chunk(s) (attributes with at most a dozen values; "
           "\"mixed\" when an intent's source chunks differ).", ""]
    extra = [s for s in dict.fromkeys(e["slice"] for e in aggregates)
             if s not in ("overall", *SLICE_SECTIONS, *LANGUAGE_SLICES)]
    for slice_ in extra:
        md += [f"### {slice_}", "", *slice_table(configs, aggregates, slice_, names), ""]
    if not extra:
        md += ["No source chunk property varies across the intents.", ""]
    md += ["## Latency", "",
           "Milliseconds over the successful searches: query embedding (`embed_ms`, none for BM25), search "
           "(`search_ms`) and their sum per query.", "",
           *table(["configuration", "searches", "embed p50", "embed p95", "search p50", "search p95", "total p50",
                   "total p95"],
                  [[names.get(t["configuration"], t["configuration"]), t["searches"], *(number(t[f"{p}_{q}"], 1) for p in ("embed_ms", "search_ms",
                                                                                              "total_ms")
                                                         for q in ("p50", "p95"))] for t in times]), "",
           f"![Latency]({rel(images['latency'][0])})", "",
           "## Examples", "",
           f"`examples.md`: per configuration, the {example_count} best and worst intents by mean nDCG@10, each "
           "with its best or worst query, its top 10 chunks with their grades and the relevant chunks it missed.", ""]
    example_md = ["# Search relevance examples", "",
                  f"Dataset `{dataset.manifest.dataset_id}` `{dataset.manifest.version}`. Per configuration, the "
                  f"{example_count} best and worst intents by mean nDCG@10, each with its best or worst query. "
                  "Grades: 2 relevant, 1 partly, 0 not relevant, \"unjudged\" without a qrel (never graded). "
                  "The terms and configurations are explained in `report.md`.", ""]
    example_docs = []
    by_configuration = rows_by_configuration(rows)
    for c in labels:
        lines, found = examples(dataset, by_configuration.get(c, []), c, example_count, names[c])
        example_md += [f"## {names[c]}", "", f"Id `{c}`.", "",
                       *(lines or ["No scored query with a relevant qrel."]), ""]
        example_docs += found
    unjudged = {c: overall[c]["metrics"][COVERAGE_METRIC] for c in labels}
    md += ["## Limitations", "", *limitations(dataset, configs, unjudged, excluded, inconsistent), "",
           "## Files", "",
           "- `examples.md`: the examples above.",
           "- `report.json`: everything in this report, machine-readable.",
           "- `summary.csv`: every slice and metric (mean, CI, counts) per configuration.",
           "- `queries.csv`: every query's status and metrics per configuration.",
           "- `latency.csv`: latency percentiles per configuration.",
           f"- `plots/`: {', '.join(sorted(p.name for ps in images.values() for p in ps))}.", ""]
    (out / "report.md").write_text("\n".join(md), encoding="utf-8")
    (out / "examples.md").write_text("\n".join(example_md), encoding="utf-8")

    settings = {"exclude_inconsistent": exclude_inconsistent, "bootstrap_samples": samples, "seed": seed,
                "primary": PRIMARY, "primary_variant": "standard", "ci": "95% percentile bootstrap over intents"}
    doc = {"dataset": {**dataset.manifest.model_dump(mode="json", exclude={"files"}),
                       "manifest_sha256": dataset.manifest_sha256()},
           "runs": [r.manifest.model_dump(mode="json") for r in runs],
           "configurations": [{"label": c.label, "run_id": c.run_id, **c.config.model_dump(mode="json")}
                              for c in configs],
           "settings": settings, "inconsistent_intents": inconsistent, "excluded_intents": excluded,
           "aggregates": aggregates, "latency": times, "examples": example_docs,
           "queries": [query_record(r) for r in rows]}
    write_json(out / "report.json", doc)
    write_summary_csv(out / "summary.csv", aggregates)
    write_csv(out / "queries.csv", QUERY_HEAD, [[query_record(r)[k] for k in QUERY_HEAD] for r in rows])
    write_csv(out / "latency.csv", list(times[0]) if times else ["configuration"],
              [list(t.values()) for t in times])
    return doc


QUERY_HEAD = ["configuration", "query_id", "intent_id", "query_language", "source_language", "style", "status",
              "error", "embed_ms", "search_ms", *METRICS]


def query_record(row: Row) -> dict[str, Any]:
    return {"configuration": row.configuration, "query_id": row.query_id, "intent_id": row.intent_id,
            "query_language": row.query_language, "source_language": row.source_language, "style": row.style,
            "status": row.status, "error": row.error, "embed_ms": row.embed_ms, "search_ms": row.search_ms,
            **{m: row.metrics.get(m) for m in METRICS}}


def write_summary_csv(path: Path, aggregates: Sequence[dict[str, Any]]) -> None:
    head = ["configuration", "slice", "group", "queries", "scored", "failed", "missing", "intents", "no_relevant",
            *(f"{m}_{part}" for m in METRICS for part in ("mean", "low", "high", "n"))]
    rows = [[e["configuration"], e["slice"], e["group"], e["queries"], e["scored"], e["failed"], e["missing"],
             e["intents"], e["no_relevant"],
             *(e["metrics"][m][part] for m in METRICS for part in ("mean", "low", "high", "n"))] for e in aggregates]
    write_csv(path, head, rows)


METRIC_TEXT = [
    "**Terms.** An **intent** is an information need written by a model from a source chunk; its **queries** "
    "are the same need phrased in each query language. A **qrel** (query relevance judgement) is the answer "
    "key for one (intent, chunk) pair: the grade a model judge gave that chunk for the need. Only the chunks "
    "the generator pooled for an intent were graded; a returned chunk with no qrel for the intent is "
    "**unjudged** (its relevance is unknown). See `docs/SEARCH_BENCHMARK.md` for how they are made.",
    "",
    "Every query is scored against the graded qrels of its **intent** (its translations share them; where a "
    "qrel was judged per query language, a query uses its own language's grade). "
    "Grades: 2 relevant, 1 partly relevant, 0 not relevant.",
    "",
    "- **nDCG@10**: DCG of the top 10 with gain 2^grade − 1 and discount log2(rank + 1), divided by the DCG of the "
    "ideal ranking of **all** the intent's qrels (not only the retrieved ones).",
    "- **P@10**: share of the 10 slots holding a chunk graded ≥ 1; **P@10 (grade 2)** counts grade 2 only. "
    "Fewer than 10 hits leave empty slots that count as misses.",
    "- **Hit@10 (source)**: 1 when a chunk the intent was written from is in the top 10.",
    "- **Recall@20, Recall@50**: share of the intent's judged relevant chunks (grade ≥ 1) in the top 20 / 50; "
    "not shown for a configuration that keeps fewer chunks (its depth).",
    "- **unjudged@10**: share of the returned top-10 chunks without a qrel for the intent.",
    "- Queries whose intent has no relevant qrel have no nDCG, P or recall; intents without a source chunk have "
    "no Hit@10. Means leave them out, and the tables count them.",
    "- **Unjudged results.** The **standard** variant (primary) treats an unjudged chunk as not relevant: a lower "
    "bound when pooling missed relevant chunks. The **condensed** variant removes unjudged chunks from the "
    "ranking before scoring; it ignores them instead and tends to overestimate. Both are reported.",
    "- **Queries without a result**: a search that ended in an error in the run (a *search error*) or a query "
    "the run did not search (*not searched*) is left out of the means; the Overall section counts them.",
    "- **queries, intents** (slice tables): how many scored queries, and of how many intents, a group's mean "
    "is over.",
    "- **Means and CIs.** A mean is over the scored queries; its 95% CI is a percentile bootstrap that resamples "
    "**intents** with replacement (all formulations of an intent together, since its translations are not "
    "independent), with a fixed seed.",
]


# ---- compare ------------------------------------------------------------------------------

def resolve(configs: Sequence[Configuration], name: str) -> Configuration:
    """A configuration by its label, or ``run_id/configuration_id``, or its id when unique."""
    for c in configs:
        if name in (c.label, f"{c.run_id}/{c.config.configuration_id}"):
            return c
    matches = [c for c in configs if c.config.configuration_id == name]
    if len(matches) == 1:
        return matches[0]
    known = ", ".join(c.label for c in configs)
    raise ContractError(f"configuration {name!r} is {'ambiguous' if matches else 'unknown'}; known: {known}")


def build_compare(dataset: Dataset, runs: Sequence[Run], a_name: str, b_name: str, out: Path, *,
                  exclude_inconsistent: bool = False, samples: int = BOOTSTRAP_SAMPLES,
                  seed: int = SEED) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    configs, rows = score(dataset, runs, exclude_inconsistent)
    a, b = resolve(configs, a_name), resolve(configs, b_name)
    if a.label == b.label:
        raise ContractError("compare needs two different configurations")
    pair = [a, b]
    rows_a = [r for r in rows if r.configuration == a.label]
    rows_b = [r for r in rows if r.configuration == b.label]
    aggregates = aggregate(pair, rows, seed=seed, samples=samples)
    times = latency(pair, rows)
    inconsistent = len(inconsistent_intents(dataset))
    excluded = inconsistent if exclude_inconsistent else 0
    key = (a.label, b.label)
    overall = [paired(rows_a, rows_b, m, key=(*key, "overall"), seed=seed, samples=samples) for m in METRICS]
    slices: list[dict[str, Any]] = []
    for slice_ in slice_names(rows_a):
        groups = sorted({r.slices[slice_] for r in rows_a})
        for group in groups:
            entry = paired(rows_a, rows_b, PRIMARY, key=(*key, slice_, group), seed=seed, samples=samples,
                           where=lambda r, s=slice_, g=group: r.slices[s] == g)
            slices.append({"slice": slice_, "group": group, **entry})
    plot_dir = out / "plots"
    query_langs, source_langs = languages(dataset)
    delta_grid = [[next((s for s in slices if s["slice"] == "language pair" and s["group"] == f"{q}→{s_}"), None)
                   for s_ in source_langs] for q in query_langs]
    images = {
        "matrix": plots.matrices([f"Δ nDCG@10: {b.label} − {a.label}"],
                                 [[[None if v is None else v["delta"] for v in line] for line in delta_grid]],
                                 query_langs, source_langs, plot_dir, "delta_language_matrix", label="Δ nDCG@10",
                                 diverging=True),
        "slices": plots.deltas([f"{s['slice']}: {s['group']}" for s in slices if s["slice"] != "language pair"],
                               [s for s in slices if s["slice"] != "language pair"], "nDCG@10", plot_dir,
                               "delta_by_slice"),
        "latency": plots.latency([a.label, b.label], times, plot_dir, "latency"),
    }

    def rel(path: Path) -> str:
        return path.relative_to(out).as_posix()

    by_metric = {e["metric"]: e for e in overall}
    primary = by_metric[PRIMARY]
    names = display_names(pair)
    summary = [f"- A = {names[a.label]} (`{a.label}`), B = {names[b.label]} (`{b.label}`); Δ = B − A over the queries both scored "
               f"({primary['n']} queries, {primary['clusters']} intents); 95% CI from a paired bootstrap over intents."]
    for metric in (PRIMARY, f"{PRIMARY}_condensed", "p@10", "hit@10", "recall@50"):
        e = by_metric[metric]
        if e["delta"] is None:
            continue
        if e["low"] is None:
            verdict = "too few intents for a CI"
        elif e["low"] > 0:
            verdict = "B higher (CI above 0)"
        elif e["high"] < 0:
            verdict = "B lower (CI below 0)"
        else:
            verdict = "no difference resolved at this sample size (CI includes 0)"
        summary.append(f"- {label(metric)}: A {number(e['a'])}, B {number(e['b'])}, Δ {signed(e['delta'])} "
                       f"{delta_ci(e)}: {verdict}.")
    for s in (x for x in slices if x["slice"] == "language match" and x["delta"] is not None):
        summary.append(f"- {s['group']}: Δ nDCG@10 {signed(s['delta'])} {delta_ci(s)} "
                       f"({s['n']} queries).")
    t = {x["configuration"]: x for x in times}
    if t[a.label]["total_ms_p50"] is not None and t[b.label]["total_ms_p50"] is not None:
        summary.append(f"- Latency p50 (embedding + search): A {number(t[a.label]['total_ms_p50'], 1)} ms, "
                       f"B {number(t[b.label]['total_ms_p50'], 1)} ms.")
    ov = {c.label: find(aggregates, c.label, "overall", "all") for c in pair}
    unjudged = {c.label: ov[c.label]["metrics"][COVERAGE_METRIC] for c in pair}

    md = [f"# Search relevance comparison: {a.label} vs {b.label}", "", "## Summary", "", *summary, "",
          "## Conclusions", "", CONCLUSIONS, "",
          "## Dataset and runs", "", *provenance(dataset, list({r.manifest.run_id: r for r in runs
                                                                 if r.manifest.run_id in (a.run_id, b.run_id)}.values())),
          "", "## Configurations", "", *configuration_table(pair, names), "",
          "## Overall", "",
          "Means over the queries scored by both configurations with a value of the metric (paired); "
          "standard variant unless named condensed. See the report's metric definitions.", "",
          *table(["metric", f"A {a.label}", f"B {b.label}", "Δ (B − A)", "95% CI of Δ", "paired queries", "intents"],
                 [[label(e["metric"]), number(e["a"]), number(e["b"]), signed(e["delta"]),
                   delta_ci(e), e["n"], e["clusters"]]
                  for e in overall]), "",
          "## Sample sizes and judged coverage", "",
          *table(["configuration", "queries", "scored", "failed", "missing", "intents", "no relevant qrel",
                  "unjudged@10 [95% CI]", "nDCG@10 (all its scored queries)", "nDCG@10 condensed"],
                 [[c.label, ov[c.label]["queries"], ov[c.label]["scored"], ov[c.label]["failed"],
                   ov[c.label]["missing"], ov[c.label]["intents"], ov[c.label]["no_relevant"],
                   with_ci(unjudged[c.label]), with_ci(ov[c.label]["metrics"][PRIMARY]),
                   with_ci(ov[c.label]["metrics"][f"{PRIMARY}_condensed"])] for c in pair]), "",
          "## Query language × source language", "",
          "Δ nDCG@10 (B − A) by query language (rows) and source language (columns), with its paired 95% CI.", "",
          *table(["query ↓ / source →", *source_langs],
                 [[q, *("–" if v is None or v["delta"] is None else
                        f"{signed(v['delta'])} {'' if v['low'] is None else delta_ci(v) + ' '}(n={v['n']})" for v in line)]
                  for q, line in zip(query_langs, delta_grid)]), "",
          f"![Δ nDCG@10 by language pair]({rel(images['matrix'][0])})", "",
          "## Slices", "",
          *table(["slice", "group", "A nDCG@10", "B nDCG@10", "Δ", "95% CI of Δ", "paired queries", "intents"],
                 [[s["slice"], s["group"], number(s["a"]), number(s["b"]), signed(s["delta"]),
                   delta_ci(s), s["n"], s["clusters"]]
                  for s in slices if s["slice"] != "language pair"]), "",
          f"![Δ nDCG@10 by slice]({rel(images['slices'][0])})", "",
          "## Latency trade-off", "",
          *table(["", f"A {a.label}", f"B {b.label}", "Δ (B − A)"],
                 [[f"{part} {q}", number(t[a.label][f"{part}_{q}"], 1), number(t[b.label][f"{part}_{q}"], 1),
                   "–" if t[a.label][f"{part}_{q}"] is None or t[b.label][f"{part}_{q}"] is None
                   else f"{t[b.label][f'{part}_{q}'] - t[a.label][f'{part}_{q}']:+.1f}"]
                  for part in ("embed_ms", "search_ms", "total_ms") for q in ("p50", "p95")]
                 + [["successful searches", t[a.label]["searches"], t[b.label]["searches"], ""]]), "",
          f"![Latency]({rel(images['latency'][0])})", "",
          "## Limitations", "", *limitations(dataset, pair, unjudged, excluded, inconsistent), "",
          "## Files", "", "- `comparison.json`: everything above, machine-readable.",
          "- `comparison.csv`: the overall and per-slice deltas.",
          f"- `plots/`: {', '.join(sorted(p.name for ps in images.values() for p in ps))}.", ""]
    (out / "comparison.md").write_text("\n".join(md), encoding="utf-8")
    doc = {"dataset": {"dataset_id": dataset.manifest.dataset_id, "version": dataset.manifest.version,
                       "manifest_sha256": dataset.manifest_sha256()},
           "a": {"label": a.label, "run_id": a.run_id, **a.config.model_dump(mode="json")},
           "b": {"label": b.label, "run_id": b.run_id, **b.config.model_dump(mode="json")},
           "settings": {"exclude_inconsistent": exclude_inconsistent, "bootstrap_samples": samples, "seed": seed,
                        "delta": "B - A", "ci": "95% paired percentile bootstrap over intents"},
           "inconsistent_intents": inconsistent, "excluded_intents": excluded,
           "overall": overall, "slices": slices, "aggregates": aggregates, "latency": times}
    write_json(out / "comparison.json", doc)
    head = ["slice", "group", "metric", "a", "b", "delta", "low", "high", "n", "clusters"]
    write_csv(out / "comparison.csv", head,
              [["overall", "all", *(e[k] for k in head[2:])] for e in overall]
              + [[s[k] for k in head] for s in slices])
    return doc


# ---- command line -------------------------------------------------------------------------

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m semant_demo.benchmarks.search_relevance.report",
                                description="Offline relevance reports of saved search benchmark runs.")
    commands = p.add_subparsers(dest="command", required=True)

    def common(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--dataset", type=Path, required=True, help="the dataset directory")
        sub.add_argument("--run", type=Path, action="append", required=True, help="a run directory (repeatable)")
        sub.add_argument("--out", type=Path, required=True, help="the output directory")
        sub.add_argument("--exclude-inconsistent", action="store_true",
                         help="leave out intents with qrels whose per-language grades disagree")
        sub.add_argument("--bootstrap", type=int, default=BOOTSTRAP_SAMPLES, help="bootstrap samples (0: no CIs)")
        sub.add_argument("--seed", type=int, default=SEED, help="bootstrap seed")

    report = commands.add_parser("report", help="a report of every configuration of the runs")
    common(report)
    report.add_argument("--examples", type=int, default=2, help="best and worst intents shown per configuration")
    report.add_argument("--conclusions", type=Path,
                        help="a Markdown file with the reviewer's conclusions, shown in the Conclusions section")
    compare = commands.add_parser("compare", help="two configurations side by side")
    common(compare)
    compare.add_argument("--a", required=True, help="configuration A (the baseline)")
    compare.add_argument("--b", required=True, help="configuration B (Δ = B − A)")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        dataset, runs = load(args.dataset, args.run)
        if args.command == "report":
            conclusions = args.conclusions.read_text(encoding="utf-8") if args.conclusions else None
            build_report(dataset, runs, args.out, exclude_inconsistent=args.exclude_inconsistent,
                         samples=args.bootstrap, seed=args.seed, example_count=args.examples,
                         conclusions=conclusions)
            print(f"Wrote {args.out / 'report.md'}")
        else:
            build_compare(dataset, runs, args.a, args.b, args.out, exclude_inconsistent=args.exclude_inconsistent,
                          samples=args.bootstrap, seed=args.seed)
            print(f"Wrote {args.out / 'comparison.md'}")
    except ContractError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
