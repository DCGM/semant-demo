"""The search benchmark runner (#727): searches a frozen dataset's queries in the benchmark-owned
Weaviate (``store_api``) with every configuration of an experiment config (``runner_config``)
and writes a run directory (``contracts.write_run``) for the reports (#728)::

    python -m semant_demo.benchmarks.search_relevance.runner run --config FILE --run-id ID
        [--out RUNS_DIR] [--configurations ID,...] [--retry-failed] [--dry-run]
    python -m semant_demo.benchmarks.search_relevance.runner list-configurations --config FILE

**Incremental.** While it runs, every finished search is appended to ``results.partial.jsonl``
in the run directory (``run.partial.json`` names the dataset and configurations). A rerun with
the same run id skips the (configuration, query) pairs already in the run or the partial log, so
an interrupted run resumes, and configurations added to the config (or picked with
``--configurations``) are added to the existing run. The run is then written again with all its
results through ``write_run`` and the partial files are removed. A run of another dataset, or a
configuration id whose settings changed, is refused.

**Safety.** The runner reaches Weaviate only through ``BenchmarkStore``, which writes only to an
instance holding the benchmark's ownership marker. Embedding keys are read from environment
variables named in the config and never written; errors record the exception class only, never
query text.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from semant_demo.benchmarks.search_relevance.contracts import (
    ID_PATTERN, MANIFEST, ContractError, Dataset, DatasetRef, Hit, Query, Run, RunConfiguration, RunResult,
    load_dataset, load_run, to_json, write_run)
from semant_demo.benchmarks.search_relevance.runner_config import (
    ConfigError, RunnerConfig, expand, load_config, select, select_queries)
from semant_demo.benchmarks.search_relevance.shareable import shareable
from semant_demo.benchmarks.search_relevance.store_api import BenchmarkStore, OpenStore, Searcher

PARTIAL_RESULTS = "results.partial.jsonl"
PARTIAL_STATE = "run.partial.json"
REFUSED = 2


class RunnerError(RuntimeError):
    """A run that cannot go on (another dataset, changed configurations, a missing key)."""


Key = tuple[str, str]
"""(configuration id, query id)"""


# ---- the plan -----------------------------------------------------------------------------

@dataclass(frozen=True)
class Plan:
    config: RunnerConfig
    dataset: Dataset
    configurations: list[RunConfiguration]
    """The configurations to run in this session."""
    queries: list[Query]
    config_path: Path | None = None
    config_sha256: str | None = None


def make_plan(config: RunnerConfig, *, config_path: Path | None = None, config_sha256: str | None = None,
              only: list[str] | None = None, dataset: Dataset | None = None) -> Plan:
    configurations = select(expand(config), only)
    dataset = dataset or load_dataset(config.dataset)
    return Plan(config, dataset, configurations, select_queries(dataset, config.budget), config_path, config_sha256)


# ---- run state (finished work) ------------------------------------------------------------

@dataclass
class RunState:
    """What a run directory already holds: its manifest's results and the partial log."""
    created: str | None = None
    configurations: dict[str, RunConfiguration] = field(default_factory=dict)
    results: dict[Key, RunResult] = field(default_factory=dict)
    sessions: list[dict[str, Any]] = field(default_factory=list)
    """The environments of earlier sessions, oldest first."""
    complete: bool = False
    """A manifest exists and the partial log adds nothing to it."""

    def adopt(self, configurations: Iterable[RunConfiguration]) -> None:
        """Add configurations, refusing an id that ran with other settings."""
        for configuration in configurations:
            known = self.configurations.get(configuration.configuration_id)
            if known is not None and known != configuration:
                raise RunnerError(f"configuration {configuration.configuration_id} ran with other settings in this "
                                  f"run: give the changed one a new id, or start a new run")
            self.configurations.setdefault(configuration.configuration_id, configuration)


