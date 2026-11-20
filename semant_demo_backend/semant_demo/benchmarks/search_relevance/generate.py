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
    run.add_argument("--source-host")
    run.add_argument("--source-port", type=int)
    run.add_argument("--source-grpc-port", type=int)
    budget = sub.add_parser("budget", help="estimate model calls and cost (no call is made)")
    budget.add_argument("config", type=Path)
    budget.add_argument("--work", type=Path, help="use the outputs of an earlier run")
    validate = sub.add_parser("validate", help="load a dataset and print its summary")
    validate.add_argument("dataset", type=Path)
    return p


def _resources(config, args, opened: list) -> Resources:
    from semant_demo.adapters.llm.gateway import LlmGateway, ProviderSettings
    from semant_demo.config import Config

    settings = Config()
    usage = UsageTotals()
    llm = LlmGateway(config.catalog(), ProviderSettings.from_config(settings), usage)

    async def source():
        from semant_demo.adapters.weaviate.client import connect_weaviate
        from semant_demo.benchmarks.search_relevance.source import WeaviateSource

        overrides = {"WEAVIATE_HOST": args.source_host or config.source.host,
                     "WEAVIATE_REST_PORT": args.source_port or config.source.rest_port,
                     "WEAVIATE_GRPC_PORT": args.source_grpc_port or config.source.grpc_port}
        environ = {**os.environ, **{k: str(v) for k, v in overrides.items() if v}}
        source_config = Config(environ=environ)
        client = await connect_weaviate(source_config, query_timeout=config.source.query_timeout)
        opened.append(client)
        return WeaviateSource(client, source_config.collectionNames, {
            "weaviate": f"{source_config.WEAVIATE_HOST}:{source_config.WEAVIATE_REST_PORT}",
            "description": config.source.description})

    async def open_store(spec):
        from semant_demo.benchmarks.search_relevance.store import open_store as real_open_store
        return await real_open_store(spec)

    return Resources(llm=llm, usage=usage, source=source, open_store=open_store)


async def _run(args) -> int:
    from semant_demo.benchmarks.search_relevance.config import load_config

    config, data, sha = load_config(args.config)
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
            print(json.dumps(estimate(config, args.work), indent=1))
            return 0
        return asyncio.run(_run(args))
    except (Refused, ContractError, ValidationError, FileNotFoundError) as e:
        print(f"Refused: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
