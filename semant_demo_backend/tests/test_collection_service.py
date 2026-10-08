"""Collections service (features/collections/service.py) called directly, without HTTP or a store.

The service enforces access itself, so denied calls must not reach any repository write
or user lookup.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from semant_demo.core.errors import InvalidRequestError, NotFoundError
from semant_demo.features.collections import service
from semant_demo.features.collections.access import AccessDenied, AuthenticationRequired
from semant_demo.features.collections.schemas import Collection, PatchCollection, PostCollection
from semant_demo.users.schemas import UserSearchResult

OWNER, SHARED, OTHER = (SimpleNamespace(id=uuid4(), name=n, is_superuser=False) for n in ("Owner", "Shared", "Other"))
ADMIN = SimpleNamespace(id=uuid4(), name="Admin", is_superuser=True)
COLLECTION, CHUNK, DOCUMENT = uuid4(), uuid4(), uuid4()
NOW = datetime(2026, 10, 8, tzinfo=timezone.utc)


def collection(**update) -> Collection:
    return Collection(id=COLLECTION, name="C", owner="Owner", created_at=NOW, updated_at=NOW, color="red", **update)


class FakeCollections:
    """Owner/shared record for one collection; every other method is recorded and returns ``result``."""

    def __init__(self, result=None):
        self.calls = []
        self.result = result

    async def read_access_record(self, cid):
        return (OWNER.id, {SHARED.id}) if cid == COLLECTION else None

    async def document_in_collection(self, document_id, cid):
        return document_id == DOCUMENT and cid == COLLECTION

    def __getattr__(self, name):
        async def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self.result
        return record


class FakeUsers:
    def __init__(self, *known):
        self.known = {u.id: UserSearchResult(id=u.id, name=u.name) for u in known}
        self.calls = 0

    async def get_user(self, user_id):
        self.calls += 1
        return self.known.get(user_id)

    async def get_users(self, ids):
        self.calls += 1
        return [self.known[i] for i in ids if i in self.known]


MEMBERSHIP_WRITES = [
    lambda c, u: service.add_chunk(c, u, COLLECTION, str(CHUNK)),
    lambda c, u: service.remove_chunk(c, u, COLLECTION, str(CHUNK)),
    lambda c, u: service.add_document(c, u, COLLECTION, str(DOCUMENT)),
    lambda c, u: service.remove_document(c, u, COLLECTION, str(DOCUMENT)),
]
OWNER_WRITES = [
    lambda c, u: service.update_collection(c, u, COLLECTION, PatchCollection(name="x")),
    lambda c, u: service.delete_collection(c, u, COLLECTION),
    lambda c, u: service.share_collection(c, FakeUsers(OTHER), u, COLLECTION, OTHER.id),
    lambda c, u: service.unshare_collection(c, u, COLLECTION, SHARED.id),
]
READS = [
    lambda c, u: service.get_collection(c, u, COLLECTION),
    lambda c, u: service.get_collection_stats(c, u, COLLECTION),
    lambda c, u: service.list_documents(c, u, COLLECTION),
    lambda c, u: service.list_tags(c, FakeCollections([]), u, COLLECTION),
    lambda c, u: service.list_members(c, FakeUsers(), u, COLLECTION),
    lambda c, u: service.get_document_stats(c, u, COLLECTION, DOCUMENT),
    lambda c, u: service.get_document_chunks(c, u, COLLECTION, DOCUMENT),
    lambda c, u: service.get_neighbour_chunk(c, u, COLLECTION, DOCUMENT, "next", 0),
    lambda c, u: service.get_chunks_in_range(c, u, COLLECTION, DOCUMENT, None, None),
]


@pytest.mark.parametrize("call", MEMBERSHIP_WRITES + OWNER_WRITES)
async def test_shared_user_cannot_change_membership_metadata_or_sharing(call):
    collections = FakeCollections()

    with pytest.raises(AccessDenied):
        await call(collections, SHARED)
    assert collections.calls == []


@pytest.mark.parametrize("call", MEMBERSHIP_WRITES + OWNER_WRITES + READS)
@pytest.mark.parametrize("user, error", [(OTHER, NotFoundError), (ADMIN, NotFoundError), (None, AuthenticationRequired)],
                         ids=["unrelated", "admin", "anonymous"])
async def test_users_without_access_reach_no_repository_call(call, user, error):
    collections = FakeCollections()

    with pytest.raises(error):
        await call(collections, user)
    assert collections.calls == []


@pytest.mark.parametrize("call", MEMBERSHIP_WRITES + OWNER_WRITES)
async def test_owner_writes_reach_the_repository(call):
    collections = FakeCollections(collection())

    await call(collections, OWNER)

    assert len(collections.calls) == 1


@pytest.mark.parametrize("call", READS)
async def test_shared_user_reads(call):
    await call(FakeCollections(collection()), SHARED)


async def test_document_of_another_collection_is_not_found():
    collections = FakeCollections()

    with pytest.raises(NotFoundError):
        await service.get_document_chunks(collections, OWNER, COLLECTION, uuid4())
    assert collections.calls == []


@pytest.mark.parametrize("user, shared_with_me", [(OWNER, False), (SHARED, True)])
async def test_get_collection_marks_shared_collections(user, shared_with_me):
    result = await service.get_collection(FakeCollections(collection()), user, str(COLLECTION))

    assert result.is_shared_with_me is shared_with_me


async def test_created_collection_is_owned_by_the_caller():
    collections = FakeCollections(collection())
    request = PostCollection(name="C", color="red")

    await service.create_collection(collections, OWNER, request)

    assert collections.calls == [("create", (request,), {"owner_id": OWNER.id, "owner_name": "Owner"})]
    with pytest.raises(AuthenticationRequired):
        await service.create_collection(collections, None, request)


async def test_listing_is_for_the_caller_and_needs_login():
    collections = FakeCollections([])

    await service.list_collections(collections, SHARED)

    assert collections.calls == [("read_all", (SHARED.id,), {})]
    with pytest.raises(AuthenticationRequired):
        await service.list_collections(collections, None)


async def test_sharing_with_the_owner_or_an_unknown_user_writes_nothing():
    collections = FakeCollections()

    with pytest.raises(InvalidRequestError):
        await service.share_collection(collections, FakeUsers(OWNER), OWNER, COLLECTION, OWNER.id)
    with pytest.raises(NotFoundError):
        await service.share_collection(collections, FakeUsers(), OWNER, COLLECTION, OTHER.id)
    assert collections.calls == []


async def test_members_are_looked_up_in_the_user_store():
    collections = FakeCollections([SHARED.id, uuid4()])

    members = await service.list_members(collections, FakeUsers(SHARED), SHARED, COLLECTION)

    assert [m.id for m in members] == [SHARED.id]


@pytest.mark.parametrize("user, error", [(OWNER, AccessDenied), (SHARED, AccessDenied), (None, AuthenticationRequired)],
                         ids=["owner", "shared", "anonymous"])
async def test_owner_change_is_admin_only(user, error):
    collections, users = FakeCollections(), FakeUsers(OTHER)

    with pytest.raises(error):
        await service.change_owner(collections, users, user, COLLECTION, OTHER.id)
    assert collections.calls == [] and users.calls == 0


async def test_admin_changes_owner_to_an_existing_user():
    collections = FakeCollections(collection())

    await service.change_owner(collections, FakeUsers(OTHER), ADMIN, str(COLLECTION), OTHER.id)

    assert collections.calls == [("set_owner", (COLLECTION, OTHER.id, "Other"), {})]
    with pytest.raises(NotFoundError):
        await service.change_owner(FakeCollections(), FakeUsers(), ADMIN, COLLECTION, uuid4())
