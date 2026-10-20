from abc import ABC, abstractmethod
from contextlib import nullcontext
from typing import Callable, Sequence, Optional

from classconfig import ConfigurableMixin
from classconfig.configurable import CreatableMixin

from semant_demo.adapters.llm.gateway import LlmGateway
from semant_demo.adapters.llm.usage import OperationBudget
from semant_demo.features.search.schemas import SearchResponse, SummaryRequestBase
from semant_demo.features.documents.schemas import DocumentChunk
from semant_demo.features.summarization.schemas import SummaryLength


class SearchResultsSummarizer(ABC, ConfigurableMixin, CreatableMixin):
    """
    Abstract base class for summarizers.

    Prompts and options come from the configuration; the model is the
    ``search_summary`` feature's tier of ``llm``, set after construction.
    """

    llm: LlmGateway | None = None
    max_generated_results: int = 10
    """Results that get a generated title and per-result summary in one search."""

    def operation(self, budget: OperationBudget | None = None):
        """``async with``: the ``search_summary`` LLM operation, admitted against ``budget``."""
        return self.llm.operation("search_summary", budget) if self.llm is not None else nullcontext()

    async def __call__(self, request: SummaryRequestBase, results: SearchResponse,
                       budget: OperationBudget | None = None) -> list[str]:
        """
        Creates summaries for the search results.

        :param results: search results to summarize
            Is modified in place.
        :param budget: admits the generation (one operation); its refusal propagates before
            any model call. Nothing is admitted when the request asks for no generation.
        :return: the kinds of the parts that could not be generated ("title", "query_summary",
            "results_summary"), once per failed part; they hold the configured fallback text.
            "results_limit" once when titles or per-result summaries were asked for more than
            ``max_generated_results`` results: the later results have none (``None``).
        """
        failures: list[str] = []
        per_result = results.results[:self.max_generated_results]
        if (request.search_title_generate or request.search_summary_generate) and len(per_result) < len(results.results):
            failures.append("results_limit")

        if not (request.search_title_generate or request.search_summary_generate
                or request.search_results_summary_generate):
            return failures
        # All calls of one search are one operation, whose call count the gateway caps.
        async with self.operation(budget):
            if request.search_title_generate:
                await self.gen_titles(request.query, per_result, request.search_title_prompt,
                                      on_error=failures.append)

            if request.search_summary_generate:
                await self.gen_query_summary_for_text_chunks(request.query, per_result, request.search_summary_prompt,
                                                             on_error=failures.append)

            if request.search_results_summary_generate:
                results.results_summary = await self.gen_results_summary(request.query, results.results,
                                                                         request.search_results_summary_prompt,
                                                                         on_error=failures.append)
        return failures

    async def gen_titles(self, query: str, results: list[DocumentChunk], prompt: Optional[str] = None, brevity: Optional[int] = None,
                         on_error: Optional[Callable[[str], None]] = None):
        """
        Creates titles for the search results in place.

        :param query: search query that was used to get the results
        :param results: search results to create titles for
         Is modified in place.
        :param prompt: optional prompt to use instead of the default one
        :param brevity: optional brevity to instruct the model to use
        :param on_error: called with "title" for each title that could not be generated
        """
        for res in results:
            res.query_title = await self.gen_title(query, res, prompt, brevity, on_error=on_error)

    @abstractmethod
    async def gen_title(self, query: str, text: DocumentChunk, prompt: Optional[str] = None, brevity: Optional[int] = None,
                        on_error: Optional[Callable[[str], None]] = None) -> str:
        """
        Creates a title for a single text chunk.

        :param query: search query that was used to get the results
        :param text: text chunk to create a title for
        :param prompt: optional prompt to use instead of the default one
        :param brevity: optional brevity to instruct the model to use
        :return: generated title
        """
        ...

    @abstractmethod
    async def gen_results_summary(self, query: str, results: Sequence[DocumentChunk], prompt: Optional[str] = None, brevity: Optional[int] = None,
                                  on_error: Optional[Callable[[str], None]] = None,
                                  length: Optional[SummaryLength] = None) -> str:
        """
        Creates an overall summary for the search results.

        :param query: search query that was used to get the results
        :param results: search results to create a summary for
        :param prompt: optional prompt to use instead of the default one
        :param brevity: optional brevity to instruct the model to use; overrides the words of the length level
        :param length: length level of the summary; None for the configured default
        :return: generated summary
        """
        ...

    async def gen_query_summary_for_text_chunks(self, query: str, text: list[DocumentChunk], prompt: Optional[str] = None, brevity: Optional[int] = None,
                                                on_error: Optional[Callable[[str], None]] = None):
        """
        Creates a summary for a single text chunk.

        :param query: search query that was used to get the results
        :param text: text chunks to create a summary for
        :param prompt: optional prompt to use instead of the default one
        :param brevity: optional brevity to instruct the model to use
        :return: generated summary
        """

        for res in text:
            res.query_summary = await self.gen_query_summary_for_text_chunk(query, res, prompt, brevity,
                                                                            on_error=on_error)

    @abstractmethod
    async def gen_query_summary_for_text_chunk(self, query: str, text: DocumentChunk, prompt: Optional[str] = None, brevity: Optional[int] = None,
                                               on_error: Optional[Callable[[str], None]] = None) -> str:
        """
        Creates a summary for a single text chunk.

        :param query: search query that was used to get the results
        :param text: text chunk to create a summary for
        :param prompt: optional prompt to use instead of the default one
        :param brevity: optional brevity to instruct the model to use
        :return: generated summary
        """
        ...

