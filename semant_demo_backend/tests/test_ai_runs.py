"""SQL-backed run history is independent of remaining auto spans (#801)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from semant_demo.adapters.sql.ai_runs import AiRunRepository, AiSuggestionRunRow
from semant_demo.features.annotations.suggestion_routes import _registered_response, _run_response


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


@pytest.mark.asyncio
async def test_history_registration_uses_authorized_canonical_ids():
    collection, document, owner = uuid4(), uuid4(), uuid4()
    run = SimpleNamespace(run_id=str(uuid4()), config_name='fake-local',
                          collection_id=collection, document_id=document, summary=None,
                          completed_units=0, release=AsyncMock())
    history = SimpleNamespace(start=AsyncMock(), finish=AsyncMock())
    # Raw request strings are deliberately not in canonical UUID form.
    request = SimpleNamespace(collection_id=collection.hex.upper(), document_id=document.hex.upper(),
                              tag_ids=['tag'])
    await _registered_response(run, request, SimpleNamespace(id=owner), history, 'selection')
    history.start.assert_awaited_once_with(run.run_id, str(collection), str(document),
                                           owner, 'selection', 'fake-local', ['tag'])


@pytest.mark.asyncio
async def test_disconnect_before_first_stream_chunk_finishes_history():
    run = SimpleNamespace(run_id=str(uuid4()), summary=None, completed_units=0, release=AsyncMock())
    history = SimpleNamespace(finish=AsyncMock())
    response = _run_response(run, history)
    # The async generator has never been started (aclose does not enter finally).
    await response._work.release()
    history.finish.assert_awaited_once_with(run.run_id, 'cancelled', 0, units_completed=0)
    run.release.assert_awaited_once()
