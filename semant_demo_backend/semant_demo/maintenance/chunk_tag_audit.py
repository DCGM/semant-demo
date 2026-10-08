"""Audit, and on explicit request correct, chunk tag references against their spans (#204).

Chunk ``automaticTag`` / ``positiveTag`` / ``negativeTag`` references must be backed by a
span of the matching type and tag anchored on that chunk (ADR 0004). References without
one are data inconsistencies, not a supported legacy feature; spans whose reference is
missing are invisible to tag-filtered search.

Audit (read-only, the default)::

    python -m semant_demo.maintenance.chunk_tag_audit --report chunk_tags.json

Correct the pairs listed in a reviewed report (back up the data first)::

    python -m semant_demo.maintenance.chunk_tag_audit --apply chunk_tags.json \\
        --remove-unbacked [--add-missing] --confirm-endpoint localhost:8080

The Weaviate endpoint comes from ``WEAVIATE_HOST`` / ``WEAVIATE_REST_PORT`` /
``WEAVIATE_GRPC_PORT``. Applying refuses to run unless ``--confirm-endpoint`` and the
report's endpoint both equal the configured one. Every listed pair is re-derived from the
spans stored at that moment, so references backed by spans created after the audit are
kept, and a failed read stops that pair instead of being taken as "no spans". Nothing
here runs at startup or during requests.
"""
import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from weaviate import WeaviateAsyncClient

import semant_demo.schemas as schemas
from semant_demo.adapters.weaviate.chunk_tags import ChunkTagIssue, apply_chunk_tag_fixes, audit_chunk_tags


def _counts(issues: list[ChunkTagIssue]) -> dict[str, int]:
    return dict(sorted(Counter(f"{i.kind}:{i.ref}" for i in issues).items()))


async def build_report(client: WeaviateAsyncClient, names: schemas.CollectionNames, endpoint: str) -> dict:
    issues = await audit_chunk_tags(client, names)
    return {
        "endpoint": endpoint,
        "created": datetime.now(timezone.utc).isoformat(),
        "counts": _counts(issues),
        "issues": [{"chunk_id": str(i.chunk_id), "tag_id": str(i.tag_id), "ref": i.ref, "kind": i.kind}
                   for i in issues],
    }


def issues_of(report: dict) -> list[ChunkTagIssue]:
    return [ChunkTagIssue(UUID(i["chunk_id"]), UUID(i["tag_id"]), i["ref"], i["kind"]) for i in report["issues"]]


async def apply_report(client: WeaviateAsyncClient, names: schemas.CollectionNames, report: dict,
                       *, remove_unbacked: bool, add_missing: bool) -> dict:
    done, failed = await apply_chunk_tag_fixes(client, names, issues_of(report),
                                               remove_unbacked=remove_unbacked, add_missing=add_missing)
    return {
        "corrected_pairs": len(done),
        "failed": [f.model_dump() for f in failed],
    }


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--report", type=Path, help="write the audit report (JSON) to this file")
    p.add_argument("--apply", type=Path, metavar="REPORT", help="correct the pairs listed in this reviewed report")
    p.add_argument("--remove-unbacked", action="store_true", help="with --apply: remove references without a span")
    p.add_argument("--add-missing", action="store_true", help="with --apply: add references spans require")
    p.add_argument("--confirm-endpoint", metavar="HOST:PORT", help="with --apply: the configured Weaviate endpoint")
    return p


async def _main(argv: list[str]) -> int:
    from semant_demo.adapters.weaviate.client import connect_weaviate
    from semant_demo.config import Config

    args = _parser().parse_args(argv)
    config = Config()
    endpoint = f"{config.WEAVIATE_HOST}:{config.WEAVIATE_REST_PORT}"

    report = None
    if args.apply:
        if not (args.remove_unbacked or args.add_missing):
            print("--apply needs --remove-unbacked and/or --add-missing", file=sys.stderr)
            return 2
        report = json.loads(args.apply.read_text(encoding="utf-8"))
        if args.confirm_endpoint != endpoint or report.get("endpoint") != endpoint:
            print(f"Refusing to write: configured endpoint {endpoint}, --confirm-endpoint "
                  f"{args.confirm_endpoint}, report endpoint {report.get('endpoint')}", file=sys.stderr)
            return 2

    print(f"Weaviate endpoint: {endpoint}", file=sys.stderr)
    client = await connect_weaviate(config)
    try:
        if report is not None:
            result = await apply_report(client, config.collectionNames, report,
                                        remove_unbacked=args.remove_unbacked, add_missing=args.add_missing)
            print(json.dumps(result, indent=2))
            return 1 if result["failed"] else 0
        new_report = await build_report(client, config.collectionNames, endpoint)
        if args.report:
            args.report.write_text(json.dumps(new_report, indent=2), encoding="utf-8")
        print(json.dumps({"endpoint": endpoint, "counts": new_report["counts"],
                          "issues": len(new_report["issues"])}, indent=2))
        return 0
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
