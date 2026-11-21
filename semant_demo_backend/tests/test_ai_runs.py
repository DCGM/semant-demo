"""SQL-backed run history is independent of remaining auto spans (#801)."""
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from semant_demo.adapters.sql.ai_runs import AiRunRepository, AiSuggestionRunRow


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

        await runs.finish(str(run), "complete", 0)
        persisted = (await runs.list_document(str(collection), str(document)))[0]
        assert persisted.outcome == "complete"
        assert persisted.saved == 0  # Even a run that generated nothing remains in history.
        assert persisted.finished_at is not None
    finally:
        await engine.dispose()
