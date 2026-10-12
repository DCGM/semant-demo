# -*- coding: UTF-8 -*-
"""
Created on 22.09.25

:author:     Martin Dočekal
"""
import logging
from typing import Callable, Sequence, Optional

from classconfig import ConfigurableValue, ConfigurableFactory, ConfigurableMixin
from ruamel.yaml.scalarstring import LiteralScalarString

from semant_demo.adapters.llm.gateway import LlmGateway
from semant_demo.features.documents.schemas import DocumentChunk
from semant_demo.features.summarization.base import SearchResultsSummarizer
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


class TemplatedSearchResultsSummarizer(SearchResultsSummarizer):

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

    gen_results_summary_model_options: ModelOptions = ConfigurableFactory(
        ModelOptions,
        desc="Model options for search results summary generation."
    )
    gen_results_summary_error_summary: str = ConfigurableValue(
        user_default="N/A",
        desc="Summary to use when search results summary generation fails."
    )
    gen_results_summary_system_prompt: Template = ConfigurableValue(
        user_default=LiteralScalarString("""Jsi asistent pro sumarizaci textů.  
Dostaneš úryvky textu, z nichž každý bude označen unikátním ID jako [doc0], [doc1], … [doc15].  
Tvým úkolem je vytvořit jediný, stručný souhrn, který pokryje všechny klíčové body relevantní k uživatelskému vyhledávacímu dotazu.  
Po každém faktu, který z úryvku získáš, připoj ID daného úryvku v hranatých závorkách – například: „Gen ABC je nadregulován v nádorových buňkách [doc3].“  
Pokud stejný fakt podporuje více úryvků, uveď všechna jejich ID: „Tento přístup zlepšil přesnost o 12 % [doc2][doc7][doc11].“  
Nikdy neslučuj více id do jednoho, jako [doc2-4] nebo [doc2, doc3, doc4], ale vždy je uváděj jednotlivě.
Nevymýšlej žádná fakta, která v úryvcích nejsou. Soustřeď se pouze na informace relevantní k uživatelskému dotazu.  
Piš přehledně a stručně.
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

    async def _generate(self, system_prompt: Template, prompt: Template, values: dict,
                        options: ModelOptions) -> str:
        """The generated text; raises when the model call fails."""
        if self.llm is None:
            raise RuntimeError("The summarizer has no LLM gateway.")
        reply = await self.llm.complete(
            "search_summary",
            [{"role": "system", "content": system_prompt.render(values)},
             {"role": "user", "content": prompt.render(values)}],
            temperature=options.temperature, max_tokens=options.max_completion_tokens,
            context_size=options.context_size)
        return reply.strip()

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
                                  on_error: Optional[Callable[[str], None]] = None) -> str:
        return await self._generate_or_fallback(
            "results_summary", self.gen_results_summary_error_summary, on_error,
            self.gen_results_summary_system_prompt, self.handle_prompt(prompt, self.gen_results_summary_prompt),
            {"results": results, "query": query, "brevity": brevity}, self.gen_results_summary_model_options)

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
