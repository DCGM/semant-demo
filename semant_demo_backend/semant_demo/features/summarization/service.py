"""Summarization use cases over search results: the overall results summary and a question
answered from the results. Search titles and per-result summaries are added by
``search`` (``features/search/service.py``) with the same summarizer.

Calls go through the LLM gateway (the ``search_summary`` and ``question`` tiers). Logs
never carry the query, the question, snippets or the generated text.
"""
import logging
import time

from semant_demo.adapters.llm.gateway import LlmGateway
from semant_demo.core.errors import InvalidRequestError
from semant_demo.features.search.schemas import SearchResponse
from semant_demo.features.summarization.base import SearchResultsSummarizer
from semant_demo.features.summarization.schemas import SummaryResponse

logger = logging.getLogger(__name__)

QUESTION_SYSTEM_PROMPT = "\n".join([
    "You are a summarization assistant.",
    "You will be given text snippets, each labeled with a unique ID like [doc1], [doc2], … [doc15].",
    "When answering, rely only on the information in the snippets. Do not include any information that is not in the snippets.",
    "Any information you provide must be supported by the snippets and the snipet labels must be included as much as possible."
])


class QuestionFailed(Exception):
    """The model did not answer; carries the error message shown to the client."""


async def summarize(summarizer: SearchResultsSummarizer, summary_type: str,
                    search_response: SearchResponse) -> SummaryResponse:
    """The summary of ``summary_type`` of the results; only ``results`` is supported.

    A failed generation returns the summarizer's configured fallback text.
    """
    start_time = time.time()
    if summary_type != "results":
        raise InvalidRequestError(f"Unknown summary type: {summary_type}")
    summary = await summarizer.gen_results_summary(search_response.search_request.query, search_response.results)
    return SummaryResponse(summary=summary, time_spent=time.time() - start_time)


async def answer_question(llm: LlmGateway, question: str, search_response: SearchResponse) -> SummaryResponse:
    """An answer to ``question`` from the result snippets, citing them as ``[docN]``.

    ``time_spent`` is the search's. Raises :class:`QuestionFailed` when the model call fails.
    """
    snippets = [f"[doc{i+1}]" + res.text.replace('\\n', ' ') for i, res in enumerate(search_response.results)]
    messages = [
        {"role": "system", "content": QUESTION_SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(["Here are the text snippets I want to talk about:", *snippets])},
        {"role": "user", "content": question},
    ]
    try:
        summary_text = await llm.complete("question", messages, temperature=0.0, max_tokens=300)
    except Exception as e:
        logger.error("Question answering failed: %s", type(e).__name__)
        raise QuestionFailed(str(e)) from e
    return SummaryResponse(summary=summary_text.strip(), time_spent=search_response.time_spent)
