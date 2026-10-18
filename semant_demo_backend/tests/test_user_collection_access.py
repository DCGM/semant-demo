"""Collection access rules (features/user_collections/access.py), without a store."""
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from semant_demo.features.user_collections import access
from semant_demo.features.user_collections.access import AccessDenied, AuthenticationRequired, ResourceNotFound

OWNER, SHARED, OTHER, ADMIN = (SimpleNamespace(id=uuid4(), is_superuser=su) for su in (False, False, False, True))
COLLECTION, OTHER_COLLECTION = uuid4(), uuid4()
TAG, OTHER_TAG, ORPHAN_TAG, DOUBLE_TAG = uuid4(), uuid4(), uuid4(), uuid4()
SPAN, OTHER_SPAN = uuid4(), uuid4()
CHUNK, FOREIGN_CHUNK = uuid4(), uuid4()
DOCUMENT, FOREIGN_DOCUMENT = uuid4(), uuid4()


class FakeStore:
    """Fake collection, tag and span repositories with only the lookups the access checks use."""

    def __init__(self, fail=False):
        records = {COLLECTION: (OWNER.id, {SHARED.id}), OTHER_COLLECTION: (OTHER.id, set())}
        tags = {TAG: [COLLECTION], OTHER_TAG: [OTHER_COLLECTION], ORPHAN_TAG: [], DOUBLE_TAG: [COLLECTION, OTHER_COLLECTION]}
        # Spans by the collection whose annotation tenant holds them (#327).
        spans = {COLLECTION: {SPAN}, OTHER_COLLECTION: {OTHER_SPAN}}
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

        async def read_many(cid, ids):
            return {s: f"span {s}" for s in ids if s in spans.get(cid, set())}

        self.collections = SimpleNamespace(read_access_record=read_access_record,
                                              chunk_ids_in_collection=chunk_ids_in_collection,
                                              document_in_collection=document_in_collection)
        self.tags = SimpleNamespace(read_collection_ids=read_collection_ids)
        self.spans = SimpleNamespace(read_many=read_many)


SHARED_RIGHTS = [access.require_collection_read, access.require_annotation_edit, access.require_tag_definition_edit]
OWNER_RIGHTS = [access.require_membership_edit, access.require_collection_owner]


@pytest.mark.parametrize("check", SHARED_RIGHTS + OWNER_RIGHTS, ids=lambda f: f.__name__)
async def test_owner_has_every_right(check):
    grant = await check(FakeStore().collections, OWNER, str(COLLECTION))

    assert grant.collection_id == COLLECTION and grant.is_owner


@pytest.mark.parametrize("check", SHARED_RIGHTS, ids=lambda f: f.__name__)
async def test_shared_user_reads_and_annotates(check):
    grant = await check(FakeStore().collections, SHARED, COLLECTION)

    assert not grant.is_owner


@pytest.mark.parametrize("check", OWNER_RIGHTS, ids=lambda f: f.__name__)
async def test_shared_user_cannot_change_membership_or_manage(check):
    with pytest.raises(AccessDenied):
        await check(FakeStore().collections, SHARED, COLLECTION)


@pytest.mark.parametrize("check", SHARED_RIGHTS + OWNER_RIGHTS, ids=lambda f: f.__name__)
@pytest.mark.parametrize("user", [OTHER, ADMIN], ids=["unrelated", "admin"])
async def test_unrelated_users_and_admins_do_not_see_the_collection(check, user):
    with pytest.raises(ResourceNotFound):
        await check(FakeStore().collections, user, COLLECTION)


@pytest.mark.parametrize("check", SHARED_RIGHTS + OWNER_RIGHTS, ids=lambda f: f.__name__)
async def test_anonymous_must_log_in(check):
    with pytest.raises(AuthenticationRequired):
        await check(FakeStore().collections, None, COLLECTION)


@pytest.mark.parametrize("collection_id", [uuid4(), "not-a-uuid"])
async def test_unknown_or_malformed_collection_is_not_found(collection_id):
    with pytest.raises(ResourceNotFound):
        await access.require_collection_read(FakeStore().collections, OWNER, collection_id)


async def test_store_errors_do_not_grant_access():
    with pytest.raises(ConnectionError):
        await access.require_collection_read(FakeStore(fail=True).collections, OWNER, COLLECTION)


async def test_tag_resolves_to_its_collection_and_spans_are_read_from_theirs():
    assert await access.collection_of_tags(FakeStore().tags, [str(TAG)]) == COLLECTION
    assert await access.require_spans_in_collection(FakeStore().spans, [str(SPAN)], COLLECTION) == {
        SPAN: f"span {SPAN}"}


@pytest.mark.parametrize("tags", [[ORPHAN_TAG], [DOUBLE_TAG], [uuid4()], [TAG, OTHER_TAG], []],
                         ids=["no-collection", "two-collections", "unknown", "mixed", "empty"])
async def test_ambiguous_or_mixed_tags_are_not_found(tags):
    with pytest.raises(ResourceNotFound):
        await access.collection_of_tags(FakeStore().tags, tags)


@pytest.mark.parametrize("spans", [[SPAN, OTHER_SPAN], [OTHER_SPAN], [uuid4()], ["not-a-uuid"], []],
                         ids=["mixed", "other-collection", "unknown", "malformed", "empty"])
async def test_spans_outside_the_named_collection_are_not_found(spans):
    # A span id of another collection is not a credential: it is not even looked up there.
    with pytest.raises(ResourceNotFound):
        await access.require_spans_in_collection(FakeStore().spans, spans, COLLECTION)


async def test_tags_and_chunks_must_belong_to_the_collection():
    store = FakeStore()
    assert await access.require_tags_in_collection(store.tags, [TAG], COLLECTION) == [TAG]
    assert await access.require_chunks_in_collection(store.collections, [str(CHUNK), CHUNK], COLLECTION) == [CHUNK]

    with pytest.raises(ResourceNotFound):
        await access.require_tags_in_collection(store.tags, [OTHER_TAG], COLLECTION)
    with pytest.raises(ResourceNotFound):
        await access.require_chunks_in_collection(store.collections, [CHUNK, FOREIGN_CHUNK], COLLECTION)


def test_parse_id_accepts_uuid_and_string():
    value = uuid4()

    assert access.parse_id(value, "X") is value
    assert access.parse_id(str(value), "X") == UUID(str(value))


async def test_document_must_be_linked_to_the_collection():
    store = FakeStore()
    assert await access.require_document_in_collection(store.collections, str(DOCUMENT), COLLECTION) == DOCUMENT

    for document in (FOREIGN_DOCUMENT, uuid4(), "not-a-uuid"):
        with pytest.raises(ResourceNotFound):
            await access.require_document_in_collection(store.collections, document, COLLECTION)
