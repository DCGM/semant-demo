"""Search chat (features/chat/service.py, #245, ADR 0012) with fake search backends and a
fake streaming LLM: only the chosen results, read again under the search's criteria and
collection, one citation numbering per request, input fitting."""
from uuid import uuid4

import pytest

from semant_demo.adapters.llm.usage import LlmInputTooLarge
from semant_demo.core.errors import InvalidRequestError, NotFoundError
from semant_demo.features.chat import service
from semant_demo.features.chat.schemas import ChatTurn, SearchChatRequest
from semant_demo.features.documents.criteria import ChunkFilters, DocumentFilters, SearchCriteria
from semant_demo.features.user_collections.access import AuthenticationRequired
from tests.fakes import FakeOperation
from tests.test_chat.test_document_chat import FakeLlm
from tests.test_search_service import COLLECTION, DEFINITIONS, FOREIGN, OTHER, OWNER, SHARED, FakeChunks, backends, \
    hit


def results(count: int, text="Odstavec") -> list:
    hits = [hit(f"{text} {i}") for i in range(count)]
    for i, h in enumerate(hits):
        h.document_object.title, h.document_object.yearIssued = f"Kronika {i}", 1900 + i
    return hits


def ask(ids, question="Kdo psal kroniku?", history=(), criteria=None, collection=None) -> SearchChatRequest:
    return SearchChatRequest(question=question, history=list(history), chunk_ids=list(ids),
                             criteria=criteria or SearchCriteria(text_query="kronika"),
                             user_collection_id=str(collection) if collection else None)


async def run(llm, chunks, request, user=None):
    prepared = await service.prepare_search_chat(backends(chunks), llm, user, request, DEFINITIONS)
    return prepared, [event async for event in prepared.events(llm, FakeOperation())]


def prompt(llm) -> str:
    return llm.calls[-1][-1]["content"]


async def test_only_the_chosen_results_are_given_in_result_order_with_their_documents():
    hits = results(4)
    chunks = FakeChunks(hits)
    llm = FakeLlm(deltas=["Kronikář [doc1]", " a [doc2]."])

    prepared, events = await run(llm, chunks, ask([hits[2].id, hits[0].id]))

    assert [c.id for c in prepared.chunks] == [hits[2].id, hits[0].id]
    assert "[doc1] (Kronika 2, 1902) Odstavec 2" in prompt(llm)
    assert "[doc2] (Kronika 0, 1900) Odstavec 0" in prompt(llm)
    assert 'found by the search for "kronika"' in prompt(llm)
    assert "Odstavec 1" not in prompt(llm) and "Odstavec 3" not in prompt(llm)
    assert llm.calls[-1][0]["content"] == service.SEARCH_PROMPT
    assert [(s.citation, s.chunk_id, s.document_id) for s in events[-2].sources] == [
        (1, hits[2].id, hits[2].document), (2, hits[0].id, hits[0].document)]
    assert (events[-1].coverage, events[-1].used_chunks, events[-1].total_chunks) == ("all", 2, 2)


async def test_ids_the_search_could_not_return_are_left_out_never_replaced():
    # Another collection, a deleted chunk or one no longer matching the criteria.
    hits = results(3)
    chunks = FakeChunks(hits)
    chunks.out_of_scope = {hits[1].id}
    llm = FakeLlm()

    prepared, _ = await run(llm, chunks, ask([hits[0].id, hits[1].id, uuid4(), hits[0].id]))

    assert [c.id for c in prepared.chunks] == [hits[0].id]
    assert chunks.queries == []  # nothing is ranked again
    assert "Odstavec 2" not in prompt(llm)


async def test_the_passages_are_read_under_the_search_criteria_and_collection():
    hits = results(2)
    chunks = FakeChunks(hits)
    criteria = SearchCriteria(text_query="kronika", document_filters=DocumentFilters(year_min=1850),
                              chunk_filters=ChunkFilters(languages=["CES"]))

    await run(FakeLlm(), chunks, ask([hits[0].id], criteria=criteria, collection=COLLECTION), user=SHARED)

    [(read, scope)] = chunks.read
    assert read == [hits[0].id]
    assert scope.collection_id == COLLECTION
    assert scope.document_conditions and [(c.prop, c.values) for c in scope.chunk_conditions] == [("language", ("ces",))]


