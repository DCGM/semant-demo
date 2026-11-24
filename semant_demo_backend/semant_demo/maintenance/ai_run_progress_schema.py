"""Add run progress columns to a SQLite database used by an earlier draft of #801.

New installations get these columns through create_all. Existing SQLite databases
need this explicit, repeatable step while the backend is stopped::

    python -m semant_demo.maintenance.ai_run_progress_schema
    python -m semant_demo.maintenance.ai_run_progress_schema --db PATH

Old run outcomes and saved counts are preserved. Their exact progress cannot be
reconstructed, so the new counters start at zero (and 0/0 is hidden in the UI).
"""
import argparse
import sqlite3
import sys
from pathlib import Path

from semant_demo.maintenance.attribute_scope_schema import sqlite_path

TABLE = "ai_suggestion_run"
COLUMNS = {
    "unit": "VARCHAR(16) NOT NULL DEFAULT 'chunk'",
    "units_total": "INTEGER NOT NULL DEFAULT 0",
    "units_completed": "INTEGER NOT NULL DEFAULT 0",
    "provider_failures": "INTEGER NOT NULL DEFAULT 0",
    "save_failures": "INTEGER NOT NULL DEFAULT 0",
}


def update(path: Path) -> str:
    if not path.is_file():
        return f"no database at {path}; startup creates it"
    conn = sqlite3.connect(f"file:{path}?mode=rw", uri=True, isolation_level=None)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone():
                return f"no {TABLE} table; startup creates it"
            existing = {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")}
            added = [column for column in COLUMNS if column not in existing]
            for column in added:
                conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN {column} {COLUMNS[column]}")
            if "unit" in added:
                conn.execute(f"UPDATE {TABLE} SET unit = CASE mode "
                             "WHEN 'optimized' THEN 'call' WHEN 'selection' THEN 'selection' "
                             "ELSE 'chunk' END")
            conn.execute("COMMIT")
            return f"added {', '.join(added)}" if added else "run progress columns already exist"
        finally:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
    finally:
        conn.close()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, help="SQLite file (default: from SQL_DB_URL)")
    args = parser.parse_args(argv)
    path = args.db
    if path is None:
        from semant_demo.config import Config
        path = sqlite_path(Config().SQL_DB_URL)
        if path is None:
            print("SQL_DB_URL is not a SQLite file database", file=sys.stderr)
            return 2
    print(f"{path}: {update(path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
