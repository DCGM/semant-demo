"""RAG answer feedback table and its writes."""
import datetime

import sqlalchemy.sql.functions as funcs
from sqlalchemy import JSON, Column, DateTime, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession

from semant_demo.adapters.sql.base import Base


class RagUserFeedback(Base):
    __tablename__ = "rag_user_feedback"
    id = Column(Integer, primary_key=True, autoincrement=True)
    response_id = Column(String(36), index=True, unique=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=funcs.now())
    rag_id = Column(String(255), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    rating = Column(Integer, nullable=False)  # 1 - like, -1 - dislike
    # list of error types, if rating is -1
    error_types = Column(JSON, nullable=True)
    comment = Column(Text, nullable=True)
    sources = Column(JSON, nullable=True)


async def save_rag_feedback(session: AsyncSession, *, response_id: str, rag_id: str, question: str, answer: str,
                            rating: int, error_types: str | None, comment: str | None, sources: list[dict]) -> None:
    """Store the rating of an answer, replacing an earlier rating of the same response.

    A replaced rating keeps the stored question, answer and sources. Rolls back and
    re-raises when the write fails.
    """
    try:
        existing = (await session.execute(
            select(RagUserFeedback).where(RagUserFeedback.response_id == response_id))).scalar_one_or_none()
        if existing is not None:
            existing.rating = rating
            existing.comment = comment
            existing.error_types = error_types
            existing.timestamp = datetime.datetime.now(datetime.timezone.utc)
        else:
            session.add(RagUserFeedback(response_id=response_id, rag_id=rag_id, question=question, answer=answer,
                                        rating=rating, error_types=error_types, comment=comment, sources=sources))
        await session.commit()
    except Exception:
        await session.rollback()
        raise
