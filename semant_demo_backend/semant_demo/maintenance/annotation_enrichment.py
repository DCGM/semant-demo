"""Annotation derived data (#328): schema, status and backfill.

Span writes store each annotation's text, context, positions and contextual vector
(``features/annotations/derivation.py``, ``enrichment.py``) once the annotation collection
holds the derived properties. Spans saved before, spans whose derivation or embedding
failed, and vectors of another configuration (``ANNOTATION_VECTOR_CONFIG`` ``id``) are
completed by an explicit, bounded backfill.

Add the derived properties and the named vector to an existing ``Annotation`` collection
(no existing object is changed; a dry run lists what is missing)::

    python -m semant_demo.maintenance.annotation_enrichment add-schema
    python -m semant_demo.maintenance.annotation_enrichment add-schema --execute --confirm-endpoint localhost:8080

Then restart the backend: it decides at startup what it derives.

Status: spans per collection by text state (current / outdated / missing / failed /
invalid) and vector state (current / pending / failed / stale), and how many are
incomplete (read-only; reading a tenant activates it)::

    python -m semant_demo.maintenance.annotation_enrichment status [--collection ID ...]

Backfill at most ``--limit`` incomplete spans (a dry run reports the status)::

    python -m semant_demo.maintenance.annotation_enrichment backfill --limit 500 [--collection ID ...] \\
        [--no-vectors] --execute --confirm-endpoint localhost:8080

Only derived properties are written, never a span's offsets, chunk, tag, type or revision;
nothing is deleted. A span edited while it is backfilled keeps its newer derivation.
``remaining`` counts incomplete spans left for the next run. Embedding calls the configured
provider once per span. Exits 1 when some steps failed (listed in ``failed``).
"""
import argparse
import asyncio
import json
import sys
from uuid import UUID

DEFAULT_LIMIT = 500


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("add-schema", help="add the derived properties and the named vector (dry run unless --execute)")
    s = sub.add_parser("status", help="count spans by derived-data state (read-only)")
    b = sub.add_parser("backfill", help="derive incomplete spans (dry run unless --execute)")
    for cmd in (s, b):
        cmd.add_argument("--collection", action="append", type=UUID, help="only this collection (repeatable)")
    b.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help=f"at most this many spans (default {DEFAULT_LIMIT})")
    b.add_argument("--no-vectors", action="store_true", help="derive text and positions only, call no embedder")
    for cmd in (a, b):
        cmd.add_argument("--execute", action="store_true")
        cmd.add_argument("--confirm-endpoint", metavar="HOST:PORT", help="with --execute: the configured Weaviate endpoint")
    return p


async def _main(argv: list[str]) -> int:
    from semant_demo.adapters.weaviate.client import connect_weaviate
    from semant_demo.adapters.weaviate.spans import add_enrichment_schema, enrichment_schema
    from semant_demo.bootstrap import WeaviateRepositories, detect_enrichment, load_annotation_vector
    from semant_demo.config import Config
    from semant_demo.features.annotations import backfill
    from semant_demo.features.annotations.service import AnnotationStore

    args = _parser().parse_args(argv)
    config = Config()
    endpoint = f"{config.WEAVIATE_HOST}:{config.WEAVIATE_REST_PORT}"
    execute = getattr(args, "execute", False)
    if execute and args.confirm_endpoint != endpoint:
        print(f"Refusing to write: configured endpoint {endpoint}, --confirm-endpoint {args.confirm_endpoint}",
              file=sys.stderr)
        return 2
    if args.command == "backfill" and args.limit < 1:
        print("--limit must be positive", file=sys.stderr)
        return 2
    print(f"Weaviate endpoint: {endpoint}", file=sys.stderr)

    vector = load_annotation_vector(config)
    client = await connect_weaviate(config)
    try:
        names = config.collectionNames
        target = vector.target_vector if vector else None
        if args.command == "add-schema":
            missing, has_vector = await enrichment_schema(client, names, target)
            if not execute:
                print(json.dumps({"missing_properties": missing,
                                  "missing_vector": target if target and not has_vector else None}, indent=2))
                return 0
            print(json.dumps({"added": await add_enrichment_schema(client, names, target)}, indent=2))
            return 0

        repos = WeaviateRepositories.create(client, config)
        enrichment = await detect_enrichment(client, config, vector)
        if not enrichment.derived:
            print("The annotation collection lacks the derived properties: run add-schema first.", file=sys.stderr)
            return 2
        store = AnnotationStore(collections=repos.user_collections, tags=repos.tags, spans=repos.spans,
                                chunk_tags=repos.chunk_tags, documents=repos.documents, enrichment=enrichment)
        collections = args.collection or sorted(UUID(name) for name in await repos.spans.list_tenants())
        if args.command == "status" or not execute:
            reports = await backfill.status(store, collections)
            print(json.dumps({"vector_config": enrichment.vector.id if enrichment.vector else None,
                              "incomplete": sum(r.incomplete for r in reports),
                              "collections": [r.as_dict() for r in reports]}, indent=2))
            return 0
        result = await backfill.backfill(store, collections, limit=args.limit, vectors=not args.no_vectors)
        print(json.dumps(result.as_dict(), indent=2))
        return 1 if result.failed else 0
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
