"""The search benchmark dataset generator (#726, docs/SEARCH_BENCHMARK.md).

    python -m semant_demo.benchmarks.search_relevance.generate run CONFIG --work DIR [--out DIR]
        [--from STEP] [--until STEP] [--force] [--source-host HOST --source-port PORT --source-grpc-port PORT]
    python -m semant_demo.benchmarks.search_relevance.generate budget CONFIG [--work DIR]
    python -m semant_demo.benchmarks.search_relevance.generate validate DATASET_DIR

``run`` executes the steps ``sample``, ``intents``, ``translate``, ``pool``, ``judge`` and
``write`` (see ``pipeline``), skipping those whose outputs are up to date; the dataset goes to
``--out`` (default ``<work>/dataset``) with ``summary.md``. The source store is read only (its
address from the configuration, the options or the environment, as the backend's ``Config``).
Model providers come from the environment (``OPENAI_API_KEY``, ``OPENAI_API_URL``,
``OLLAMA_URLS``) and the models from the configuration's ``models`` catalog. ``budget`` estimates
the model calls and cost without any call; ``validate`` loads a dataset and prints its summary.

Exit codes: 0 done, 1 failed, 2 refused (configuration, a missing setting, an invalid dataset).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from semant_demo.benchmarks.search_relevance.contracts import ContractError, load_dataset
from semant_demo.benchmarks.search_relevance.llm import Refused, UsageTotals
from semant_demo.benchmarks.search_relevance.pipeline import STEPS, Generator, Resources
from semant_demo.benchmarks.search_relevance.source import SourceError
from semant_demo.benchmarks.search_relevance.summary import summarize


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m semant_demo.benchmarks.search_relevance.generate",
                                description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="generate (or resume) a dataset")
    run.add_argument("config", type=Path)
    run.add_argument("--work", type=Path, required=True, help="work directory (step outputs, model call cache)")
    run.add_argument("--out", type=Path, help="dataset directory (default: WORK/dataset)")
    run.add_argument("--from", dest="start", choices=STEPS, help="rerun this step and every later one")
    run.add_argument("--until", choices=STEPS, help="stop after this step")
    run.add_argument("--force", action="store_true", help="rerun every step (cached model calls are reused)")
    budget = sub.add_parser("budget", help="estimate model calls and cost (no call is made)")
    budget.add_argument("config", type=Path)
    budget.add_argument("--work", type=Path, help="use the outputs of an earlier run")
    for command in (run, budget):  # budget takes run's source, so that it judges the same steps fresh
        command.add_argument("--source-host")
        command.add_argument("--source-port", type=int)
        command.add_argument("--source-grpc-port", type=int)
    validate = sub.add_parser("validate", help="load a dataset and print its summary")
    validate.add_argument("dataset", type=Path)
    return p


def with_source_overrides(config, args):
    """The config with the command line's source (``--source-*``) instead of its own: the
    sample step's inputs include the source, so pointing at another store reruns the sampling."""
    source = {key: value for key, value in (("host", args.source_host), ("rest_port", args.source_port),
                                            ("grpc_port", args.source_grpc_port)) if value is not None}
    return config.model_copy(update={"source": config.source.model_copy(update=source)}) if source else config


def _resources(config, args, opened: list) -> Resources:
    from semant_demo.adapters.llm.gateway import LlmGateway, ProviderSettings
    from semant_demo.config import Config

    settings = Config()
    usage = UsageTotals()
    llm = LlmGateway(config.catalog(), ProviderSettings.from_config(settings), usage)

    async def source():
        from semant_demo.adapters.weaviate.client import connect_weaviate
        from semant_demo.benchmarks.search_relevance.source import WeaviateSource

        overrides = {"WEAVIATE_HOST": config.source.host, "WEAVIATE_REST_PORT": config.source.rest_port,
                     "WEAVIATE_GRPC_PORT": config.source.grpc_port}
        environ = {**os.environ, **{k: str(v) for k, v in overrides.items() if v}}
        source_config = Config(environ=environ)
        client = await connect_weaviate(source_config, query_timeout=config.source.query_timeout)
        opened.append(client)
        # The manifest describes the source without naming its host (datasets may be shared).
        return WeaviateSource(client, source_config.collectionNames, {"description": config.source.description},
                              include_restricted=config.source.include_restricted_documents)

    async def open_store(spec):
        from semant_demo.benchmarks.search_relevance.store import open_store as real_open_store
        return await real_open_store(spec)

    return Resources(llm=llm, usage=usage, source=source, open_store=open_store)


async def _run(args) -> int:
    from semant_demo.benchmarks.search_relevance.config import load_config

    config, data, sha = load_config(args.config)
    config = with_source_overrides(config, args)
    missing = config.pooling.missing_key_envs()  # before any step, so no model call precedes the refusal
    if missing:
        raise Refused(f"{', '.join(missing)} is not set; a pooling endpoint's api_key_env names it")
    work = args.work
    work.mkdir(parents=True, exist_ok=True)
    opened: list = []
    generator = Generator(config, data, sha, work, args.out or work / "dataset", _resources(config, args, opened),
                          config_name=args.config.name, progress=lambda m: print(m, file=sys.stderr))
    try:
        ran = await generator.run(args.start, args.until, args.force)
    finally:
        for client in opened:
            await client.close()
    print(json.dumps({"ran": ran, "dataset": str(generator.out), "usage": generator.usage()}, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "validate":
            print(summarize(load_dataset(args.dataset)), end="")
            return 0
        if args.command == "budget":
            from semant_demo.benchmarks.search_relevance.budget import estimate
            from semant_demo.benchmarks.search_relevance.config import load_config

            config, _, _ = load_config(args.config)
            config = with_source_overrides(config, args)
            # The gateway ``run`` would use (no call is made): a step counts as done only when fresh.
            llm = _resources(config, args, []).llm if args.work is not None else None
            print(json.dumps(estimate(config, args.work, llm), indent=1))
            return 0
        return asyncio.run(_run(args))
    except (Refused, SourceError, ContractError, ValidationError, FileNotFoundError) as e:
        print(f"Refused: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
