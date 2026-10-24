"""Collection attributes: definitions, their values and the record of assignment changes (#331).

Definitions belong to one user collection (never global). Attributes and values have stable
UUIDs that annotations store (``features/annotations/attribute_codec.py``); labels, descriptions and the
tags an attribute applies to can change without touching any annotation. Names are unique per
collection and labels per attribute, ignoring case and surrounding spaces. The accepted
assignments themselves live on the annotations in Weaviate; ``AttributeChangeRow`` only records
who changed what (ADR 0011), never a second copy of the current state.

Every method takes the collection whose definitions it uses; the service passes only a
collection it has authorized, so an id of another collection is "not found".
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, delete, select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload, relationship

from semant_demo.adapters.sql.base import Base
from semant_demo.core.errors import InvalidRequestError
from semant_demo.features.attributes.schemas import (
    Attribute, AttributeChange, AttributeValue, AssignSource, Cardinality, PatchAttribute, PatchAttributeValue,
    PostAttribute, PostAttributeValue, ValueKind,
)


class AttributeRow(Base):
    __tablename__ = "annotation_attribute"
    __table_args__ = (UniqueConstraint("collection_id", "name_key", name="uq_annotation_attribute_name"),)
    id = Column(String(36), primary_key=True)
    collection_id = Column(String(36), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    name_key = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")
    cardinality = Column(String(8), nullable=False)
    tag_ids = Column(JSON, nullable=False, default=list)
    retired = Column(Boolean, nullable=False, default=False)
    revision = Column(Integer, nullable=False, default=1)
    created_by = Column(String(36), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    values = relationship("AttributeValueRow", order_by="AttributeValueRow.position", lazy="raise",
                          cascade="all, delete-orphan")


class AttributeValueRow(Base):
    __tablename__ = "annotation_attribute_value"
    __table_args__ = (UniqueConstraint("attribute_id", "label_key", name="uq_annotation_attribute_value_label"),)
    id = Column(String(36), primary_key=True)
    attribute_id = Column(String(36), ForeignKey("annotation_attribute.id", ondelete="CASCADE"), nullable=False,
                          index=True)
    label = Column(String(200), nullable=False)
    label_key = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")
    examples = Column(JSON, nullable=False, default=list)
    kind = Column(String(16), nullable=False, default=ValueKind.value.value)
    retired = Column(Boolean, nullable=False, default=False)
    position = Column(Integer, nullable=False, default=0)


class AttributeChangeRow(Base):
    __tablename__ = "annotation_attribute_change"
    id = Column(Integer, primary_key=True, autoincrement=True)
    collection_id = Column(String(36), nullable=False, index=True)
    annotation_id = Column(String(36), nullable=False, index=True)
    attribute_id = Column(String(36), nullable=False)
    previous = Column(JSON, nullable=False)
    current = Column(JSON, nullable=False)
    actor_id = Column(String(36), nullable=False)
    at = Column(DateTime(timezone=True), nullable=False)
    source = Column(String(16), nullable=False)
    run_id = Column(String(36), nullable=True)
    annotation_edit_version = Column(Integer, nullable=True)
    attribute_revision = Column(Integer, nullable=False)


def _key(text: str) -> str:
    return text.strip().casefold()


def _utc(value: datetime) -> datetime:
    # SQLite returns naive datetimes; they are stored in UTC.
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _value(row: AttributeValueRow) -> AttributeValue:
    return AttributeValue(id=UUID(row.id), label=row.label, description=row.description or "",
                          examples=list(row.examples or []), kind=ValueKind(row.kind), retired=bool(row.retired))


def _attribute(row: AttributeRow) -> Attribute:
    return Attribute(id=UUID(row.id), name=row.name, description=row.description or "",
                     cardinality=Cardinality(row.cardinality), tag_ids=[UUID(t) for t in row.tag_ids or []],
                     retired=bool(row.retired), revision=row.revision, values=[_value(v) for v in row.values])


def _new_value(attribute_id: str, value: PostAttributeValue, position: int) -> AttributeValueRow:
    return AttributeValueRow(id=str(uuid4()), attribute_id=attribute_id, label=value.label.strip(),
                             label_key=_key(value.label), description=value.description,
                             examples=list(value.examples), kind=value.kind.value, retired=False, position=position)


class AttributeRepository:
    def __init__(self, session_maker: async_sessionmaker):
        self.session_maker = session_maker

    async def _load(self, session: AsyncSession, collection_id: UUID, attribute_id: UUID) -> AttributeRow | None:
        result = await session.execute(
            select(AttributeRow).options(selectinload(AttributeRow.values)).where(
                AttributeRow.id == str(attribute_id), AttributeRow.collection_id == str(collection_id)))
        return result.scalar_one_or_none()

    async def _commit(self, session: AsyncSession, what: str) -> None:
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise InvalidRequestError(f"{what} already exists") from None

    async def read_all(self, collection_id: UUID) -> list[Attribute]:
        """The collection's attributes with their values, by name."""
        async with self.session_maker() as session:
            result = await session.execute(
                select(AttributeRow).options(selectinload(AttributeRow.values))
                .where(AttributeRow.collection_id == str(collection_id)).order_by(AttributeRow.name_key))
            return [_attribute(r) for r in result.scalars()]

    async def read(self, collection_id: UUID, attribute_id: UUID) -> Attribute | None:
        async with self.session_maker() as session:
            row = await self._load(session, collection_id, attribute_id)
            return _attribute(row) if row is not None else None

    async def create(self, collection_id: UUID, attribute: PostAttribute, actor_id: UUID) -> Attribute:
        """Raises ``InvalidRequestError`` when the name (or a label) is already taken."""
        async with self.session_maker() as session:
            row = AttributeRow(
                id=str(uuid4()), collection_id=str(collection_id), name=attribute.name.strip(),
                name_key=_key(attribute.name), description=attribute.description,
                cardinality=attribute.cardinality.value, tag_ids=[str(t) for t in dict.fromkeys(attribute.tag_ids)],
                retired=False, revision=1, created_by=str(actor_id), created_at=datetime.now(timezone.utc))
            row.values = [_new_value(row.id, v, i) for i, v in enumerate(attribute.values)]
            session.add(row)
            await self._commit(session, "An attribute with this name, or a value with the same label,")
            return _attribute(row)

    async def update(self, collection_id: UUID, attribute_id: UUID, patch: PatchAttribute) -> Attribute | None:
        async with self.session_maker() as session:
            row = await self._load(session, collection_id, attribute_id)
            if row is None:
                return None
            if patch.name is not None:
                row.name, row.name_key = patch.name.strip(), _key(patch.name)
            if patch.description is not None:
                row.description = patch.description
            if patch.tag_ids is not None:
                row.tag_ids = [str(t) for t in dict.fromkeys(patch.tag_ids)]
            if patch.retired is not None:
                row.retired = patch.retired
            row.revision += 1
            await self._commit(session, "An attribute with this name")
            return _attribute(row)

    async def delete(self, collection_id: UUID, attribute_id: UUID) -> bool:
        async with self.session_maker() as session:
            row = await self._load(session, collection_id, attribute_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def add_value(self, collection_id: UUID, attribute_id: UUID, value: PostAttributeValue
                        ) -> Attribute | None:
        async with self.session_maker() as session:
            row = await self._load(session, collection_id, attribute_id)
            if row is None:
                return None
            row.values.append(_new_value(row.id, value, max((v.position for v in row.values), default=-1) + 1))
            row.revision += 1
            await self._commit(session, "A value with this label")
            return _attribute(await self._load(session, collection_id, attribute_id))

    async def update_value(self, collection_id: UUID, attribute_id: UUID, value_id: UUID,
                           patch: PatchAttributeValue) -> Attribute | None:
        """The attribute after the change, or None when the attribute or the value is not found."""
        async with self.session_maker() as session:
            row = await self._load(session, collection_id, attribute_id)
            value = next((v for v in row.values if v.id == str(value_id)), None) if row is not None else None
            if value is None:
                return None
            if patch.label is not None:
                value.label, value.label_key = patch.label.strip(), _key(patch.label)
            if patch.description is not None:
                value.description = patch.description
            if patch.examples is not None:
                value.examples = list(patch.examples)
            if patch.retired is not None:
                value.retired = patch.retired
            row.revision += 1
            await self._commit(session, "A value with this label")
            return _attribute(await self._load(session, collection_id, attribute_id))

    async def delete_value(self, collection_id: UUID, attribute_id: UUID, value_id: UUID) -> Attribute | None:
        async with self.session_maker() as session:
            row = await self._load(session, collection_id, attribute_id)
            value = next((v for v in row.values if v.id == str(value_id)), None) if row is not None else None
            if value is None:
                return None
            row.values.remove(value)
            row.revision += 1
            await session.commit()
            return _attribute(await self._load(session, collection_id, attribute_id))

    async def record_changes(self, collection_id: UUID, changes: list[AttributeChange]) -> None:
        """Appends the change records (one transaction)."""
        if not changes:
            return
        async with self.session_maker() as session:
            session.add_all(AttributeChangeRow(
                collection_id=str(collection_id), annotation_id=str(c.annotation_id),
                attribute_id=str(c.attribute_id), previous=[str(v) for v in c.previous],
                current=[str(v) for v in c.current], actor_id=str(c.actor_id), at=c.at, source=c.source.value,
                run_id=str(c.run_id) if c.run_id else None, annotation_edit_version=c.annotation_edit_version,
                attribute_revision=c.attribute_revision) for c in changes)
            await session.commit()

    async def read_changes(self, collection_id: UUID, annotation_id: UUID) -> list[AttributeChange]:
        """The annotation's change records, oldest first."""
        async with self.session_maker() as session:
            result = await session.execute(
                select(AttributeChangeRow).where(AttributeChangeRow.collection_id == str(collection_id),
                                                 AttributeChangeRow.annotation_id == str(annotation_id))
                .order_by(AttributeChangeRow.id))
            return [AttributeChange(
                id=r.id, annotation_id=UUID(r.annotation_id), attribute_id=UUID(r.attribute_id),
                previous=[UUID(v) for v in r.previous], current=[UUID(v) for v in r.current],
                actor_id=UUID(r.actor_id), at=_utc(r.at), source=AssignSource(r.source),
                run_id=UUID(r.run_id) if r.run_id else None, annotation_edit_version=r.annotation_edit_version,
                attribute_revision=r.attribute_revision) for r in result.scalars()]

    async def delete_collection(self, collection_id: UUID) -> None:
        """Removes the collection's definitions and change records (repeating it is safe)."""
        async with self.session_maker() as session:
            for row in (await session.execute(select(AttributeRow).options(selectinload(AttributeRow.values))
                                              .where(AttributeRow.collection_id == str(collection_id)))).scalars():
                await session.delete(row)
            await session.execute(delete(AttributeChangeRow).where(
                AttributeChangeRow.collection_id == str(collection_id)))
            await session.commit()
