"""The file contract between the stages of the search relevance benchmark (#712).

The stages are separate commands that exchange only these files (docs/SEARCH_BENCHMARK.md):

* a **dataset** directory, written by the generator (#726) and frozen as a version (#730)::

      manifest.json   identity, provenance, file hashes, pooling methods, judges, limitations
      corpus.jsonl    CorpusChunk: the sampled chunks with their text
      intents.jsonl   Intent: one information need, its style and source chunk(s)
      queries.jsonl   Query: one formulation of an intent in one language
      qrels.jsonl     Qrel: the graded relevance of a chunk to an intent

* a **run** directory, written by the runner (#727) and read by the reports (#728)::

      manifest.json   the dataset it ran on, configurations, environment, file hashes
      results.jsonl   RunResult: the ranked chunks of one query in one configuration

Every file is written before its manifest, and a manifest names the SHA-256 of every file, so a
directory without a manifest is incomplete and a changed file is detected when it is loaded.
Records are validated on read and write; unknown fields are refused (a newer schema version
must be read by newer code).
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

DATASET_SCHEMA = "search-benchmark-dataset/1"
RUN_SCHEMA = "search-benchmark-run/1"
DATASET_FILES = ("corpus.jsonl", "intents.jsonl", "queries.jsonl", "qrels.jsonl")
RUN_FILES = ("results.jsonl",)
MANIFEST = "manifest.json"
SOURCE = "source"
"""The pooling method id of an intent's own source chunks (known positives)."""

Grade = Literal[0, 1, 2]
"""0 not relevant, 1 partly relevant, 2 relevant."""
ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"
LANGUAGE_PATTERN = r"^[a-z]{3}$"
"""ISO 639-3, as the corpus stores languages (``ces``, ``eng``, ``deu``)."""
Scalar = str | int | float | bool | None


class ContractError(ValueError):
    """A dataset or run that does not satisfy the contract; the message says where."""


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---- dataset records ----------------------------------------------------------------------

class DocumentInfo(_Record):
    """The few document properties a chunk is shown and sliced with."""
    title: str | None = None
    year: int | None = None
    document_type: str | None = None


class CorpusChunk(_Record):
    chunk_id: UUID
    """The chunk's id in the source corpus, kept so results can be traced back."""
    document_id: UUID
    order: int
    """Position of the chunk in its document (as stored)."""
    language: str = Field(pattern=LANGUAGE_PATTERN)
    text: str = Field(min_length=1)
    title: str | None = None
    """The chunk's generated title, if it had one (it is searchable by BM25)."""
    document: DocumentInfo = DocumentInfo()
    attributes: dict[str, Scalar] = Field(default_factory=dict)
    """Sampling and slicing properties, e.g. ``stratum``, ``period``, ``ocr_quality``,
    ``context_of`` (the chunk it was sampled as context for)."""


class Intent(_Record):
    """One information need; its queries are formulations of it in several languages."""
    intent_id: str = Field(pattern=ID_PATTERN)
    style: str = Field(min_length=1)
    """``keywords``, ``question``, ``entity``, ``long_question``, ``paraphrase``, … (the
    manifest lists the styles used)."""
    need: str = Field(min_length=1)
    """The information need in a sentence (any language), what the judge grades against."""
    source_chunk_ids: tuple[UUID, ...] = ()
    """The chunks it was written from (known positives); empty for an imported intent."""
    source_language: str | None = Field(None, pattern=LANGUAGE_PATTERN)
    origin: Literal["generated", "imported"] = "generated"


class Query(_Record):
    query_id: str = Field(pattern=ID_PATTERN)
    intent_id: str = Field(pattern=ID_PATTERN)
    language: str = Field(pattern=LANGUAGE_PATTERN)
    text: str = Field(min_length=1)
    origin: Literal["generated", "translated", "imported"] = "generated"
    translated_from: str | None = None
    """The query this one translates (``origin: translated``)."""


