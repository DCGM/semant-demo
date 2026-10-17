"""Deployed instances keep the SQLite database and its rollback journal together on the host (#406).

SQLite writes ``tasks.db-journal`` beside the database. When only the database file was
bind-mounted, the journal lived in the container's writable layer and was lost when the
container was recreated, so an interrupted write could leave uncommitted changes in the file.
"""
import asyncio
import sqlite3
import subprocess
import sys
from pathlib import PurePosixPath

import pytest
import yaml
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from tests.test_deploy_commit import REPO_ROOT

DEPLOY = REPO_ROOT / "deploy"
SQL_DIR_MOUNT = {"type": "bind", "source": "${SQL_DB_PATH}", "target": "/app/sql_data",
                 "bind": {"create_host_path": False}}
ROWS = 2000


def _app_service(compose):
    return yaml.safe_load((DEPLOY / compose).read_text())["services"]["app"]


@pytest.mark.parametrize("compose", ["docker-compose.app.yaml", "docker-compose.app-test.yml"])
def test_app_compose_opens_the_database_in_the_mounted_instance_directory(compose):
    app = _app_service(compose)
    url = app["environment"]["SQL_DB_URL"]
    db_path = PurePosixPath(url.removeprefix("sqlite+aiosqlite:///"))

    assert url.startswith("sqlite+aiosqlite:////")
    assert SQL_DIR_MOUNT in app["volumes"]
    # Same host file as before the change (${SQL_DB_PATH}/tasks.db), and no file-only mount.
    assert db_path == PurePosixPath(SQL_DIR_MOUNT["target"]) / "tasks.db"
    assert not any(str(v.get("source", "")).endswith("tasks.db") for v in app["volumes"])


def test_backup_cron_reads_the_production_database_file():
    [env_dir] = [line.split("=", 1)[1] for line in (DEPLOY / ".env.example").read_text().splitlines()
                 if line.startswith("SQL_DB_PATH=")]
    [job] = [line for line in (DEPLOY / "semant-sqlite-backup.cron").read_text().splitlines()
             if line and not line.startswith("#") and "=" not in line.split()[0]]

    assert job.split()[7] == f"{env_dir}/tasks.db"


CRASH_MID_TRANSACTION = """
import os, signal, sqlite3, sys
conn = sqlite3.connect(sys.argv[1], isolation_level=None)
conn.execute("PRAGMA cache_size=10")  # spill uncommitted pages into the database file
conn.execute("BEGIN")
conn.execute("UPDATE item SET value = 'uncommitted'")
os.kill(os.getpid(), signal.SIGKILL)
"""


@pytest.fixture
def crashed_db(tmp_path):
    """A database whose writer was killed mid-transaction, leaving a hot journal beside it."""
    db = tmp_path / "instance" / "tasks.db"
    db.parent.mkdir()
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE item(id INTEGER PRIMARY KEY, value TEXT, pad TEXT)")
        conn.executemany("INSERT INTO item(value, pad) VALUES ('committed', ?)", [("x" * 500,)] * ROWS)
    conn.close()
    subprocess.run([sys.executable, "-c", CRASH_MID_TRANSACTION, str(db)], check=False)
    assert db.with_name("tasks.db-journal").stat().st_size > 0
    return db


def _values(db):
    async def read():
        engine = create_async_engine(f"sqlite+aiosqlite:///{db}", poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                values = dict((await conn.execute(text("SELECT value, count(*) FROM item GROUP BY value"))).all())
                check = (await conn.execute(text("PRAGMA integrity_check"))).scalar_one()
        finally:
            await engine.dispose()
        return values, check
    return asyncio.run(read())


def test_reopening_the_persisted_directory_rolls_back_the_interrupted_write(crashed_db):
    values, check = _values(crashed_db)

    assert values == {"committed": ROWS}
    assert check == "ok"
    assert not crashed_db.with_name("tasks.db-journal").exists()


def test_the_database_file_alone_keeps_uncommitted_changes(crashed_db, tmp_path):
    # The former file-only mount: a recreated container sees the file without its journal.
    file_only = tmp_path / "recreated" / "tasks.db"
    file_only.parent.mkdir()
    file_only.write_bytes(crashed_db.read_bytes())

    values, _ = _values(file_only)

    assert values.get("uncommitted", 0) > 0