def read_partial_results(path: Path, repair: bool = True) -> list[RunResult]:
    """The partial log's results. A last line cut short by an interruption is dropped and, with
    ``repair``, the file rewritten without it, so appending goes on cleanly (a dry run reads
    without repairing); a bad line elsewhere is refused."""
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    found: list[RunResult] = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            if not line.endswith("\n"):
                raise ValueError("unterminated line")
            found.append(RunResult.model_validate_json(line))
        except (ValidationError, ValueError):
            if number != len(lines):
                raise ContractError(f"{path.name}:{number}: not a result") from None
            if not repair:
                continue
            partial = path.with_name(path.name + ".tmp")
            partial.write_text("".join(r.model_dump_json() + "\n" for r in found), encoding="utf-8")
            partial.replace(path)
    return found


def read_state(directory: Path, dataset: Dataset, repair: bool = True) -> RunState:
    """The run's state from its manifest and partial files; ``repair=False`` (dry run) never writes."""
    state = RunState()
    if (directory / MANIFEST).exists():
        run = load_run(directory, dataset)  # refuses another dataset, or a changed one
        state.created = run.manifest.created.isoformat()
        state.adopt(run.manifest.configurations)
        state.results = {(r.configuration_id, r.query_id): r for r in run.results}
        environment = dict(run.manifest.environment)
        state.sessions = [*environment.pop("sessions", []), environment]
        state.complete = True
    partial_state = directory / PARTIAL_STATE
    if partial_state.exists():
        data = json.loads(partial_state.read_text(encoding="utf-8"))
        if DatasetRef.model_validate(data["dataset"]) != dataset.ref():
            raise RunnerError(f"{directory} holds unfinished results of another dataset "
                              f"({data['dataset']['dataset_id']} {data['dataset']['version']})")
        state.created = state.created or data.get("created")
        state.adopt(RunConfiguration.model_validate(c) for c in data["configurations"])
        # The partial state's sessions were written from this run's sessions (the manifest's and
        # any interrupted ones), so they are the complete list.
        state.sessions = data.get("sessions", state.sessions)
        if data.get("current_session"):  # a session that was interrupted: its results are in the log
            state.sessions = [*state.sessions, {**data["current_session"], "interrupted": True}]
        for result in read_partial_results(directory / PARTIAL_RESULTS, repair):
            if result.configuration_id not in state.configurations:
                raise ContractError(f"{PARTIAL_RESULTS}: result of unknown configuration {result.configuration_id}")
            if state.results.get((result.configuration_id, result.query_id)) != result:
                state.complete = False
            state.results[(result.configuration_id, result.query_id)] = result
    elif (directory / PARTIAL_RESULTS).exists():
        raise RunnerError(f"{directory}: {PARTIAL_RESULTS} without {PARTIAL_STATE}")
    return state


def pending(plan: Plan, state: RunState, retry_failed: bool = False) -> list[tuple[RunConfiguration, Query]]:
    """The searches still to do, configuration by configuration."""
    found = []
    for configuration in plan.configurations:
        for query in plan.queries:
            done = state.results.get((configuration.configuration_id, query.query_id))
            if done is None or (retry_failed and done.error is not None):
                found.append((configuration, query))
    return found


# ---- searching ----------------------------------------------------------------------------

