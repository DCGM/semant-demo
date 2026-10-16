"""Report, and on explicit request apply or sync, document metadata from the Kramerius mirror (#257).

Each Weaviate document takes its metadata from exactly one mirror row: the row of its own
source library, ``(id, library)``. Nothing is taken from another library's row: a value the
selected row lacks stays as it is. The source library is, in this order:

1. ``--library-override`` (CSV ``document_id,library``): an approved correction; it also
   replaces a different stored ``library``;
2. ``--library-map`` (same CSV format): a verified library; a stored library that differs
   from it makes the document unresolved (``library_conflict``);
3. with ``--infer-library-from-pages``: the library in which the mirror rows of the
   document's chunk start pages (``Chunks.start_page_id``) lead, through
   ``(parent_id, parent_library)``, to the document itself (``page_ancestry``; confidence
   ``high`` with 2+ distinct pages, ``low`` with one). It replaces a stored library the pages
   contradict. When the pages reach the document in several libraries (a library mirroring
   another's page UUIDs), a stored library among them is kept, else the choice among them
   (below, ``page_metadata`` or ``page_priority``), else the document is unresolved
   (``page_evidence_ambiguous``);
4. the stored ``library`` property, unless its value is listed by ``--distrust-stored``
   (e.g. ``mzk``, which older code used as a default);
5. with ``--infer-library-from-mirror``, for documents without page evidence (no chunks or
   no page reaching the document): the mirror's only library for the id (``mirror_unique``),
   else the choice among the mirror's libraries (``mirror_metadata`` or ``mirror_priority``).

The choice among several libraries: with ``--prefer-library-with-metadata``, the only one
whose row has bibliographic metadata (MODS, ``metadata_json``; ``*_metadata``), else, among
those that have it (or all if none has), the first in ``--library-priority`` (``*_priority``).
The mirror downloaded MODS only for part of the documents, so a library without it gives no
author or publisher.

Anything else (no library, a conflict, several mirror libraries without a choice, no row
for the library) is ``unresolved`` with the libraries the mirror has for the id. Each entry
records ``library_from`` and the page evidence; ``--inferred FILE`` writes the inferred
libraries (3 and 5) with their evidence as a CSV to sample, correct and pass back as
``--library-override``.

Report (read-only, the default)::

    KRAMERIUS_METADATA_DSN=postgresql+psycopg://user@host:5888/librarymetadata_all \\
    python -m semant_demo.maintenance.metadata_sync --report metadata.json \\
        [--library-map verified.csv] [--library-override corrections.csv] [--distrust-stored mzk] \\
        [--infer-library-from-pages] [--library-priority mzk,nkp] [--infer-library-from-mirror] \\
        [--prefer-library-with-metadata] \\
        [--inferred inferred.csv] [--document-ids ids.txt | --after UUID] [--limit N] [--overwrite]

Declare ``Documents.library`` where it is missing (an additive, reviewed schema change)::

    python -m semant_demo.maintenance.metadata_sync --add-library-property --confirm-endpoint localhost:8080

Or plan and write in a single pass, page by page, without a report (back up the data first)::

    python -m semant_demo.maintenance.metadata_sync --sync --confirm-endpoint localhost:8080 \\
        --checkpoint sync.json [--manifest sync.jsonl] [the report's library options] [--overwrite] \\
        [--after UUID] [--limit N]

Each page of ``Documents`` is planned from the values just read, its changes are written and the
written documents read back; nothing is reread afterwards. The checkpoint (JSON) is saved after
each page with the last finished id, running counts (including ``public`` transitions) and the
ids whose write failed or did not read back; running the same command again resumes it,
planning those ids again first. The manifest lists unresolved and failed ids with reasons.
The exit code is 1 while failed ids remain. Resuming requires the same endpoint, collection,
declared types and options; use a new checkpoint per environment.

Apply the changes listed in a reviewed report (back up the data first)::

    python -m semant_demo.maintenance.metadata_sync --apply metadata.json --confirm-endpoint localhost:8080 \\
        [--accept-incomplete]

Only properties the documents collection declares are written, converted to their declared
type; a value that does not fit (e.g. ``seriesNumber`` "IV" for an ``int`` property) is
reported and skipped. ``title`` joins the own titles of the row and its ancestors in the same
library (periodical, volume, issue; near-duplicates left out). ``library`` and ``public``
always follow the selected row, so access matches the source library's record. Other empty
properties are filled; a differing stored value is replaced only with ``--overwrite``, else
listed as ``held``. Values are never cleared: stored values the source row lacks are listed
as ``stale``. ``in_library`` is reported, not used: the mirror sets it on rows added or
updated since it was introduced, so ``false`` may only mean "not reprocessed".

Applying refuses to run unless ``--confirm-endpoint`` and the report's endpoint both equal
the configured Weaviate endpoint, the collection declares ``library`` and the declared
property types still match the report, and, unless ``--accept-incomplete``, the report has
no unresolved documents. Per document it reads the stored values and writes
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
import hashlib
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

from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.adapters.sql.kramerius_metadata import PageChain, read_ancestors, read_meta_records, read_page_chains
from semant_demo.adapters.weaviate.document_metadata import (
    add_text_property, document_property_types, read_document_page, read_documents, read_start_pages,
    update_document)
from semant_demo.maintenance.kramerius_mapping import FIELDS, SourceRecord, map_record

PAGE_SIZE = 100
DSN_VARIABLE = "KRAMERIUS_METADATA_DSN"
LIBRARY = "library"
INFERRED = ("page_ancestry", "page_metadata", "page_priority", "mirror_unique", "mirror_metadata",
            "mirror_priority")
"""Library origins that are inferred rather than stored or given (``--inferred`` lists them)."""
MAX_CHUNKS_PER_DOCUMENT = 1000
"""Chunks read per document for page evidence."""
CONCURRENT_CHUNK_READS = 16
PAGE_SAMPLE = 3

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


def classify_pages(start_pages: list[Any], truncated: bool, chains: list[PageChain]) -> dict[str, Any]:
    """The page evidence of one document from its chunks' ``start_page_id`` values and the
    mirror chains of those pages (``read_page_chains``).

    ``confidence``: ``no_chunks``; ``none`` (no page chain reaches the document); ``high``
    (2+ distinct pages reach it, all in one library); ``low`` (one such page); ``ambiguous``
    (chains reach it in several libraries, e.g. a page UUID mirrored by two libraries).
    """
    valid: set[UUID] = set()
    invalid = 0
    for value in start_pages:
        try:
            valid.add(UUID(str(value)))
        except ValueError:
            invalid += 1
    verified: dict[str, set[UUID]] = {}
    other = Counter()
    for chain in chains:
        if chain.status == "verified":
            verified.setdefault(chain.library, set()).add(chain.page_id)
        else:
            other[chain.status] += 1
    counts = {library: len(pages) for library, pages in sorted(verified.items())}
    if not start_pages:
        confidence = "no_chunks"
    elif not counts:
        confidence = "none"
    elif len(counts) > 1:
        confidence = "ambiguous"
    else:
        confidence = "high" if next(iter(counts.values())) >= 2 else "low"
    sample = sorted(chains, key=lambda c: (c.status != "verified", c.library, str(c.page_id)))[:PAGE_SAMPLE]
    return {
        "method": "page_ancestry", "confidence": confidence, "chunks": len(start_pages), "truncated": truncated,
        "start_pages": len(valid), "invalid_page_ids": invalid,
        "pages_not_in_mirror": len(valid - {c.page_id for c in chains}),
        "verified_pages": counts, "unverified_chains": dict(sorted(other.items())),
        "sample": [{"page": str(c.page_id), "library": c.library, "status": c.status,
                    "path": [str(i) for i in c.path]} for c in sample],
    }


def _first_by_priority(libraries: list[str], priority: tuple[str, ...]) -> str | None:
    return next((library for library in priority if library in libraries), None)


def _choose(libraries: list[str], priority: tuple[str, ...],
            with_metadata: frozenset[str] | None) -> tuple[str, str] | None:
    """(library, "metadata" or "priority") chosen among several, or None: the only one with
    metadata (if ``with_metadata`` is given), else the first by priority among those with it,
    or among all if none has it."""
    if with_metadata is not None:
        having = [library for library in libraries if library in with_metadata]
        if len(having) == 1:
            return having[0], "metadata"
        libraries = having or libraries
    chosen = _first_by_priority(libraries, priority)
    return (chosen, "priority") if chosen else None


def resolve_library(stored: Any, libraries: list[str], *, mapped: str | None = None, override: str | None = None,
                    distrusted: frozenset[str] = frozenset(), pages: dict[str, Any] | None = None,
                    priority: tuple[str, ...] = (), infer_from_mirror: bool = False,
                    with_metadata: frozenset[str] | None = None) -> tuple[str, str]:
    """(library, where it came from) of a document whose mirror rows have ``libraries`` and
    whose page evidence (``classify_pages``, if requested) is ``pages``; raises ``Unresolved``.
    ``with_metadata``, if given, are the libraries whose rows have metadata, preferred when
    choosing among several."""
    page_libraries = sorted(pages["verified_pages"]) if pages else []
    if override:
        return override, "override"
    stored = stored.strip() if isinstance(stored, str) else None
    if stored in distrusted:
        stored = None
    if stored and mapped and stored != mapped:
        raise Unresolved("library_conflict", f"stored library {stored!r} differs from mapped library {mapped!r}")
    if mapped:
        return mapped, "stored" if stored == mapped else "library_map"
    if len(page_libraries) == 1:
        return page_libraries[0], "page_ancestry"
    if page_libraries:
        if stored in page_libraries:
            return stored, "stored"
        if chosen := _choose(page_libraries, priority, with_metadata):
            return chosen[0], f"page_{chosen[1]}"
        raise Unresolved("page_evidence_ambiguous",
                         f"the start pages reach the document in {', '.join(page_libraries)}"
                         + (f", stored library {stored!r}" if stored else "")
                         + "; none of them is in --library-priority")
    if stored:
        return stored, "stored"
    if infer_from_mirror and len(libraries) == 1:
        return libraries[0], "mirror_unique"
    if infer_from_mirror and (chosen := _choose(libraries, priority, with_metadata)):
        return chosen[0], f"mirror_{chosen[1]}"
    if len(libraries) > 1:
        raise Unresolved("multiple_libraries", f"the mirror has rows for {', '.join(libraries)}"
                         + ("; none of them is in --library-priority" if infer_from_mirror
                            else "; --infer-library-from-mirror with --library-priority chooses one"))
    if libraries:
        raise Unresolved("no_library", f"no library; the mirror's only row is from {libraries[0]} "
                                       "(--infer-library-from-mirror uses it)")
    raise Unresolved("no_library", "no library and no mirror row")


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
                  pages: dict[str, Any] | None = None, priority: tuple[str, ...] = (),
                  infer_from_mirror: bool = False, prefer_metadata: bool = False,
                  ancestors: dict[tuple[str, str], list[SourceRecord]] | None = None,
                  overwrite: bool = False) -> dict[str, Any]:
    """The report entry of one document: its source and the property changes. ``ancestors``
    (``read_ancestors``) of the selected row compose its title. ``prefer_metadata`` prefers,
    among several libraries, those whose row has ``metadata_json``."""
    libraries = sorted({r.library for r in records})
    with_metadata = frozenset(r.library for r in records if r.metadata_json) if prefer_metadata else None
    entry: dict[str, Any] = {"id": str(document_id), "stored_library": jsonable(stored.get(LIBRARY)),
                             "mirror_libraries": libraries}
    if pages is not None:
        entry["page_evidence"] = pages
    try:
        library, origin = resolve_library(stored.get(LIBRARY), libraries, mapped=mapped_library,
                                          override=override_library, distrusted=distrusted, pages=pages,
                                          priority=priority, infer_from_mirror=infer_from_mirror,
                                          with_metadata=with_metadata)
        record = select_record(records, library)
    except Unresolved as e:
        return {**entry, "status": "unresolved", "kind": e.kind, "reason": str(e)}
    entry.update(library=library, library_from=origin, in_library=record.in_library,
                 has_metadata=bool(record.metadata_json))
    if pages and pages["verified_pages"] and library not in pages["verified_pages"]:
        entry["page_evidence_disagrees"] = True  # an explicit map or override wins; shown for review

    mapped = map_record(record, (ancestors or {}).get((record.id, record.library), ()))
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
        if field not in ("public", LIBRARY) and not _empty(old) and not overwrite:
            held[prop] = {"old": old, "new": new, "reason": "differs from the stored value; needs --overwrite"}
        else:
            changes[prop] = {"old": old, "new": new}
    entry["status"] = "update" if changes else "unchanged"
    for key, value in (("changes", changes), ("held", held), ("skipped", skipped), ("stale", stale)):
        if value:
            entry[key] = value
    return entry


async def _pages(client: WeaviateAsyncClient, names: CollectionNames, document_ids: list[UUID] | None,
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


async def build_report(client: WeaviateAsyncClient, names: CollectionNames, source: Connection, *,
                       endpoint: str, source_name: str, library_map: dict[UUID, str] | None = None,
                       library_override: dict[UUID, str] | None = None, distrusted: frozenset[str] = frozenset(),
                       infer_from_pages: bool = False, priority: tuple[str, ...] = (),
                       infer_from_mirror: bool = False, prefer_metadata: bool = False,
                       document_ids: list[UUID] | None = None,
                       after: UUID | None = None, limit: int | None = None, overwrite: bool = False) -> dict:
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
    cache: dict[tuple[str, str], SourceRecord | None] = {}
    async for page in _pages(client, names, document_ids, after, limit):
        entries += await _plan_page(
            client, names, source, page, targets, cache, library_map=library_map,
            library_override=library_override, distrusted=distrusted, infer_from_pages=infer_from_pages,
            priority=priority, infer_from_mirror=infer_from_mirror, prefer_metadata=prefer_metadata,
            overwrite=overwrite)
        last = page[-1][0]

    reached_limit = document_ids is None and limit is not None and len(entries) == limit
    plain = {"id", "status", "stored_library", "mirror_libraries", "library", "library_from", "in_library",
             "has_metadata"}
    return {
        "endpoint": endpoint,
        "collection": names.document_collection_name,
        "source": source_name,
        "created": datetime.now(timezone.utc).isoformat(),
        "options": {"overwrite": overwrite, "after": after and str(after),
                    "limit": limit, "document_ids": document_ids is not None, "library_map": len(library_map),
                    "library_override": len(library_override), "distrust_stored": sorted(distrusted),
                    "infer_library_from_pages": infer_from_pages, "library_priority": list(priority),
                    "infer_library_from_mirror": infer_from_mirror,
                    "prefer_library_with_metadata": prefer_metadata},
        "target_schema": {prop: data_type for prop, data_type in targets.values()},
        "undeclared_fields": undeclared,
        "counts": _counts(entries),
        "next_after": str(last) if reached_limit and last else None,
        "documents": [e for e in entries
                      if e["status"] != "unchanged" or set(e) - plain or e.get("library_from") in INFERRED],
    }


async def _plan_page(client: WeaviateAsyncClient, names: CollectionNames, source: Connection,
                     page: list[tuple[UUID, dict[str, Any] | None]], targets: dict[str, tuple[str, str]],
                     cache: dict[tuple[str, str], SourceRecord | None], *, library_map: dict[UUID, str],
                     library_override: dict[UUID, str], distrusted: frozenset[str], infer_from_pages: bool,
                     priority: tuple[str, ...], infer_from_mirror: bool, prefer_metadata: bool,
                     overwrite: bool) -> list[dict[str, Any]]:
    """The report entries (``plan_document``) of one page of (id, stored properties or None)."""
    present = [i for i, stored in page if stored is not None]
    records = read_meta_records(source, present)
    ancestors = read_ancestors(source, [r for rows in records.values() for r in rows], cache)
    if len(cache) > 100_000:  # parents (periodicals, volumes) recur on neighbouring pages
        cache.clear()
    evidence = await _page_evidence(client, names, source, present) if infer_from_pages else {}
    entries = []
    for document_id, stored in page:
        if stored is None:
            entries.append({"id": str(document_id), "status": "unresolved", "kind": "not_in_target",
                            "reason": "no such document in the target collection"})
            continue
        entries.append(plan_document(
            document_id, stored, records.get(document_id, []), targets,
            mapped_library=library_map.get(document_id), override_library=library_override.get(document_id),
            distrusted=distrusted, pages=evidence.get(document_id), priority=priority,
            infer_from_mirror=infer_from_mirror, prefer_metadata=prefer_metadata, ancestors=ancestors,
            overwrite=overwrite))
    return entries


async def _page_evidence(client: WeaviateAsyncClient, names: CollectionNames, source: Connection,
                         document_ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    """``classify_pages`` of each document, from its chunks' start pages and the mirror."""
    limit = asyncio.Semaphore(CONCURRENT_CHUNK_READS)

    async def read(document_id: UUID) -> tuple[list[Any], bool]:
        async with limit:
            return await read_start_pages(client, names, document_id, MAX_CHUNKS_PER_DOCUMENT)
    start_pages = dict(zip(document_ids, await asyncio.gather(*(read(i) for i in document_ids))))
    valid: dict[UUID, set[UUID]] = {}
    for document_id, (values, _) in start_pages.items():
        valid[document_id] = set()
        for value in values:
            try:
                valid[document_id].add(UUID(str(value)))
            except ValueError:
                pass
    chains = read_page_chains(source, valid)
    return {i: classify_pages(values, truncated, chains[i]) for i, (values, truncated) in start_pages.items()}


