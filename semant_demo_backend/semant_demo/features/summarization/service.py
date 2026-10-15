"""Summarization use cases over search results: the overall results summary and a question
answered from the results. Search titles and per-result summaries are added by
``search`` (``features/search/service.py``) with the same summarizer. The document summary
(#249) is a separate use case over a whole document's chunks; see ``summarize_document``.

Calls go through the LLM gateway (the ``search_summary``, ``document_summary`` and
``question`` tiers). Logs never carry the query, the question, snippets or the generated text.
"""
import logging
import time
from uuid import UUID

from semant_demo.adapters.llm.gateway import LlmGateway
from semant_demo.adapters.llm.usage import LlmNotConfigured
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.core.errors import InvalidRequestError
from semant_demo.features.documents import service as documents_service
from semant_demo.features.search.schemas import SearchResponse
from semant_demo.features.summarization.base import SearchResultsSummarizer
from semant_demo.features.summarization.document import TemplatedDocumentSummarizer
from semant_demo.features.summarization.schemas import DocumentSummaryCitation, DocumentSummaryResponse, SummaryResponse
from semant_demo.features.user_collections.access import Principal

logger = logging.getLogger(__name__)

Id = str | UUID

QUESTION_SYSTEM_PROMPT = "\n".join([
    "You are a summarization assistant.",
    "You will be given text snippets, each labeled with a unique ID like [doc1], [doc2], … [doc15].",
    "When answering, rely only on the information in the snippets. Do not include any information that is not in the snippets.",
    "Any information you provide must be supported by the snippets and the snipet labels must be included as much as possible."
])


QUESTION_FAILED_MESSAGE = "The language model could not answer the question."


class QuestionFailed(Exception):
    """The model did not answer; carries the safe error message shown to the client.

    Provider exception messages may echo the request, endpoints or credentials, so only a
    fixed message, or the server-authored :class:`LlmNotConfigured` one, is passed on.
    """


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
        raise QuestionFailed(str(e) if isinstance(e, LlmNotConfigured) else QUESTION_FAILED_MESSAGE) from e
    return SummaryResponse(summary=summary_text.strip(), time_spent=search_response.time_spent)


async def summarize_document(documents: DocumentRepository, collections: UserCollectionRepository,
                             document_summarizer: TemplatedDocumentSummarizer, user: Principal | None,
                             document_id: Id, collection_id: Id) -> DocumentSummaryResponse:
    """
    A summary of the current document of ``collection_id`` (#249), with citations to the
    chunks it was built from.

    Authorization and chunk access go entirely through
    ``features.documents.service.read_chunks_in_collection`` (collection-read access, then
    the document must belong to the collection) rather than a new Weaviate read: a denied
    request never reaches the summarizer. Chunks are sorted by their document ``order``
    (chunks without one sort last) and truncated to the summarizer's configured
    ``chunk_limit`` (first N chunks in document order); the citations list exactly the
    chunks sent to the model, so a generation failure still returns accurate (if partial)
    citations alongside the configured fallback summary text.
    """
    start_time = time.time()
    detail = await documents_service.read_chunks_in_collection(documents, collections, user, document_id,
                                                                collection_id)
    chunks = sorted(detail.chunks, key=lambda chunk: (chunk.order is None, chunk.order))
    truncated = chunks[:document_summarizer.chunk_limit]
    summary = await document_summarizer.gen_document_summary(truncated, document_title=detail.document.title)
    citations = [
        DocumentSummaryCitation(chunk_id=chunk.id, order=chunk.order, from_page=chunk.from_page,
                                to_page=chunk.to_page)
        for chunk in truncated
    ]
    return DocumentSummaryResponse(document_id=detail.document.id, summary=summary, citations=citations,
                                   time_spent=time.time() - start_time)
