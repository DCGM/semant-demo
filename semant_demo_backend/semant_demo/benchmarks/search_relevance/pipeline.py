"""The generator's resumable steps (#726): ``sample``, ``intents``, ``translate``, ``pool``,
``judge`` and ``write``.

Each step writes its outputs and then ``<work>/<step>/state.json`` with the hash of its inputs
(its configuration sections, models and prompt versions, and the output hashes of every
earlier step) and of its outputs. A step whose state matches and whose outputs are unchanged
is skipped; a changed input reruns it, and every later step whose inputs then differ. Model calls are cached separately
(``<work>/calls``), so even a forced rerun asks the models only what it has not asked before.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from semant_demo.adapters.llm.gateway import LlmGateway
from semant_demo.benchmarks.search_relevance import prompts
from semant_demo.benchmarks.search_relevance.calls import CachedModel
from semant_demo.benchmarks.search_relevance.config import (
    INTENTS_FEATURE, JUDGE_FEATURE, TRANSLATION_FEATURE, GeneratorConfig)
from semant_demo.benchmarks.search_relevance.contracts import (
    CorpusChunk, Dataset, Intent, PoolingMethod, Qrel, Query, iter_jsonl, sha256_file, to_json, write_dataset,
    write_jsonl)
from semant_demo.benchmarks.search_relevance.generation import (
    generate_intents, import_source_ids, imported_intents, translate)
from semant_demo.benchmarks.search_relevance.judging import judge_pools
from semant_demo.benchmarks.search_relevance.llm import USAGE_KEYS, UsageTotals, model_provenance
from semant_demo.benchmarks.search_relevance.pooling import pool_candidates
from semant_demo.benchmarks.search_relevance.sampling import sample_corpus
from semant_demo.benchmarks.search_relevance.source import SourceReader
from semant_demo.benchmarks.search_relevance.store_api import BenchmarkStore, StoreSpec
from semant_demo.benchmarks.search_relevance.summary import summarize

STEPS = ("sample", "intents", "translate", "pool", "judge", "write")
TOOL = "semant_demo.benchmarks.search_relevance.generate"
STATE = "state.json"
FEATURE_PROMPTS = {INTENTS_FEATURE: prompts.INTENT_PROMPT_VERSION,
                   TRANSLATION_FEATURE: prompts.TRANSLATION_PROMPT_VERSION,
                   JUDGE_FEATURE: prompts.JUDGE_PROMPT_VERSION}


@dataclass
class Resources:
    """What the steps use, opened only by the steps that need them."""
    llm: LlmGateway
    usage: UsageTotals
    source: Callable[[], Awaitable[SourceReader]]
    open_store: Callable[[StoreSpec], Awaitable[BenchmarkStore]]


def git_revision() -> str | None:
    try:
        here = Path(__file__).parent
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=here, capture_output=True, text=True,
                                  timeout=10, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=here,
                               capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        return revision + ("-dirty" if dirty else "")
    except (OSError, subprocess.SubprocessError):
        return None


def _sha(value: Any) -> str:
    return hashlib.sha256(to_json(value).encode()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    partial = path.with_name(path.name + ".partial")
    partial.write_text(json.dumps(value, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    partial.replace(path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class Generator:
    def __init__(self, config: GeneratorConfig, config_data: dict[str, Any], config_sha256: str, work: Path,
                 out: Path, resources: Resources, *, config_name: str = "config.yaml",
                 progress: Callable[[str], None] = lambda message: None):
        self.config, self.config_data, self.config_sha256 = config, config_data, config_sha256
        self.work, self.out, self.resources, self.progress = work, out, resources, progress
        self.config_name = config_name
        self.ran: list[str] = []
        self._models: dict[str, CachedModel] = {}

    # ---- state ----------------------------------------------------------------------------

    def dir(self, step: str) -> Path:
        return self.work / step

    def state(self, step: str) -> dict[str, Any] | None:
        path = self.dir(step) / STATE
        return read_json(path) if path.is_file() else None

    def model(self, feature: str) -> CachedModel:
        if feature not in self._models:
            self._models[feature] = CachedModel(self.resources.llm, feature, FEATURE_PROMPTS[feature],
                                                self.work / "calls")
        return self._models[feature]

    def _model_identity(self, feature: str) -> dict[str, Any]:
        provenance = model_provenance(self.resources.llm, feature)
        return {k: provenance[k] for k in ("tier", "provider", "model", "model_endpoint")}

    def inputs(self, step: str) -> dict[str, Any]:
        """What a step's outputs depend on, besides the outputs of the step before it."""
        c = self.config
        prompt = prompts.prompt_provenance(c.intents.descriptions())
        if step == "sample":
            imports = c.intents.imports
            return {"languages": c.languages, "sample": c.sample.model_dump(mode="json"), "seed": c.seeds.sample,
                    "source": c.source.model_dump(mode="json"),
                    "imports": _file_sha(imports.path) if imports and c.sample.include_import_sources else None}
        if step == "intents":
            imports = c.intents.imports
            return {"intents": c.intents.model_dump(mode="json", by_alias=True), "seed": c.seeds.intents,
                    "languages": c.languages, "query_languages": c.query_languages,
                    "imports": _file_sha(imports.path) if imports else None,
                    "model": self._model_identity(INTENTS_FEATURE), "prompt": prompt["intents"]}
        if step == "translate":
            return {"translation": c.translation.model_dump(mode="json"), "query_languages": c.query_languages,
                    "seed": c.seeds.intents, "model": self._model_identity(TRANSLATION_FEATURE),
                    "prompt": prompt["translation"]}
        if step == "pool":
            return {"pooling": c.pooling.model_dump(mode="json"), "dataset": [c.dataset_id, c.version]}
        if step == "judge":
            return {"judge": c.judge.model_dump(mode="json"), "seed": c.seeds.judge,
                    "model": self._model_identity(JUDGE_FEATURE), "prompt": prompt["judge"]}
        return {"config_sha256": self.config_sha256, "out": str(self.out)}

    def inputs_hash(self, step: str) -> str:
        earlier = {s: (self.state(s) or {}).get("outputs") for s in STEPS[:STEPS.index(step)]}
        return _sha({"step": step, "inputs": self.inputs(step), "earlier": earlier})

    def fresh(self, step: str) -> bool:
        state = self.state(step)
        if state is None or state.get("inputs") != self.inputs_hash(step):
            return False
        base = self.out if step == "write" else self.dir(step)
        return all((base / name).is_file() and sha256_file(base / name) == sha
                   for name, sha in state["outputs"].items())

    def _finish(self, step: str, inputs: str, outputs: list[str], report: dict[str, Any],
                usage_before: dict[str, float]) -> None:
        base = self.out if step == "write" else self.dir(step)
        usage = {k: self.resources.usage.totals[k] - usage_before[k] for k in USAGE_KEYS}
        write_json(self.dir(step) / STATE, {
            "step": step, "inputs": inputs, "finished": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "outputs": {name: sha256_file(base / name) for name in outputs}, "usage": usage, "report": report})

    # ---- running --------------------------------------------------------------------------

    async def run(self, start: str | None = None, until: str | None = None, force: bool = False) -> list[str]:
        """Run the steps up to ``until`` (all by default); ``start`` and every later step run even
        when fresh, ``force`` reruns all. Returns the steps that ran."""
        last = STEPS.index(until) if until else len(STEPS) - 1
        first_forced = 0 if force else STEPS.index(start) if start else len(STEPS)
        for index, step in enumerate(STEPS[:last + 1]):
            if index < first_forced and self.fresh(step):
                self.progress(f"{step}: up to date, skipped")
                continue
            self.progress(f"{step}: running")
            inputs = self.inputs_hash(step)
            self.dir(step).mkdir(parents=True, exist_ok=True)
            (self.dir(step) / STATE).unlink(missing_ok=True)
            before = dict(self.resources.usage.totals)
            outputs, report = await getattr(self, f"_{step}")()
            self._finish(step, inputs, outputs, report, before)
            self.ran.append(step)
        return self.ran

    # ---- steps ----------------------------------------------------------------------------

    def corpus(self) -> list[CorpusChunk]:
        return list(iter_jsonl(self.dir("sample") / "corpus.jsonl", CorpusChunk))

    def _records(self, step: str, name: str, model):
        return list(iter_jsonl(self.dir(step) / name, model))

    async def _sample(self) -> tuple[list[str], dict[str, Any]]:
        source = await self.resources.source()
        corpus, report = await sample_corpus(source, self.config, import_source_ids(self.config))
        report["source"] = source.describe()
        write_jsonl(self.dir("sample") / "corpus.jsonl", corpus)
        write_json(self.dir("sample") / "report.json", report)
        self.progress(f"sample: {len(corpus)} chunks ({report['selected']})")
        return ["corpus.jsonl", "report.json"], report

    async def _intents(self) -> tuple[list[str], dict[str, Any]]:
        corpus = self.corpus()
        intents, queries, report = await generate_intents(corpus, self.config, self.model(INTENTS_FEATURE))
        imported, imported_queries, import_report = imported_intents(corpus, self.config)
        known = {i.intent_id for i in intents}
        clashes = [i.intent_id for i in imported if i.intent_id in known]
        if clashes:
            import_report["skipped_id_clash"] = len(clashes)
        intents += [i for i in imported if i.intent_id not in known]
        queries += [q for q in imported_queries if q.intent_id not in known]
        report["imports"] = import_report
        write_jsonl(self.dir("intents") / "intents.jsonl", intents)
        write_jsonl(self.dir("intents") / "queries.jsonl", queries)
        write_json(self.dir("intents") / "report.json", report)
        self.progress(f"intents: {report['generated']} generated, {len(imported)} imported")
        return ["intents.jsonl", "queries.jsonl", "report.json"], report

    async def _translate(self) -> tuple[list[str], dict[str, Any]]:
        intents = self._records("intents", "intents.jsonl", Intent)
        queries = self._records("intents", "queries.jsonl", Query)
        intents, queries, report = await translate(intents, queries, self.config, self.model(TRANSLATION_FEATURE))
        write_jsonl(self.dir("translate") / "intents.jsonl", intents)
        write_jsonl(self.dir("translate") / "queries.jsonl", queries)
        write_json(self.dir("translate") / "report.json", report)
        self.progress(f"translate: {report['translated']} translations, {len(report['dropped_intents'])} intents dropped")
        return ["intents.jsonl", "queries.jsonl", "report.json"], report

    def corpus_dataset(self) -> Dataset:
        """The sampled corpus as a dataset of no intents: what the benchmark store loads."""
        return write_dataset(self.dir("pool") / "corpus", {
            "dataset_id": self.config.dataset_id, "version": self.config.version,
            "description": "The sampled corpus only (pooling input of the generator).",
            "generator": {"tool": TOOL}, "languages": self.config.languages}, self.corpus(), [], [], [])

    async def _pool(self) -> tuple[list[str], dict[str, Any]]:
        intents = self._records("translate", "intents.jsonl", Intent)
        queries = self._records("translate", "queries.jsonl", Query)
        dataset = self.corpus_dataset()
        store = await self.resources.open_store(self.config.pooling.store.spec())
        try:
            pools, report = await pool_candidates(store, dataset, intents, queries, self.config,
                                                  self.work / "embeddings")
            report["store_schema"] = await store.describe()
        finally:
            await store.close()
        path = self.dir("pool") / "pools.jsonl"
        partial = path.with_name(path.name + ".partial")
        with partial.open("w", encoding="utf-8") as f:
            for intent in intents:
                f.write(json.dumps({"intent_id": intent.intent_id,
                                    "candidates": [c.record() for c in pools[intent.intent_id]]}) + "\n")
        partial.replace(path)
        write_json(self.dir("pool") / "report.json", report)
        self.progress(f"pool: {report['candidates']} candidates ({report['left_out_by_cap']} left out by the caps)")
        return ["pools.jsonl", "report.json"], report

    def pools(self) -> dict[str, list[dict[str, Any]]]:
        found = {}
        for line in (self.dir("pool") / "pools.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                entry = json.loads(line)
                found[entry["intent_id"]] = entry["candidates"]
        return found

    async def _judge(self) -> tuple[list[str], dict[str, Any]]:
        intents = self._records("translate", "intents.jsonl", Intent)
        queries = self._records("translate", "queries.jsonl", Query)
        corpus = {c.chunk_id: c for c in self.corpus()}
        model = self.model(JUDGE_FEATURE)
        qrels, dropped, report = await judge_pools(intents, queries, self.pools(), corpus, self.config, model)
        report["provenance"] = {**model.provenance, **prompts.prompt_provenance({})["judge"]}
        write_jsonl(self.dir("judge") / "qrels.jsonl", qrels)
        write_json(self.dir("judge") / "report.json", report)
        self.progress(f"judge: {report['judged']} judged, {sum(report['unjudged'].values())} unjudged")
        return ["qrels.jsonl", "report.json"], report

    async def _write(self) -> tuple[list[str], dict[str, Any]]:
        dataset = write_dataset(self.out, self.manifest(), *self.records())
        (self.out / "summary.md").write_text(summarize(dataset), encoding="utf-8")
        self.progress(f"write: {self.out}")
        return ["manifest.json", "summary.md"], {"counts": dataset.manifest.counts}

    # ---- the dataset ----------------------------------------------------------------------

    def records(self) -> tuple[list[CorpusChunk], list[Intent], list[Query], list[Qrel]]:
        dropped = set(self.state("judge")["report"]["dropped_intents"])
        intents = [i for i in self._records("translate", "intents.jsonl", Intent) if i.intent_id not in dropped]
        queries = [q for q in self._records("translate", "queries.jsonl", Query) if q.intent_id not in dropped]
        return self.corpus(), intents, queries, self._records("judge", "qrels.jsonl", Qrel)

    def usage(self) -> dict[str, float]:
        totals = {k: 0.0 for k in USAGE_KEYS}
        for step in STEPS[:-1]:
            state = self.state(step) or {}
            for key, value in (state.get("usage") or {}).items():
                totals[key] = totals.get(key, 0) + value
        return {k: round(v, 6) if k == "cost_usd" else int(v) for k, v in totals.items()}

    def manifest(self) -> dict[str, Any]:
        c = self.config
        reports = {step: (self.state(step) or {}).get("report", {}) for step in STEPS[:-1]}
        sample, intents, translation, pool, judge = (reports[s] for s in STEPS[:-1])
        prompt = prompts.prompt_provenance(c.intents.descriptions())
        models = {
            "intents": {**model_provenance(self.resources.llm, INTENTS_FEATURE), **prompt["intents"]},
            "translation": {**model_provenance(self.resources.llm, TRANSLATION_FEATURE), **prompt["translation"]},
            "judge": judge.get("provenance", {}),
        }
        models.update({f"pooling_{m.id}": {"vector": m.vector.model_dump(mode="json"),
                                           "endpoint": m.endpoint.base_url if m.endpoint else None}
                       for m in c.pooling.methods if m.vector is not None})
        _, intent_list, query_list, qrels = self.records()
        unjudged = sum(judge.get("unjudged", {}).values())
        limitations = [
            *c.limitations,
            f"Pooling is incomplete: candidates come from {', '.join(m.id for m in c.pooling.methods)} (top "
            f"{max(m.depth for m in c.pooling.methods)} per query) and the source chunks, at most "
            f"{pool.get('cap_per_intent')} per intent; {pool.get('left_out_by_cap', 0)} proposed candidates were "
            "left out by the caps. A search model can surface relevant chunks that were never judged: count "
            "unjudged hits rather than treating them as not relevant.",
            "Grades are one LLM judge's, without human review.",
        ]
        if unjudged:
            limitations.append(f"{unjudged} pooled pairs could not be judged and are not in the qrels.")
        if sample.get("short"):
            limitations.append(f"Languages below their sample target: {sample['short']}.")
        if pool.get("store_schema") is not None:
            limitations.append("The store pooled in has the test schema's shape, not production's exact schema "
                               "(tokenization and indexes affect BM25).")
        checks = {
            "sampling": {k: sample.get(k) for k in ("excluded_languages", "drawn_exclusions", "methods", "short",
                                                     "context_added", "near_duplicates", "imported_sources_missing")},
            "intents": {k: intents.get(k) for k in ("requested", "generated", "short", "failed_attempts",
                                                     "near_copy_replies", "regenerated_after_near_copy", "imports")},
            "translation": {k: translation.get(k) for k in ("requested", "translated", "failed", "dropped_intents",
                                                             "flags", "back_translation")},
            "pooling": {k: pool.get(k) for k in ("candidates_before_cap", "candidates", "left_out_by_cap",
                                                  "cap_per_intent", "per_intent", "failed_searches",
                                                  "hits_outside_corpus", "proposed_by", "proposed_only_by",
                                                  "sources_found_by")},
            "judging": {k: judge.get(k) for k in ("pairs", "judged", "unjudged", "dropped_intents",
                                                   "source_graded_0", "per_language", "passages_cut")},
            "coverage": {"judged_share_of_pool": round(len(qrels) / pool["candidates"], 4)
                         if pool.get("candidates") else None},
        }
        return {
            "dataset_id": c.dataset_id, "version": c.version, "description": c.description,
            "generator": {"tool": TOOL, "git_revision": git_revision(), "command": " ".join(sys.argv),
                          "usage": self.usage(),
                          "model_calls": {s: reports[s].get("model_calls") for s in ("intents", "translate", "judge")}},
            "config": {"name": self.config_name, "sha256": self.config_sha256, "data": self.config_data},
            "seeds": c.seeds.model_dump(),
            "source": {**sample.get("source", {}), "inventory": sample.get("inventory"),
                       "sampled": datetime.fromisoformat(self.state("sample")["finished"]).isoformat()},
            "languages": c.languages, "styles": tuple(sorted({i.style for i in intent_list})),
            "models": models,
            "pooling": [PoolingMethod(id=m["id"], description=m.get("description", ""),
                                      settings={k: v for k, v in m.items() if k not in ("id", "description")})
                        for m in pool.get("methods", [])],
            "judges": [{"id": judge["judge"], "provenance": judge.get("provenance", {})}] if judge.get("judge") else [],
            "store_schema": pool.get("store_schema"),
            "counts": {"documents": len({c.document_id for c in self.corpus()}),
                       "query_languages": len({q.language for q in query_list})},
            "checks": checks,
            "limitations": limitations,
        }


def _file_sha(path: Path) -> str | None:
    path = path.expanduser()
    return sha256_file(path) if path.is_file() else None
