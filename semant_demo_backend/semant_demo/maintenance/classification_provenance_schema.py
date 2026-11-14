"""Declare, on explicit request, the chunks' classification status (#590).

``Chunks.classification_provenance`` (``text``, ``field`` tokenization, filterable, not
searchable): ``UNPROCESSED`` on the chunks ``chunk_ingest`` inserts, the classifier's
model/version identifier once a chunk is classified. Chunks stored before the property is
declared get no value and are never selected for classification; nothing existing is
rewritten. The collection name is resolved through its alias. Never runs during a request or
at startup, never drops or changes a declared property.

Check (read-only, the default) and apply::

    python -m semant_demo.maintenance.classification_provenance_schema
    python -m semant_demo.maintenance.classification_provenance_schema --apply --confirm-endpoint HOST:PORT

Repeatable: applying again adds nothing. A property already declared differently (another
type, tokenization or filter index) is refused before anything is added: index settings of a
declared property cannot be changed in place, so it needs a separate, reviewed migration.
``chunk_ingest`` refuses a store without the property.

Exit code 0 when the property is declared as expected, 1 when a check finds it missing, 2 when
refused.
"""
import argparse
import asyncio
import json
import sys
from typing import Any

from weaviate import WeaviateAsyncClient

from semant_demo.adapters.weaviate import classification_provenance as provenance
from semant_demo.adapters.weaviate.chunk_summaries import declared_properties
from semant_demo.adapters.weaviate.document_cleanup import resolve_collection
from semant_demo.adapters.weaviate.names import CollectionNames


class Refused(LookupError):
    """Nothing was added."""


async def update(client: WeaviateAsyncClient, names: CollectionNames, *, apply: bool) -> dict[str, Any]:
    """The state of the property, after adding it with ``apply`` when missing. Raises
    ``Refused`` (nothing added) for a missing collection or a property declared differently."""
    chunks = await resolve_collection(client, names.chunks_collection_name)
    if not await client.collections.exists(chunks):
        raise Refused(f"Collection {chunks} does not exist")
    declared = await declared_properties(client, chunks)
    state = provenance.status(declared)
    if state == "different":
        raise Refused(f"{chunks} declares {provenance.PROPERTY} as {json.dumps(vars(declared[provenance.PROPERTY]))}, "
                      f"expected {json.dumps(vars(provenance.EXPECTED))}; this needs a separate, reviewed "
                      "migration. Nothing was added")
    added = False
    if apply and state == "missing":
        await provenance.add_property(client, chunks)
        added, state = True, provenance.status(await declared_properties(client, chunks))
    return {"chunks": chunks, "property": provenance.PROPERTY, "expected": vars(provenance.EXPECTED),
            "missing": state == "missing", "added": added}


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true", help="declare the missing property")
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
