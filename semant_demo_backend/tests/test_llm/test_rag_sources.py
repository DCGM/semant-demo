"""The sources of a RAG answer and its ``[doc N]`` citations (#370): the agent numbers the
chunks of all its searches once per answer, so a citation from any search names that chunk
in the returned sources; web search results are distinct, non-corpus sources."""
import logging
from uuid import UUID, uuid4

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, ToolMessage

from semant_demo.features.documents.schemas import Document
from semant_demo.features.rag.citations import cited_numbers, unresolved_citations
from semant_demo.features.rag.pipelines import incremental_rag
from semant_demo.features.rag.schemas import RagRequest, RagSearch
from semant_demo.features.search.schemas import SearchRequest, SearchResponse, SearchResultChunk
from tests.test_llm.test_features import AGENT_PARAMS, llm, load_rag, metrics  # noqa: F401 (fixtures)


def chunk(text: str) -> SearchResultChunk:
    doc = uuid4()
    return SearchResultChunk(id=uuid4(), text=text, start_page_id=uuid4(), from_page=1, to_page=1, order=0,
                             document=doc, document_object=Document(id=doc, library="mzk"))


A, B, C, D = (chunk(t) for t in ("Alfa", "Beta", "Gama", "Delta"))


class ScriptedRetriever:
    """Answers each search query with its listed chunks."""

    def __init__(self, results: dict[str, list[SearchResultChunk]]):
        self.results = results

    async def __call__(self, request: SearchRequest) -> SearchResponse:
        return SearchResponse(results=self.results[request.query], search_request=request, time_spent=0.0,
                              search_log=[])


class ScriptedChat:
    """A chat model answering with the listed messages, in order; records what it was sent."""

    def __init__(self, *replies: AIMessage):
        self.replies = list(replies)
        self.received: list[list] = []

    async def ainvoke(self, messages):
        self.received.append(list(messages))
        return self.replies.pop(0)