def _counts(entries: list[dict[str, Any]]) -> dict[str, Any]:
    status = Counter(e["status"] for e in entries)
    mirror = Counter(min(len(e["mirror_libraries"]), 2) for e in entries if "mirror_libraries" in e)

    def per_property(key: str) -> dict[str, int]:
        return dict(sorted(Counter(p for e in entries for p in e.get(key, {})).items()))
    return {
        "in_scope": len(entries),
        "eligible": status["update"],
        "unchanged": status["unchanged"],
        "unresolved": dict(sorted(Counter(e["kind"] for e in entries if e["status"] == "unresolved").items())),
        "mirror_libraries": {"none": mirror[0], "one": mirror[1], "several": mirror[2]},
        "library_from": dict(sorted(Counter(e["library_from"] for e in entries if "library_from" in e).items())),
        "page_evidence": dict(sorted(Counter(e["page_evidence"]["confidence"] for e in entries
                                             if "page_evidence" in e).items())),
        "page_evidence_disagrees": sum(1 for e in entries if e.get("page_evidence_disagrees")),
        "without_source_metadata": sum(1 for e in entries if e.get("has_metadata") is False),
        "library_replaced": sum(1 for e in entries if not _empty(e.get("changes", {}).get(LIBRARY, {}).get("old"))),
        "with_held_changes": sum(1 for e in entries if "held" in e),
        "with_skipped_values": sum(1 for e in entries if "skipped" in e),
        "with_stale_values": sum(1 for e in entries if "stale" in e),
        "changed_properties": per_property("changes"),
        "held_properties": per_property("held"),
    }


