"""Saved research selections of user collections (#824, parent #335).

One row per saved selection; every method takes the collection it reads or writes, so an id of
another collection is "not found". Names are unique per collection, ignoring case and surrounding
spaces. The query is stored as JSON and validated again on every read: a row written for an
older query model is returned as unreadable instead of failing the whole list.
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import JSON, Column, DateTime, String, UniqueConstraint, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from semant_demo.adapters.sql.base import Base
from semant_demo.core.errors import InvalidRequestError
from semant_demo.features.saved_selections.schemas import LiveQuery, SavedSelectionKind

NAME_TAKEN = "A saved selection with this name already exists in the collection"


class SavedSelectionRow(Base):
    __tablename__ = "saved_selection"
    __table_args__ = (UniqueConstraint("collection_id", "name_key", name="uq_saved_selection_name"),)
    id = Column(String(36), primary_key=True)
    collection_id = Column(String(36), nullable=False, index=True)
    kind = Column(String(16), nullable=False)
    name = Column(String(200), nullable=False)
    name_key = Column(String(200), nullable=False)
    query = Column(JSON, nullable=False)
    created_by = Column(String(36), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_by = Column(String(36), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class StoredSelection:
    """A row as the service uses it; ``query`` is None when it no longer validates."""

    def __init__(self, row: SavedSelectionRow):
        self.id = UUID(row.id)
        self.collection_id = UUID(row.collection_id)
        self.kind = SavedSelectionKind(row.kind)
        self.name = row.name
        try:
            self.query: LiveQuery | None = LiveQuery.model_validate(row.query)
        except ValidationError:
            self.query = None
        self.created_by = UUID(row.created_by)
        self.created_at = _utc(row.created_at)
        self.updated_by = UUID(row.updated_by)
        self.updated_at = _utc(row.updated_at)


def _key(name: str) -> str:
    return name.strip().casefold()


def _utc(value: datetime) -> datetime:
    # SQLite returns naive datetimes; they are stored in UTC.
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SavedSelectionRepository:
    def __init__(self, session_maker: async_sessionmaker):
        self.session_maker = session_maker

    async def read_all(self, collection_id: UUID) -> list[StoredSelection]:
        """The collection's saved selections, by name."""
        async with self.session_maker() as session:
            rows = await session.execute(select(SavedSelectionRow).where(
                SavedSelectionRow.collection_id == str(collection_id)).order_by(SavedSelectionRow.name_key))
            return [StoredSelection(r) for r in rows.scalars()]

    async def read(self, collection_id: UUID, selection_id: UUID) -> StoredSelection | None:
        async with self.session_maker() as session:
            row = await self._load(session, collection_id, selection_id)
            return StoredSelection(row) if row is not None else None

    async def count(self, collection_id: UUID) -> int:
        async with self.session_maker() as session:
            return (await session.execute(select(func.count()).select_from(SavedSelectionRow).where(
                SavedSelectionRow.collection_id == str(collection_id)))).scalar_one()

    async def create(self, collection_id: UUID, kind: SavedSelectionKind, name: str, query: LiveQuery,
                     actor_id: UUID) -> StoredSelection:
        """Raises ``InvalidRequestError`` when the name is taken."""
        now = _now()
        row = SavedSelectionRow(id=str(uuid4()), collection_id=str(collection_id), kind=kind.value, name=name,
                                name_key=_key(name), query=query.model_dump(mode="json"), created_by=str(actor_id),
                                created_at=now, updated_by=str(actor_id), updated_at=now)
        async with self.session_maker() as session:
            session.add(row)
            await self._commit(session)
            return StoredSelection(row)

    async def update(self, collection_id: UUID, selection_id: UUID, actor_id: UUID, *, name: str | None = None,
                     query: LiveQuery | None = None) -> StoredSelection | None:
        """Renames and/or replaces the query; None when there is no such selection."""
        async with self.session_maker() as session:
            row = await self._load(session, collection_id, selection_id)
            if row is None:
                return None
            if name is not None:
                row.name, row.name_key = name, _key(name)
            if query is not None:
                row.query = query.model_dump(mode="json")
            row.updated_by, row.updated_at = str(actor_id), _now()
            await self._commit(session)
            return StoredSelection(row)

    async def delete(self, collection_id: UUID, selection_id: UUID) -> bool:
        async with self.session_maker() as session:
            result = await session.execute(delete(SavedSelectionRow).where(
                SavedSelectionRow.id == str(selection_id), SavedSelectionRow.collection_id == str(collection_id)))
            await session.commit()
            return result.rowcount > 0

    async def delete_collection(self, collection_id: UUID) -> None:
        """Removes every saved selection of the collection (repeating it is safe)."""
        async with self.session_maker() as session:
            await session.execute(delete(SavedSelectionRow).where(
                SavedSelectionRow.collection_id == str(collection_id)))
            await session.commit()

    @staticmethod
    async def _load(session, collection_id: UUID, selection_id: UUID) -> SavedSelectionRow | None:
        return (await session.execute(select(SavedSelectionRow).where(
            SavedSelectionRow.id == str(selection_id),
            SavedSelectionRow.collection_id == str(collection_id)))).scalar_one_or_none()

    @staticmethod
    async def _commit(session) -> None:
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise InvalidRequestError(NAME_TAKEN) from None
