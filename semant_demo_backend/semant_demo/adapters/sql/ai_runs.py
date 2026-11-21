"""Persistent metadata for AI suggestion runs (#801).

A run record survives deleting/reviewing every proposal. The span's existing
provenance ``aiRunId`` links suggestions to the run; no model names are inferred
from creation timestamps. Access control is enforced by the HTTP service before
calling this repository.
"""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import Column, Index, Integer, JSON, String, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from semant_demo.adapters.sql.base import Base
from semant_demo.features.annotations.schemas import AiSuggestionRunInfo


class AiSuggestionRunRow(Base):
    __tablename__ = "ai_suggestion_run"

    id = Column(String(36), primary_key=True)
    collection_id = Column(String(36), nullable=False)
    document_id = Column(String(36), nullable=False)
    created_by = Column(String(36), nullable=False)
    mode = Column(String(16), nullable=False)
    config_name = Column(String(200), nullable=False)
    tag_ids = Column(JSON, nullable=False)
    started_at = Column(String(40), nullable=False)
    finished_at = Column(String(40), nullable=True)
    outcome = Column(String(16), nullable=False, default="running")
    saved = Column(Integer, nullable=False, default=0)

    __table_args__ = (Index("ix_ai_suggestion_run_document", "collection_id", "document_id", "started_at"),)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AiRunRepository:
    def __init__(self, session_maker: async_sessionmaker):
        self.session_maker = session_maker

    async def start(self, run_id: str, collection_id: str, document_id: str, created_by: UUID,
                    mode: str, config_name: str, tag_ids: list[str]) -> None:
        async with self.session_maker() as session:
            session.add(AiSuggestionRunRow(
                id=run_id, collection_id=collection_id, document_id=document_id,
                created_by=str(created_by), mode=mode, config_name=config_name,
                tag_ids=tag_ids, started_at=_now(), outcome="running", saved=0,
            ))
            await session.commit()

    async def finish(self, run_id: str, outcome: str, saved: int) -> None:
        async with self.session_maker() as session:
            await session.execute(update(AiSuggestionRunRow).where(AiSuggestionRunRow.id == run_id).values(
                outcome=outcome, saved=saved, finished_at=_now()))
            await session.commit()

    async def list_document(self, collection_id: str, document_id: str) -> list[AiSuggestionRunInfo]:
        async with self.session_maker() as session:
            rows = (await session.execute(
                select(AiSuggestionRunRow).where(
                    AiSuggestionRunRow.collection_id == collection_id,
                    AiSuggestionRunRow.document_id == document_id,
                ).order_by(AiSuggestionRunRow.started_at.desc()).limit(100)
            )).scalars().all()
        now = datetime.now(timezone.utc)
        history = []
        for r in rows:
            started = datetime.fromisoformat(r.started_at)
            # Unfinished runs older than an hour cannot still be trusted to be live.
            outcome = ("interrupted" if r.outcome == "running" and
                       (now - started).total_seconds() > 3600 else r.outcome)
            history.append(AiSuggestionRunInfo(
                id=r.id, mode=r.mode, config_name=r.config_name, tag_ids=r.tag_ids,
                started_at=started,
                finished_at=datetime.fromisoformat(r.finished_at) if r.finished_at else None,
                outcome=outcome, saved=r.saved,
            ))
        return history
