"""Document chat (features/chat/service.py, #248, ADR 0012) with fake repositories and a
fake streaming LLM: access, only the document's chunks in the collection, one citation
numbering per request, input fitting and stream errors."""
from uuid import uuid4

import pytest

from semant_demo.adapters.llm.models import FeatureLimits, FeaturePolicy, ModelCatalog, ModelTier
from semant_demo.adapters.llm.usage import LlmInputTooLarge, LlmNotConfigured, LlmOperationLimitExceeded
from semant_demo.core.errors import NotFoundError
from semant_demo.features.chat import service
from semant_demo.features.chat.schemas import ChatTurn, ContextChatRequest
from semant_demo.features.user_collections.access import AuthenticationRequired
from tests.fakes import FakeOperation
from tests.test_summarization.test_document_service import COLLECTION, DOCUMENT, OTHER, OUTSIDE_DOCUMENT, OWNER, \
    SHARED, FakeCollections, FakeDocuments, chunk


class FakeLlm:
    """Streams ``deltas`` (then raises ``error``) and records the messages of each call."""

    def __init__(self, deltas=("Odpověď [doc1].",), error: Exception | None = None, max_input_tokens: int = 48000):
        self.catalog = ModelCatalog(tiers={}, features={service.FEATURE: FeaturePolicy(
            default=ModelTier.small, allowed=frozenset({ModelTier.small}),
            limits=FeatureLimits(max_input_tokens=max_input_tokens))})
        self.deltas = list(deltas)
        self.error = error
        self.calls: list[list[dict[str, str]]] = []

    def operation(self, feature, budget=None):
        return FakeOperation(budget)

    async def stream(self, feature, messages):
        assert feature == service.FEATURE
        self.calls.append(list(messages))
        for delta in self.deltas:
            yield delta
        if self.error is not None:
            raise self.error


def ask(question="Kdo psal kroniku?", history=()):
    return ContextChatRequest(question=question, history=list(history))


async def run(llm, chunks, user=OWNER, request=None, document=DOCUMENT):
    prepared = await service.prepare_document_chat(FakeDocuments(chunks), FakeCollections(), llm, user, COLLECTION,
                                                   document, request or ask())
    return prepared, [event async for event in prepared.events(llm, FakeOperation())]


def prompt(llm) -> str:
    return llm.calls[-1][-1]["content"]


async def test_owner_and_shared_user_chat_about_only_the_chunks_in_the_collection():
    inside, outside, last = chunk(0), chunk(1, in_user_collection=False, text="Cizí odstavec"), chunk(2)
    llm = FakeLlm(deltas=["Kronikář [doc1]", " a [doc2]."])

    for user in (OWNER, SHARED):
        prepared, events = await run(llm, [last, outside, inside], user=user)

        assert [c.id for c in prepared.chunks] == [inside.id, last.id]
        assert "[doc1] Odstavec 0" in prompt(llm) and "[doc2] Odstavec 2" in prompt(llm)
        assert "Cizí odstavec" not in "".join(m["content"] for m in llm.calls[-1])
        assert [e.event for e in events] == ["delta", "delta", "sources", "end"]
        assert [(s.citation, s.chunk_id) for s in events[2].sources] == [(1, inside.id), (2, last.id)]
        assert (events[3].coverage, events[3].used_chunks, events[3].total_chunks) == ("all", 2, 2)


@pytest.mark.parametrize("user, document, error", [
    (None, DOCUMENT, AuthenticationRequired), (OTHER, DOCUMENT, NotFoundError), (OWNER, OUTSIDE_DOCUMENT, NotFoundError)])
async def test_denied_requests_read_no_chunks_and_call_no_model(user, document, error):
    documents, llm = FakeDocuments([chunk(0)]), FakeLlm()

    with pytest.raises(error):
        await service.prepare_document_chat(documents, FakeCollections(), llm, user, COLLECTION, document, ask())

    assert documents.reads == [] and llm.calls == []


async def test_a_document_without_chunks_in_the_collection_is_not_found():
    with pytest.raises(NotFoundError):
        await run(FakeLlm(), [chunk(0, in_user_collection=False)])


async def test_citations_the_server_cannot_map_are_not_sources():
    llm = FakeLlm(deltas=["Viz [doc2], [doc9] a znovu [doc2][doc1]."])

    _, events = await run(llm, [chunk(0), chunk(1)])

    assert [s.citation for s in events[-2].sources] == [2, 1]


async def test_history_citations_are_renumbered_and_those_out_of_scope_removed():
    a, b, gone = chunk(0), chunk(1), uuid4()
    history = [ChatTurn(role="user", text="Co píše o [doc5] obci?"),
               ChatTurn(role="assistant", text="Obec [doc1], kronikář [doc2], jinde [doc3].",
                        chunk_ids=[b.id, gone, a.id])]
    llm = FakeLlm()

    await run(llm, [a, b], request=ask(history=history))

    turns = llm.calls[-1][1:-1]
    assert turns == [{"role": "user", "content": "Co píše o  obci?"},
                     {"role": "assistant", "content": "Obec [doc2], kronikář , jinde [doc1]."}]