class RateLimiter:
    """Starts at most ``per_second`` searches a second (evenly spaced); None: no limit."""

    def __init__(self, per_second: float | None, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self.interval = 1 / per_second if per_second else 0.0
        self.clock, self.sleep = clock, sleep
        self._next = 0.0

    async def wait(self) -> None:
        if not self.interval:
            return
        now = self.clock()
        slot = max(now, self._next)
        self._next = slot + self.interval  # reserved before awaiting: callers never share a slot
        if slot > now:
            await self.sleep(slot - now)


async def search_one(searcher: Searcher, configuration: RunConfiguration, query: Query,
                     dataset: Dataset) -> RunResult:
    """One search as a result: hits truncated to the depth, each chunk once, or the error class."""
    key = {"configuration_id": configuration.configuration_id, "query_id": query.query_id}
    try:
        outcome = await searcher(query.text)
    except Exception as e:  # recorded, never raised: one failure must not stop the run
        return RunResult(**key, error=type(e).__name__)
    hits: list[Hit] = []
    seen = set()
    error = None
    for chunk_id, score in outcome.hits:
        if chunk_id in seen:
            continue
        if chunk_id not in dataset.corpus:
            error, hits = "ChunkOutsideDataset", []
            break
        seen.add(chunk_id)
        hits.append(Hit(chunk_id=chunk_id, score=score))
        if len(hits) == configuration.depth:
            break
    try:
        return RunResult(**key, hits=tuple(hits), embed_ms=outcome.embed_ms, search_ms=outcome.search_ms, error=error)
    except ValidationError:
        return RunResult(**key, error="InvalidOutcome")


async def search_all(work: list[tuple[RunConfiguration, Query]], searchers: dict[str, Searcher], dataset: Dataset,
                     concurrency: int, limiter: RateLimiter, record: Callable[[RunResult], None]) -> None:
    """Every search of ``work`` with at most ``concurrency`` in flight; ``record`` gets each result
    as it finishes. An exception other than a search failure (an interruption) stops all."""
    queue = iter(work)

    async def worker() -> None:
        for configuration, query in queue:
            await limiter.wait()
            record(await search_one(searchers[configuration.configuration_id], configuration, query, dataset))

    workers = [asyncio.create_task(worker()) for _ in range(min(concurrency, len(work)))]
    try:
        await asyncio.gather(*workers)
    finally:
        for task in workers:
            task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)


# ---- execution ----------------------------------------------------------------------------

class Progress:
    """Logs about twenty progress lines a session: counts and failure classes, never text."""

    def __init__(self, run_id: str, total: int, log: Callable[[str], None]):
        self.run_id, self.total, self.log = run_id, total, log
        self.done = 0
        self.failed: Counter[str] = Counter()
        self.step = max(1, total // 20)

    def add(self, result: RunResult) -> None:
        self.done += 1
        if result.error:
            self.failed[result.error] += 1
        if self.done % self.step == 0 or self.done == self.total:
            self.log(f"{self.run_id}: {self.done}/{self.total} searches, failed {dict(self.failed)}")


def git_revision() -> dict[str, Any]:
    here = Path(__file__).parent
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5,
                                  cwd=here).stdout.strip() or None
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True,
                                    text=True, timeout=5, cwd=here).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return {"revision": None}
    return {"revision": revision, "dirty": dirty}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jsonable(value: Any) -> Any:
    return json.loads(to_json(value))


def _write_partial_state(directory: Path, dataset: Dataset, state: RunState,
                         current: dict[str, Any] | None = None) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    data = {"dataset": dataset.ref().model_dump(), "created": state.created,
            "configurations": [c.model_dump(mode="json") for c in state.configurations.values()],
            "sessions": state.sessions,
            # This session's environment, so that it is kept when the session is interrupted.
            "current_session": shareable(current) if current is not None else None}
    path = directory / PARTIAL_STATE
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _check_keys(plan: Plan, vector_ids: Iterable[str]) -> None:
    missing = sorted({e.api_key_env for v in vector_ids if (e := plan.config.endpoints[v]).api_key_env
                      and not os.environ.get(e.api_key_env)})
    if missing:
        raise RunnerError(f"environment variables not set: {', '.join(missing)}")