class Qrel(_Record):
    """The graded relevance of a chunk to an intent, shared by the intent's queries."""
    intent_id: str = Field(pattern=ID_PATTERN)
    chunk_id: UUID
    grade: Grade
    judge: str = Field(pattern=ID_PATTERN)
    """A judge id of the manifest (model, prompt, settings)."""
    pooled_by: tuple[str, ...] = Field(min_length=1)
    """Pooling method ids of the manifest that proposed the chunk; ``source`` for a source chunk."""
    language_grades: dict[str, Grade] | None = None
    """Grades judged per query language when they were judged separately."""
    consistent: bool = True
    """False when the per-language grades disagree (``grade`` is then their documented
    aggregate); reports can leave such intents out."""


# ---- dataset manifest ---------------------------------------------------------------------

class FileEntry(_Record):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    records: int = Field(ge=0)


class PoolingMethod(_Record):
    id: str = Field(pattern=ID_PATTERN)
    description: str = ""
    settings: dict[str, Any] = Field(default_factory=dict)


class Judge(_Record):
    id: str = Field(pattern=ID_PATTERN)
    provenance: dict[str, Any]
    """Model, provider, endpoint, prompt version and SHA-256, settings."""


class DatasetManifest(_Record):
    schema_version: Literal["search-benchmark-dataset/1"] = DATASET_SCHEMA
    dataset_id: str = Field(pattern=ID_PATTERN)
    version: str = Field(pattern=ID_PATTERN)
    created: datetime
    description: str = ""
    generator: dict[str, Any] = Field(default_factory=dict)
    """Tool name, git revision, command."""
    config: dict[str, Any] = Field(default_factory=dict)
    """The generation configuration, its path and SHA-256."""
    seeds: dict[str, int] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=dict)
    """Where the corpus was sampled from (store, collections, time); never a credential."""
    languages: tuple[str, ...] = ()
    styles: tuple[str, ...] = ()
    models: dict[str, dict[str, Any]] = Field(default_factory=dict)
    """Provenance by role: ``queries``, ``translation``, ``pooling_embedding``, …"""
    pooling: tuple[PoolingMethod, ...] = ()
    judges: tuple[Judge, ...] = ()
    store_schema: dict[str, Any] | None = None
    """The schema of the store pooled in (tokenization and indexes affect BM25)."""
    files: dict[str, FileEntry]
    counts: dict[str, int] = Field(default_factory=dict)
    checks: dict[str, Any] = Field(default_factory=dict)
    """Automated sanity checks and their results."""
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _files(self) -> "DatasetManifest":
        missing = [name for name in DATASET_FILES if name not in self.files]
        if missing:
            raise ValueError(f"files lacks {', '.join(missing)}")
        return self


# ---- run records --------------------------------------------------------------------------

class VectorSpec(_Record):
    """The embedding a vector or hybrid configuration searches with."""
    id: str = Field(pattern=ID_PATTERN)
    model: str
    target_vector: str
    query_prefix: str = ""
    document_template: str = "{text}"
    dimensions: int | None = None


class RunConfiguration(_Record):
    configuration_id: str = Field(pattern=ID_PATTERN)
    mode: Literal["text", "vector", "hybrid"]
    alpha: float | None = Field(None, ge=0, le=1)
    fusion: Literal["relativeScore", "ranked"] | None = None
    vector: VectorSpec | None = None
    properties: dict[str, float] | None = None
    """BM25 properties with their boosts; None: the application's default properties."""
    depth: int = Field(100, ge=1)
    """Ranked chunks kept per query."""

    @model_validator(mode="after")
    def _consistent(self) -> "RunConfiguration":
        if self.mode != "text" and self.vector is None:
            raise ValueError(f"{self.configuration_id}: a {self.mode} configuration needs a vector")
        if self.mode == "hybrid" and self.alpha is None:
            raise ValueError(f"{self.configuration_id}: a hybrid configuration needs alpha")
        if self.mode != "hybrid" and (self.alpha is not None or self.fusion is not None):
            raise ValueError(f"{self.configuration_id}: alpha and fusion apply to hybrid only")
        return self