async def test_a_long_document_is_cut_to_its_first_chunks_and_says_so():
    chunks = [chunk(i, text="slovo " * 400) for i in range(10)]  # ~2400 characters each
    llm = FakeLlm(max_input_tokens=2000)  # ~8000 characters

    prepared, events = await run(llm, chunks)

    used = len(prepared.chunks)
    assert 0 < used < 10 and [c.id for c in prepared.chunks] == [c.id for c in chunks[:used]]
    assert f"only its first {used} of 10 passages" in prompt(llm)
    assert (events[-1].coverage, events[-1].used_chunks, events[-1].total_chunks) == ("part", used, 10)
    assert sum(len(m["content"]) for m in llm.calls[-1]) <= 2000 * 4


async def test_the_oldest_history_turns_are_dropped_to_fit_and_history_starts_with_a_question():
    history = [ChatTurn(role="user", text="stará otázka " * 200), ChatTurn(role="assistant", text="stará odpověď " * 200),
               ChatTurn(role="user", text="nová otázka"), ChatTurn(role="assistant", text="nová odpověď")]
    llm = FakeLlm(max_input_tokens=1500)

    prepared, _ = await run(llm, [chunk(0), chunk(1)], request=ask(history=history))

    assert len(prepared.chunks) == 2
    assert [m["content"] for m in llm.calls[-1][1:-1]] == ["nová otázka", "nová odpověď"]


async def test_history_never_cuts_a_document_that_fits():
    # Passages take most of the ~8000 characters; the long history gets only the room left.
    chunks = [chunk(i, text="slovo " * 200) for i in range(5)]  # ~1200 characters each
    history = [ChatTurn(role="user", text="otázka " * 300), ChatTurn(role="assistant", text="odpověď " * 300),
               ChatTurn(role="user", text="nová otázka"), ChatTurn(role="assistant", text="nová odpověď")]
    llm = FakeLlm(max_input_tokens=2000)

    prepared, events = await run(llm, chunks, request=ask(history=history))

    assert len(prepared.chunks) == 5 and events[-1].coverage == "all"
    assert [m["content"] for m in llm.calls[-1][1:-1]] == ["nová otázka", "nová odpověď"]


async def test_an_exchange_with_a_turn_left_empty_by_removed_citations_is_not_sent():
    # The question of an answer left empty goes too, so questions and answers still alternate.
    history = [ChatTurn(role="user", text="Kde?"), ChatTurn(role="assistant", text=" [doc1] ", chunk_ids=[uuid4()]),
               ChatTurn(role="user", text="[doc1]"), ChatTurn(role="assistant", text="Nevím."),
               ChatTurn(role="user", text="Kdo?"), ChatTurn(role="assistant", text="Kronikář.")]
    llm = FakeLlm()

    await run(llm, [chunk(0)], request=ask(history=history))

    assert [m["content"] for m in llm.calls[-1][1:-1]] == ["Kdo?", "Kronikář."]


async def test_a_question_with_a_first_chunk_above_the_limit_is_refused_before_streaming():
    llm = FakeLlm(max_input_tokens=100)

    with pytest.raises(LlmInputTooLarge):
        await run(llm, [chunk(0, text="x" * 1000)])

    assert llm.calls == []


@pytest.mark.parametrize("error, code, message", [
    (LlmInputTooLarge("Too large."), "too_large", "Too large."),
    (LlmOperationLimitExceeded("No more calls."), "refused", "No more calls."),
    (LlmNotConfigured("OPENAI_API_KEY is not configured on the server"), "failed",
     "OPENAI_API_KEY is not configured on the server"),
    (RuntimeError("provider echoed Kdo psal kroniku?"), "failed", service.FAILED_MESSAGE),
])
async def test_stream_errors_end_with_a_safe_error_event(error, code, message, caplog):
    llm = FakeLlm(deltas=["Část"], error=error)

    _, events = await run(llm, [chunk(0)])

    assert [e.event for e in events] == ["delta", "sources", "error"]
    assert (events[-1].code, events[-1].message) == (code, message)
    assert "Kdo psal" not in caplog.text


async def test_a_partial_answer_keeps_its_citations_and_a_failure_before_any_text_has_no_sources():
    first, second = chunk(0), chunk(1)
    cut = FakeLlm(deltas=["Kronikář [doc2] psal"], error=RuntimeError("provider failed"))
    nothing = FakeLlm(deltas=[], error=RuntimeError("provider failed"))

    _, partial = await run(cut, [first, second])
    _, empty = await run(nothing, [first, second])

    assert [(s.citation, s.chunk_id) for s in partial[1].sources] == [(2, second.id)]
    assert [e.event for e in empty] == ["error"]


async def test_the_operation_is_entered_and_left_around_the_stream():
    llm, operation = FakeLlm(), FakeOperation()
    prepared = await service.prepare_document_chat(FakeDocuments([chunk(0)]), FakeCollections(), llm, OWNER,
                                                   COLLECTION, DOCUMENT, ask())

    events = [event async for event in prepared.events(llm, operation)]

    assert operation.events == ["enter", "exit"] and events[-1].event == "end"

