# -*- coding: UTF-8 -*-
"""
Created on 22.09.25

:author:     Martin Dočekal
"""
import logging
from typing import Sequence, Optional

from classconfig import ConfigurableValue, ConfigurableFactory, ConfigurableMixin
from ruamel.yaml.scalarstring import LiteralScalarString

from semant_demo.llm_api import APIRequest
from semant_demo.schemas import TextChunk
from semant_demo.summarization.base import SearchResultsSummarizer
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

    gen_title_model: str = ConfigurableValue(
        user_default="gpt-oss:20b",
        desc="Model to use for title generation."
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

    gen_results_summary_model: str = ConfigurableValue(
        user_default="gpt-oss:20b",
        desc="Model to use for search results summary generation."
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
Dostaneš úryvky textu, z nichž každý bude označen unikátním ID jako [doc1], [doc2], … [doc15].  
Tvým úkolem je vytvořit jediný, stručný souhrn, který pokryje všechny klíčové body relevantní k uživatelskému vyhledávacímu dotazu.  
Po každém faktu, který z úryvku získáš, připoj ID daného úryvku v hranatých závorkách – například: „Gen ABC je nadregulován v nádorových buňkách [doc3].“  
Pokud stejný fakt podporuje více úryvků, uveď všechna jejich ID oddělená čárkami: „Tento přístup zlepšil přesnost o 12 % [doc2, doc7, doc11].“  
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

    gen_query_summary_model: str = ConfigurableValue(
        user_default="gpt-oss:20b",
        desc="Model to use for query summary generation."
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

    def handle_prompt_and_model(self, prompt: Optional[str], model: Optional[str], default_model: str = None, default_prompt: Template = None) -> tuple[Template, str]:
        """
        Handles the prompt and model selection logic.
        If a prompt or model is provided, it is used. Otherwise, the default values are used.

        :param prompt: the provided prompt
        :param model: the provided model
        :param default_model: the default model to use if no model is provided
        :param default_prompt: the default prompt to use if no prompt is provided
        :return: a tuple of the selected prompt and model
        :raises ValueError: if neither a prompt nor a default prompt is provided or the provided prompt or model is not str
        """

        if prompt is not None:
            if not isinstance(prompt, str):
                raise ValueError("Prompt must be a string.")
            prompt = Template(prompt)
        else:
            if default_prompt is None:
                raise ValueError("No prompt provided and no default prompt available.")
            prompt = default_prompt

        if model is not None:
            if not isinstance(model, str):
                raise ValueError("Model must be a string.")
        else:
            if default_model is None:
                raise ValueError("No model provided and no default model available.")
            model = default_model

        return prompt, model

    async def gen_title(self, query: str, text: TextChunk, prompt: Optional[str] = None, model: Optional[str] = None, brevity: Optional[int] = None) -> str:
        prompt, model = self.handle_prompt_and_model(prompt, model, self.gen_title_model, self.gen_title_prompt)

        request = APIRequest(
            custom_id="gen_title",
            model=model,
            messages=[
                {"role": "system", "content": self.gen_title_system_prompt.render({"text": text, "query": query, "brevity": brevity})},
                {"role": "user", "content": prompt.render({"text": text, "query": query, "brevity": brevity})},
            ],
        )
        output = await self.api.process_single_request(request)
        
        if output.error is not None:
            logging.error(output.error)
            return self.gen_title_error_title
        return output.response.get_raw_content().strip()

    async def gen_results_summary(self, query: str, results: Sequence[TextChunk], prompt: Optional[str] = None, model: Optional[str] = None, brevity: Optional[int] = None) -> str:
        prompt, model = self.handle_prompt_and_model(prompt, model, self.gen_results_summary_model, self.gen_results_summary_prompt)
        request = APIRequest(
            custom_id="gen_results_summary",
            model=model,
            messages=[
                {"role": "system", "content": self.gen_results_summary_system_prompt.render({"results": results, "query": query, "brevity": brevity})},
                {"role": "user", "content": prompt.render({"results": results, "query": query, "brevity": brevity})},
            ],
        )
        output = await self.api.process_single_request(request)
        
        if output.error is not None:
            logging.error(output.error)
            return self.gen_results_summary_error_summary
        return output.response.get_raw_content().strip()

    async def gen_query_summary_for_text_chunk(self, query: str, text: TextChunk, prompt: Optional[str] = None, model: Optional[str] = None, brevity: Optional[int] = None) -> str:
        prompt, model = self.handle_prompt_and_model(prompt, model, self.gen_query_summary_model, self.gen_query_summary_prompt)
        request = APIRequest(
            custom_id="gen_query_summary",
            model=model,
            messages=[
                {"role": "system", "content": self.gen_query_summary_system_prompt.render({"text": text, "query": query, "brevity": brevity})},
                {"role": "user", "content": prompt.render({"text": text, "query": query, "brevity": brevity})},
            ],
        )
        output = await self.api.process_single_request(request)

        if output.error is not None:
            logging.error(output.error)
            return self.gen_query_summary_error_summary
        return output.response.get_raw_content().strip()