class Hit(_Record):
    chunk_id: UUID
    score: float | None = None


class RunResult(_Record):
    configuration_id: str = Field(pattern=ID_PATTERN)
    query_id: str = Field(pattern=ID_PATTERN)
    hits: tuple[Hit, ...] = ()
    """Best first, each chunk once, at most the configuration's depth."""
    embed_ms: float | None = Field(None, ge=0)
    """Query embedding time; None for BM25."""
    search_ms: float | None = Field(None, ge=0)
    error: str | None = None
    """The failure's class or a short reason (never query or chunk text); hits are then empty."""

    @model_validator(mode="after")
    def _hits(self) -> "RunResult":
        ids = [hit.chunk_id for hit in self.hits]
        if len(set(ids)) != len(ids):
            raise ValueError(f"{self.configuration_id}/{self.query_id}: a chunk is ranked twice")
        if self.error is not None and self.hits:
            raise ValueError(f"{self.configuration_id}/{self.query_id}: a failed search has no hits")
        return self


class DatasetRef(_Record):
    dataset_id: str
    version: str
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RunManifest(_Record):
    schema_version: Literal["search-benchmark-run/1"] = RUN_SCHEMA
    run_id: str = Field(pattern=ID_PATTERN)
    created: datetime
    dataset: DatasetRef
    configurations: tuple[RunConfiguration, ...] = Field(min_length=1)
    environment: dict[str, Any] = Field(default_factory=dict)
    """Git revision, Weaviate version, store schema, embedding endpoints, host."""
    files: dict[str, FileEntry]
    counts: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _unique(self) -> "RunManifest":
        ids = [c.configuration_id for c in self.configurations]
        if len(set(ids)) != len(ids):
            raise ValueError("configuration ids must be unique")
        missing = [name for name in RUN_FILES if name not in self.files]
        if missing:
            raise ValueError(f"files lacks {', '.join(missing)}")
        return self


# ---- reading and writing ------------------------------------------------------------------

R = TypeVar("R", bound=BaseModel)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_jsonl(path: Path, records: Iterable[BaseModel]) -> FileEntry:
    """Write the records, one JSON object per line (UTF-8), through a temporary file; their entry."""
    partial = path.with_name(path.name + ".partial")
    count = 0
    with partial.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(record.model_dump_json(exclude_defaults=False) + "\n")
            count += 1
    partial.replace(path)
    return FileEntry(sha256=sha256_file(path), records=count)


def iter_jsonl(path: Path, model: type[R]) -> Iterator[R]:
    """The validated records of a JSON Lines file; ``ContractError`` names the bad line."""
    with path.open(encoding="utf-8") as f:
        for number, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                yield model.model_validate_json(line)
            except ValidationError as e:
                raise ContractError(f"{path.name}:{number}: {_first_error(e)}") from None


def _first_error(e: ValidationError) -> str:
    error = e.errors()[0]
    where = ".".join(str(p) for p in error["loc"])
    return f"{where}: {error['msg']}" if where else error["msg"]


def _write_manifest(directory: Path, manifest: BaseModel) -> None:
    path = directory / MANIFEST
    partial = path.with_name(MANIFEST + ".partial")
    partial.write_text(manifest.model_dump_json(indent=1) + "\n", encoding="utf-8")
    partial.replace(path)


def _read_manifest(directory: Path, model: type[R]) -> R:
    path = directory / MANIFEST
    if not path.is_file():
        raise ContractError(f"{directory}: no {MANIFEST} (an incomplete or unrelated directory)")
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as e:
        raise ContractError(f"{MANIFEST}: {_first_error(e)}") from None


