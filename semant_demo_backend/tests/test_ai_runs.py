"""SQL-backed run history is independent of remaining auto spans (#801)."""
import sqlite3
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from semant_demo.adapters.sql.ai_runs import AiRunRepository, AiSuggestionRunRow
from semant_demo.maintenance.ai_run_progress_schema import update


@pytest.mark.asyncio
async def test_run_history_is_persistent_scoped_and_records_completion():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(AiSuggestionRunRow.__table__.create)
        runs = AiRunRepository(async_sessionmaker(engine, expire_on_commit=False))
        collection, document, owner, run = (uuid4() for _ in range(4))
        await runs.start(str(run), str(collection), str(document), owner, "optimized", "fake-local", ["tag"])

        listing = await runs.list_document(str(collection), str(document))
        assert len(listing) == 1
        assert listing[0].id == str(run)
        assert listing[0].config_name == "fake-local"
        assert listing[0].outcome == "running"
        assert listing[0].started_at.tzinfo is not None
        assert await runs.list_document(str(uuid4()), str(document)) == []
        assert await runs.list_document(str(collection), str(uuid4())) == []

        await runs.finish(str(run), "complete", 0, unit="call", units_total=4, units_completed=4)
        persisted = (await runs.list_document(str(collection), str(document)))[0]
        assert persisted.outcome == "complete"
        assert persisted.saved == 0  # Even a run that generated nothing remains in history.
        assert persisted.unit == "call"
        assert persisted.units_total == 4
        assert persisted.units_completed == 4
        assert persisted.finished_at is not None

        cancelled = uuid4()
        await runs.start(str(cancelled), str(collection), str(document), owner, "thorough", "fake-local", ["tag"])
        await runs.finish(str(cancelled), "cancelled", 2, unit="chunk", units_total=8,
                          units_completed=3, provider_failures=1, save_failures=1)
        interrupted = (await runs.list_document(str(collection), str(document)))[0]
        assert interrupted.outcome == "cancelled"
        assert interrupted.saved == 2
        assert interrupted.units_completed == 3
        assert interrupted.units_total == 8
        assert interrupted.provider_failures == 1
        assert interrupted.save_failures == 1
    finally:
        await engine.dispose()


def test_run_progress_schema_migrates_an_existing_sqlite_database(tmp_path):
    path = tmp_path / 'old-runs.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE ai_suggestion_run (id TEXT PRIMARY KEY, mode TEXT NOT NULL)')
        conn.execute("INSERT INTO ai_suggestion_run VALUES ('run-1', 'optimized')")
    assert 'unit' in update(path)
    assert update(path) == 'run progress columns already exist'
    with sqlite3.connect(path) as conn:
        row = conn.execute('SELECT id, mode, unit, units_total, units_completed, '
                           'provider_failures, save_failures FROM ai_suggestion_run').fetchone()
    assert row == ('run-1', 'optimized', 'call', 0, 0, 0, 0)
