"""Documents service (features/documents/service.py) with in-memory fakes.

Corpus reads are public; collection-scoped reads check collection read access (and, for
chunk membership, that the document is in the collection) before any document read.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from semant_demo.core.errors import NotFoundError
from semant_demo.features.collections.access import AuthenticationRequired
from semant_demo.features.documents import service
from semant_demo.schema.documents import Document, DocumentBrowse, DocumentDetail

OWNER, SHARED, OTHER = (SimpleNamespace(id=uuid4(), is_superuser=False) for _ in range(3))
COLLECTION, DOCUMENT, OUTSIDE_DOCUMENT = uuid4(), uuid4(), uuid4()


class FakeCollections:
    async def read_access_record(self, cid):
        return (OWNER.id, {SHARED.id}) if cid == COLLECTION else None

    async def document_in_collection(self, document_id, cid):
        return (document_id, cid) == (DOCUMENT, COLLECTION)


class FakeDocuments:
    def __init__(self):
        self.reads: list[tuple] = []

    async def read(self, document_id):
        self.reads.append(("read", document_id))
        return Document(id=document_id, title="Kronika") if document_id in (DOCUMENT, OUTSIDE_DOCUMENT) else None

    async def count_chunks(self, document_id):
        self.reads.append(("count", document_id))
        return 3

    async def browse(self, collection_id=None, **options):
        self.reads.append(("browse", collection_id, options))
        return DocumentBrowse(items=[], has_more=False, total_count=0)

    async def read_chunks(self, document_id, collection_id):
        self.reads.append(("chunks", document_id, collection_id))
        return DocumentDetail(document=Document(id=document_id), chunks=[])


async def test_corpus_reads_are_public():
    documents = FakeDocuments()

    assert (await service.read_document(documents, str(DOCUMENT))).title == "Kronika"
    assert await service.count_chunks(documents, DOCUMENT) == 3
    await service.browse(documents, FakeCollections(), None, limit=5)

    assert documents.reads[-1] == ("browse", None, {"limit": 5})


@pytest.mark.parametrize("document_id", [str(uuid4()), "not-a-uuid"])
async def test_unknown_or_malformed_document_is_not_found(document_id):
    with pytest.raises(NotFoundError):
        await service.read_document(FakeDocuments(), document_id)


@pytest.mark.parametrize("user", [OWNER, SHARED])
async def test_collection_reads_for_owner_and_shared_user(user):
    documents = FakeDocuments()

    await service.browse(documents, FakeCollections(), user, str(COLLECTION), offset=10)
    await service.read_chunks_in_collection(documents, FakeCollections(), user, str(DOCUMENT), str(COLLECTION))

    assert documents.reads == [("browse", COLLECTION, {"offset": 10}), ("chunks", DOCUMENT, COLLECTION)]


@pytest.mark.parametrize("user, error", [(None, AuthenticationRequired), (OTHER, NotFoundError)])
async def test_denied_collection_reads_read_no_documents(user, error):
    documents = FakeDocuments()

    with pytest.raises(error):
        await service.browse(documents, FakeCollections(), user, COLLECTION)
    with pytest.raises(error):
        await service.read_chunks_in_collection(documents, FakeCollections(), user, DOCUMENT, COLLECTION)

    assert documents.reads == []


async def test_document_outside_the_collection_is_not_read():
    documents = FakeDocuments()

    with pytest.raises(NotFoundError):
        await service.read_chunks_in_collection(documents, FakeCollections(), OWNER, OUTSIDE_DOCUMENT, COLLECTION)

    assert documents.reads == []