def _check_hashes(directory: Path, files: dict[str, FileEntry]) -> None:
    for name, entry in files.items():
        path = directory / name
        if not path.is_file():
            raise ContractError(f"{name}: missing")
        if sha256_file(path) != entry.sha256:
            raise ContractError(f"{name}: changed since its manifest was written (SHA-256 differs)")


def _unique(values: Iterable[Any], what: str) -> None:
    repeated = [value for value, count in Counter(values).items() if count > 1]
    if repeated:
        raise ContractError(f"duplicate {what}: {', '.join(map(str, repeated[:5]))}")


# ---- datasets -----------------------------------------------------------------------------

@dataclass(frozen=True)
class Dataset:
    directory: Path
    manifest: DatasetManifest
    corpus: dict[UUID, CorpusChunk]
    intents: dict[str, Intent]
    queries: dict[str, Query]
    qrels: tuple[Qrel, ...]

    def manifest_sha256(self) -> str:
        return sha256_file(self.directory / MANIFEST)

    def ref(self) -> DatasetRef:
        return DatasetRef(dataset_id=self.manifest.dataset_id, version=self.manifest.version,
                          manifest_sha256=self.manifest_sha256())

    def grades(self) -> dict[str, dict[UUID, int]]:
        """Intent id -> chunk id -> grade."""
        found: dict[str, dict[UUID, int]] = {}
        for qrel in self.qrels:
            found.setdefault(qrel.intent_id, {})[qrel.chunk_id] = qrel.grade
        return found


def check_dataset(corpus: dict[UUID, CorpusChunk], intents: dict[str, Intent], queries: dict[str, Query],
                  qrels: Iterable[Qrel], pooling: Iterable[str], judges: Iterable[str]) -> None:
    """Referential integrity: every id a record names exists, every intent has a query, each
    (intent, chunk) is graded once and every source chunk is graded."""
    methods, judge_ids = {SOURCE, *pooling}, set(judges)
    for intent in intents.values():
        unknown = [str(c) for c in intent.source_chunk_ids if c not in corpus]
        if unknown:
            raise ContractError(f"intent {intent.intent_id}: source chunks not in the corpus: {', '.join(unknown)}")
    for query in queries.values():
        if query.intent_id not in intents:
            raise ContractError(f"query {query.query_id}: unknown intent {query.intent_id}")
        if query.translated_from is not None and query.translated_from not in queries:
            raise ContractError(f"query {query.query_id}: translates unknown query {query.translated_from}")
    without = sorted(set(intents) - {q.intent_id for q in queries.values()})
    if without:
        raise ContractError(f"intents without a query: {', '.join(without[:5])}")
    graded: set[tuple[str, UUID]] = set()
    for qrel in qrels:
        key = (qrel.intent_id, qrel.chunk_id)
        if qrel.intent_id not in intents:
            raise ContractError(f"qrel {qrel.intent_id}/{qrel.chunk_id}: unknown intent")
        if qrel.chunk_id not in corpus:
            raise ContractError(f"qrel {qrel.intent_id}/{qrel.chunk_id}: chunk not in the corpus")
        if key in graded:
            raise ContractError(f"qrel {qrel.intent_id}/{qrel.chunk_id}: graded twice")
        if qrel.judge not in judge_ids:
            raise ContractError(f"qrel {qrel.intent_id}/{qrel.chunk_id}: unknown judge {qrel.judge}")
        unknown_methods = set(qrel.pooled_by) - methods
        if unknown_methods:
            raise ContractError(f"qrel {qrel.intent_id}/{qrel.chunk_id}: unknown pooling methods "
                                f"{', '.join(sorted(unknown_methods))}")
        graded.add(key)
    for intent in intents.values():
        ungraded = [str(c) for c in intent.source_chunk_ids if (intent.intent_id, c) not in graded]
        if ungraded:
            raise ContractError(f"intent {intent.intent_id}: source chunks without a grade: {', '.join(ungraded)}")


