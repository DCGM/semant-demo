"""Document summary service (features/summarization/service.py::summarize_document, #249)
with fake Weaviate repositories and a fake LLM gateway.

Authorization and data access are delegated entirely to
``features.documents.service.read_chunks_in_collection``: the fakes here mirror
``tests/test_document_service.py``'s ``FakeCollections``/``FakeDocuments`` so the same
access rules (owner/shared/other, document-in-collection) are exercised for the summary.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from semant_demo.config import SCRIPT_PATH
from semant_demo.core.errors import NotFoundError
from semant_demo.features.documents.schemas import Document, DocumentDetail, DocumentViewChunk
from semant_demo.features.summarization import service
from semant_demo.features.summarization.document import load_document_summarizer
from semant_demo.features.user_collections.access import AuthenticationRequired
from tests.fakes import FakeLlm

OWNER, SHARED, OTHER = (SimpleNamespace(id=uuid4(), is_superuser=False) for _ in range(3))
COLLECTION, DOCUMENT, OUTSIDE_DOCUMENT = uuid4(), uuid4(), uuid4()


def chunk(order: int, **overrides) -> DocumentViewChunk:
    fields = dict(id=uuid4(), text=f"Odstavec {order}", start_page_id=uuid4(), from_page=order + 1,
                 to_page=order + 1, document=DOCUMENT, order=order, in_user_collection=True)
    fields.update(overrides)
    return DocumentViewChunk(**fields)


class FakeCollections:
    async def read_access_record(self, cid):
        return (OWNER.id, {SHARED.id}) if cid == COLLECTION else None

    async def document_in_collection(self, document_id, cid):
        return (document_id, cid) == (DOCUMENT, COLLECTION)


class FakeDocuments:
    """Only ``read_chunks`` is needed: ``read_chunks_in_collection`` never calls the others."""

    def __init__(self, chunks: list[DocumentViewChunk], title: str = "Kronika obce Lhota"):
        self._chunks = chunks
        self._title = title
        self.reads: list[tuple] = []

    async def read_chunks(self, document_id, collection_id):
        self.reads.append((document_id, collection_id))
        if document_id != DOCUMENT:
            return None
        return DocumentDetail(document=Document(id=document_id, title=self._title), chunks=self._chunks)


def summarizer(llm, **overrides):
    s = load_document_summarizer(str(SCRIPT_PATH / "configs" / "document_summarizer.yaml"), llm)
    for key, value in overrides.items():
        setattr(s, key, value)
    return s


async def test_owner_and_shared_user_get_a_summary_citing_only_this_document():
    chunks = [chunk(0), chunk(1)]
    documents = FakeDocuments(chunks)
    llm = FakeLlm(" Shrnutí [doc1][doc2]. ")

    for user in (OWNER, SHARED):
        response = await service.summarize_document(documents, FakeCollections(), summarizer(llm), user, DOCUMENT,
                                                     COLLECTION)

        assert response.document_id == DOCUMENT
        assert response.summary == "Shrnutí [doc1][doc2]."
        assert [c.chunk_id for c in response.citations] == [c.id for c in chunks]
        assert [(c.order, c.from_page, c.to_page) for c in response.citations] == \
               [(c.order, c.from_page, c.to_page) for c in chunks]
    # The prompt labelled chunks [docN] in document order, same convention the search summarizer uses.
    [(feature, messages, _), *_] = llm.calls
    assert feature == "document_summary"
    assert "[doc1] Odstavec 0" in messages[1]["content"] and "[doc2] Odstavec 1" in messages[1]["content"]


@pytest.mark.parametrize("user, error", [(None, AuthenticationRequired), (OTHER, NotFoundError)])
async def test_denied_requests_never_read_chunks_or_call_the_provider(user, error):
    documents = FakeDocuments([chunk(0)])
    llm = FakeLlm()

    with pytest.raises(error):
        await service.summarize_document(documents, FakeCollections(), summarizer(llm), user, DOCUMENT, COLLECTION)

    assert documents.reads == []
    assert llm.calls == []


async def test_document_outside_the_collection_is_not_summarized():
    documents = FakeDocuments([chunk(0)])
    llm = FakeLlm()

    with pytest.raises(NotFoundError):
        await service.summarize_document(documents, FakeCollections(), summarizer(llm), OWNER, OUTSIDE_DOCUMENT,
                                         COLLECTION)

    assert documents.reads == []
    assert llm.calls == []


async def test_long_documents_are_truncated_to_the_configured_chunk_limit():
    chunks = [chunk(i) for i in range(5)]
    documents = FakeDocuments(chunks)
    llm = FakeLlm(lambda messages: messages[1]["content"])  # echo the prompt back to inspect it

    response = await service.summarize_document(documents, FakeCollections(), summarizer(llm, chunk_limit=3), OWNER,
                                                 DOCUMENT, COLLECTION)

    assert [c.chunk_id for c in response.citations] == [c.id for c in chunks[:3]]
    assert "[doc3] Odstavec 2" in response.summary
    assert "Odstavec 3" not in response.summary and "Odstavec 4" not in response.summary


async def test_chunks_are_summarized_in_document_order_even_when_returned_unordered():
    shuffled = [chunk(2), chunk(0), chunk(1)]
    documents = FakeDocuments(shuffled)
    llm = FakeLlm(lambda messages: messages[1]["content"])

    response = await service.summarize_document(documents, FakeCollections(), summarizer(llm), OWNER, DOCUMENT,
                                                 COLLECTION)

    assert [c.order for c in response.citations] == [0, 1, 2]
    assert response.summary.index("Odstavec 0") < response.summary.index("Odstavec 1") < \
        response.summary.index("Odstavec 2")


async def test_provider_failure_falls_back_without_leaking_the_error_or_chunk_text(caplog):
    secret_text = "TOP SECRET CHRONICLE TEXT sk-SECRET-MARKER"
    documents = FakeDocuments([chunk(0, text=secret_text)])

    def failing(messages):
        raise RuntimeError(f"provider refused prompt={messages[-1]['content']}")

    response = await service.summarize_document(documents, FakeCollections(), summarizer(FakeLlm(failing)), OWNER,
                                                 DOCUMENT, COLLECTION)

    assert response.summary == "N/A"  # the configured fallback (configs/document_summarizer.yaml)
    assert len(response.citations) == 1  # citations are still reported even though generation failed
    assert "Document summary generation failed: RuntimeError" in caplog.text
    assert secret_text not in caplog.text and "provider refused" not in caplog.text