async def execute(plan: Plan, directory: Path, run_id: str, open_store: OpenStore, *, retry_failed: bool = False,
                  log: Callable[[str], None] = print) -> Run:
    """Run the plan's pending searches into the run directory and write the run."""
    dataset, config = plan.dataset, plan.config
    state = read_state(directory, dataset)
    state.adopt(plan.configurations)
    work = pending(plan, state, retry_failed)
    if not work and state.complete:
        log(f"{run_id}: nothing to do, every selected search is in the run")
        return load_run(directory, dataset)
    vector_ids = list(dict.fromkeys(c.vector.id for c, _ in work if c.vector is not None))
    _check_keys(plan, vector_ids)
    started = _now()
    state.created = state.created or started
    spec = config.store.spec()
    environment: dict[str, Any] = {
        "git": git_revision(), "started": started,
        "config": {"path": str(plan.config_path) if plan.config_path else None, "sha256": plan.config_sha256},
        "store_spec": _jsonable(asdict(spec)),
        "embedding_endpoints": {v: _jsonable(asdict(config.endpoint(v))) for v in vector_ids},
        "budget": config.budget.model_dump(mode="json"),
        "queries_selected": len(plan.queries),
        "configurations_run": [c.configuration_id for c in plan.configurations],
        "searches": len(work), "resumed": len(state.results)}
    # Nothing is recorded before the store is ready: a session that fails to open the store or to
    # ensure a vector leaves the run as it was (its configurations are not adopted on disk).
    log(f"{run_id}: {len(work)} searches ({len(plan.configurations)} configurations, {len(plan.queries)} queries)")
    if work:
        store: BenchmarkStore = await open_store(spec)
        try:
            environment["load"] = _jsonable(asdict(await store.load(dataset)))
            environment["vectors"] = {}
            for vector_id in vector_ids:
                base = config.vectors[vector_id].spec(vector_id)  # documents never get the query prefix
                report = await store.ensure_vector(base, config.endpoint(vector_id), config.cache_dir)
                environment["vectors"][vector_id] = _jsonable(asdict(report))
                if report.failed:  # a chunk without a vector is never found: the comparison would be unfair
                    raise RunnerError(
                        f"vector {vector_id}: {sum(report.failed.values())} chunks could not be embedded "
                        f"{report.failed}; fix the model or endpoint and rerun (embeddings made so far are "
                        "cached). An HTTP400 often means a setting the server refuses, e.g. `dimensions`")
            environment["store"] = _jsonable(await store.describe())
            _write_partial_state(directory, dataset, state, environment)
            to_search = {c.configuration_id for c, _ in work}
            searchers = {c.configuration_id: store.searcher(c, config.endpoint(c.vector.id) if c.vector else None)
                         for c in plan.configurations if c.configuration_id in to_search}
            progress = Progress(run_id, len(work), log)
            with (directory / PARTIAL_RESULTS).open("a", encoding="utf-8") as log_file:
                def record(result: RunResult) -> None:
                    log_file.write(result.model_dump_json() + "\n")
                    log_file.flush()
                    state.results[(result.configuration_id, result.query_id)] = result
                    progress.add(result)
                await search_all(work, searchers, dataset, config.budget.concurrency,
                                 RateLimiter(config.budget.max_qps), record)
        finally:
            await store.close()
    environment["finished"] = _now()
    return finish(directory, run_id, dataset, state, environment)


def finish(directory: Path, run_id: str, dataset: Dataset, state: RunState, environment: dict[str, Any]) -> Run:
    """Write the run with every result (earlier ones included) and remove the partial files. The
    partial log first gets the earlier results too, so an interruption here loses nothing."""
    logged = {(r.configuration_id, r.query_id) for r in read_partial_results(directory / PARTIAL_RESULTS)}
    with (directory / PARTIAL_RESULTS).open("a", encoding="utf-8") as f:
        for key, result in state.results.items():
            if key not in logged:
                f.write(result.model_dump_json() + "\n")
        f.flush()
        os.fsync(f.fileno())
    order = {c: i for i, c in enumerate(state.configurations)}
    results = sorted(state.results.values(), key=lambda r: (order[r.configuration_id], r.query_id))
    manifest = {"run_id": run_id, "created": state.created, "dataset": dataset.ref(),
                "configurations": list(state.configurations.values()),
                "environment": shareable({**environment, "sessions": state.sessions}),
                "counts": {"configurations": len(state.configurations)}}
    run = write_run(directory, manifest, results, dataset)
    (directory / PARTIAL_RESULTS).unlink(missing_ok=True)
    (directory / PARTIAL_STATE).unlink(missing_ok=True)
    return run


