"""Collection access rules (features/collections/access.py), without a store."""
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from semant_demo.features.collections import access
from semant_demo.features.collections.access import AccessDenied, AuthenticationRequired, ResourceNotFound

OWNER, SHARED, OTHER, ADMIN = (SimpleNamespace(id=uuid4(), is_superuser=su) for su in (False, False, False, True))
COLLECTION, OTHER_COLLECTION = uuid4(), uuid4()
TAG, OTHER_TAG, ORPHAN_TAG, DOUBLE_TAG = uuid4(), uuid4(), uuid4(), uuid4()
SPAN, OTHER_SPAN = uuid4(), uuid4()
CHUNK, FOREIGN_CHUNK = uuid4(), uuid4()
DOCUMENT, FOREIGN_DOCUMENT = uuid4(), uuid4()


class FakeStore:
    """Only the lookups the access checks use."""

    def __init__(self, fail=False):
        records = {COLLECTION: (OWNER.id, {SHARED.id}), OTHER_COLLECTION: (OTHER.id, set())}
        tags = {TAG: [COLLECTION], OTHER_TAG: [OTHER_COLLECTION], ORPHAN_TAG: [], DOUBLE_TAG: [COLLECTION, OTHER_COLLECTION]}
        spans = {SPAN: ([TAG], [CHUNK]), OTHER_SPAN: ([OTHER_TAG], [FOREIGN_CHUNK])}
        members = {COLLECTION: {CHUNK}}
        documents = {COLLECTION: {DOCUMENT}, OTHER_COLLECTION: {FOREIGN_DOCUMENT}}

        async def read_access_record(cid):
            if fail:
                raise ConnectionError("store down")
            return records.get(cid)

        async def chunk_ids_in_collection(ids, cid, document_id=None):
            return set(ids) & members.get(cid, set())

        async def document_in_collection(document_id, cid):
            return document_id in documents.get(cid, set())

        async def read_collection_ids(ids):
            return {t: tags[t] for t in ids if t in tags}

        async def read_refs(ids):
            return {s: spans[s] for s in ids if s in spans}

        self.userCollection = SimpleNamespace(read_access_record=read_access_record,
                                              chunk_ids_in_collection=chunk_ids_in_collection,
                                              document_in_collection=document_in_collection)
        self.tag = SimpleNamespace(read_collection_ids=read_collection_ids)
        self.span = SimpleNamespace(read_refs=read_refs)


SHARED_RIGHTS = [access.require_collection_read, access.require_annotation_edit, access.require_tag_definition_edit]
OWNER_RIGHTS = [access.require_membership_edit, access.require_collection_owner]


@pytest.mark.parametrize("check", SHARED_RIGHTS + OWNER_RIGHTS, ids=lambda f: f.__name__)
async def test_owner_has_every_right(check):
    grant = await check(FakeStore(), OWNER, str(COLLECTION))

    assert grant.collection_id == COLLECTION and grant.is_owner


@pytest.mark.parametrize("check", SHARED_RIGHTS, ids=lambda f: f.__name__)
async def test_shared_user_reads_and_annotates(check):
    grant = await check(FakeStore(), SHARED, COLLECTION)

    assert not grant.is_owner


@pytest.mark.parametrize("check", OWNER_RIGHTS, ids=lambda f: f.__name__)
async def test_shared_user_cannot_change_membership_or_manage(check):
    with pytest.raises(AccessDenied):
        await check(FakeStore(), SHARED, COLLECTION)


@pytest.mark.parametrize("check", SHARED_RIGHTS + OWNER_RIGHTS, ids=lambda f: f.__name__)
@pytest.mark.parametrize("user", [OTHER, ADMIN], ids=["unrelated", "admin"])
async def test_unrelated_users_and_admins_do_not_see_the_collection(check, user):
    with pytest.raises(ResourceNotFound):
        await check(FakeStore(), user, COLLECTION)


@pytest.mark.parametrize("check", SHARED_RIGHTS + OWNER_RIGHTS, ids=lambda f: f.__name__)
async def test_anonymous_must_log_in(check):
    with pytest.raises(AuthenticationRequired):
        await check(FakeStore(), None, COLLECTION)


@pytest.mark.parametrize("collection_id", [uuid4(), "not-a-uuid"])
async def test_unknown_or_malformed_collection_is_not_found(collection_id):
    with pytest.raises(ResourceNotFound):
        await access.require_collection_read(FakeStore(), OWNER, collection_id)


async def test_store_errors_do_not_grant_access():
    with pytest.raises(ConnectionError):
        await access.require_collection_read(FakeStore(fail=True), OWNER, COLLECTION)


async def test_tag_and_span_resolve_to_their_collection():
    assert await access.collection_of_tags(FakeStore(), [str(TAG)]) == COLLECTION
    assert await access.collection_of_spans(FakeStore(), [SPAN]) == COLLECTION


@pytest.mark.parametrize("tags", [[ORPHAN_TAG], [DOUBLE_TAG], [uuid4()], [TAG, OTHER_TAG], []],
                         ids=["no-collection", "two-collections", "unknown", "mixed", "empty"])
async def test_ambiguous_or_mixed_tags_are_not_found(tags):
    with pytest.raises(ResourceNotFound):
        await access.collection_of_tags(FakeStore(), tags)


async def test_spans_from_different_collections_are_rejected():
    with pytest.raises(ResourceNotFound):
        await access.collection_of_spans(FakeStore(), [SPAN, OTHER_SPAN])


async def test_tags_and_chunks_must_belong_to_the_collection():
    store = FakeStore()
    assert await access.require_tags_in_collection(store, [TAG], COLLECTION) == [TAG]
    assert await access.require_chunks_in_collection(store, [str(CHUNK), CHUNK], COLLECTION) == [CHUNK]

    with pytest.raises(ResourceNotFound):
        await access.require_tags_in_collection(store, [OTHER_TAG], COLLECTION)
    with pytest.raises(ResourceNotFound):
        await access.require_chunks_in_collection(store, [CHUNK, FOREIGN_CHUNK], COLLECTION)


def test_parse_id_accepts_uuid_and_string():
    value = uuid4()

    assert access.parse_id(value, "X") is value
    assert access.parse_id(str(value), "X") == UUID(str(value))


async def test_document_must_be_linked_to_the_collection():
    store = FakeStore()
    assert await access.require_document_in_collection(store, str(DOCUMENT), COLLECTION) == DOCUMENT

    for document in (FOREIGN_DOCUMENT, uuid4(), "not-a-uuid"):
        with pytest.raises(ResourceNotFound):
            await access.require_document_in_collection(store, document, COLLECTION)
