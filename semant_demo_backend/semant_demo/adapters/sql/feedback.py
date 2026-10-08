"""RAG answer feedback table."""
import sqlalchemy.sql.functions as funcs
from sqlalchemy import JSON, Column, DateTime, Integer, String, Text

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
