# -*- coding: UTF-8 -*-
"""
Created on 22.09.25

:author:     Martin Dočekal
"""
import logging
from typing import Callable, Sequence, Optional

from classconfig import ConfigurableValue, ConfigurableFactory, ConfigurableMixin
from pydantic import BaseModel, Field, StrictInt
from ruamel.yaml.scalarstring import LiteralScalarString

from semant_demo.adapters.llm.gateway import LlmGateway
from semant_demo.features.documents.schemas import DocumentChunk
from semant_demo.features.summarization.base import SearchResultsSummarizer
from semant_demo.features.summarization.schemas import SummaryLength
from semant_demo.utils.template import Template, TemplateTransformer


class ModelOptions(ConfigurableMixin):
    temperature: Optional[float] = ConfigurableValue(
        user_default=None,
        desc="Temperature for the model.",
        voluntary=True
    )
    context_size: Optional[int] = ConfigurableValue(
        user_default=None,
        desc="Context size for the model.",
        voluntary=True
    )
    max_completion_tokens: Optional[int] = ConfigurableValue(
        user_default=None,
        desc="Maximum number of tokens to generate. None for default.",
        voluntary=True
    )


class LengthOptions(BaseModel, extra="forbid", frozen=True):
    """What one summary length level means (#360)."""
    words: StrictInt = Field(gt=0)
    """Maximum length of the summary in words; given to the prompt templates as ``brevity``."""
    max_completion_tokens: StrictInt = Field(gt=0)
    """Maximum number of tokens to generate for the summary."""


class SummaryLengths(BaseModel, extra="forbid", frozen=True):
    """The summary length levels a client may choose from (``SummaryLength``) and the default one (#360)."""
    default: SummaryLength = SummaryLength.short
    short: LengthOptions
    detailed: LengthOptions

    def resolve(self, length: SummaryLength | None) -> tuple[SummaryLength, LengthOptions]:
        """The requested level, or the configured default when none is requested, and its options."""
        level = length or self.default
        return level, getattr(self, level.value)


class SummaryModelOptions(BaseModel, extra="forbid", frozen=True):
    """Model options of a summary whose token limit is set by its length level (#360), not here."""
    temperature: float | None = None
    context_size: int | None = None
    max_completion_tokens: None = None
    """Only empty, as in configurations from before #360; the length level sets the token limit."""


class TemplateGenerationMixin:
    """
    Prompt-selection and single-call LLM generation shared by both templated summarizers
    (``TemplatedSearchResultsSummarizer`` here and ``TemplatedDocumentSummarizer`` in
    ``document.py``). Pulled out (#358 review) because the two classes had near-identical
    copies of this logic, differing only in which gateway feature-tier they generate with;
    each keeps its own ``_generate_or_fallback``, since the two differ in what their
    ``on_error`` callback gets — a document summary has only one generated part and passes the
    exception itself to its caller, search summaries have several and only track which kind
    failed.
    """

    llm: LlmGateway | None = None

    @staticmethod
    def handle_prompt(prompt: Optional[str], default_prompt: Template) -> Template:
        """
        The provided prompt, or the default one when none is provided.

        :raises ValueError: if the provided prompt is not str
        """
        if prompt is None:
            return default_prompt
        if not isinstance(prompt, str):
            raise ValueError("Prompt must be a string.")
        return Template(prompt)

    @staticmethod
    def with_length(options: SummaryModelOptions, length: LengthOptions) -> ModelOptions:
        """``options`` with the token limit of the chosen length level."""
        return ModelOptions(temperature=options.temperature, context_size=options.context_size,
                            max_completion_tokens=length.max_completion_tokens)

    async def _complete(self, feature: str, system_prompt: Template, prompt: Template, values: dict,
                        options: ModelOptions) -> str:
        """The generated text; raises when the model call fails."""
        if self.llm is None:
            raise RuntimeError("The summarizer has no LLM gateway.")
        reply = await self.llm.complete(
            feature,
            [{"role": "system", "content": system_prompt.render(values)},
             {"role": "user", "content": prompt.render(values)}],
            temperature=options.temperature, max_tokens=options.max_completion_tokens,
            context_size=options.context_size)
        return reply.strip()


