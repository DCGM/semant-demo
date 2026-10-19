"""Span discussion chat (features/annotations/span_chat.py) with in-memory fakes.

Access and request validation happen before anything is streamed; denied requests read
no context and call no provider. Real-store context reads: tests/integration/test_span_chat.py.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from semant_demo.adapters.sql.tenant_activity import NoTenantActivity
from semant_demo.core.errors import InvalidRequestError, NotFoundError
from semant_demo.features.annotations import span_chat
from semant_demo.features.annotations.schemas import DiscussSpanRequest, SpanType, Tag, TagSpan, AnnotationChunk
from semant_demo.features.user_collections.access import AuthenticationRequired
from semant_demo.features.documents.schemas import Document
from tests.fakes import FakeStreamingChat

OWNER, SHARED, OTHER = (SimpleNamespace(id=uuid4(), is_superuser=False) for _ in range(3))
COLLECTION, DOCUMENT, TAG = uuid4(), uuid4(), uuid4()
OTHER_COLLECTION = uuid4()
CHUNKS = [AnnotationChunk(id=uuid4(), document_id=DOCUMENT, order=i, text=t)
          for i, t in enumerate(["Before. ", "Jan Nov", "ák went home. ", "After."])]


def span(start: int, end: int, chunk: int = 1, chunks=CHUNKS) -> TagSpan:
    return TagSpan(id=str(uuid4()), chunkId=str(chunks[chunk].id), tagId=str(TAG), start=start, end=end,
                   type=SpanType.pos)


class FakeStore:
    def __init__(self, stored: TagSpan, chunks=CHUNKS):
        self.span = stored
        self.chunks = chunks
        self.reads: list[str] = []
        self.collections = SimpleNamespace(read_access_record=self._access)
        self.tags = SimpleNamespace(read_collection_ids=self._tag_collections, read=self._tag)
        self.spans = SimpleNamespace(read_many=self._spans_of, read=self._span)
        self.activity = NoTenantActivity()
        self.documents = SimpleNamespace(read_chunk_text=self._chunk, read=self._document,
                                         read_following_chunk_texts=self._following)

    async def _access(self, cid):
        return {COLLECTION: (OWNER.id, {SHARED.id}), OTHER_COLLECTION: (OWNER.id, set())}.get(cid)

    async def _tag_collections(self, ids):
        return {t: [COLLECTION] for t in ids if t == TAG}

    async def _spans_of(self, cid, ids):
        # The span is stored in COLLECTION's tenant only.
        return {i: self.span for i in ids if str(i) == self.span.id and cid == COLLECTION}

    async def _span(self, cid, span_id):
        self.reads.append("span")
        return self.span if str(span_id) == self.span.id and cid == COLLECTION else None

    async def _tag(self, tag_id):
        self.reads.append("tag")
        return Tag(id=TAG, name="Person", shorthand="P", color="#000", pictogram="", definition="A human.",
                   examples=["Karel"])

    async def _chunk(self, chunk_id):
        self.reads.append("chunk")
        return next((c for c in self.chunks if c.id == chunk_id), None)

    async def _document(self, document_id):
        self.reads.append("document")
        return Document(id=DOCUMENT, title="Kronika", author=["A", "B"])

    async def _following(self, document_id, after_order, limit):
        self.reads.append(f"following:{after_order}:{limit}")
        return [c for c in self.chunks if c.order > after_order][:limit]


def request(stored: TagSpan, *messages: tuple[str, str]) -> DiscussSpanRequest:
    turns = messages or (("user", "Fits?"),)
    return DiscussSpanRequest(collection_id=str(COLLECTION), span_id=stored.id,
                              messages=[{"role": r, "content": c} for r, c in turns])


async def run(store, provider, user=OWNER, req=None, context_chars=5, history_limit=20) -> list[str]:
    discussion = await span_chat.prepare_discussion(store, user, req or request(store.span), provider,
                                                    context_chars=context_chars, history_limit=history_limit)
    return [d async for d in discussion.deltas()]


@pytest.mark.parametrize("user, error", [(None, AuthenticationRequired), (OTHER, NotFoundError)])
async def test_denied_discussion_reads_no_context_and_calls_no_provider(user, error):
    store, provider = FakeStore(span(0, 3)), FakeStreamingChat()

    with pytest.raises(error):
        await span_chat.prepare_discussion(store, user, request(store.span), provider,
                                           context_chars=5, history_limit=20)

    assert store.reads == [] and provider.calls == []


async def test_unknown_span_is_not_found():
    store = FakeStore(span(0, 3))
    req = DiscussSpanRequest(collection_id=str(COLLECTION), span_id=str(uuid4()),
                             messages=[{"role": "user", "content": "?"}])

    with pytest.raises(NotFoundError):
        await span_chat.prepare_discussion(store, OWNER, req, FakeStreamingChat(), context_chars=5, history_limit=20)


async def test_span_named_with_another_readable_collection_is_not_found():
    # The owner can read OTHER_COLLECTION too, but the span is not one of its spans.
    store = FakeStore(span(0, 3))
    req = DiscussSpanRequest(collection_id=str(OTHER_COLLECTION), span_id=store.span.id,
                             messages=[{"role": "user", "content": "?"}])

    with pytest.raises(NotFoundError):
        await span_chat.prepare_discussion(store, OWNER, req, FakeStreamingChat(), context_chars=5, history_limit=20)
    assert store.reads == []


@pytest.mark.parametrize("messages", [(), (("user", "a"), ("assistant", "b"))])
async def test_invalid_history_is_refused_before_access(messages):
    store = FakeStore(span(0, 3))
    req = DiscussSpanRequest(collection_id=str(COLLECTION), span_id=store.span.id,
                             messages=[{"role": r, "content": c} for r, c in messages])

    with pytest.raises(InvalidRequestError):
        await span_chat.prepare_discussion(store, None, req, FakeStreamingChat(), context_chars=5, history_limit=20)


async def test_shared_user_discusses_a_span_with_document_and_tag_context():
    store, provider = FakeStore(span(0, 3)), FakeStreamingChat(["Fits", " the tag."])

    assert await run(store, provider, user=SHARED) == ["Fits", " the tag."]

    instructions, turns = provider.calls[0]
    assert instructions.startswith(span_chat.SYSTEM_PROMPT)
    assert "- Title: Kronika" in instructions and "- Author(s): A, B" in instructions
    assert "- Name: Person" in instructions and "  * Karel" in instructions
    assert 'SPAN TEXT (verbatim, 3 chars): "Jan"' in instructions
    assert "<<<SPAN>>>Jan<<<END_SPAN>>> Nov" in instructions
    # The window (5 characters) is not filled inside the chunk, so neighbours are added.
    assert "[earlier in document, ~5 chars] ...ore. \n<<<SPAN>>>" in instructions
    assert "[later in document, ~5 chars] ák we..." in instructions
    assert turns == [{"role": "user", "content": "Fits?"}]


async def test_cross_chunk_span_reads_the_following_chunks():
    # "Jan Nov" + "ák went home. ": the span "Jan Novák" ends in the next chunk.
    store, provider = FakeStore(span(0, 9)), FakeStreamingChat()

    await run(store, provider)

    instructions = provider.calls[0][0]
    assert 'SPAN TEXT (verbatim, 9 chars): "Jan Novák"' in instructions
    assert "<<<SPAN>>>Jan Novák<<<END_SPAN>>> went" in instructions
    # The following chunk is part of the span, not repeated as later context.
    assert "[later in document, ~5 chars] After..." in instructions
    assert "following:1:8" in store.reads


# Span offsets are UTF-16 code units (ADR 0006): a non-BMP character counts as two.
EMOJI_CHUNKS = [AnnotationChunk(id=uuid4(), document_id=DOCUMENT, order=i, text=t)
                for i, t in enumerate(["Before. ", "😀 Karel 😀 Nov", "ák went home. ", "After."])]


@pytest.mark.parametrize("start, end, expected", [
    # Non-BMP characters before and inside the span ("😀 " is 3 units).
    (3, 11, "<<<SPAN>>>Karel 😀<<<END_SPAN>>> Nov"),
    # Cross-chunk: "😀 Karel 😀 Nov" is 15 units, so end 17 is 2 units into the next chunk.
    (12, 17, "<<<SPAN>>>Novák<<<END_SPAN>>> went"),
])
async def test_span_offsets_after_non_bmp_characters_are_utf16(start, end, expected):
    store, provider = FakeStore(span(start, end, 1, EMOJI_CHUNKS), EMOJI_CHUNKS), FakeStreamingChat()

    await run(store, provider)

    assert expected in provider.calls[0][0]


async def test_history_is_limited_to_the_latest_messages():
    store, provider = FakeStore(span(0, 3)), FakeStreamingChat()
    req = request(store.span, ("user", "1"), ("assistant", "2"), ("user", "3"))

    await run(store, provider, req=req, history_limit=2)

    assert [t["content"] for t in provider.calls[0][1]] == ["2", "3"]


async def test_span_deleted_after_the_check_fails_the_stream_without_a_provider_call():
    store, provider = FakeStore(span(0, 3)), FakeStreamingChat()
    discussion = await span_chat.prepare_discussion(store, OWNER, request(store.span), provider,
                                                    context_chars=5, history_limit=20)
    store.span = span(0, 3)

    with pytest.raises(ValueError, match="not found"):
        [d async for d in discussion.deltas()]
    assert provider.calls == []


# ── HTTP: NDJSON events ────────────────────────────────────────────────────

async def _events(store, provider) -> list[dict]:
    import json

    from semant_demo.features.annotations.span_chat_routes import _stream

    discussion = await span_chat.prepare_discussion(store, OWNER, request(store.span), provider,
                                                    context_chars=5, history_limit=20)
    return [json.loads(line) async for line in _stream(discussion, provider.operation())]


async def test_stream_ends_with_done():
    assert await _events(FakeStore(span(0, 3)), FakeStreamingChat(["a", "b"])) == \
        [{"delta": "a"}, {"delta": "b"}, {"done": True}]


async def test_provider_failure_mid_stream_ends_with_an_error_event():
    events = await _events(FakeStore(span(0, 3)), FakeStreamingChat(["a"], error=RuntimeError("quota")))

    assert events == [{"delta": "a"}, {"error": "The assistant reply failed."}]


SECRET = "sk-SECRET-MARKER-7f3a"


async def test_provider_error_text_reaches_neither_the_client_nor_the_log(caplog):
    error = RuntimeError(f"401 key={SECRET} prompt=Jan Novák")

    events = await _events(FakeStore(span(0, 3)), FakeStreamingChat(["a"], error=error))

    assert events[-1] == {"error": "The assistant reply failed."}
    assert "Span discussion stream failed: RuntimeError" in caplog.text
    assert SECRET not in caplog.text and "Novák" not in caplog.text and caplog.records[-1].exc_info is None


async def test_failed_context_reads_log_only_the_error_class(caplog):
    async def failing(*args):
        raise RuntimeError(f"weaviate echoed key={SECRET} text=Jan Novák")

    store, provider = FakeStore(span(0, 3)), FakeStreamingChat(["ok"])
    store.tags.read = store.documents.read = store.documents.read_following_chunk_texts = failing

    assert await run(store, provider) == ["ok"]

    assert [r.getMessage().rsplit(": ", 1)[1] for r in caplog.records] == ["RuntimeError"] * 3
    assert SECRET not in caplog.text and "Novák" not in caplog.text


async def test_a_server_refusal_reaches_the_client_with_its_safe_message():
    from semant_demo.adapters.llm.usage import LlmInputTooLarge

    refusal = LlmInputTooLarge("The request is too large for the language model (about 16000 tokens are allowed).")
    events = await _events(FakeStore(span(0, 3)), FakeStreamingChat([], error=refusal))

    assert events == [{"error": str(refusal)}]
