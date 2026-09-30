import unittest
from unittest.mock import AsyncMock

import ollama
from ollama import ChatResponse

from semant_demo.llm_api import APIOutput, APIModelResponseOllama, APIRequest
from semant_demo.summarization.templated import TemplatedSearchResultsSummarizer, ModelOptions
from semant_demo.utils.template import Template

class TestTemplatedSearchResultsSummarizer(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.api = AsyncMock()
        self.summarizer = TemplatedSearchResultsSummarizer(
            api=self.api,
            gen_title_model="gpt-oss:20b",
            gen_title_model_options=ModelOptions(),
            gen_results_summary_model="gpt-oss:20b",
            gen_results_summary_model_options=ModelOptions(),
            gen_query_summary_model="gpt-oss:20b",
            gen_query_summary_model_options=ModelOptions(),
            gen_title_system_prompt=Template("Jsi užitečný asistent, který generuje nadpisy pro texty historických dokumentů. {% if brevity %}Nadpis by neměl být delší než {{ brevity }} slov. {% endif %}Odpověz pouze nadpisem, bez dalších komentářů nebo úvodních frází."),
            gen_title_prompt=Template("Vygeneruj nadpis pro následující text historického dokumentu.\n\"{{ text.text }}\"\nNadpis by měl být relevantní k dotazu uživatele: \"{{ query }}\".\n"),
            gen_results_summary_system_prompt=Template("Jsi asistent pro sumarizaci textů.  \nDostaneš úryvky textu, z nichž každý bude označen unikátním ID jako [doc1], [doc2], … [doc15].  \nTvým úkolem je vytvořit jediný, stručný souhrn, který pokryje všechny klíčové body relevantní k uživatelskému vyhledávacímu dotazu.  \nPo každém faktu, který z úryvku získáš, připoj ID daného úryvku v hranatých závorkách – například: „Gen ABC je nadregulován v nádorových buňkách [doc3].“  \nPokud stejný fakt podporuje více úryvků, uveď všechna jejich ID oddělená čárkami: „Tento přístup zlepšil přesnost o 12 % [doc2, doc7, doc11].“  \nNevymýšlej žádná fakta, která v úryvcích nejsou. Soustřeď se pouze na informace relevantní k uživatelskému dotazu.  \nPiš přehledně a stručně.\n{% if brevity %} Souhrn by neměl být delší než {{ brevity }} slov. {% endif %}\nOdpověz pouze souhrnem, bez dalších komentářů nebo úvodních frází.\n"),
            gen_results_summary_prompt=Template("Vytvoř souhrn následujících výsledků vyhledávání.\n\nUživatel zadal do vyhledávače historických dokumentů dotaz:\n\n\"{{ query }}\"\n\nTento dotaz mu vrátil následující výsledky:\n{% for result in results %}\n[doc{{ loop.index }}] {{ result.text }}\n{% endfor %}\n"),
            gen_query_summary_system_prompt=Template("Jsi užitečný asistent, který generuje sumarizace textů historických dokumentů. {% if brevity %}Souhrn by neměl být delší než {{ brevity }} slov. {% endif %}Odpověz pouze souhrnem, bez dalších komentářů nebo úvodních frází."),
            gen_query_summary_prompt=Template("Prosím vytvoř krátký souhrn následujícího textu, který je relevantní k vyhledávacímu dotazu. Souhrn by měl být výstižný a obsahovat klíčové informace z textu.\nText historického dokumentu:\n\"{{ text.text }}\"\nUživatel zadal do vyhledávače historických dokumentů dotaz:\n\"{{ query }}\"\n")
        )

    async def test_gen_title(self):
        self.api.process_single_request = AsyncMock(return_value=APIOutput(
            custom_id="test1",
            response=APIModelResponseOllama(
                body=ChatResponse(
                    message=ollama.Message(
                        role="assistant",
                        content="Generated Title"
                    )
                ),
                structured=False
            )
        ))
        title = await self.summarizer.gen_title("What is AI?", AsyncMock(text="AI is..."))
        self.api.process_single_request.assert_called_once_with(
            APIRequest(
                custom_id="gen_title",
                model="gpt-oss:20b",
                messages=[
                    {"role": "system", "content": "Jsi užitečný asistent, který generuje nadpisy pro texty historických dokumentů. Odpověz pouze nadpisem, bez dalších komentářů nebo úvodních frází."},
                    {"role": "user", "content": "Vygeneruj nadpis pro následující text historického dokumentu.\n\"AI is...\"\nNadpis by měl být relevantní k dotazu uživatele: \"What is AI?\"."}
                ],
            )
        )
        self.assertEqual(title, "Generated Title")

    async def test_gen_results_summary(self):
        self.api.process_single_request = AsyncMock(return_value=APIOutput(
            custom_id="test2",
            response=APIModelResponseOllama(
                body=ChatResponse(
                    message=ollama.Message(
                        role="assistant",
                        content="Summary of results"
                    )
                ),
                structured=False
            )
        ))
        summary = await self.summarizer.gen_results_summary("What is AI?", [AsyncMock(text="AI is...")])
        self.api.process_single_request.assert_called_once_with(
            APIRequest(
                custom_id="gen_results_summary",
                model="gpt-oss:20b",
                messages=[
                    {"role": "system", "content": "Jsi asistent pro sumarizaci textů.  \nDostaneš úryvky textu, z nichž každý bude označen unikátním ID jako [doc1], [doc2], … [doc15].  \nTvým úkolem je vytvořit jediný, stručný souhrn, který pokryje všechny klíčové body relevantní k uživatelskému vyhledávacímu dotazu.  \nPo každém faktu, který z úryvku získáš, připoj ID daného úryvku v hranatých závorkách – například: „Gen ABC je nadregulován v nádorových buňkách [doc3].“  \nPokud stejný fakt podporuje více úryvků, uveď všechna jejich ID oddělená čárkami: „Tento přístup zlepšil přesnost o 12 % [doc2, doc7, doc11].“  \nNevymýšlej žádná fakta, která v úryvcích nejsou. Soustřeď se pouze na informace relevantní k uživatelskému dotazu.  \nPiš přehledně a stručně.\n\nOdpověz pouze souhrnem, bez dalších komentářů nebo úvodních frází."},
                    {"role": "user", "content": "Vytvoř souhrn následujících výsledků vyhledávání.\n\nUživatel zadal do vyhledávače historických dokumentů dotaz:\n\n\"What is AI?\"\n\nTento dotaz mu vrátil následující výsledky:\n\n[doc1] AI is...\n"}
                ],
            )
        )
        self.assertEqual(summary, "Summary of results")

    async def test_gen_query_summary_for_text_chunk(self):
        self.api.process_single_request = AsyncMock(return_value=APIOutput(
            custom_id="test3",
            response=APIModelResponseOllama(
                body=ChatResponse(
                    message=ollama.Message(
                        role="assistant",
                        content="Query-specific summary"
                    )
                ),
                structured=False
            )
        ))
        query_summary = await self.summarizer.gen_query_summary_for_text_chunk("What is AI?", AsyncMock(text="AI is..."))
        self.api.process_single_request.assert_called_once_with(
            APIRequest(
                custom_id="gen_query_summary",
                model="gpt-oss:20b",
                messages=[
                    {"role": "system", "content": "Jsi užitečný asistent, který generuje sumarizace textů historických dokumentů. Odpověz pouze souhrnem, bez dalších komentářů nebo úvodních frází."},
                    {"role": "user", "content": "Prosím vytvoř krátký souhrn následujícího textu, který je relevantní k vyhledávacímu dotazu. Souhrn by měl být výstižný a obsahovat klíčové informace z textu.\nText historického dokumentu:\n\"AI is...\"\nUživatel zadal do vyhledávače historických dokumentů dotaz:\n\"What is AI?\""}
                ],
            )
        )
        self.assertEqual(query_summary, "Query-specific summary")