async def test_results_that_can_no_longer_be_read_are_not_found():
    hits = results(1)
    chunks = FakeChunks(hits)
    chunks.out_of_scope = {hits[0].id}
    llm = FakeLlm()

    with pytest.raises(NotFoundError):
        await run(llm, chunks, ask([hits[0].id]))
    assert llm.calls == []


@pytest.mark.parametrize("user, collection, error", [
    (None, COLLECTION, AuthenticationRequired), (OTHER, COLLECTION, NotFoundError), (OWNER, FOREIGN, NotFoundError)])
async def test_a_collection_the_user_cannot_read_is_refused_before_reading(user, collection, error):
    hits = results(1)
    chunks, llm = FakeChunks(hits), FakeLlm()

    with pytest.raises(error):
        await run(llm, chunks, ask([hits[0].id], collection=collection), user=user)
    assert chunks.read == [] and llm.calls == []


async def test_invalid_filters_are_refused_before_reading():
    hits = results(1)
    chunks = FakeChunks(hits)
    criteria = SearchCriteria(text_query="x", chunk_filters=ChunkFilters(classifications={"complexity": ["trivial"]}))

    with pytest.raises(InvalidRequestError):
        await run(FakeLlm(), chunks, ask([hits[0].id], criteria=criteria))
    assert chunks.read == []


async def test_citations_outside_the_scope_are_not_sources_and_history_is_renumbered():
    hits = results(3)
    a, b, c = hits
    # The earlier answer was about a, b and c; the next question is about c and a only.
    history = [ChatTurn(role="user", text="Kdo?"),
               ChatTurn(role="assistant", text="A [doc1], B [doc2], C [doc3].", chunk_ids=[a.id, b.id, c.id])]
    llm = FakeLlm(deltas=["Viz [doc2] a [doc5]."])

    _, events = await run(llm, FakeChunks(hits), ask([c.id, a.id], history=history))

    assert llm.calls[-1][1:-1] == [{"role": "user", "content": "Kdo?"},
                                   {"role": "assistant", "content": "A [doc2], B , C [doc1]."}]
    assert [(s.citation, s.chunk_id) for s in events[-2].sources] == [(2, a.id)]


async def test_results_beyond_the_input_limit_are_cut_and_the_answer_says_so():
    hits = results(10, text="slovo " * 400)  # ~2400 characters each
    llm = FakeLlm(max_input_tokens=2000)  # ~8000 characters

    prepared, events = await run(llm, FakeChunks(hits), ask([h.id for h in hits]))

    used = len(prepared.chunks)
    assert 0 < used < 10 and [c.id for c in prepared.chunks] == [h.id for h in hits[:used]]
    assert f"only the first {used} of 10 results fit" in prompt(llm)
    assert (events[-1].coverage, events[-1].used_chunks, events[-1].total_chunks) == ("part", used, 10)
    assert sum(len(m["content"]) for m in llm.calls[-1]) <= 2000 * 4


async def test_a_first_result_above_the_limit_is_refused_before_streaming():
    hits = results(1, text="x" * 1000)
    llm = FakeLlm(max_input_tokens=100)

    with pytest.raises(LlmInputTooLarge, match="first search result"):
        await run(llm, FakeChunks(hits), ask([hits[0].id]))
    assert llm.calls == []


def test_the_request_needs_results_and_takes_no_unknown_fields():
    with pytest.raises(ValueError):
        SearchChatRequest(question="?", chunk_ids=[], criteria=SearchCriteria())
    with pytest.raises(ValueError):
        SearchChatRequest(question="?", chunk_ids=[uuid4()], criteria=SearchCriteria(), sources=["text"])