class TemplatedSearchResultsSummarizer(TemplateGenerationMixin, SearchResultsSummarizer):

    max_generated_results: int = ConfigurableValue(
        user_default=10,
        desc="Results of one search that get a generated title and per-result summary; later results get "
             "none, and the search response says so in a warning. Keep within the search_summary "
             "max_calls limit (two calls per result plus the results summary)."
    )

    gen_title_model_options: ModelOptions = ConfigurableFactory(
        ModelOptions,
        desc="Model options for title generation.",
    )
    gen_title_error_title: str = ConfigurableValue(
        user_default="N/A",
        desc="Title to use when title generation fails."
    )
    gen_title_system_prompt: Template = ConfigurableValue(
        user_default=LiteralScalarString("""Jsi užitečný asistent, který generuje nadpisy pro texty historických dokumentů.{% if brevity %} Nadpis by neměl být delší než {{ brevity }} slov. {% endif %} Odpověz pouze nadpisem, bez dalších komentářů nebo úvodních frází."""),
        desc="System prompt for title generation.",
        transform=TemplateTransformer()
    )
    gen_title_prompt: Template = ConfigurableValue(
        user_default=LiteralScalarString("""Vygeneruj nadpis pro následující text historického dokumentu.
\"{{ text.text }}\"
Nadpis by měl být relevantní k dotazu uživatele: \"{{ query }}\".
"""),
        desc="Prompt for title generation.",
        transform=TemplateTransformer()
    )

    gen_results_summary_model_options: SummaryModelOptions = ConfigurableValue(
        user_default={"temperature": None, "context_size": None},
        desc="Model options for search results summary generation: temperature and context_size. The token limit "
             "is set by the length level (gen_results_summary_lengths).",
        transform=SummaryModelOptions.model_validate,
        voluntary=True
    )
    gen_results_summary_error_summary: str = ConfigurableValue(
        user_default="N/A",
        desc="Summary to use when search results summary generation fails."
    )
    gen_results_summary_lengths: SummaryLengths = ConfigurableValue(
        user_default={"default": "short", "short": {"words": 100, "max_completion_tokens": 512},
                      "detailed": {"words": 300, "max_completion_tokens": 1024}},
        desc="Length levels of the search results summary. default is the level used when a request names none "
             "(short when omitted): by API clients that omit length and for the results summary a search request "
             "asks for. The frontend panels always send the level the user sees (Short initially), so this default "
             "does not change them. Each level has words (the word limit given to the prompts as brevity) and "
             "max_completion_tokens (keep it within the feature's max_output_tokens in LLM_MODELS_CONFIG).",
        transform=SummaryLengths.model_validate,
        voluntary=True
    )
    gen_results_summary_system_prompt: Template = ConfigurableValue(
        user_default=LiteralScalarString("""Jsi asistent pro sumarizaci textů.  
Dostaneš úryvky textu, z nichž každý bude označen unikátním ID jako [doc0], [doc1], … [doc15].  
Tvým úkolem je vytvořit jediný souhrn, který pokryje všechny klíčové body relevantní k uživatelskému vyhledávacímu dotazu.  
Po každém faktu, který z úryvku získáš, připoj ID daného úryvku v hranatých závorkách – například: „Gen ABC je nadregulován v nádorových buňkách [doc3].“  
Pokud stejný fakt podporuje více úryvků, uveď všechna jejich ID: „Tento přístup zlepšil přesnost o 12 % [doc2][doc7][doc11].“  
Nikdy neslučuj více id do jednoho, jako [doc2-4] nebo [doc2, doc3, doc4], ale vždy je uváděj jednotlivě.
Nevymýšlej žádná fakta, která v úryvcích nejsou. Soustřeď se pouze na informace relevantní k uživatelskému dotazu.  
{% if length == "detailed" %}Piš přehledně a podrobně: rozveď jednotlivé body a uveď i méně významné informace, pokud jsou relevantní k dotazu.{% else %}Piš přehledně a stručně, uveď jen nejdůležitější body.{% endif %}
{% if brevity %} Souhrn by neměl být delší než {{ brevity }} slov. {% endif %}
Odpověz pouze souhrnem, bez dalších komentářů nebo úvodních frází.
"""),
        desc="System prompt for search results summary generation.",
        transform=TemplateTransformer()
    )
    gen_results_summary_prompt: Template = ConfigurableValue(
        user_default=LiteralScalarString("""Vytvoř souhrn následujících výsledků vyhledávání.

Uživatel zadal do vyhledávače historických dokumentů dotaz:

\"{{ query }}\"

Tento dotaz mu vrátil následující výsledky:
{% for result in results %}
[doc{{ loop.index }}] {{ result.text }}
{% endfor %}
"""),
        desc="Prompt for search results summary generation.",
        transform=TemplateTransformer()
    )

    gen_query_summary_model_options: ModelOptions = ConfigurableFactory(
        ModelOptions,
        desc="Model options for query summary generation."
    )
    gen_query_summary_error_summary: str = ConfigurableValue(
        user_default="N/A",
        desc="Summary to use when query summary generation fails."
    )
    gen_query_summary_system_prompt: Template = ConfigurableValue(
        user_default=LiteralScalarString("""Jsi užitečný asistent, který generuje sumarizace textů historických dokumentů.{% if brevity %} Souhrn by neměl být delší než {{ brevity }} slov. {% endif %}Odpověz pouze souhrnem, bez dalších komentářů nebo úvodních frází."""),
        desc="System prompt for query summary generation.",
        transform=TemplateTransformer()
    )
    gen_query_summary_prompt: Template = ConfigurableValue(
        user_default=LiteralScalarString("""Prosím vytvoř krátký souhrn následujícího textu, který je relevantní k vyhledávacímu dotazu. Souhrn by měl být výstižný a obsahovat klíčové informace z textu.
Text historického dokumentu:
\"{{ text.text }}\"
Uživatel zadal do vyhledávače historických dokumentů dotaz:
\"{{ query }}\"
"""),
        desc="Prompt for query summary generation.",
        transform=TemplateTransformer()
    )

    async def _generate(self, system_prompt: Template, prompt: Template, values: dict,
                        options: ModelOptions) -> str:
        """The generated text; raises when the model call fails."""
        return await self._complete("search_summary", system_prompt, prompt, values, options)

    async def _generate_or_fallback(self, kind: str, fallback: str, on_error: Optional[Callable[[str], None]],
                                    *args) -> str:
        try:
            return await self._generate(*args)
        except Exception as e:
            # Content-free: the provider error may quote the request.
            logging.error("Search %s generation failed: %s", kind, type(e).__name__)
            if on_error is not None:
                on_error(kind)
            return fallback

    async def gen_title(self, query: str, text: DocumentChunk, prompt: Optional[str] = None, brevity: Optional[int] = None,
                        on_error: Optional[Callable[[str], None]] = None) -> str:
        return await self._generate_or_fallback(
            "title", self.gen_title_error_title, on_error, self.gen_title_system_prompt,
            self.handle_prompt(prompt, self.gen_title_prompt), {"text": text, "query": query, "brevity": brevity},
            self.gen_title_model_options)

    async def gen_results_summary(self, query: str, results: Sequence[DocumentChunk], prompt: Optional[str] = None, brevity: Optional[int] = None,
                                  on_error: Optional[Callable[[str], None]] = None,
                                  length: Optional[SummaryLength] = None) -> str:
        level, options = self.gen_results_summary_lengths.resolve(length)
        return await self._generate_or_fallback(
            "results_summary", self.gen_results_summary_error_summary, on_error,
            self.gen_results_summary_system_prompt, self.handle_prompt(prompt, self.gen_results_summary_prompt),
            {"results": results, "query": query, "length": level.value, "brevity": options.words},
            self.with_length(self.gen_results_summary_model_options, options))

    async def gen_query_summary_for_text_chunk(self, query: str, text: DocumentChunk, prompt: Optional[str] = None, brevity: Optional[int] = None,
                                               on_error: Optional[Callable[[str], None]] = None) -> str:
        return await self._generate_or_fallback(
            "query_summary", self.gen_query_summary_error_summary, on_error,
            self.gen_query_summary_system_prompt, self.handle_prompt(prompt, self.gen_query_summary_prompt),
            {"text": text, "query": query, "brevity": brevity}, self.gen_query_summary_model_options)


def load_summarizer(path: str, llm: LlmGateway) -> TemplatedSearchResultsSummarizer:
    """The summarizer configured in the YAML file at ``path``, generating with ``llm``."""
    summarizer = TemplatedSearchResultsSummarizer.create(path)
    summarizer.llm = llm
    return summarizer
