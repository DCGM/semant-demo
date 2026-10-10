"""Report, and on explicit request apply, document metadata from the Kramerius mirror (#257).

Each Weaviate document takes its metadata from exactly one mirror row: the row of its own
source library, ``(id, library)``. Nothing is taken from another library's row: a value the
selected row lacks stays as it is. The source library is, in this order:

1. ``--library-override`` (CSV ``document_id,library``): an approved correction; it also
   replaces a different stored ``library``;
2. the stored ``library`` property, unless its value is listed by ``--distrust-stored``
   (e.g. ``mzk``, which older code used as a default);
3. ``--library-map`` (same CSV format): a verified library for documents storing none; a
   stored library that differs from it makes the document unresolved;
4. with ``--infer-unique-library`` only: the library of the mirror's only row for the id.
   Such documents are ``candidate``, never applied; ``--candidates FILE`` writes them as a
   CSV to review and pass back as ``--library-map``.

Anything else (no library, a conflict, several mirror libraries without a verified one, no
row for the library) is ``unresolved`` with the libraries the mirror has for the id.

Report (read-only, the default)::

    KRAMERIUS_METADATA_DSN=postgresql+psycopg://user@host:5888/librarymetadata_all \\
    python -m semant_demo.maintenance.metadata_sync --report metadata.json \\
        [--library-map verified.csv] [--library-override corrections.csv] \\
        [--distrust-stored mzk] [--infer-unique-library --candidates candidates.csv] \\
        [--document-ids ids.txt | --after UUID] [--limit N] [--overwrite] [--update-access]

Declare ``Documents.library`` where it is missing (an additive, reviewed schema change)::

    python -m semant_demo.maintenance.metadata_sync --add-library-property --confirm-endpoint localhost:8080

Apply the changes listed in a reviewed report (back up the data first)::

    python -m semant_demo.maintenance.metadata_sync --apply metadata.json --confirm-endpoint localhost:8080 \\
        [--accept-incomplete]

Only properties the documents collection declares are written, converted to their declared
type; a value that does not fit (e.g. ``seriesNumber`` "IV" for an ``int`` property) is
reported and skipped. Empty properties are filled; a differing stored value is replaced only
with ``--overwrite``, and ``public`` only with ``--update-access`` (never for a candidate);
both are otherwise listed as ``held``. Values are never cleared: stored values the source
row lacks are listed as ``stale``. ``in_library`` is reported, not used: the mirror sets it on
rows added or updated since it was introduced, so ``false`` may only mean "not reprocessed".

Applying refuses to run unless ``--confirm-endpoint`` and the report's endpoint both equal
the configured Weaviate endpoint, the collection declares ``library`` and the declared
property types still match the report, and, unless ``--accept-incomplete``, the report has
no unresolved or candidate documents. Per document it reads the stored values and writes
only if the stored library and every changed property still equal the report's old values;
documents changed since the report are listed and not written. This check and the write are
not atomic: run it in a window without other metadata writers. Written values are read back;
applying again (e.g. after a failure) skips finished documents. The exit code is 1 when
nothing was eligible or any eligible document was not updated and verified.

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
    add_text_property, document_property_types, read_document_page, read_documents, update_document)
from semant_demo.maintenance.kramerius_mapping import FIELDS, SourceRecord, map_record

PAGE_SIZE = 100
DSN_VARIABLE = "KRAMERIUS_METADATA_DSN"
LIBRARY = "library"

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


def resolve_library(stored: Any, libraries: list[str], *, mapped: str | None = None, override: str | None = None,
                    distrusted: frozenset[str] = frozenset(), infer_unique: bool = False) -> tuple[str, str]:
    """(library, where it came from) of a document whose mirror rows have ``libraries``;
    raises ``Unresolved``."""
    if override:
        return override, "override"
    stored = stored.strip() if isinstance(stored, str) else None
    if stored in distrusted:
        stored = None
    if stored and mapped and stored != mapped:
        raise Unresolved("library_conflict", f"stored library {stored!r} differs from mapped library {mapped!r}")
    if stored:
        return stored, "stored"
    if mapped:
        return mapped, "library_map"
    if len(libraries) > 1:
        raise Unresolved("multiple_libraries", f"the mirror has rows for {', '.join(libraries)}; "
                                               "needs a verified library map")
    if len(libraries) == 1 and infer_unique:
        return libraries[0], "inferred_unique"
    if libraries:
        raise Unresolved("no_library", f"no verified library; the mirror's only row is from {libraries[0]} "
                                       "(--infer-unique-library proposes it)")
    raise Unresolved("no_library", "no verified library and no mirror row")


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
                  targets: dict[str, tuple[str, str]], *, mapped_library: str | None = None,
                  override_library: str | None = None, distrusted: frozenset[str] = frozenset(),
                  infer_unique: bool = False, overwrite: bool = False, update_access: bool = False) -> dict[str, Any]:
    """The report entry of one document: its source and the property changes."""
    libraries = sorted({r.library for r in records})
    entry: dict[str, Any] = {"id": str(document_id), "stored_library": jsonable(stored.get(LIBRARY)),
                             "mirror_libraries": libraries}
    try:
        library, origin = resolve_library(stored.get(LIBRARY), libraries, mapped=mapped_library,
                                          override=override_library, distrusted=distrusted,
                                          infer_unique=infer_unique)
        record = select_record(records, library)
    except Unresolved as e:
        return {**entry, "status": "unresolved", "kind": e.kind, "reason": str(e)}
    entry.update(library=library, library_from=origin, in_library=record.in_library)
    inferred = origin == "inferred_unique"

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
        if field == "public" and inferred:
            held[prop] = {"old": old, "new": new, "reason": "access flag; never changed for an inferred library"}
        elif field == "public" and not update_access:
            held[prop] = {"old": old, "new": new, "reason": "access flag; needs --update-access"}
        elif field not in ("public", LIBRARY) and not _empty(old) and not overwrite:
            held[prop] = {"old": old, "new": new, "reason": "differs from the stored value; needs --overwrite"}
        else:
            changes[prop] = {"old": old, "new": new}
    entry["status"] = "candidate" if inferred else "update" if changes else "unchanged"
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
                       library_override: dict[UUID, str] | None = None, distrusted: frozenset[str] = frozenset(),
                       infer_unique: bool = False, document_ids: list[UUID] | None = None,
                       after: UUID | None = None, limit: int | None = None,
                       overwrite: bool = False, update_access: bool = False) -> dict:
    """The report of the documents in scope. Reads only. Raises ``LookupError`` if the
    documents collection does not exist."""
    types = await document_property_types(client, names)
    if types is None:
        raise LookupError(f"Collection {names.document_collection_name} does not exist")
    targets, undeclared = target_properties(types)
    library_map = library_map or {}
    library_override = library_override or {}

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
            entries.append(plan_document(
                document_id, stored, records.get(document_id, []), targets,
                mapped_library=library_map.get(document_id), override_library=library_override.get(document_id),
                distrusted=distrusted, infer_unique=infer_unique, overwrite=overwrite, update_access=update_access))

    reached_limit = document_ids is None and limit is not None and len(entries) == limit
    plain = {"id", "status", "stored_library", "mirror_libraries", "library", "library_from", "in_library"}
    return {
        "endpoint": endpoint,
        "collection": names.document_collection_name,
        "source": source_name,
        "created": datetime.now(timezone.utc).isoformat(),
        "options": {"overwrite": overwrite, "update_access": update_access, "after": after and str(after),
                    "limit": limit, "document_ids": document_ids is not None, "library_map": len(library_map),
                    "library_override": len(library_override), "distrust_stored": sorted(distrusted),
                    "infer_unique_library": infer_unique},
        "target_schema": {prop: data_type for prop, data_type in targets.values()},
        "undeclared_fields": undeclared,
        "counts": _counts(entries),
        "next_after": str(last) if reached_limit and last else None,
        "documents": [e for e in entries if e["status"] != "unchanged" or set(e) - plain],
    }


def _counts(entries: list[dict[str, Any]]) -> dict[str, Any]:
    status = Counter(e["status"] for e in entries)
    mirror = Counter(min(len(e["mirror_libraries"]), 2) for e in entries if "mirror_libraries" in e)

    def per_property(key: str) -> dict[str, int]:
        return dict(sorted(Counter(p for e in entries for p in e.get(key, {})).items()))
    return {
        "in_scope": len(entries),
        "eligible": status["update"],
        "unchanged": status["unchanged"],
        "candidate": status["candidate"],
        "unresolved": dict(sorted(Counter(e["kind"] for e in entries if e["status"] == "unresolved").items())),
        "mirror_libraries": {"none": mirror[0], "one": mirror[1], "several": mirror[2]},
        "library_from": dict(sorted(Counter(e["library_from"] for e in entries if "library_from" in e).items())),
        "with_held_changes": sum(1 for e in entries if "held" in e),
        "with_skipped_values": sum(1 for e in entries if "skipped" in e),
        "with_stale_values": sum(1 for e in entries if "stale" in e),
        "changed_properties": per_property("changes"),
        "held_properties": per_property("held"),
    }


def incomplete(report: dict) -> int:
    """Documents in the report that applying leaves without verified source metadata."""
    counts = report["counts"]
    return sum(counts["unresolved"].values()) + counts["candidate"]


def _to_weaviate(value: Any, data_type: str) -> Any:
    return datetime.fromisoformat(value) if data_type == "date" and isinstance(value, str) else value


def check_applicable(types: dict[str, str] | None, report: dict, *, accept_incomplete: bool) -> None:
    """Raises ``LookupError`` if the report must not be applied to a store with these types."""
    expected = report["target_schema"]
    if types is None or any(types.get(prop) != data_type for prop, data_type in expected.items()):
        raise LookupError("The documents collection schema differs from the report's; create a new report")
    if expected.get(LIBRARY) != "text":
        raise LookupError("The report's collection declares no text property 'library', so the source library "
                          "cannot be stored; declare it (--add-library-property) and create a new report")
    if incomplete(report) and not accept_incomplete:
        raise LookupError(f"{incomplete(report)} documents in the report are unresolved or candidates; resolve "
                          "them or pass --accept-incomplete")


async def apply_report(client: WeaviateAsyncClient, names: schemas.CollectionNames, report: dict,
                       *, accept_incomplete: bool = False) -> dict:
    """Write the reviewed changes and read them back. Raises ``LookupError`` if the report
    must not be applied (see ``check_applicable``)."""
    types = await document_property_types(client, names)
    check_applicable(types, report, accept_incomplete=accept_incomplete)

    entries = [e for e in report["documents"] if e["status"] == "update"]
    applied = verified = already_applied = 0
    not_applied: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []
    for start in range(0, len(entries), PAGE_SIZE):
        page = entries[start:start + PAGE_SIZE]
        current = await read_documents(client, names, [UUID(e["id"]) for e in page])
        written: dict[UUID, dict[str, Any]] = {}
        for entry in page:
            document_id = UUID(entry["id"])
            stored = current.get(document_id)
            if stored is None:
                not_applied.append({"id": entry["id"], "reason": "the document no longer exists"})
                continue
            pending, conflict = {}, None
            allowed_libraries = [entry["stored_library"]]
            if LIBRARY in entry["changes"]:
                allowed_libraries.append(entry["changes"][LIBRARY]["new"])
            if jsonable(stored.get(LIBRARY)) not in allowed_libraries:
                conflict = "library changed since the report"
            for prop, change in entry["changes"].items():
                if conflict:
                    break
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
                    await update_document(client, names, document_id, pending)
                except Exception as e:  # the write may or may not have happened; applying again re-checks
                    failed.append({"id": entry["id"], "error": f"{type(e).__name__}: {e}"})
                else:
                    applied += 1
                    written[document_id] = {p: entry["changes"][p]["new"] for p in pending}
        read_back = await read_documents(client, names, list(written))
        for document_id, expected in written.items():
            stored = read_back.get(document_id, {})
            differing = sorted(p for p, value in expected.items() if jsonable(stored.get(p)) != value)
            if differing:
                failed.append({"id": str(document_id), "error": f"read back differs: {', '.join(differing)}"})
            else:
                verified += 1
    counts = report["counts"]
    return {"in_scope": counts["in_scope"], "unresolved": sum(counts["unresolved"].values()),
            "candidate": counts["candidate"], "with_held_changes": counts["with_held_changes"],
            "with_skipped_values": counts["with_skipped_values"], "eligible": len(entries),
            "applied": applied, "verified": verified, "already_applied": already_applied,
            "not_applied": not_applied, "failed": failed}


def apply_exit_code(result: dict) -> int:
    """0 only if something was eligible and every eligible document is verified or was already applied."""
    complete = result["verified"] + result["already_applied"] == result["eligible"]
    return 0 if result["eligible"] and complete and not result["failed"] and not result["not_applied"] else 1


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


def write_candidates(path: Path, report: dict) -> int:
    """Write the report's candidate libraries as a library map to review; the number written."""
    candidates = [e for e in report["documents"] if e["status"] == "candidate"]
    with path.open("w", encoding="utf-8", newline="") as file:
        file.write("# Inferred from the mirror's only row for each id; review before using as --library-map\n")
        csv.writer(file).writerows((e["id"], e["library"]) for e in candidates)
    return len(candidates)


