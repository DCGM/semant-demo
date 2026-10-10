"""Report, and on explicit request apply, document metadata from the Kramerius mirror (#257).

Each Weaviate document takes its metadata from exactly one mirror row: the row of its own
source library, ``(id, library)``. The library is the document's stored ``library``
property or, for stores without one, the ``--library-map`` CSV (``document_id,library``
lines). Nothing is taken from another library's row: a value the selected row lacks stays
as it is, and a document whose library is unknown or conflicting, or whose row is missing,
is reported as unresolved and left unchanged.

Report (read-only, the default)::

    KRAMERIUS_METADATA_DSN=postgresql+psycopg://user@host:5888/librarymetadata_all \\
    python -m semant_demo.maintenance.metadata_sync --report metadata.json \\
        [--library-map libraries.csv] [--document-ids ids.txt | --after UUID] [--limit N] \\
        [--overwrite] [--update-access]

Apply the changes listed in a reviewed report (back up the data first)::

    python -m semant_demo.maintenance.metadata_sync --apply metadata.json --confirm-endpoint localhost:8080

Only properties the documents collection declares are written, converted to their declared
type; a value that does not fit (e.g. ``seriesNumber`` "IV" for an ``int`` property) is
reported and skipped. The schema is never changed. Empty properties are filled; a differing
stored value is replaced only with ``--overwrite``, and ``public`` only with
``--update-access``; both are otherwise listed as ``held``. Values are never cleared:
stored values the source row lacks are listed as ``stale``.

Applying refuses to run unless ``--confirm-endpoint`` and the report's endpoint both equal
the configured Weaviate endpoint and the declared property types still match. A change is
written only while the stored value still equals the reviewed old value, so applying again
(e.g. after a failure) skips finished documents; documents changed since the report are
listed and not written. The exit code is 1 when any listed document was not updated.
The Weaviate endpoint comes from ``WEAVIATE_HOST`` / ``WEAVIATE_REST_PORT`` /
``WEAVIATE_GRPC_PORT``; the mirror from ``KRAMERIUS_METADATA_DSN`` (a SQLAlchemy URL; the
PostgreSQL driver, e.g. ``psycopg``, is installed separately).
"""
import argparse
import asyncio
import csv
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.engine import Connection
from weaviate import WeaviateAsyncClient

import semant_demo.schemas as schemas
from semant_demo.adapters.sql.kramerius_metadata import read_meta_records
from semant_demo.adapters.weaviate.document_metadata import (
    document_property_types, read_document_page, read_documents, update_document)
from semant_demo.maintenance.kramerius_mapping import FIELDS, SourceRecord, map_record

PAGE_SIZE = 100
DSN_VARIABLE = "KRAMERIUS_METADATA_DSN"

# Property names of older stores, after the current one.
TARGET_NAMES = {
    "author": ("author", "authors"),
    "subtitle": ("subtitle", "subTitle"),
    "placeOfPublication": ("placeOfPublication", "placeTerm"),
}


