"""Add ``annotation_attribute.all_tags`` to an existing SQLite database (#522), once, before the
backend that needs it starts.

``all_tags`` makes All tags explicit: before it, an empty ``tag_ids`` meant All tags, so an
attribute could not apply to no tag. New databases get the column from the normal startup
(``create_all``), which never alters an existing table. This command does that for an existing
one and is safe to repeat:

- no database file or no ``annotation_attribute`` table: nothing to do (startup creates it);
- the column exists: nothing to do;
- the column is missing: adds it (``NOT NULL DEFAULT 0``) and keeps what existing definitions
  meant before #522 (#574): an empty ``tag_ids`` meant All tags, so those get ``all_tags = 1``;
  definitions with tags stay Selected tags (``0``);
- a definition whose ``tag_ids`` is not a JSON list: refuses and changes nothing, because what it
  meant is unknown.

No other table is read or changed. Stop the backend that uses the file first; the check and the
change run in one write transaction. Deployment runs it in the new image against the mounted
file (``.github/workflows/ci-cd.yml``, ``deploy/README.md``)::

    python -m semant_demo.maintenance.attribute_scope_schema            # the configured SQL_DB_URL
    python -m semant_demo.maintenance.attribute_scope_schema --db PATH  # a given SQLite file

Exit status 0: the schema is current; 1: refused; 2: not a SQLite file database.
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

TABLE = "annotation_attribute"
COLUMN = "all_tags"
ADD_COLUMN = f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} BOOLEAN NOT NULL DEFAULT 0"


class SchemaUpdateRefused(Exception):
    """A definition's tag list is unreadable, so its meaning is unknown; nothing was changed."""


def update(path: Path) -> str:
    """Brings the database at ``path`` to the current attribute schema; what was done."""
    if not path.is_file():
        return f"no database at {path}; the backend creates it"
    conn = sqlite3.connect(f"file:{path}?mode=rw", uri=True, isolation_level=None)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (TABLE,)).fetchone() is None:
                return f"no {TABLE} table; the backend creates it"
            if any(row[1] == COLUMN for row in conn.execute(f"PRAGMA table_info({TABLE})")):
                return f"{TABLE}.{COLUMN} already exists"
            all_tags = [row_id for row_id, tag_ids in conn.execute(f"SELECT id, tag_ids FROM {TABLE}")
                        if not _tag_list(row_id, tag_ids)]
            rows = conn.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
            conn.execute(ADD_COLUMN)
            conn.executemany(f"UPDATE {TABLE} SET {COLUMN} = 1 WHERE id = ?", [(row_id,) for row_id in all_tags])
            conn.execute("COMMIT")
            if not rows:
                return f"added {TABLE}.{COLUMN}"
            return (f"added {TABLE}.{COLUMN}; of {rows} attribute definitions, {len(all_tags)} with no tags "
                    "now apply to All tags, as before #522")
        finally:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
    finally:
        conn.close()


def _tag_list(row_id: str, tag_ids) -> list:
    try:
        value = json.loads(tag_ids) if isinstance(tag_ids, (str, bytes)) else None
    except ValueError:
        value = None
    if not isinstance(value, list):
        raise SchemaUpdateRefused(
            f"{TABLE} {row_id} has tag_ids {tag_ids!r}, not a JSON list; nothing was changed. "
            "Which tags it applies to is unknown (#574).")
    return value


def sqlite_path(url: str) -> Path | None:
    """The file of a SQLite URL (``sqlite+aiosqlite:///tasks.db``); None for anything else."""
    from sqlalchemy.engine import make_url

    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or not parsed.database or parsed.database == ":memory:":
        return None
    return Path(parsed.database)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, help="the SQLite file (default: from SQL_DB_URL)")
    args = parser.parse_args(argv)
    path = args.db
    if path is None:
        from semant_demo.config import Config

        url = Config().SQL_DB_URL
        path = sqlite_path(url)
        if path is None:
            print("SQL_DB_URL is not a SQLite file database; nothing to do here", file=sys.stderr)
            return 2
    try:
        print(f"{path}: {update(path)}")
    except SchemaUpdateRefused as refused:
        print(f"{path}: REFUSED: {refused}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