def write_dataset(directory: Path, manifest: dict[str, Any], corpus: Iterable[CorpusChunk],
                  intents: Iterable[Intent], queries: Iterable[Query], qrels: Iterable[Qrel]) -> Dataset:
    """Validate and write a dataset: the four files, then the manifest with their hashes and
    counts (``manifest`` holds every other manifest field). Returns it as loaded back."""
    corpus, intents, queries, qrels = list(corpus), list(intents), list(queries), list(qrels)
    _unique((c.chunk_id for c in corpus), "chunk ids")
    _unique((i.intent_id for i in intents), "intent ids")
    _unique((q.query_id for q in queries), "query ids")
    pooling = [m["id"] if isinstance(m, dict) else m.id for m in manifest.get("pooling", ())]
    judges = [j["id"] if isinstance(j, dict) else j.id for j in manifest.get("judges", ())]
    check_dataset({c.chunk_id: c for c in corpus}, {i.intent_id: i for i in intents},
                  {q.query_id: q for q in queries}, qrels, pooling, judges)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / MANIFEST).unlink(missing_ok=True)  # incomplete until the new one is written
    files = {"corpus.jsonl": write_jsonl(directory / "corpus.jsonl", corpus),
             "intents.jsonl": write_jsonl(directory / "intents.jsonl", intents),
             "queries.jsonl": write_jsonl(directory / "queries.jsonl", queries),
             "qrels.jsonl": write_jsonl(directory / "qrels.jsonl", qrels)}
    counts = {"chunks": len(corpus), "intents": len(intents), "queries": len(queries), "qrels": len(qrels),
              **{f"chunks_{lang}": n for lang, n in sorted(Counter(c.language for c in corpus).items())},
              **{f"queries_{lang}": n for lang, n in sorted(Counter(q.language for q in queries).items())},
              **{f"grade_{g}": n for g, n in sorted(Counter(q.grade for q in qrels).items())}}
    fields = {"created": datetime.now(timezone.utc), **manifest, "files": files,
              "counts": {**counts, **manifest.get("counts", {})}}
    try:
        _write_manifest(directory, DatasetManifest.model_validate(fields))
    except ValidationError as e:
        raise ContractError(f"{MANIFEST}: {_first_error(e)}") from None
    return load_dataset(directory)


def load_dataset(directory: Path) -> Dataset:
    """A dataset, verified against its manifest (hashes, records, referential integrity)."""
    manifest = _read_manifest(directory, DatasetManifest)
    _check_hashes(directory, manifest.files)
    corpus_list = list(iter_jsonl(directory / "corpus.jsonl", CorpusChunk))
    intent_list = list(iter_jsonl(directory / "intents.jsonl", Intent))
    query_list = list(iter_jsonl(directory / "queries.jsonl", Query))
    qrels = tuple(iter_jsonl(directory / "qrels.jsonl", Qrel))
    _unique((c.chunk_id for c in corpus_list), "chunk ids")
    _unique((i.intent_id for i in intent_list), "intent ids")
    _unique((q.query_id for q in query_list), "query ids")
    corpus = {c.chunk_id: c for c in corpus_list}
    intents = {i.intent_id: i for i in intent_list}
    queries = {q.query_id: q for q in query_list}
    for name, records in (("corpus.jsonl", corpus), ("intents.jsonl", intents), ("queries.jsonl", queries),
                          ("qrels.jsonl", qrels)):
        if len(records) != manifest.files[name].records:
            raise ContractError(f"{name}: {len(records)} records, the manifest says {manifest.files[name].records}")
    check_dataset(corpus, intents, queries, qrels, [m.id for m in manifest.pooling], [j.id for j in manifest.judges])
    return Dataset(directory, manifest, corpus, intents, queries, qrels)


# ---- runs ---------------------------------------------------------------------------------

