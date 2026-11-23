"""Saved research selections (features/saved_selections, #824) called directly, with a real
SQLite repository and an in-memory collection access record.

Live filters: create, list, rename, replace the query and delete; names unique per collection;
who may change them (creator and collection owner); collection access checked first, revoked
access and other collections; stored queries that no longer validate; the per-collection limit;
removal with the collection.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from semant_demo.adapters.sql.base import Base
from semant_demo.adapters.sql.saved_selections import SavedSelectionRepository, SavedSelectionRow
from semant_demo.core.errors import IncompleteWriteError, InvalidRequestError, NotFoundError
from semant_demo.features.annotations.schemas import AnnotationFilters, AnnotationSort, SpanType
from semant_demo.features.saved_selections import schemas, service
from semant_demo.features.saved_selections.schemas import (
    LiveQuery, PatchSavedSelection, PostSavedSelection, SavedSelectionKind,
)
from semant_demo.features.saved_selections.service import SavedSelectionStore
from semant_demo.features.user_collections import service as collection_service
from semant_demo.features.user_collections.access import AccessDenied, AuthenticationRequired, ResourceNotFound

OWNER, SHARED, SECOND_SHARED, OTHER = (SimpleNamespace(id=uuid4(), is_superuser=False) for _ in range(4))
COLLECTION, SECOND_COLLECTION = uuid4(), uuid4()
TAG, ATTRIBUTE = uuid4(), uuid4()


class FakeCollections:
    def __init__(self):
        self.records = {COLLECTION: (OWNER.id, {SHARED.id, SECOND_SHARED.id}), SECOND_COLLECTION: (OWNER.id, set())}
        self.deleted: list = []

    async def read_access_record(self, cid):
        return self.records.get(cid)

    async def delete(self, cid):
        self.deleted.append(cid)
        self.records.pop(cid, None)


class FakeAttributes:
    async def delete_collection(self, cid):
        pass


@pytest.fixture
async def repository(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'selections.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield SavedSelectionRepository(async_sessionmaker(engine, expire_on_commit=False))
    await engine.dispose()


@pytest.fixture
def collections():
    return FakeCollections()


@pytest.fixture
def store(repository, collections):
    return SavedSelectionStore(collections=collections, selections=repository)


def query(**filters) -> LiveQuery:
    return LiveQuery(filters=AnnotationFilters(**filters))


async def save(store, user=OWNER, name="Speakers", collection=COLLECTION, **filters):
    return await service.create_saved_selection(store, user, collection,
                                                PostSavedSelection(name=name, query=query(**filters)))


async def test_a_live_filter_keeps_its_query_and_view_and_lists_by_name(store):
    stored = LiveQuery(filters=AnnotationFilters(tag_ids=[TAG], types=[SpanType.pos], q="Praha",
                                                 attribute_values=[f"{ATTRIBUTE}:{uuid4()}"]),
                       sort=AnnotationSort.attribute, sort_attribute=ATTRIBUTE, descending=True,
                       shown_attribute_ids=[ATTRIBUTE])
    created = await service.create_saved_selection(store, SHARED, COLLECTION,
                                                   PostSavedSelection(name="  Zebra  ", query=stored))
    await save(store, name="alpha")

    assert created.kind == SavedSelectionKind.live and created.name == "Zebra" and created.query == stored
    assert created.created_by == created.updated_by == SHARED.id and created.can_edit and not created.unreadable
    listed = await service.list_saved_selections(store, OWNER, COLLECTION)
    assert [s.name for s in listed] == ["alpha", "Zebra"]
    assert listed[1].query == stored and listed[1].can_edit  # the owner may edit what a shared user saved


async def test_names_are_unique_per_collection_ignoring_case_and_spaces(store):
    first = await save(store, name="Speakers")
    with pytest.raises(InvalidRequestError):
        await save(store, user=SHARED, name=" speakers ")
    await save(store, name="Speakers", collection=SECOND_COLLECTION)  # another collection may reuse it
    second = await save(store, name="Places")
    with pytest.raises(InvalidRequestError):
        await service.update_saved_selection(store, OWNER, COLLECTION, second.id, PatchSavedSelection(name="SPEAKERS"))
    renamed = await service.update_saved_selection(store, OWNER, COLLECTION, first.id,
                                                   PatchSavedSelection(name="speakers"))  # its own name, other case
    assert renamed.name == "speakers"


async def test_rename_and_replace_keep_identity_and_record_who_changed_it(store):
    created = await save(store, user=SHARED, tag_ids=[TAG])
    renamed = await service.update_saved_selection(store, SHARED, COLLECTION, created.id,
                                                   PatchSavedSelection(name="Renamed"))
    assert renamed.id == created.id and renamed.query == created.query

    replaced = await service.update_saved_selection(store, OWNER, COLLECTION, created.id,
                                                    PatchSavedSelection(query=query(q="Brno")))
    assert replaced.name == "Renamed" and replaced.query == query(q="Brno")
    assert replaced.created_by == SHARED.id and replaced.updated_by == OWNER.id
    assert replaced.updated_at >= created.updated_at and replaced.created_at == created.created_at


async def test_only_the_creator_and_the_owner_change_or_delete_it(store, repository):
    mine = await save(store, user=SHARED)
    listed = await service.list_saved_selections(store, SECOND_SHARED, COLLECTION)
    assert [s.can_edit for s in listed] == [False]  # readable, not editable, by another shared user

    with pytest.raises(AccessDenied):
        await service.update_saved_selection(store, SECOND_SHARED, COLLECTION, mine.id, PatchSavedSelection(name="x"))
    with pytest.raises(AccessDenied):
        await service.delete_saved_selection(store, SECOND_SHARED, COLLECTION, mine.id)
    assert (await repository.read(COLLECTION, mine.id)).name == "Speakers"

    owners = await save(store, user=OWNER, name="Owner's")
    with pytest.raises(AccessDenied):
        await service.delete_saved_selection(store, SHARED, COLLECTION, owners.id)
    await service.delete_saved_selection(store, OWNER, COLLECTION, mine.id)
    await service.delete_saved_selection(store, OWNER, COLLECTION, owners.id)
    assert await service.list_saved_selections(store, SHARED, COLLECTION) == []


async def test_collection_access_comes_first_and_hides_other_collections(store, collections, repository):
    created = await save(store)
    with pytest.raises(ResourceNotFound):
        await service.list_saved_selections(store, OTHER, COLLECTION)
    with pytest.raises(ResourceNotFound):
        await save(store, user=OTHER, name="intruder")
    with pytest.raises(ResourceNotFound):
        await service.delete_saved_selection(store, OTHER, COLLECTION, created.id)
    with pytest.raises(AuthenticationRequired):
        await service.list_saved_selections(store, None, COLLECTION)
    # The id of another collection's selection is not found through this one.
    with pytest.raises(NotFoundError):
        await service.update_saved_selection(store, OWNER, SECOND_COLLECTION, created.id, PatchSavedSelection(name="x"))
    with pytest.raises(ResourceNotFound):
        await service.delete_saved_selection(store, OWNER, COLLECTION, "not-a-uuid")
    assert [s.name for s in await repository.read_all(COLLECTION)] == ["Speakers"]


async def test_revoked_access_denies_the_saved_selections_the_user_created(store, collections):
    created = await save(store, user=SHARED)
    collections.records[COLLECTION] = (OWNER.id, {SECOND_SHARED.id})  # the owner stops sharing with SHARED

    with pytest.raises(ResourceNotFound):
        await service.list_saved_selections(store, SHARED, COLLECTION)
    with pytest.raises(ResourceNotFound):
        await service.update_saved_selection(store, SHARED, COLLECTION, created.id, PatchSavedSelection(name="x"))
    # It stays with the collection: still listed for its remaining readers.
    assert [s.id for s in await service.list_saved_selections(store, OWNER, COLLECTION)] == [created.id]


async def test_a_stored_query_that_no_longer_validates_is_listed_as_unreadable(store, repository):
    broken = await save(store, name="Old")
    await save(store, name="Current")
    async with repository.session_maker() as session:
        await session.execute(update(SavedSelectionRow).where(SavedSelectionRow.id == str(broken.id))
                              .values(query={"filters": {"removed_filter": 1}}))
        await session.commit()

    listed = {s.name: s for s in await service.list_saved_selections(store, OWNER, COLLECTION)}
    assert listed["Old"].unreadable and listed["Old"].query is None
    assert not listed["Current"].unreadable
    fixed = await service.update_saved_selection(store, OWNER, COLLECTION, broken.id,
                                                 PatchSavedSelection(query=query(q="nové")))
    assert not fixed.unreadable and fixed.query == query(q="nové")


async def test_a_collection_holds_a_bounded_number_of_saved_selections(store, monkeypatch):
    monkeypatch.setattr(service, "MAX_SAVED_SELECTIONS", 2)
    await save(store, name="a")
    await save(store, name="b")
    with pytest.raises(InvalidRequestError):
        await save(store, name="c")
    await save(store, name="c", collection=SECOND_COLLECTION)


async def test_deleting_a_collection_deletes_its_saved_selections_last(store, collections, repository):
    await save(store)
    kept = await save(store, collection=SECOND_COLLECTION)
    await collection_service.delete_collection(collections, OWNER, COLLECTION, FakeAttributes(), repository)
    assert collections.deleted == [COLLECTION] and await repository.read_all(COLLECTION) == []
    assert [s.id for s in await repository.read_all(SECOND_COLLECTION)] == [kept.id]

    class Broken:
        async def delete_collection(self, cid):
            raise RuntimeError("database is locked")
    with pytest.raises(IncompleteWriteError) as error:
        await collection_service.delete_collection(collections, OWNER, SECOND_COLLECTION, FakeAttributes(), Broken())
    assert error.value.step == "delete_saved_selections"
    assert error.value.completed == {"delete_collection": 1, "delete_attribute_definitions": 1}


def test_request_models_refuse_blank_names_empty_patches_and_inconsistent_sorts():
    for body in ({"name": "  ", "query": {}}, {"name": "x" * (schemas.MAX_NAME_LENGTH + 1), "query": {}},
                 {"name": "x", "query": {"filters": {"unknown": 1}}},
                 {"name": "x", "query": {"sort": "attribute"}},
                 {"name": "x", "query": {"sort_attribute": str(ATTRIBUTE)}}):
        with pytest.raises(ValidationError):
            PostSavedSelection.model_validate(body)
    with pytest.raises(ValidationError):
        PatchSavedSelection()
    with pytest.raises(ValidationError):
        PatchSavedSelection(name=" ")
    assert PostSavedSelection.model_validate({"name": "x", "query": {}}).query == LiveQuery()


# ── HTTP ──────────────────────────────────────────────────────────────────

async def test_routes_create_list_change_and_delete_with_their_statuses(tmp_path, store, collections):
    from uuid import UUID

    from asgi_lifespan import LifespanManager
    from httpx import ASGITransport, AsyncClient

    from semant_demo.main import create_app
    from semant_demo.routes.dependencies import get_saved_selection_store
    from tests.app_support import make_test_config, offline_weaviate
    from tests.auth_support import auth_headers, register

    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    app.dependency_overrides[get_saved_selection_store] = lambda: store
    path = f"/api/user_collections/{COLLECTION}/saved-selections"
    async with LifespanManager(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await register(client, email="saved@example.com", password="StrongPassw0rd!")).status_code == 201
        headers = await auth_headers(client, "saved@example.com", "StrongPassw0rd!")
        me = UUID((await client.get("/api/users/me", headers=headers)).json()["id"])
        collections.records[COLLECTION] = (OWNER.id, {me})
        anonymous = await client.get(path)
        created = await client.post(path, headers=headers, json={
            "name": "Speakers", "query": {"filters": {"tag_ids": [str(TAG)], "q": "Praha"}, "sort": "year"}})
        taken = await client.post(path, headers=headers, json={"name": "speakers", "query": {}})
        blank = await client.post(path, headers=headers, json={"name": " ", "query": {}})
        unknown = await client.post(path, headers=headers, json={"name": "x", "query": {"filters": {"year_from": 1}}})
        selection_id = created.json()["id"]
        renamed = await client.patch(f"{path}/{selection_id}", headers=headers, json={"name": "Mluvčí"})
        empty_patch = await client.patch(f"{path}/{selection_id}", headers=headers, json={})
        listed = await client.get(path, headers=headers)
        owners = await save(store, user=OWNER, name="Owner's")
        forbidden = await client.delete(f"{path}/{owners.id}", headers=headers)
        deleted = await client.delete(f"{path}/{selection_id}", headers=headers)
        missing = await client.delete(f"{path}/{selection_id}", headers=headers)
        other = await client.get(f"/api/user_collections/{uuid4()}/saved-selections", headers=headers)

    assert anonymous.status_code == 401
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["kind"] == "live" and body["name"] == "Speakers" and body["can_edit"] is True
    assert body["query"]["filters"]["q"] == "Praha" and body["query"]["sort"] == "year"
    assert body["created_by"] == str(me) and body["unreadable"] is False
    assert taken.status_code == 400 and blank.status_code == 422 and unknown.status_code == 422
    assert renamed.status_code == 200 and renamed.json()["name"] == "Mluvčí" and empty_patch.status_code == 422
    assert [s["name"] for s in listed.json()] == ["Mluvčí"]
    assert forbidden.status_code == 403 and deleted.status_code == 204 and missing.status_code == 404
    assert other.status_code == 404
