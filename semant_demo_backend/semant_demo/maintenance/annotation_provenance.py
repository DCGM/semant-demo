"""Annotation provenance (#460): add its properties to the ``Annotation`` collection.

Span writes record who created, reviewed and last edited each annotation, its origin
(``manual`` / ``ai`` with the suggestion run's ``aiRunId``) and an ``editVersion`` that
refuses a write based on an outdated copy (``features/annotations/service.py``), once the
annotation collection holds these properties. Collections created by the migration
(``annotation_migration --create-schema``) already hold them; an existing collection gets
them from this command. Existing annotations are not changed: their origin stays
``unknown``, with no actor or time, and their version is 0.

Show what is missing (read-only), then add it::

    python -m semant_demo.maintenance.annotation_provenance add-schema
    python -m semant_demo.maintenance.annotation_provenance add-schema --execute --confirm-endpoint localhost:8080

Then restart the backend: it decides at startup whether it records provenance. Adding
properties is safe while the backend runs (it keeps writing without them until restarted).
"""
import argparse
import asyncio
import json
import sys


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("add-schema", help="add the provenance properties (dry run unless --execute)")
    a.add_argument("--execute", action="store_true")
    a.add_argument("--confirm-endpoint", metavar="HOST:PORT", help="with --execute: the configured Weaviate endpoint")
    return p


async def _main(argv: list[str]) -> int:
    from semant_demo.adapters.weaviate.client import connect_weaviate
    from semant_demo.adapters.weaviate.spans import add_provenance_schema, provenance_schema
    from semant_demo.config import Config

    args = _parser().parse_args(argv)
    config = Config()
    endpoint = f"{config.WEAVIATE_HOST}:{config.WEAVIATE_REST_PORT}"
    if args.execute and args.confirm_endpoint != endpoint:
        print(f"Refusing to write: configured endpoint {endpoint}, --confirm-endpoint {args.confirm_endpoint}",
              file=sys.stderr)
        return 2
    print(f"Weaviate endpoint: {endpoint}", file=sys.stderr)

    client = await connect_weaviate(config)
    try:
        names = config.collectionNames
        if not args.execute:
            print(json.dumps({"missing_properties": await provenance_schema(client, names)}, indent=2))
            return 0
        print(json.dumps({"added": await add_provenance_schema(client, names)}, indent=2))
        return 0
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