def read_document_ids(path: Path) -> list[UUID]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return list(dict.fromkeys(UUID(line.strip()) for line in lines if line.strip() and not line.startswith("#")))


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--report", type=Path, help="write the report (JSON) to this file")
    p.add_argument("--library-map", type=Path, help="CSV of document_id,library: verified libraries")
    p.add_argument("--library-override", type=Path, help="CSV of document_id,library: approved corrections")
    p.add_argument("--distrust-stored", action="append", default=[], metavar="LIBRARY",
                   help="treat this stored library value as unverified (repeatable)")
    p.add_argument("--infer-unique-library", action="store_true",
                   help="propose the library of the mirror's only row as a candidate")
    p.add_argument("--candidates", type=Path, help="write candidate libraries (CSV) to this file")
    scope = p.add_mutually_exclusive_group()
    scope.add_argument("--document-ids", type=Path, help="only these documents (one UUID per line)")
    scope.add_argument("--after", type=UUID, help="start after this document id (a report's next_after)")
    p.add_argument("--limit", type=int, help="at most this many documents")
    p.add_argument("--overwrite", action="store_true", help="replace differing non-empty stored values")
    p.add_argument("--update-access", action="store_true", help="also change the public flag")
    p.add_argument("--apply", type=Path, metavar="REPORT", help="write the changes listed in this reviewed report")
    p.add_argument("--accept-incomplete", action="store_true",
                   help="with --apply: apply although the report has unresolved or candidate documents")
    p.add_argument("--add-library-property", action="store_true",
                   help="declare the text property 'library' on the documents collection")
    p.add_argument("--confirm-endpoint", metavar="HOST:PORT",
                   help="with --apply or --add-library-property: the configured Weaviate endpoint")
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
    if args.apply or args.add_library_property:
        if args.apply and args.add_library_property:
            print("Use --apply and --add-library-property separately", file=sys.stderr)
            return 2
        if args.confirm_endpoint != endpoint:
            print(f"Refusing to write: configured endpoint {endpoint}, --confirm-endpoint {args.confirm_endpoint}",
                  file=sys.stderr)
            return 2
    if args.apply:
        report = json.loads(args.apply.read_text(encoding="utf-8"))
        if report.get("endpoint") != endpoint or report.get("collection") != names.document_collection_name:
            print(f"Refusing to write: configured {endpoint} {names.document_collection_name}, report "
                  f"{report.get('endpoint')} {report.get('collection')}", file=sys.stderr)
            return 2
    elif not args.add_library_property:
        dsn = os.environ.get(DSN_VARIABLE)
        if not dsn:
            print(f"Set {DSN_VARIABLE} to the metadata mirror's SQLAlchemy URL", file=sys.stderr)
            return 2
        try:
            library_map = read_library_map(args.library_map) if args.library_map else None
            library_override = read_library_map(args.library_override) if args.library_override else None
            document_ids = read_document_ids(args.document_ids) if args.document_ids else None
        except ValueError as e:
            print(e, file=sys.stderr)
            return 2
        engine = create_engine(dsn)

    print(f"Weaviate endpoint: {endpoint}, collection {names.document_collection_name}", file=sys.stderr)
    client = await connect_weaviate(config)
    try:
        if args.add_library_property:
            types = await document_property_types(client, names)
            if types is None or types.get(LIBRARY, "text") != "text":
                print(f"Cannot declare {LIBRARY}: collection missing or property of type {types and types[LIBRARY]}",
                      file=sys.stderr)
                return 2
            if LIBRARY in types:
                print(f"{names.document_collection_name}.{LIBRARY} is already declared")
                return 0
            await add_text_property(client, names, LIBRARY)
            print(f"Declared {names.document_collection_name}.{LIBRARY} (text)")
            return 0
        if report is not None:
            try:
                result = await apply_report(client, names, report, accept_incomplete=args.accept_incomplete)
            except LookupError as e:
                print(e, file=sys.stderr)
                return 2
            print(json.dumps(result, indent=2))
            return apply_exit_code(result)
        with engine.connect() as source:
            try:
                new_report = await build_report(
                    client, names, source, endpoint=endpoint,
                    source_name=make_url(dsn).render_as_string(hide_password=True),
                    library_map=library_map, library_override=library_override,
                    distrusted=frozenset(args.distrust_stored), infer_unique=args.infer_unique_library,
                    document_ids=document_ids, after=args.after, limit=args.limit,
                    overwrite=args.overwrite, update_access=args.update_access)
            except LookupError as e:
                print(e, file=sys.stderr)
                return 2
        if args.report:
            args.report.write_text(json.dumps(new_report, indent=2, ensure_ascii=False), encoding="utf-8")
        if args.candidates:
            write_candidates(args.candidates, new_report)
        print(json.dumps({key: new_report[key] for key in ("endpoint", "collection", "source", "undeclared_fields",
                                                           "counts", "next_after")}, indent=2))
        return 0
    finally:
        await client.close()
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
