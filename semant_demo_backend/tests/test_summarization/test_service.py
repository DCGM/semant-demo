"""Summarization use cases (features/summarization/service.py) with a fake gateway."""
from uuid import uuid4

import pytest

from semant_demo.config import SCRIPT_PATH
from semant_demo.core.errors import InvalidRequestError
from semant_demo.features.documents.schemas import Document
from semant_demo.features.search.schemas import SearchRequest, SearchResponse, SearchResultChunk
from semant_demo.features.summarization import service
from semant_demo.features.summarization.templated import TemplatedSearchResultsSummarizer, load_summarizer
from tests.fakes import FakeLlm

QUESTION = "Kdo byl tajný kronikář?"


def results(*texts: str) -> SearchResponse:
    def hit(text):
        doc = uuid4()
        return SearchResultChunk(id=uuid4(), title="Kronika", text=text, start_page_id=uuid4(), from_page=1,
                                 to_page=1, order=0, language="ces", document=doc,
                                 document_object=Document(id=doc, library="mzk"))
    request = SearchRequest(query="kronikář", tag_uuids=[], positive=False, automatic=False)
    return SearchResponse(results=[hit(t) for t in texts], search_request=request, time_spent=0.5, search_log=[])


def summarizer(llm) -> TemplatedSearchResultsSummarizer:
    return load_summarizer(str(SCRIPT_PATH / "configs" / "search_summarizer.yaml"), llm)


async def test_results_summary_uses_the_search_summary_tier():
    llm = FakeLlm(" Souhrn [doc1]. ")

    response = await service.summarize(summarizer(llm), "results", results("Jan Novák byl kronikář."))

    assert response.summary == "Souhrn [doc1]."
    [(feature, messages, _)] = llm.calls
    assert feature == "search_summary" and "[doc1] Jan Novák byl kronikář." in messages[1]["content"]


async def test_only_results_summaries_exist():
    with pytest.raises(InvalidRequestError, match="Unknown summary type: titles"):
        await service.summarize(summarizer(FakeLlm()), "titles", results())


async def test_question_is_answered_from_numbered_snippets_with_the_search_time():
    llm = FakeLlm(" Jan Novák [doc2]. ")

    response = await service.answer_question(llm, QUESTION, results("Lhota.", "Jan Novák byl kronikář."))

    assert (response.summary, response.time_spent) == ("Jan Novák [doc2].", 0.5)
    [(feature, messages, options)] = llm.calls
    assert feature == "question" and options == {"temperature": 0.0, "max_tokens": 300}
    assert [m["role"] for m in messages] == ["system", "user", "user"]
    assert messages[1]["content"].endswith("[doc1]Lhota.\n[doc2]Jan Novák byl kronikář.")
    assert messages[2]["content"] == QUESTION


async def test_failed_question_keeps_the_error_for_the_client_but_not_the_content_in_logs(caplog):
    def failing(messages):
        raise RuntimeError(f"provider refused: {messages[-1]['content']}")

    with pytest.raises(service.QuestionFailed) as failure:
        await service.answer_question(FakeLlm(failing), QUESTION, results("Jan Novák."))

    assert str(failure.value) == f"provider refused: {QUESTION}"
    assert "Question answering failed: RuntimeError" in caplog.text and "tajný" not in caplog.text
