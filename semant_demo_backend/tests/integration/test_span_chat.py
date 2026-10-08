"""Span discussion chat against real Weaviate (#210): the context is read through the
repositories, the provider is a deterministic fake (no paid calls)."""
import json

import pytest

from semant_demo.routes.dependencies import get_span_chat
from tests.fakes import FakeStreamingChat

pytestmark = pytest.mark.integration


@pytest.fixture
def chat(api_app):
    provider = FakeStreamingChat(["Fits", "."])
    api_app.dependency_overrides[get_span_chat] = lambda: provider
    return provider


async def discuss(api_client, headers, span_id):
    return await api_client.post("/api/ai/discuss_span", headers=headers, json={
        "span_id": span_id, "messages": [{"role": "user", "content": "Sedí to?"}]})


async def test_shared_user_discusses_a_stored_span(api_client, login, ids, chat):
    response = await discuss(api_client, await login("annotator"), ids.span["novak_manual"])

    assert response.status_code == 200, response.text
    assert [json.loads(line) for line in response.text.splitlines()] == [{"delta": "Fits"}, {"delta": "."},
                                                                         {"done": True}]
    instructions, turns = chat.calls[0]
    assert "- Title: Kronika obce Lhota" in instructions
    assert "- Name: " in instructions and "(tag could not be loaded)" not in instructions
    assert "<<<SPAN>>>Jan Novák<<<END_SPAN>>> a ubytoval" in instructions
    # The default window is longer than the chunk: the following chunks are added.
    assert "[later in document" in instructions and "Kronikář zaznamenal" in instructions
    assert turns == [{"role": "user", "content": "Sedí to?"}]


async def test_cross_chunk_span_text_is_read_from_the_following_chunk(api_client, login, ids, corpus, chat):
    owner = await login("owner")
    first = len(corpus.chunks["chronicle_1"]["text"])
    created = await api_client.post("/api/tag_spans", headers=owner, json={
        "chunkId": ids.chunk["chronicle_1"], "tagId": ids.tag["person"], "start": 80, "end": first + 8,
        "type": "pos"})
    assert created.status_code == 200, created.text

    response = await discuss(api_client, owner, created.json()["id"])

    assert response.status_code == 200, response.text
    assert 'SPAN TEXT (verbatim, 14 chars): "elena.Kronikář"' in chat.calls[0][0]


@pytest.mark.parametrize("user, status", [(None, 401), ("outsider", 404)])
async def test_denied_discussion_makes_no_provider_call(api_client, login, ids, chat, user, status):
    response = await discuss(api_client, await login(user), ids.span["novak_manual"])

    assert response.status_code == status
    assert chat.calls == []