# ---- command line -------------------------------------------------------------------------

def describe_configuration(c: RunConfiguration) -> str:
    parts = [c.mode]
    if c.vector:
        parts.append(f"vector={c.vector.id}")
    if c.mode == "hybrid":
        parts += [f"alpha={c.alpha:g}", f"fusion={c.fusion or 'default'}"]
    if c.vector:
        parts.append(f"prefix={c.vector.query_prefix!r}" if len(c.vector.query_prefix) <= 40
                     else f"prefix={c.vector.query_prefix[:37]!r}...")
    if c.mode != "vector":
        parts.append(f"properties={c.properties}" if c.properties else "properties=default")
    parts.append(f"depth={c.depth}")
    return " ".join(parts)


def dry_run(plan: Plan, directory: Path, run_id: str, retry_failed: bool, out: Callable[[str], None]) -> None:
    languages = Counter(q.language for q in plan.queries)
    out(f"dataset {plan.dataset.manifest.dataset_id} {plan.dataset.manifest.version}: "
        f"{len(plan.queries)} queries selected of {len(plan.dataset.queries)} "
        f"({', '.join(f'{k} {v}' for k, v in sorted(languages.items()))}), "
        f"{len({q.intent_id for q in plan.queries})} intents")
    state = read_state(directory, plan.dataset, repair=False) if directory.exists() else RunState()
    state.adopt(plan.configurations)
    todo = Counter(c.configuration_id for c, _ in pending(plan, state, retry_failed))
    for c in plan.configurations:
        out(f"  {c.configuration_id}: {describe_configuration(c)}; {todo[c.configuration_id]} to search")
    out(f"run {run_id} in {directory}: {sum(todo.values())} searches to do (nothing was searched: dry run)")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m semant_demo.benchmarks.search_relevance.runner",
                                     description="Search a frozen benchmark dataset in the benchmark-owned Weaviate.")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run (or resume, or extend) a run")
    run.add_argument("--config", required=True, type=Path)
    run.add_argument("--run-id", required=True,
                     help="the run's name: a new id starts a run, an existing one resumes and extends it")
    run.add_argument("--out", type=Path, help="the runs directory (default: runs_dir of the config)")
    run.add_argument("--configurations", help="comma-separated configuration ids (default: all)")
    run.add_argument("--retry-failed", action="store_true", help="search again the queries that failed")
    run.add_argument("--dry-run", action="store_true", help="print the plan; touch no store")
    listing = commands.add_parser("list-configurations", help="print the expanded configurations")
    listing.add_argument("--config", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None, open_store: OpenStore | None = None,
         out: Callable[[str], None] = print) -> int:
    args = _parser().parse_args(argv)
    try:
        config, sha = load_config(args.config)
        if args.command == "list-configurations":
            for c in expand(config):
                out(f"{c.configuration_id}\t{describe_configuration(c)}")
            return 0
        run_id = args.run_id
        if not re.match(ID_PATTERN, run_id):
            raise ConfigError(f"run id {run_id!r}: letters, digits, '_', '.', ':' and '-'")
        only = [i.strip() for i in args.configurations.split(",") if i.strip()] if args.configurations else None
        plan = make_plan(config, config_path=args.config.resolve(), config_sha256=sha, only=only)
        directory = (args.out.expanduser() if args.out else config.runs_dir) / run_id
        existing = directory.is_dir() and any(directory.iterdir())
        out(f"{'continuing' if existing else 'new'} run {run_id} in {directory}")
        if args.dry_run:
            dry_run(plan, directory, run_id, args.retry_failed, out)
            return 0
        if open_store is None:
            from semant_demo.benchmarks.search_relevance.store import open_store  # the only use of the store stage
        run = asyncio.run(execute(plan, directory, run_id, open_store, retry_failed=args.retry_failed, log=out))
    except (ConfigError, ContractError, RunnerError) as e:
        print(f"error: {e}", file=sys.stderr)
        return REFUSED
    out(f"wrote {run.directory}: {run.manifest.counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