def incomplete(report: dict) -> int:
    """Documents in the report that applying leaves without source metadata."""
    return sum(report["counts"]["unresolved"].values())


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
        raise LookupError(f"{incomplete(report)} documents in the report are unresolved; resolve them or pass "
                          "--accept-incomplete")


async def apply_report(client: WeaviateAsyncClient, names: CollectionNames, report: dict,
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
            "with_held_changes": counts["with_held_changes"],
            "with_skipped_values": counts["with_skipped_values"], "eligible": len(entries),
            "applied": applied, "verified": verified, "already_applied": already_applied,
            "not_applied": not_applied, "failed": failed}


def apply_exit_code(result: dict) -> int:
    """0 only if something was eligible and every eligible document is verified or was already applied."""
    complete = result["verified"] + result["already_applied"] == result["eligible"]
    return 0 if result["eligible"] and complete and not result["failed"] and not result["not_applied"] else 1


SYNC_ATTEMPTS = 3
"""Tries of one batch (read, plan, write, read back) before the run stops; batches are idempotent."""
SYNC_BACKOFF = 10.0


def _fingerprint(mapping: dict[UUID, str] | None) -> str | None:
    if not mapping:
        return None
    lines = "\n".join(f"{i},{library}" for i, library in sorted(mapping.items()))
    return hashlib.sha256(lines.encode()).hexdigest()[:16]


