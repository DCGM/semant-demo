"""The one-time ``annotation_attribute.all_tags`` schema step (#522) and the startup check.

New databases get the column from ``create_all``; an existing empty table gets it from
``maintenance/attribute_scope_schema.py``, which is repeatable and refuses, changing nothing, a
table that already holds attribute definitions. Startup refuses a table without the column.
"""
import os
import sqlite3
import subprocess
import sys

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from semant_demo.adapters.sql.tables import OutdatedSchemaError, create_tables
from semant_demo.maintenance import attribute_scope_schema as schema
from tests.test_deploy_commit import DEPLOY_JOBS, REPO_ROOT, _job, _step

# annotation_attribute as created before #522.
OLD_TABLE = """CREATE TABLE annotation_attribute (
    id VARCHAR(36) PRIMARY KEY, collection_id VARCHAR(36) NOT NULL, name VARCHAR(200) NOT NULL,
    name_key VARCHAR(200) NOT NULL, description TEXT NOT NULL, cardinality VARCHAR(8) NOT NULL,
    tag_ids JSON NOT NULL, retired BOOLEAN NOT NULL, revision INTEGER NOT NULL,
    created_by VARCHAR(36) NOT NULL, created_at DATETIME NOT NULL,
    CONSTRAINT uq_annotation_attribute_name UNIQUE (collection_id, name_key))"""
OLD_ROW = ("INSERT INTO annotation_attribute VALUES "
           "('a1', 'c1', 'Mood', 'mood', '', 'single', '[]', 0, 1, 'u1', '2026-10-01 00:00:00')")


def old_database(path, *, attributes=False):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE user (id VARCHAR(36) PRIMARY KEY, email VARCHAR NOT NULL)")
        conn.execute("INSERT INTO user VALUES ('u1', 'kept@example.com')")
        conn.execute(OLD_TABLE)
        if attributes:
            conn.execute(OLD_ROW)
    conn.close()
    return path


def columns(path):
    with sqlite3.connect(path) as conn:
        result = {row[1]: row for row in conn.execute("PRAGMA table_info(annotation_attribute)")}
    conn.close()
    return result


def dump(path):
    with sqlite3.connect(path) as conn:
        result = list(conn.iterdump())
    conn.close()
    return result


async def start(path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    try:
        await create_tables(engine)
    finally:
        await engine.dispose()


async def test_a_new_database_gets_the_column_from_startup_and_needs_no_step(tmp_path):
    db = tmp_path / "new.db"
    await start(db)

    assert "all_tags" in columns(db)
    assert schema.update(db) == "annotation_attribute.all_tags already exists"


def test_nothing_to_do_without_a_database_or_without_the_table(tmp_path):
    missing = tmp_path / "missing.db"
    assert "no database" in schema.update(missing)
    assert not missing.exists()

    empty = tmp_path / "touched.db"  # as the deployment creates it before the first start
    empty.touch()
    assert "no annotation_attribute table" in schema.update(empty)
    assert dump(empty) == ["BEGIN TRANSACTION;", "COMMIT;"]


async def test_an_empty_old_table_gets_the_column_once_and_then_starts(tmp_path):
    db = old_database(tmp_path / "old.db")
    with pytest.raises(OutdatedSchemaError, match="attribute_scope_schema"):
        await start(db)

    assert schema.update(db) == "added annotation_attribute.all_tags"
    all_tags = columns(db)["all_tags"]
    assert (all_tags[2], all_tags[3], all_tags[4]) == ("BOOLEAN", 1, "0")  # type, NOT NULL, default
    after = dump(db)
    assert schema.update(db) == "annotation_attribute.all_tags already exists"
    assert dump(db) == after
    await start(db)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT id, email FROM user").fetchall() == [("u1", "kept@example.com")]
    conn.close()


def test_existing_attribute_definitions_are_refused_and_nothing_changes(tmp_path):
    db = old_database(tmp_path / "used.db", attributes=True)
    before = dump(db)

    with pytest.raises(schema.SchemaUpdateRefused, match="1 attribute definitions"):
        schema.update(db)
    assert dump(db) == before
    assert "all_tags" not in columns(db)


def test_the_command_uses_the_configured_database_and_reports_a_refusal(tmp_path):
    backend = REPO_ROOT / "semant_demo_backend"
    ok, used = old_database(tmp_path / "ok.db"), old_database(tmp_path / "used.db", attributes=True)

    def run(db):
        # The normal environment (Config imports Logfire, which needs HOME), with this database.
        env = {**os.environ, "SQL_DB_URL": f"sqlite+aiosqlite:///{db}"}
        return subprocess.run([sys.executable, "-m", "semant_demo.maintenance.attribute_scope_schema"], cwd=backend,
                              env=env, capture_output=True, text=True, timeout=60)

    added = run(ok)
    assert added.returncode == 0, added.stderr
    assert f"{ok}: added annotation_attribute.all_tags" in added.stdout
    refused = run(used)
    assert refused.returncode == 1
    assert "REFUSED" in refused.stderr and "all_tags" not in columns(used)


def test_only_sqlite_files_are_handled():
    assert schema.sqlite_path("sqlite+aiosqlite:////app/sql_data/tasks.db").as_posix() == "/app/sql_data/tasks.db"
    assert schema.sqlite_path("sqlite+aiosqlite:///tasks.db").as_posix() == "tasks.db"
    assert schema.sqlite_path("sqlite+aiosqlite:///:memory:") is None
    assert schema.sqlite_path("postgresql+asyncpg://u:p@db/semant") is None


@pytest.mark.parametrize("name", DEPLOY_JOBS)
def test_every_deployment_updates_the_schema_after_stopping_the_old_app_and_before_starting_the_new(name):
    script = " ".join(_step(_job(name), "Build and start")["run"].replace("\\\n", " ").split())
    down, step, up = (script.index(part) for part in (
        " down ", " run --rm --no-deps -T -l traefik.enable=false --entrypoint python app "
                  "-m semant_demo.maintenance.attribute_scope_schema", " up -d"))
    # The one-off container is the app service: the same image, mount and SQL_DB_URL as the app.
    assert down < step < up


def test_the_local_development_backend_updates_its_schema_before_starting():
    script = (REPO_ROOT / "scripts" / "local-dev.sh").read_text()
    body = script[script.index("cmd_backend()"):script.index("cmd_frontend()")]
    assert body.index("semant_demo.maintenance.attribute_scope_schema") < body.index("-m uvicorn")