@dataclass(frozen=True)
class Run:
    directory: Path
    manifest: RunManifest
    results: tuple[RunResult, ...]

    def rankings(self) -> dict[str, dict[str, list[UUID]]]:
        """Configuration id -> query id -> ranked chunk ids (failed searches left out)."""
        found: dict[str, dict[str, list[UUID]]] = {c.configuration_id: {} for c in self.manifest.configurations}
        for result in self.results:
            if result.error is None:
                found[result.configuration_id][result.query_id] = [hit.chunk_id for hit in result.hits]
        return found


def check_run(manifest: RunManifest, results: Iterable[RunResult], dataset: Dataset | None = None) -> None:
    configurations = {c.configuration_id: c for c in manifest.configurations}
    seen: set[tuple[str, str]] = set()
    for result in results:
        key = (result.configuration_id, result.query_id)
        configuration = configurations.get(result.configuration_id)
        if configuration is None:
            raise ContractError(f"result {key}: unknown configuration")
        if key in seen:
            raise ContractError(f"result {key}: written twice")
        if len(result.hits) > configuration.depth:
            raise ContractError(f"result {key}: {len(result.hits)} hits, depth {configuration.depth}")
        if dataset is not None:
            if result.query_id not in dataset.queries:
                raise ContractError(f"result {key}: unknown query")
            outside = [str(h.chunk_id) for h in result.hits if h.chunk_id not in dataset.corpus]
            if outside:
                raise ContractError(f"result {key}: chunks not in the dataset: {', '.join(outside[:3])}")
        seen.add(key)


def write_run(directory: Path, manifest: dict[str, Any], results: Iterable[RunResult],
              dataset: Dataset | None = None) -> Run:
    """Validate and write a run: ``results.jsonl``, then its manifest."""
    results = list(results)
    try:
        configurations = [RunConfiguration.model_validate(c) if isinstance(c, dict) else c
                          for c in manifest["configurations"]]
        probe = RunManifest.model_validate({"created": datetime.now(timezone.utc), **manifest,
                                            "configurations": configurations,
                                            "files": {"results.jsonl": FileEntry(sha256="0" * 64, records=0)}})
    except ValidationError as e:
        raise ContractError(f"{MANIFEST}: {_first_error(e)}") from None
    check_run(probe, results, dataset)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / MANIFEST).unlink(missing_ok=True)
    entry = write_jsonl(directory / "results.jsonl", results)
    counts = {"results": len(results), "failed": sum(1 for r in results if r.error is not None),
              **manifest.get("counts", {})}
    _write_manifest(directory, probe.model_copy(update={"files": {"results.jsonl": entry}, "counts": counts}))
    return load_run(directory, dataset)


def load_run(directory: Path, dataset: Dataset | None = None) -> Run:
    """A run, verified against its manifest and, given the dataset, against the dataset it names."""
    manifest = _read_manifest(directory, RunManifest)
    _check_hashes(directory, manifest.files)
    results = tuple(iter_jsonl(directory / "results.jsonl", RunResult))
    if len(results) != manifest.files["results.jsonl"].records:
        raise ContractError(f"results.jsonl: {len(results)} records, the manifest says "
                            f"{manifest.files['results.jsonl'].records}")
    if dataset is not None:
        ref = dataset.ref()
        if (manifest.dataset.dataset_id, manifest.dataset.version) != (ref.dataset_id, ref.version):
            raise ContractError(f"the run is of {manifest.dataset.dataset_id} {manifest.dataset.version}, "
                                f"not {ref.dataset_id} {ref.version}")
        if manifest.dataset.manifest_sha256 != ref.manifest_sha256:
            raise ContractError("the dataset's manifest changed since the run (SHA-256 differs)")
    check_run(manifest, results, dataset)
    return Run(directory, manifest, results)


def to_json(value: Any) -> str:
    """Stable JSON for hashing configurations."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