def _sync_counts() -> dict[str, Any]:
    return {"examined": 0, "updated": 0, "unchanged": 0, "unresolved": {}, "failed": 0, "library_from": {},
            "public": {"false_to_true": 0, "true_to_false": 0, "unset_to_true": 0, "unset_to_false": 0},
            "without_source_metadata": 0, "with_held_changes": 0, "with_skipped_values": 0,
            "changed_properties": {}}


def _add(counter: dict[str, int], key: str, n: int = 1) -> None:
    counter[key] = counter.get(key, 0) + n


def _public_transition(change: dict[str, Any]) -> str:
    old = {True: "true", False: "false"}.get(change["old"], "unset")
    return f"{old}_to_{'true' if change['new'] else 'false'}"


def _write_json(path: Path, data: Any) -> None:
    """Replace the file atomically, so a crash leaves the previous checkpoint."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


async def _sync_batch(client: WeaviateAsyncClient, names: CollectionNames, source: Connection,
                      page: list[tuple[UUID, dict[str, Any] | None]], targets: dict[str, tuple[str, str]],
                      types: dict[str, str], cache: dict, plan_options: dict[str, Any]) -> dict[str, Any]:
    """Plan one page, write its changes and read the written documents back. Returns its counts,
    manifest lines and the ids not verified; changes nothing else, so a failed batch can be retried."""
    entries = await _plan_page(client, names, source, page, targets, cache, **plan_options)
    counts = _sync_counts()
    manifest: list[dict[str, Any]] = []
    failed: list[str] = []
    written: dict[UUID, dict[str, Any]] = {}
    for entry in entries:
        counts["examined"] += 1
        counts["with_held_changes"] += "held" in entry
        counts["with_skipped_values"] += "skipped" in entry
        counts["without_source_metadata"] += entry.get("has_metadata") is False
        if "library_from" in entry:
            _add(counts["library_from"], entry["library_from"])
        if entry["status"] == "unresolved":
            _add(counts["unresolved"], entry["kind"])
            manifest.append({"id": entry["id"], "status": "unresolved", "kind": entry["kind"],
                             "reason": entry["reason"], "mirror_libraries": entry.get("mirror_libraries", [])})
        elif entry["status"] == "unchanged":
            counts["unchanged"] += 1
        else:
            document_id = UUID(entry["id"])
            pending = {prop: _to_weaviate(change["new"], types[prop]) for prop, change in entry["changes"].items()}
            try:
                await update_document(client, names, document_id, pending)
            except Exception as e:  # the write may or may not have happened; a retry plans it again
                failed.append(entry["id"])
                manifest.append({"id": entry["id"], "status": "failed", "reason": f"{type(e).__name__}: {e}"})
            else:
                written[document_id] = entry
    read_back = await read_documents(client, names, list(written))
    for document_id, entry in written.items():
        stored = read_back.get(document_id, {})
        differing = sorted(p for p, c in entry["changes"].items() if jsonable(stored.get(p)) != c["new"])
        if differing:
            failed.append(entry["id"])
            manifest.append({"id": entry["id"], "status": "failed",
                             "reason": f"read back differs: {', '.join(differing)}"})
            continue
        counts["updated"] += 1
        for prop in entry["changes"]:
            _add(counts["changed_properties"], prop)
        if "public" in entry["changes"]:
            _add(counts["public"], _public_transition(entry["changes"]["public"]))
    counts["failed"] = len(failed)
    return {"counts": counts, "manifest": manifest, "failed": failed}


def _merge_counts(total: dict[str, Any], batch: dict[str, Any]) -> None:
    for key, value in batch.items():
        if isinstance(value, dict):
            for k, n in value.items():
                _add(total[key], k, n)
        else:
            total[key] += value


async def sync(client: WeaviateAsyncClient, names: CollectionNames, source: Connection, *,
               checkpoint: Path, manifest: Path, endpoint: str, source_name: str,
               library_map: dict[UUID, str] | None = None, library_override: dict[UUID, str] | None = None,
               distrusted: frozenset[str] = frozenset(), infer_from_pages: bool = False,
               priority: tuple[str, ...] = (), infer_from_mirror: bool = False, prefer_metadata: bool = False,
               overwrite: bool = False, after: UUID | None = None, limit: int | None = None,
               progress=lambda line: print(line, file=sys.stderr, flush=True)) -> dict[str, Any]:
    """Plan and apply the documents one page at a time, in a single pass (#259).

    Each page is planned from the values just read (as ``build_report``), its changes are
    written at once and the written documents read back. ``checkpoint`` (JSON) holds the last
    id of the finished pages, the running counts and the ids whose write failed or did not read
    back; it is saved after each page, and an existing checkpoint is resumed: its failed ids are
    planned again first, then the pass continues after its last id. ``manifest`` (JSON lines)
    gets one line per unresolved or failed document. ``limit`` bounds the documents of this run.
    Raises ``LookupError`` before writing if the collection does not declare ``library`` as
    text, or if the checkpoint belongs to another endpoint, collection, schema or options."""
    types = await document_property_types(client, names)
    if types is None:
        raise LookupError(f"Collection {names.document_collection_name} does not exist")
    if types.get(LIBRARY) != "text":
        raise LookupError(f"{names.document_collection_name} declares no text property '{LIBRARY}'; declare it "
                          "first (--add-library-property)")
    targets, undeclared = target_properties(types)
    target_schema = {prop: data_type for prop, data_type in targets.values()}
    library_map = library_map or {}
    library_override = library_override or {}
    plan_options = {"library_map": library_map, "library_override": library_override, "distrusted": distrusted,
                    "infer_from_pages": infer_from_pages, "priority": priority,
                    "infer_from_mirror": infer_from_mirror, "prefer_metadata": prefer_metadata,
                    "overwrite": overwrite}
    options = {"overwrite": overwrite, "distrust_stored": sorted(distrusted),
               "infer_library_from_pages": infer_from_pages, "library_priority": list(priority),
               "infer_library_from_mirror": infer_from_mirror, "prefer_library_with_metadata": prefer_metadata,
               "library_map": _fingerprint(library_map),
               "library_override": _fingerprint(library_override)}
    identity = {"endpoint": endpoint, "collection": names.document_collection_name, "options": options,
                "target_schema": target_schema}

    if checkpoint.exists():
        state = json.loads(checkpoint.read_text(encoding="utf-8"))
        differing = sorted(key for key, value in identity.items() if state.get(key) != value)
        if differing:
            raise LookupError(f"The checkpoint {checkpoint} has a different {', '.join(differing)}; use the same "
                              "options or a new checkpoint")
        if after is not None:
            raise LookupError("--after cannot be combined with resuming a checkpoint")
        progress(f"Resuming {checkpoint}: after {state['after']}, {len(state['retry'])} failed to retry")
    else:
        state = {**identity, "source": source_name, "undeclared_fields": undeclared,
                 "started": datetime.now(timezone.utc).isoformat(), "after": after and str(after), "done": False,
                 "retry": [], "counts": _sync_counts()}
        _write_json(checkpoint, state)

    cache: dict[tuple[str, str], SourceRecord | None] = {}
    started = datetime.now(timezone.utc)
    examined = 0

    async def run(read_page) -> dict[str, Any]:
        for attempt in range(1, SYNC_ATTEMPTS + 1):
            try:
                page = await read_page()
                return {"page": page, **(await _sync_batch(client, names, source, page, targets, types, cache,
                                                           plan_options) if page else {})}
            except Exception as e:
                if attempt == SYNC_ATTEMPTS:
                    raise
                progress(f"Batch after {state['after']} failed ({type(e).__name__}: {e}); retrying")
                await asyncio.sleep(SYNC_BACKOFF * attempt)

    def finish(batch: dict[str, Any], retried: list[str]) -> None:
        with manifest.open("a", encoding="utf-8") as file:
            for line in batch["manifest"]:
                file.write(json.dumps(line, ensure_ascii=False) + "\n")
            for document_id in sorted(set(retried) - set(batch["failed"])):
                file.write(json.dumps({"id": document_id, "status": "verified_on_retry"}) + "\n")
        state["retry"] = sorted((set(state["retry"]) - set(retried)) | set(batch["failed"]))
        state["updated"] = datetime.now(timezone.utc).isoformat()
        _write_json(checkpoint, state)
        counts = state["counts"]
        seconds = max((datetime.now(timezone.utc) - started).total_seconds(), 1e-3)
        progress(f"examined {counts['examined']} updated {counts['updated']} unchanged {counts['unchanged']} "
                 f"unresolved {sum(counts['unresolved'].values())} failed {counts['failed']} "
                 f"to retry {len(state['retry'])} after {state['after']} ({examined / seconds:.1f}/s this run)")

    # paginate a snapshot: finish() rewrites state["retry"] after each batch
    pending = list(state["retry"])
    for start in range(0, len(pending), PAGE_SIZE):
        retried = pending[start:start + PAGE_SIZE]
        ids = [UUID(i) for i in retried]

        async def read_retried(ids=ids):
            stored = await read_documents(client, names, ids)
            return [(i, stored.get(i)) for i in ids]
        batch = await run(read_retried)
        counts = batch["counts"]
        # counted when first examined; the outcome replaces the failure
        counts.update(examined=0, library_from={}, without_source_metadata=0, with_held_changes=0,
                      with_skipped_values=0)
        state["counts"]["failed"] -= len(retried)
        _merge_counts(state["counts"], counts)
        finish(batch, retried)

    while not state["done"] and (limit is None or examined < limit):
        size = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit - examined)
        cursor = UUID(state["after"]) if state["after"] else None
        batch = await run(lambda: read_document_page(client, names, cursor, size))
        if not batch["page"]:
            state["done"] = True
            _write_json(checkpoint, state)
            break
        examined += len(batch["page"])
        state["after"] = str(batch["page"][-1][0])
        state["done"] = len(batch["page"]) < size
        _merge_counts(state["counts"], batch["counts"])
        finish(batch, [])

    state["finished"] = datetime.now(timezone.utc).isoformat()
    _write_json(checkpoint, state)
    return {key: state[key] for key in ("endpoint", "collection", "source", "options", "undeclared_fields",
                                        "after", "done", "counts")} | {
        "to_retry": len(state["retry"]), "checkpoint": str(checkpoint), "manifest": str(manifest)}


def sync_exit_code(result: dict) -> int:
    """0 unless documents remain whose write failed or did not read back."""
    return 1 if result["to_retry"] else 0


def read_library_map(path: Path) -> dict[UUID, str]:
    """``document_id,library`` lines (further columns, e.g. inferred-library evidence, are ignored);
    blank lines and ``#`` comments are ignored. Raises
    ``ValueError`` for a malformed line or an id listed with two libraries."""
    mapping: dict[UUID, str] = {}
    with path.open(encoding="utf-8", newline="") as file:
        for number, row in enumerate(csv.reader(file), start=1):
            if not row or not row[0].strip() or row[0].lstrip().startswith("#"):
                continue
            if len(row) < 2 or not row[1].strip():
                raise ValueError(f"{path}:{number}: expected document_id,library[,evidence...]")
            document_id, library = UUID(row[0].strip()), row[1].strip()
            if mapping.get(document_id, library) != library:
                raise ValueError(f"{path}:{number}: {document_id} is listed with two libraries")
            mapping[document_id] = library
    return mapping


INFERRED_COLUMNS = ("document_id", "library", "method", "confidence", "verified_pages", "stored_library")


def write_inferred(path: Path, report: dict) -> int:
    """Write the report's inferred libraries with their evidence as a CSV (to sample, or to
    correct and pass back as ``--library-override``); the number written. The columns after
    ``document_id,library`` are evidence; ``read_library_map`` ignores them."""
    inferred = [e for e in report["documents"] if e.get("library_from") in INFERRED]
    with path.open("w", encoding="utf-8", newline="") as file:
        file.write("# " + ",".join(INFERRED_COLUMNS) + "\n")
        csv.writer(file).writerows(
            (e["id"], e["library"], e["library_from"], (e.get("page_evidence") or {}).get("confidence", ""),
             (e.get("page_evidence") or {}).get("verified_pages", {}).get(e["library"], ""), e["stored_library"] or "")
            for e in inferred)
    return len(inferred)


def read_document_ids(path: Path) -> list[UUID]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return list(dict.fromkeys(UUID(line.strip()) for line in lines if line.strip() and not line.startswith("#")))


def _libraries(text: str) -> tuple[str, ...]:
    libraries = tuple(dict.fromkeys(part.strip() for part in text.split(",") if part.strip()))
    if not libraries:
        raise argparse.ArgumentTypeError("expected a comma-separated list of libraries")
    return libraries


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--report", type=Path, help="write the report (JSON) to this file")
    p.add_argument("--library-map", type=Path, help="CSV of document_id,library: verified libraries")
    p.add_argument("--library-override", type=Path, help="CSV of document_id,library: approved corrections")
    p.add_argument("--distrust-stored", action="append", default=[], metavar="LIBRARY",
                   help="treat this stored library value as unverified (repeatable)")
    p.add_argument("--infer-library-from-pages", action="store_true",
                   help="use the library whose mirror page chains (from the chunks' start_page_id) reach the "
                        "document; it replaces a stored library they contradict")
    p.add_argument("--library-priority", type=_libraries, default=(), metavar="LIB,LIB,...",
                   help="libraries, highest priority first, choosing among several the pages reach "
                        "(and with --infer-library-from-mirror among the mirror's rows)")
    p.add_argument("--infer-library-from-mirror", action="store_true",
                   help="for documents without page evidence and without a stored library: the mirror's "
                        "only library, else the first of --library-priority it has")
    p.add_argument("--prefer-library-with-metadata", action="store_true",
                   help="choosing among several libraries (pages or mirror), prefer the one whose mirror row has "
                        "bibliographic metadata (metadata_json); --library-priority breaks remaining ties")
    p.add_argument("--inferred", type=Path, help="write the inferred libraries and their evidence (CSV) to this file")
    scope = p.add_mutually_exclusive_group()
    scope.add_argument("--document-ids", type=Path, help="only these documents (one UUID per line)")
    scope.add_argument("--after", type=UUID, help="start after this document id (a report's next_after)")
    p.add_argument("--limit", type=int, help="at most this many documents")
    p.add_argument("--overwrite", action="store_true", help="replace differing non-empty stored values")
    p.add_argument("--apply", type=Path, metavar="REPORT", help="write the changes listed in this reviewed report")
    p.add_argument("--accept-incomplete", action="store_true",
                   help="with --apply: apply although the report has unresolved documents")
    p.add_argument("--add-library-property", action="store_true",
                   help="declare the text property 'library' on the documents collection")
    p.add_argument("--sync", action="store_true",
                   help="plan and write page by page in a single pass (needs --confirm-endpoint, --checkpoint)")
    p.add_argument("--checkpoint", type=Path,
                   help="with --sync: progress file (JSON); an existing one is resumed")
    p.add_argument("--manifest", type=Path,
                   help="with --sync: unresolved and failed documents (JSON lines; default CHECKPOINT.manifest.jsonl)")
    p.add_argument("--confirm-endpoint", metavar="HOST:PORT",
                   help="with --sync, --apply or --add-library-property: the configured Weaviate endpoint")
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
    if args.apply or args.add_library_property or args.sync:
        if sum(map(bool, (args.apply, args.add_library_property, args.sync, args.report))) > 1:
            print("Use --report, --sync, --apply and --add-library-property separately", file=sys.stderr)
            return 2
        if args.sync and (not args.checkpoint or args.document_ids or args.inferred):
            print("--sync needs --checkpoint and takes neither --document-ids nor --inferred", file=sys.stderr)
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
        if args.sync:
            with engine.connect() as source:
                try:
                    result = await sync(
                        client, names, source, checkpoint=args.checkpoint,
                        manifest=args.manifest or args.checkpoint.with_name(args.checkpoint.name + ".manifest.jsonl"),
                        endpoint=endpoint, source_name=make_url(dsn).render_as_string(hide_password=True),
                        library_map=library_map, library_override=library_override,
                        distrusted=frozenset(args.distrust_stored), infer_from_pages=args.infer_library_from_pages,
                        priority=args.library_priority, infer_from_mirror=args.infer_library_from_mirror,
                        prefer_metadata=args.prefer_library_with_metadata,
                        overwrite=args.overwrite, after=args.after, limit=args.limit)
                except LookupError as e:
                    print(e, file=sys.stderr)
                    return 2
            print(json.dumps(result, indent=2))
            return sync_exit_code(result)
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
                    distrusted=frozenset(args.distrust_stored), infer_from_pages=args.infer_library_from_pages,
                    priority=args.library_priority, infer_from_mirror=args.infer_library_from_mirror,
                    prefer_metadata=args.prefer_library_with_metadata,
                    document_ids=document_ids, after=args.after, limit=args.limit, overwrite=args.overwrite)
            except LookupError as e:
                print(e, file=sys.stderr)
                return 2
        if args.report:
            args.report.write_text(json.dumps(new_report, indent=2, ensure_ascii=False), encoding="utf-8")
        if args.inferred:
            write_inferred(args.inferred, new_report)
        print(json.dumps({key: new_report[key] for key in ("endpoint", "collection", "source", "undeclared_fields",
                                                           "counts", "next_after")}, indent=2))
        return 0
    finally:
        await client.close()
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
