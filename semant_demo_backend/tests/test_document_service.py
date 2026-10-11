"""Documents service (features/documents/service.py) with in-memory fakes.

Corpus reads are public; collection-scoped reads check collection read access (and, for
chunk membership, that the document is in the collection) before any document read.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from semant_demo.core.errors import InvalidRequestError, NotFoundError
from semant_demo.features.collections.access import AuthenticationRequired
from semant_demo.features.documents import service
from semant_demo.schema.chunks import TextChunk
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


#####################################
# Passage around a chunk (#244)     #
#####################################

def _chunk(order, document=DOCUMENT):
    return TextChunk(id=uuid4(), text=f"Odstavec {order}", start_page_id=uuid4(), from_page=order, to_page=order,
                     document=document, order=order)


class FakeChunks(FakeDocuments):
    """A document with chunks at orders 0, 1, 2, 4, 5 (a gap at 3), and one chunk of another document."""

    def __init__(self):
        super().__init__()
        self.chunks = [_chunk(order) for order in (0, 1, 2, 4, 5)]
        self.foreign = _chunk(0, OUTSIDE_DOCUMENT)

    async def read_chunk(self, chunk_id):
        return next((c for c in [*self.chunks, self.foreign] if c.id == chunk_id), None)

    async def read_adjacent_chunks(self, document_id, order, direction, limit):
        self.reads.append(("adjacent", direction, limit))
        if direction == "before":
            return [c for c in self.chunks if c.order < order][-limit:]
        return [c for c in self.chunks if c.order > order][:limit]


@pytest.mark.parametrize("anchor, before, after, orders, has_before, has_after", [
    (2, 1, 1, [1, 2, 4], True, True),
    (2, 5, 5, [0, 1, 2, 4, 5], False, False),
    (0, 3, 1, [0, 1], False, True),
    (5, 2, 0, [2, 4, 5], True, False),
    (4, 0, 0, [4], True, True),
])
async def test_chunk_window_is_bounded_and_in_document_order(anchor, before, after, orders, has_before, has_after):
    documents = FakeChunks()
    chunk = next(c for c in documents.chunks if c.order == anchor)

    window = await service.read_chunk_window(documents, str(DOCUMENT), str(chunk.id), before, after)

    assert [c.order for c in window.chunks] == orders
    assert (window.has_before, window.has_after) == (has_before, has_after)
    assert window.anchor_chunk_id == chunk.id
    assert (window.document.title, window.total_chunks) == ("Kronika", 3)


async def test_chunk_window_of_a_chunk_without_order_is_the_chunk_alone():
    documents = FakeChunks()
    chunk = documents.chunks[0].model_copy(update={"order": None})
    documents.chunks = [chunk]

    window = await service.read_chunk_window(documents, DOCUMENT, chunk.id, 3, 3)

    assert ([c.id for c in window.chunks], window.has_before, window.has_after) == ([chunk.id], False, False)


@pytest.mark.parametrize("case", ["unknown chunk", "chunk of another document", "malformed chunk",
                                  "malformed document"])
async def test_chunk_window_needs_a_chunk_of_the_document(case):
    documents = FakeChunks()
    document_id, chunk_id = {
        "unknown chunk": (DOCUMENT, uuid4()),
        "chunk of another document": (DOCUMENT, documents.foreign.id),
        "malformed chunk": (DOCUMENT, "not-a-uuid"),
        "malformed document": ("not-a-uuid", documents.chunks[0].id),
    }[case]

    with pytest.raises(NotFoundError):
        await service.read_chunk_window(documents, document_id, chunk_id, 1, 1)

    assert documents.reads == []


@pytest.mark.parametrize("before, after", [(-1, 0), (0, service.MAX_WINDOW_SIDE + 1)])
async def test_chunk_window_size_is_limited(before, after):
    documents = FakeChunks()

    with pytest.raises(InvalidRequestError):
        await service.read_chunk_window(documents, DOCUMENT, documents.chunks[0].id, before, after)

    assert documents.reads == []


@pytest.mark.parametrize("anchor, direction, limit, orders, has_more", [
    (4, "before", 2, [1, 2], True),
    (4, "before", 5, [0, 1, 2], False),
    (2, "after", 1, [4], True),
    (2, "after", 2, [4, 5], False),
    (5, "after", 3, [], False),
])
async def test_adjacent_chunks_extend_without_metadata_or_count(anchor, direction, limit, orders, has_more):
    documents = FakeChunks()
    chunk = next(c for c in documents.chunks if c.order == anchor)

    adjacent = await service.read_adjacent_chunks(documents, str(DOCUMENT), str(chunk.id), direction, limit)

    assert ([c.order for c in adjacent.chunks], adjacent.has_more) == (orders, has_more)
    # Only the neighbours are read: no document metadata, no chunk count aggregation.
    assert documents.reads == [("adjacent", direction, limit + 1)]


@pytest.mark.parametrize("case", ["unknown chunk", "chunk of another document"])
async def test_adjacent_chunks_need_a_chunk_of_the_document(case):
    documents = FakeChunks()
    chunk_id = uuid4() if case == "unknown chunk" else documents.foreign.id

    with pytest.raises(NotFoundError):
        await service.read_adjacent_chunks(documents, DOCUMENT, chunk_id, "after", 5)

    assert documents.reads == []


@pytest.mark.parametrize("direction, limit", [("sideways", 5), ("after", service.MAX_WINDOW_SIDE + 1), ("before", -1)])
async def test_adjacent_chunks_request_is_validated(direction, limit):
    documents = FakeChunks()

    with pytest.raises(InvalidRequestError):
        await service.read_adjacent_chunks(documents, DOCUMENT, documents.chunks[0].id, direction, limit)

    assert documents.reads == []