class Unresolved(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def resolve_library(stored: Any, mapped: str | None) -> tuple[str, str]:
    """(library, where it came from) of a document; raises ``Unresolved``."""
    stored = stored.strip() if isinstance(stored, str) else None
    if stored and mapped and stored != mapped:
        raise Unresolved("library_conflict", f"stored library {stored!r} differs from mapped library {mapped!r}")
    if stored:
        return stored, "stored"
    if mapped:
        return mapped, "library_map"
    raise Unresolved("no_library", "the document stores no library and the library map lists none")


def select_record(records: list[SourceRecord], library: str) -> SourceRecord:
    """The record of this library; raises ``Unresolved`` for none or several."""
    matching = [r for r in records if r.library == library]
    if len(matching) == 1:
        return matching[0]
    if matching:
        raise Unresolved("ambiguous_source_row", f"{len(matching)} mirror rows for library {library!r}")
    others = sorted({r.library for r in records})
    raise Unresolved("no_source_row", f"no mirror row for library {library!r}"
                     + (f" (rows exist for {', '.join(others)}; not used)" if others else ""))


def target_properties(types: dict[str, str]) -> tuple[dict[str, tuple[str, str]], list[str]]:
    """(field -> (declared property, type), fields without a declared property)."""
    targets, undeclared = {}, []
    for field in FIELDS:
        name = next((n for n in TARGET_NAMES.get(field, (field,)) if n in types), None)
        if name is None:
            undeclared.append(field)
        else:
            targets[field] = (name, types[name])
    return targets, undeclared


def jsonable(value: Any) -> Any:
    """The value as written to a report; also the form in which values are compared."""
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return aware.astimezone(timezone.utc).isoformat()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def coerce(value: Any, data_type: str) -> Any:
    """The value converted to a Weaviate data type; raises ``ValueError`` if it does not fit."""
    if isinstance(value, bool):
        if data_type == "boolean":
            return value
    elif data_type == "text" and isinstance(value, (str, int)):
        return str(value)
    elif data_type == "text[]" and isinstance(value, list):
        return [str(v) for v in value]
    elif data_type == "int" and (isinstance(value, int) or (isinstance(value, str) and value.isdigit())):
        return int(value)
    elif data_type == "number" and isinstance(value, (int, float, str)):
        try:
            number = float(value)
        except ValueError:
            pass
        else:
            return int(number) if number.is_integer() else number
    elif data_type == "date" and isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raise ValueError(f"{value!r} does not fit {data_type}")


def plan_document(document_id: UUID, stored: dict[str, Any], records: list[SourceRecord],
                  mapped_library: str | None, targets: dict[str, tuple[str, str]],
                  *, overwrite: bool = False, update_access: bool = False) -> dict[str, Any]:
    """The report entry of one document: its source and the property changes."""
    entry: dict[str, Any] = {"id": str(document_id)}
    try:
        library, origin = resolve_library(stored.get("library"), mapped_library)
        record = select_record(records, library)
    except Unresolved as e:
        return {**entry, "status": "unresolved", "kind": e.kind, "reason": str(e)}
    entry.update(library=library, library_from=origin, in_library=record.in_library)

    mapped = map_record(record)
    changes: dict[str, Any] = {}
    held: dict[str, Any] = {}
    skipped: dict[str, str] = {}
    stale: list[str] = []
    for field, (prop, data_type) in targets.items():
        old = jsonable(stored.get(prop))
        if field not in mapped:
            if not _empty(old):
                stale.append(prop)
            continue
        try:
            new = jsonable(coerce(mapped[field], data_type))
        except ValueError as e:
            skipped[prop] = str(e)
            continue
        if new == old:
            continue
        if field == "public" and not update_access:
            held[prop] = {"old": old, "new": new, "reason": "access flag; needs --update-access"}
        elif field != "public" and not _empty(old) and not overwrite:
            held[prop] = {"old": old, "new": new, "reason": "differs from the stored value; needs --overwrite"}
        else:
            changes[prop] = {"old": old, "new": new}
    entry["status"] = "update" if changes else "unchanged"
    for key, value in (("changes", changes), ("held", held), ("skipped", skipped), ("stale", stale)):
        if value:
            entry[key] = value
    return entry


async def _pages(client: WeaviateAsyncClient, names: schemas.CollectionNames, document_ids: list[UUID] | None,
                 after: UUID | None, limit: int | None):
    """Pages of (id, stored properties or None if missing), at most ``limit`` documents."""
    remaining = limit
    if document_ids is not None:
        document_ids = document_ids[:limit] if limit is not None else document_ids
        for start in range(0, len(document_ids), PAGE_SIZE):
            ids = document_ids[start:start + PAGE_SIZE]
            stored = await read_documents(client, names, ids)
            yield [(i, stored.get(i)) for i in ids]
        return
    while remaining is None or remaining > 0:
        size = PAGE_SIZE if remaining is None else min(PAGE_SIZE, remaining)
        page = await read_document_page(client, names, after, size)
        if not page:
            return
        yield page
        after = page[-1][0]
        if remaining is not None:
            remaining -= len(page)
        if len(page) < size:
            return


async def build_report(client: WeaviateAsyncClient, names: schemas.CollectionNames, source: Connection, *,
                       endpoint: str, source_name: str, library_map: dict[UUID, str] | None = None,
                       document_ids: list[UUID] | None = None, after: UUID | None = None,
                       limit: int | None = None, overwrite: bool = False, update_access: bool = False) -> dict:
    """The report of the documents in scope. Reads only. Raises ``LookupError`` if the
    documents collection does not exist."""
    types = await document_property_types(client, names)
    if types is None:
        raise LookupError(f"Collection {names.document_collection_name} does not exist")
    targets, undeclared = target_properties(types)
    library_map = library_map or {}

    entries: list[dict[str, Any]] = []
    last: UUID | None = None
    async for page in _pages(client, names, document_ids, after, limit):
        records = read_meta_records(source, [i for i, stored in page if stored is not None])
        for document_id, stored in page:
            last = document_id
            if stored is None:
                entries.append({"id": str(document_id), "status": "unresolved", "kind": "not_in_target",
                                "reason": "no such document in the target collection"})
                continue
            entries.append(plan_document(document_id, stored, records.get(document_id, []),
                                         library_map.get(document_id), targets,
                                         overwrite=overwrite, update_access=update_access))

    reached_limit = document_ids is None and limit is not None and len(entries) == limit
    return {
        "endpoint": endpoint,
        "collection": names.document_collection_name,
        "source": source_name,
        "created": datetime.now(timezone.utc).isoformat(),
        "options": {"overwrite": overwrite, "update_access": update_access, "after": after and str(after),
                    "limit": limit, "document_ids": document_ids is not None, "library_map": bool(library_map)},
        "target_schema": {prop: data_type for prop, data_type in targets.values()},
        "undeclared_fields": undeclared,
        "counts": _counts(entries),
        "next_after": str(last) if reached_limit and last else None,
        "documents": [e for e in entries if set(e) - {"id", "status", "library", "library_from", "in_library"}],
    }


def _counts(entries: list[dict[str, Any]]) -> dict[str, Any]:
    status = Counter(e["status"] for e in entries)
    return {
        "documents": len(entries),
        "update": status["update"],
        "unchanged": status["unchanged"],
        "unresolved": dict(sorted(Counter(e["kind"] for e in entries if e["status"] == "unresolved").items())),
        "with_held_changes": sum(1 for e in entries if "held" in e),
        "with_skipped_values": sum(1 for e in entries if "skipped" in e),
        "with_stale_values": sum(1 for e in entries if "stale" in e),
        "changed_properties": dict(sorted(Counter(p for e in entries for p in e.get("changes", {})).items())),
    }


def _to_weaviate(value: Any, data_type: str) -> Any:
    return datetime.fromisoformat(value) if data_type == "date" and isinstance(value, str) else value


async def apply_report(client: WeaviateAsyncClient, names: schemas.CollectionNames, report: dict) -> dict:
    """Write the reviewed changes. Raises ``LookupError`` if the declared property types
    differ from the report's."""
    types = await document_property_types(client, names)
    expected = report["target_schema"]
    if types is None or any(types.get(prop) != data_type for prop, data_type in expected.items()):
        raise LookupError("The documents collection schema differs from the report's; create a new report")

    entries = [e for e in report["documents"] if e.get("changes")]
    applied = already_applied = 0
    not_applied: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []
    for start in range(0, len(entries), PAGE_SIZE):
        page = entries[start:start + PAGE_SIZE]
        current = await read_documents(client, names, [UUID(e["id"]) for e in page])
        for entry in page:
            stored = current.get(UUID(entry["id"]))
            if stored is None:
                not_applied.append({"id": entry["id"], "reason": "the document no longer exists"})
                continue
            pending, conflict = {}, None
            for prop, change in entry["changes"].items():
                now = jsonable(stored.get(prop))
                if now == change["new"]:
                    continue
                if now != change["old"]:
                    conflict = f"{prop} changed since the report"
                    break
                pending[prop] = _to_weaviate(change["new"], types[prop])
            if conflict:
                not_applied.append({"id": entry["id"], "reason": conflict})
            elif not pending:
                already_applied += 1
            else:
                try:
                    await update_document(client, names, UUID(entry["id"]), pending)
                except Exception as e:  # the write may or may not have happened; applying again re-checks
                    failed.append({"id": entry["id"], "error": f"{type(e).__name__}: {e}"})
                else:
                    applied += 1
    return {"documents": len(entries), "applied": applied, "already_applied": already_applied,
            "not_applied": not_applied, "failed": failed}


def read_library_map(path: Path) -> dict[UUID, str]:
    """``document_id,library`` lines; blank lines and ``#`` comments are ignored. Raises
    ``ValueError`` for a malformed line or an id listed with two libraries."""
    mapping: dict[UUID, str] = {}
    with path.open(encoding="utf-8", newline="") as file:
        for number, row in enumerate(csv.reader(file), start=1):
            if not row or not row[0].strip() or row[0].lstrip().startswith("#"):
                continue
            if len(row) != 2 or not row[1].strip():
                raise ValueError(f"{path}:{number}: expected document_id,library")
            document_id, library = UUID(row[0].strip()), row[1].strip()
            if mapping.get(document_id, library) != library:
                raise ValueError(f"{path}:{number}: {document_id} is listed with two libraries")
            mapping[document_id] = library
    return mapping


def read_document_ids(path: Path) -> list[UUID]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return list(dict.fromkeys(UUID(line.strip()) for line in lines if line.strip() and not line.startswith("#")))


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--report", type=Path, help="write the report (JSON) to this file")
    p.add_argument("--library-map", type=Path, help="CSV of document_id,library for documents storing no library")
    scope = p.add_mutually_exclusive_group()
    scope.add_argument("--document-ids", type=Path, help="only these documents (one UUID per line)")
    scope.add_argument("--after", type=UUID, help="start after this document id (a report's next_after)")
    p.add_argument("--limit", type=int, help="at most this many documents")
    p.add_argument("--overwrite", action="store_true", help="replace differing non-empty stored values")
    p.add_argument("--update-access", action="store_true", help="also change the public flag")
    p.add_argument("--apply", type=Path, metavar="REPORT", help="write the changes listed in this reviewed report")
    p.add_argument("--confirm-endpoint", metavar="HOST:PORT", help="with --apply: the configured Weaviate endpoint")
    return p


async def _main(argv: list[str]) -> int:
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    from semant_demo.adapters.weaviate.client import connect_weaviate
    from semant_demo.config import Config

    args = _parser().parse_args(argv)
    config = Config()
    endpoint = f"{config.WEAVIATE_HOST}:{config.WEAVIATE_REST_PORT}"
    names = config.collectionNames

    report = engine = None
    if args.apply:
        report = json.loads(args.apply.read_text(encoding="utf-8"))
        if args.confirm_endpoint != endpoint or report.get("endpoint") != endpoint:
            print(f"Refusing to write: configured endpoint {endpoint}, --confirm-endpoint "
                  f"{args.confirm_endpoint}, report endpoint {report.get('endpoint')}", file=sys.stderr)
            return 2
        if report.get("collection") != names.document_collection_name:
            print(f"Refusing to write: configured collection {names.document_collection_name}, "
                  f"report collection {report.get('collection')}", file=sys.stderr)
            return 2
    else:
        dsn = os.environ.get(DSN_VARIABLE)
        if not dsn:
            print(f"Set {DSN_VARIABLE} to the metadata mirror's SQLAlchemy URL", file=sys.stderr)
            return 2
        try:
            library_map = read_library_map(args.library_map) if args.library_map else None
            document_ids = read_document_ids(args.document_ids) if args.document_ids else None
        except ValueError as e:
            print(e, file=sys.stderr)
            return 2
        engine = create_engine(dsn)

    print(f"Weaviate endpoint: {endpoint}, collection {names.document_collection_name}", file=sys.stderr)
    client = await connect_weaviate(config)
    try:
        if report is not None:
            try:
                result = await apply_report(client, names, report)
            except LookupError as e:
                print(e, file=sys.stderr)
                return 2
            print(json.dumps(result, indent=2))
            return 1 if result["not_applied"] or result["failed"] else 0
        with engine.connect() as source:
            try:
                new_report = await build_report(
                    client, names, source, endpoint=endpoint,
                    source_name=make_url(dsn).render_as_string(hide_password=True),
                    library_map=library_map, document_ids=document_ids, after=args.after, limit=args.limit,
                    overwrite=args.overwrite, update_access=args.update_access)
            except LookupError as e:
                print(e, file=sys.stderr)
                return 2
        if args.report:
            args.report.write_text(json.dumps(new_report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({key: new_report[key] for key in ("endpoint", "collection", "source", "undeclared_fields",
                                                           "counts", "next_after")}, indent=2))
        return 0
    finally:
        await client.close()
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
