"""Declare, on explicit request, the documents' chunk-value summary properties (#529).

``Documents.chunk_<dimension>`` (``text[]``, ``field`` tokenization, filterable, not
searchable) for the chunk language and each classification of ``TASK_CLASSES``, and
``Documents.chunk_summaries_computed_at`` (``date``). New properties have no values: until
``chunk_summaries --write`` recomputes them, documents match no chunk filter. The collection
name is resolved through its alias. Never runs during a request or at startup, never drops or
changes a declared property.

Check (read-only, the default) and apply::

    python -m semant_demo.maintenance.chunk_summary_schema
    python -m semant_demo.maintenance.chunk_summary_schema --apply --confirm-endpoint HOST:PORT

Repeatable: applying again adds nothing. A property already declared differently (another
type or tokenization) is refused before anything is added: index settings of a declared
property cannot be changed in place, so it needs a separate, reviewed migration.

Exit code 0 when every property is declared as expected, 1 when a check finds some missing,
2 when refused.
"""
import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from typing import Any

from weaviate import WeaviateAsyncClient

from semant_demo.adapters.weaviate import chunk_summaries as store
from semant_demo.adapters.weaviate.document_cleanup import resolve_collection
from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.maintenance.chunk_summaries import DIMENSIONS, Refused, property_status


async def update(client: WeaviateAsyncClient, names: CollectionNames, *, apply: bool,
                 dimensions: Sequence[str] = DIMENSIONS) -> dict[str, Any]:
    """The state of the summary properties, after adding the missing ones with ``apply``.
    Raises ``Refused`` (nothing added) for a missing collection or a property declared differently."""
    documents = await resolve_collection(client, names.document_collection_name)
    if not await client.collections.exists(documents):
        raise Refused(f"Collection {documents} does not exist")
    missing, different = property_status(await store.declared_properties(client, documents), dimensions)
    if different:
        raise Refused(f"{documents} declares {', '.join(different)} differently from the chunk-value summaries "
                      f"({json.dumps(different)}); this needs a separate, reviewed migration. Nothing was added")
    added = []
    if apply and missing:
        await store.add_summary_properties(client, documents, missing)
        added, missing = missing, property_status(await store.declared_properties(client, documents), dimensions)[0]
    return {"documents": documents, "expected": sorted(store.expected_properties(dimensions)),
            "missing": missing, "added": added}


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true", help="declare the missing properties")
    p.add_argument("--confirm-endpoint", metavar="HOST:PORT", help="with --apply: the configured Weaviate endpoint")
    return p


async def _main(argv: list[str]) -> int:
    from semant_demo.adapters.weaviate.client import connect_weaviate
    from semant_demo.config import Config

    args = _parser().parse_args(argv)
    config = Config()
    endpoint = f"{config.WEAVIATE_HOST}:{config.WEAVIATE_REST_PORT}"
    if args.apply and args.confirm_endpoint != endpoint:
        print(f"Refusing to apply: configured endpoint {endpoint}, --confirm-endpoint {args.confirm_endpoint}",
              file=sys.stderr)
        return 2
    print(f"Weaviate endpoint: {endpoint}", file=sys.stderr)
    client = await connect_weaviate(config)
    try:
        result = await update(client, config.collectionNames, apply=args.apply)
        print(json.dumps(result, indent=2))
        return 1 if result["missing"] else 0
    except Refused as e:
        print(e, file=sys.stderr)
        return 2
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
