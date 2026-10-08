from abc import ABC, abstractmethod
from typing import Callable, Sequence, Optional

from classconfig import ConfigurableSubclassFactory, ConfigurableMixin
from classconfig.configurable import CreatableMixin

from semant_demo.llm_api import APIAsync, OllamaAsyncAPI
from semant_demo.schemas import SearchResponse, TextChunk, SummaryRequestBase


class SearchResultsSummarizer(ABC, ConfigurableMixin, CreatableMixin):
    """
    Abstract base class for summarizers.
    """

    api: APIAsync = ConfigurableSubclassFactory(APIAsync, "API configuration.",
                                                  user_default=OllamaAsyncAPI)

    async def __call__(self, request: SummaryRequestBase, results: SearchResponse) -> list[str]:
        """
        Creates summaries for the search results.

        :param results: search results to summarize
            Is modified in place.
        :return: the kinds of the parts that could not be generated ("title", "query_summary",
            "results_summary"), once per failed part; they hold the configured fallback text
        """
        failures: list[str] = []

        if request.search_title_generate:
            await self.gen_titles(request.query, results.results, request.search_title_prompt,
                                  on_error=failures.append)

        if request.search_summary_generate:
            await self.gen_query_summary_for_text_chunks(request.query, results.results, request.search_summary_prompt,
                                                         on_error=failures.append)

        if request.search_results_summary_generate:
            results.results_summary = await self.gen_results_summary(request.query, results.results,
                                                                     request.search_results_summary_prompt,
                                                                     on_error=failures.append)
        return failures

    async def gen_titles(self, query: str, results: list[TextChunk], prompt: Optional[str] = None, model: Optional[str] = None, brevity: Optional[int] = None,
                         on_error: Optional[Callable[[str], None]] = None):
        """
        Creates titles for the search results in place.

        :param query: search query that was used to get the results
        :param results: search results to create titles for
         Is modified in place.
        :param prompt: optional prompt to use instead of the default one
        :param model: optional model to use instead of the default one
        :param brevity: optional brevity to instruct the model to use
        :param on_error: called with "title" for each title that could not be generated
        """
        for res in results:
            res.query_title = await self.gen_title(query, res, prompt, model, brevity, on_error=on_error)

    @abstractmethod
    async def gen_title(self, query: str, text: TextChunk, prompt: Optional[str] = None, model: Optional[str] = None, brevity: Optional[int] = None,
                        on_error: Optional[Callable[[str], None]] = None) -> str:
        """
        Creates a title for a single text chunk.

        :param query: search query that was used to get the results
        :param text: text chunk to create a title for
        :param prompt: optional prompt to use instead of the default one
        :param model: optional model to use instead of the default one
        :param brevity: optional brevity to instruct the model to use
        :return: generated title
        """
        ...

    @abstractmethod
    async def gen_results_summary(self, query: str, results: Sequence[TextChunk], prompt: Optional[str] = None, model: Optional[str] = None, brevity: Optional[int] = None,
                                  on_error: Optional[Callable[[str], None]] = None) -> str:
        """
        Creates an overall summary for the search results.

        :param query: search query that was used to get the results
        :param results: search results to create a summary for
        :param prompt: optional prompt to use instead of the default one
        :param model: optional model to use instead of the default one
        :param brevity: optional brevity to instruct the model to use
        :return: generated summary
        """
        ...

    async def gen_query_summary_for_text_chunks(self, query: str, text: list[TextChunk], prompt: Optional[str] = None, model: Optional[str] = None, brevity: Optional[int] = None,
                                                on_error: Optional[Callable[[str], None]] = None):
        """
        Creates a summary for a single text chunk.

        :param query: search query that was used to get the results
        :param text: text chunks to create a summary for
        :param prompt: optional prompt to use instead of the default one
        :param model: optional model to use instead of the default one
        :param brevity: optional brevity to instruct the model to use
        :return: generated summary
        """

        for res in text:
            res.query_summary = await self.gen_query_summary_for_text_chunk(query, res, prompt, model, brevity,
                                                                            on_error=on_error)

    @abstractmethod
    async def gen_query_summary_for_text_chunk(self, query: str, text: TextChunk, prompt: Optional[str] = None, model: Optional[str] = None, brevity: Optional[int] = None,
                                               on_error: Optional[Callable[[str], None]] = None) -> str:
        """
        Creates a summary for a single text chunk.

        :param query: search query that was used to get the results
        :param text: text chunk to create a summary for
        :param prompt: optional prompt to use instead of the default one
        :param model: optional model to use instead of the default one
        :param brevity: optional brevity to instruct the model to use
        :return: generated summary
        """
        ...

