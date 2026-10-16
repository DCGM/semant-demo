"""Read-only access to the Kramerius metadata mirror (``meta_records``, #257).

The mirror is an external PostgreSQL database maintained by the ``librarymetadata``
project, not an application table: its table is declared on its own ``MetaData`` so the
application's ``create_tables`` never creates it, and nothing here writes. Only the
columns used for document metadata are declared.
"""
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Boolean, Column, DateTime, MetaData, String, Table, Uuid, select
from sqlalchemy.engine import Connection

from semant_demo.maintenance.kramerius_mapping import SourceRecord

META_RECORDS = Table(
    "meta_records", MetaData(),
    Column("id", Uuid, primary_key=True),
    Column("library", String(10), primary_key=True),
    Column("parent_id", Uuid),
    Column("parent_library", String(10)),
    Column("public", Boolean),
    Column("in_library", Boolean),
    Column("record_type", String(30)),
    Column("title", String),
    Column("date", String),
    Column("start_date", DateTime),
    Column("end_date", DateTime),
    Column("metadata_json", JSON),
)


def _record(row: Any) -> SourceRecord:
    return SourceRecord(
        id=str(row["id"]), library=row["library"], public=row["public"], in_library=row["in_library"],
        record_type=row["record_type"], title=row["title"], date=row["date"],
        start_date=row["start_date"], end_date=row["end_date"], metadata_json=row["metadata_json"],
        parent_id=row["parent_id"] and str(row["parent_id"]), parent_library=row["parent_library"],
    )


def read_meta_records(connection: Connection, ids: Sequence[UUID]) -> dict[UUID, list[SourceRecord]]:
    """Every mirror row of these ids, of any library, by id. Ids without rows are absent."""
    if not ids:
        return {}
    rows = connection.execute(select(META_RECORDS).where(META_RECORDS.c.id.in_(list(ids))))
    found: dict[UUID, list[SourceRecord]] = {}
    for row in rows.mappings():
        found.setdefault(row["id"], []).append(_record(row))
    return found


ANCESTOR_MAX_DEPTH = 8


def read_ancestors(connection: Connection, records: Iterable[SourceRecord],
                   cache: dict[tuple[str, str], SourceRecord | None] | None = None,
                   max_depth: int = ANCESTOR_MAX_DEPTH) -> dict[tuple[str, str], list[SourceRecord]]:
    """The ancestors of each record, ``(id, library)``, root first, following ``(parent_id,
    parent_library)`` while the parent is in the record's library; the walk stops at a parent in
    another library, a missing row, a cycle or ``max_depth``. Rows are read level by level in
    batches; ``cache`` (``(id, library)`` -> row or None) may be shared between calls."""
    cache = {} if cache is None else cache
    walks = {(r.id, r.library): [r] for r in records}

    def parent(record: SourceRecord) -> tuple[str, str] | None:
        if record.parent_id and record.parent_library == record.library:
            return record.parent_id, record.library
        return None

    active = list(walks)
    while active:
        missing = sorted({key for walk in (walks[k] for k in active)
                          if (key := parent(walk[-1])) is not None and key not in cache})
        for start in range(0, len(missing), _ID_BATCH):
            batch = missing[start:start + _ID_BATCH]
            for key in batch:
                cache[key] = None
            ids = sorted({UUID(i) for i, _ in batch})
            for row in connection.execute(select(META_RECORDS).where(META_RECORDS.c.id.in_(ids))).mappings():
                key = (str(row["id"]), row["library"])
                if key in cache:
                    cache[key] = _record(row)
        still = []
        for key in active:
            walk = walks[key]
            up = parent(walk[-1])
            node = cache.get(up) if up else None
            if node is None or len(walk) > max_depth or any((n.id, n.library) == up for n in walk):
                continue
            walk.append(node)
            still.append(key)
        active = still
    return {key: walk[:0:-1] for key, walk in walks.items()}


PAGE_CHAIN_MAX_DEPTH = 16
_ID_BATCH = 1000


@dataclass(frozen=True)
class PageChain:
    """The walk from one mirror row of a page up its ``(parent_id, parent_library)`` chain."""
    page_id: UUID
    library: str
    status: str
    """``verified`` (reached the document in ``library``), ``other_document`` (reached a root
    without it), ``cross_library`` (a parent in another library), ``broken`` (a missing
    parent row), ``cycle`` or ``too_deep``."""
    path: tuple[UUID, ...]
    """The page and the ancestors reached, in order."""


def read_page_chains(connection: Connection, pages_by_document: dict[UUID, set[UUID]],
                     max_depth: int = PAGE_CHAIN_MAX_DEPTH) -> dict[UUID, list[PageChain]]:
    """For each document, one chain per mirror row (``(page, library)``) of each of its pages,
    walked up the parent chain within that row's library until it reaches the document.

    Pages without a mirror row give no chain. Rows are read in batches, level by level, and
    shared between documents.
    """
    columns = (META_RECORDS.c.id, META_RECORDS.c.library, META_RECORDS.c.parent_id, META_RECORDS.c.parent_library)
    nodes: dict[tuple[UUID, str], Any] = {}
    libraries: dict[UUID, list[str]] = {}
    loaded: set[UUID] = set()

    def load(ids: Iterable[UUID]) -> None:
        new = sorted(set(ids) - loaded)
        for start in range(0, len(new), _ID_BATCH):
            batch = new[start:start + _ID_BATCH]
            loaded.update(batch)
            for row in connection.execute(select(*columns).where(META_RECORDS.c.id.in_(batch))).mappings():
                nodes[(row["id"], row["library"])] = row
                libraries.setdefault(row["id"], []).append(row["library"])

    load(page for pages in pages_by_document.values() for page in pages)
    chains: dict[UUID, list[PageChain]] = {document: [] for document in pages_by_document}
    active = [(document, page, library, [page], nodes[(page, library)])
              for document, pages in pages_by_document.items() for page in sorted(pages)
              for library in sorted(libraries.get(page, []))]
    while active:
        waiting = []
        for document, page, library, path, node in active:
            status = None
            while status is None:
                parent, parent_library = node["parent_id"], node["parent_library"]
                if node["id"] == document:
                    status = "verified"
                elif parent is None:
                    status = "other_document"
                elif parent_library != library:
                    status = "cross_library"
                elif parent in path:
                    status = "cycle"
                elif len(path) > max_depth:
                    status = "too_deep"
                elif parent not in loaded:
                    waiting.append((document, page, library, path, node))
                    break
                elif (parent, library) not in nodes:
                    status = "broken"
                else:
                    node = nodes[(parent, library)]
                    path.append(parent)
            if status is not None:
                chains[document].append(PageChain(page, library, status, tuple(path)))
        load(node["parent_id"] for *_, node in waiting)
        active = waiting
    return chains
