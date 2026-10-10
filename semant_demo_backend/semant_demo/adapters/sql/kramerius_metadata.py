"""Read-only access to the Kramerius metadata mirror (``meta_records``, #257).

The mirror is an external PostgreSQL database maintained by the ``librarymetadata``
project, not an application table: its table is declared on its own ``MetaData`` so the
application's ``create_tables`` never creates it, and nothing here writes. Only the
columns used for document metadata are declared.
"""
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import JSON, Boolean, Column, DateTime, MetaData, String, Table, Uuid, select
from sqlalchemy.engine import Connection

from semant_demo.maintenance.kramerius_mapping import SourceRecord

META_RECORDS = Table(
    "meta_records", MetaData(),
    Column("id", Uuid, primary_key=True),
    Column("library", String(10), primary_key=True),
    Column("public", Boolean),
    Column("in_library", Boolean),
    Column("record_type", String(30)),
    Column("title", String),
    Column("date", String),
    Column("start_date", DateTime),
    Column("end_date", DateTime),
    Column("metadata_json", JSON),
)


def read_meta_records(connection: Connection, ids: Sequence[UUID]) -> dict[UUID, list[SourceRecord]]:
    """Every mirror row of these ids, of any library, by id. Ids without rows are absent."""
    if not ids:
        return {}
    rows = connection.execute(select(META_RECORDS).where(META_RECORDS.c.id.in_(list(ids))))
    found: dict[UUID, list[SourceRecord]] = {}
    for row in rows.mappings():
        found.setdefault(row["id"], []).append(SourceRecord(
            id=str(row["id"]), library=row["library"], public=row["public"], in_library=row["in_library"],
            record_type=row["record_type"], title=row["title"], date=row["date"],
            start_date=row["start_date"], end_date=row["end_date"], metadata_json=row["metadata_json"],
        ))
    return found