def search(query: str, call_id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": "weaviate_search", "args": {"query": query}, "id": call_id}])


def agent(tmp_path, llm, agent_model: ScriptedChat, synthesize_model: ScriptedChat | None = None, **params):  # noqa: F811
    rag = load_rag(tmp_path, llm, "xmartiAgentRag", **{**AGENT_PARAMS, **params})
    rag.agent_model = rag.final_agent_model = agent_model
    rag.synthesize_model = synthesize_model or ScriptedChat()
    return rag


def shown_to_agent(model: ScriptedChat) -> list[str]:
    """The search results the agent was shown, in order."""
    return [m.content for m in model.received[-1] if isinstance(m, ToolMessage)]


def cited(response) -> dict[int, str]:
    """Each resolvable citation of the answer and the text of the source it names."""
    return {n: response.sources[n - 1].text for n in cited_numbers(response.rag_answer)
            if 1 <= n <= len(response.sources)}


def test_citations_are_read_as_the_chat_page_reads_them():
    answer = "A [doc 1], B [doc2], C [doc 3, doc 4], D [dokument 5]; no [doc0], [doc 9]; not doc 6."
    assert cited_numbers(answer) == [1, 2, 3, 4, 5, 0, 9]
    assert unresolved_citations(answer, 5) == [0, 9]


async def test_agent_citations_from_several_searches_name_the_returned_sources(tmp_path, llm, caplog):  # noqa: F811
    # The second search finds a new chunk, one of the first search again, and a chunk twice.
    model = ScriptedChat(search("first", "1"), search("second", "2"),
                         AIMessage(content="Gama [doc 3]; Alfa [doc 1]; Beta [doc 2]; unknown [doc 4]."))
    rag = agent(tmp_path, llm, model)

    with caplog.at_level(logging.WARNING):
        response = await rag.rag_request(RagRequest(question="Q", rag_search=RagSearch()),
                                         ScriptedRetriever({"first": [A, B], "second": [C, A, C]}))

    # Each chunk once, numbered by its first retrieval; a chunk found again keeps its number.
    assert shown_to_agent(model) == ["[doc 1] Alfa\n\n[doc 2] Beta", "[doc 3] Gama\n\n[doc 1] Alfa"]
    assert [s.id for s in response.sources] == [A.id, B.id, C.id]
    assert cited(response) == {3: "Gama", 1: "Alfa", 2: "Beta"}
    # A citation without a source is reported and left as written, not moved to another chunk.
    assert response.rag_answer.endswith("unknown [doc 4].")
    assert [r.__dict__.get("rag.unresolved_citations") for r in caplog.records
            if r.message == "RAG answer cites sources it does not return"] == [1]


async def test_agent_final_synthesis_keeps_the_numbers_of_the_answer(tmp_path, llm):  # noqa: F811
    # The agent only searches until its iterations run out; the answer is synthesized from the
    # last search's chunks, which keep the numbers the agent saw.
    model = ScriptedChat(search("first", "1"), search("second", "2"), search("third", "3"))
    synthesize = ScriptedChat(AIMessage(content="Delta [doc 4], Beta [doc 2]."))
    rag = agent(tmp_path, llm, model, synthesize, agent_iterations=3)

    response = await rag.rag_request(RagRequest(question="Q", rag_search=RagSearch()), ScriptedRetriever(
        {"first": [A, B], "second": [C], "third": [D, B]}))

    assert synthesize.received[0][-1].content.endswith("[doc 4] Delta\n\n[doc 2] Beta")
    assert [s.id for s in response.sources] == [A.id, B.id, C.id, D.id]
    assert cited(response) == {4: "Delta", 2: "Beta"}


async def test_agent_final_synthesis_uses_earlier_searches_when_the_last_finds_nothing(tmp_path, llm):  # noqa: F811
    model = ScriptedChat(search("first", "1"), search("second", "2"))
    synthesize = ScriptedChat(AIMessage(content="Beta [doc 2]."))
    rag = agent(tmp_path, llm, model, synthesize, agent_iterations=2)

    response = await rag.rag_request(RagRequest(question="Q", rag_search=RagSearch()), ScriptedRetriever(
        {"first": [A, B], "second": []}))

    assert synthesize.received[0][-1].content.endswith("[doc 1] Alfa\n\n[doc 2] Beta")
    assert response.rag_answer == "Beta [doc 2]."
    assert [s.id for s in response.sources] == [A.id, B.id]
    assert cited(response) == {2: "Beta"}


async def test_agent_answer_without_searches_has_no_sources(tmp_path, llm):  # noqa: F811
    rag = agent(tmp_path, llm, ScriptedChat(AIMessage(content="Nothing [doc 1].")))

    response = await rag.rag_request(RagRequest(question="Q", rag_search=RagSearch()), ScriptedRetriever({}))

    assert response.sources == []
    assert cited(response) == {}


class FakeDdgs:
    """DuckDuckGo search results by query; the same text may come from several queries."""

    def __init__(self, results: dict[str, list[dict]]):
        self.results = results
        self.queries: list[str] = []

    def __call__(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def text(self, query, max_results):
        self.queries.append(query)
        return self.results.get(query, [])


def web_result(n: int) -> dict:
    return {"title": f"Page {n}", "href": f"https://example.org/{n}", "body": f"Snippet {n}"}


@pytest.mark.parametrize("keywords", [["Lhota kronika"], []], ids=["keywords", "keyword extraction failed"])
async def test_web_search_gives_each_result_its_own_non_corpus_source(tmp_path, llm, monkeypatch, keywords):  # noqa: F811
    ddgs = FakeDdgs({"Lhota kronika": [web_result(1), web_result(2)],
                     "Kdo psal kroniku?": [web_result(2), web_result(3)]})
    monkeypatch.setattr(incremental_rag, "DDGS", ddgs)
    rag = load_rag(tmp_path, llm, "IncrementalAdaptiveRagGenerator", tier="medium", web_search_enabled=True)
    # Without a reply the keyword extraction fails, and the question alone is searched.
    rag.model = FakeListChatModel(responses=keywords)

    state = await rag.node_web_search({"question": "Kdo psal kroniku?", "language": "ces"})

    sources = state["documents"]
    expected = ["Snippet 1", "Snippet 2", "Snippet 3"] if keywords else ["Snippet 2", "Snippet 3"]
    assert [s.text for s in sources] == expected
    assert len({s.id for s in sources}) == len(sources)
    assert len({s.document for s in sources}) == len(sources)
    for source in sources:
        assert source.origin == "web"
        assert source.document == source.document_object.id
        assert source.document_object.library is None
    assert sources[0].title == sources[0].document_object.title == f"Page {expected[0][-1]}"
    assert sources[0].document_object.url == f"https://example.org/{expected[0][-1]}"


def test_corpus_hits_are_corpus_sources_and_web_sources_survive_a_round_trip():
    # Search hits default to the corpus; a web source sent back by the client (previous
    # documents, feedback, explanation) stays a web source.
    assert A.origin == "corpus"
    web = incremental_rag.web_source(web_result(1))
    again = SearchResultChunk.model_validate(web.model_dump(mode="json"))
    assert (again.origin, again.id) == ("web", web.id)
    assert isinstance(again.id, UUID)
