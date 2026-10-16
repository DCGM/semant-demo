import unittest
from unittest.mock import AsyncMock

from semant_demo.features.summarization.templated import TemplatedSearchResultsSummarizer, ModelOptions
from semant_demo.utils.template import Template
from tests.fakes import FakeLlm

class TestTemplatedSearchResultsSummarizer(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.llm = FakeLlm("  Generated text\n")
        self.summarizer = TemplatedSearchResultsSummarizer(
            gen_title_model_options=ModelOptions(temperature=0.5, max_completion_tokens=20),
            gen_results_summary_model_options=ModelOptions(),
            gen_query_summary_model_options=ModelOptions(context_size=4096),
            gen_title_system_prompt=Template("Jsi užitečný asistent, který generuje nadpisy pro texty historických dokumentů. {% if brevity %}Nadpis by neměl být delší než {{ brevity }} slov. {% endif %}Odpověz pouze nadpisem, bez dalších komentářů nebo úvodních frází."),
            gen_title_prompt=Template("Vygeneruj nadpis pro následující text historického dokumentu.\n\"{{ text.text }}\"\nNadpis by měl být relevantní k dotazu uživatele: \"{{ query }}\".\n"),
            gen_results_summary_system_prompt=Template("Jsi asistent pro sumarizaci textů.  \nDostaneš úryvky textu, z nichž každý bude označen unikátním ID jako [doc1], [doc2], … [doc15].  \nTvým úkolem je vytvořit jediný, stručný souhrn, který pokryje všechny klíčové body relevantní k uživatelskému vyhledávacímu dotazu.  \nPo každém faktu, který z úryvku získáš, připoj ID daného úryvku v hranatých závorkách – například: „Gen ABC je nadregulován v nádorových buňkách [doc3].“  \nPokud stejný fakt podporuje více úryvků, uveď všechna jejich ID oddělená čárkami: „Tento přístup zlepšil přesnost o 12 % [doc2, doc7, doc11].“  \nNevymýšlej žádná fakta, která v úryvcích nejsou. Soustřeď se pouze na informace relevantní k uživatelskému dotazu.  \nPiš přehledně a stručně.\n{% if brevity %} Souhrn by neměl být delší než {{ brevity }} slov. {% endif %}\nOdpověz pouze souhrnem, bez dalších komentářů nebo úvodních frází.\n"),
            gen_results_summary_prompt=Template("Vytvoř souhrn následujících výsledků vyhledávání.\n\nUživatel zadal do vyhledávače historických dokumentů dotaz:\n\n\"{{ query }}\"\n\nTento dotaz mu vrátil následující výsledky:\n{% for result in results %}\n[doc{{ loop.index }}] {{ result.text }}\n{% endfor %}\n"),
            gen_query_summary_system_prompt=Template("Jsi užitečný asistent, který generuje sumarizace textů historických dokumentů. {% if brevity %}Souhrn by neměl být delší než {{ brevity }} slov. {% endif %}Odpověz pouze souhrnem, bez dalších komentářů nebo úvodních frází."),
            gen_query_summary_prompt=Template("Prosím vytvoř krátký souhrn následujícího textu, který je relevantní k vyhledávacímu dotazu. Souhrn by měl být výstižný a obsahovat klíčové informace z textu.\nText historického dokumentu:\n\"{{ text.text }}\"\nUživatel zadal do vyhledávače historických dokumentů dotaz:\n\"{{ query }}\"\n")
        )
        self.summarizer.llm = self.llm

    async def test_gen_title(self):
        title = await self.summarizer.gen_title("What is AI?", AsyncMock(text="AI is..."))
        self.assertEqual(self.llm.calls, [(
            "search_summary",
            [
                {"role": "system", "content": "Jsi užitečný asistent, který generuje nadpisy pro texty historických dokumentů. Odpověz pouze nadpisem, bez dalších komentářů nebo úvodních frází."},
                {"role": "user", "content": "Vygeneruj nadpis pro následující text historického dokumentu.\n\"AI is...\"\nNadpis by měl být relevantní k dotazu uživatele: \"What is AI?\"."}
            ],
            {"temperature": 0.5, "max_tokens": 20, "context_size": None},
        )])
        self.assertEqual(title, "Generated text")   # stripped

    async def test_gen_results_summary(self):
        summary = await self.summarizer.gen_results_summary("What is AI?", [AsyncMock(text="AI is...")])
        self.assertEqual(self.llm.calls, [(
            "search_summary",
            [
                {"role": "system", "content": "Jsi asistent pro sumarizaci textů.  \nDostaneš úryvky textu, z nichž každý bude označen unikátním ID jako [doc1], [doc2], … [doc15].  \nTvým úkolem je vytvořit jediný, stručný souhrn, který pokryje všechny klíčové body relevantní k uživatelskému vyhledávacímu dotazu.  \nPo každém faktu, který z úryvku získáš, připoj ID daného úryvku v hranatých závorkách – například: „Gen ABC je nadregulován v nádorových buňkách [doc3].“  \nPokud stejný fakt podporuje více úryvků, uveď všechna jejich ID oddělená čárkami: „Tento přístup zlepšil přesnost o 12 % [doc2, doc7, doc11].“  \nNevymýšlej žádná fakta, která v úryvcích nejsou. Soustřeď se pouze na informace relevantní k uživatelskému dotazu.  \nPiš přehledně a stručně.\n\nOdpověz pouze souhrnem, bez dalších komentářů nebo úvodních frází."},
                {"role": "user", "content": "Vytvoř souhrn následujících výsledků vyhledávání.\n\nUživatel zadal do vyhledávače historických dokumentů dotaz:\n\n\"What is AI?\"\n\nTento dotaz mu vrátil následující výsledky:\n\n[doc1] AI is...\n"}
            ],
            {"temperature": None, "max_tokens": None, "context_size": None},
        )])
        self.assertEqual(summary, "Generated text")

    async def test_gen_query_summary_for_text_chunk(self):
        query_summary = await self.summarizer.gen_query_summary_for_text_chunk("What is AI?", AsyncMock(text="AI is..."))
        self.assertEqual(self.llm.calls, [(
            "search_summary",
            [
                {"role": "system", "content": "Jsi užitečný asistent, který generuje sumarizace textů historických dokumentů. Odpověz pouze souhrnem, bez dalších komentářů nebo úvodních frází."},
                {"role": "user", "content": "Prosím vytvoř krátký souhrn následujícího textu, který je relevantní k vyhledávacímu dotazu. Souhrn by měl být výstižný a obsahovat klíčové informace z textu.\nText historického dokumentu:\n\"AI is...\"\nUživatel zadal do vyhledávače historických dokumentů dotaz:\n\"What is AI?\""}
            ],
            {"temperature": None, "max_tokens": None, "context_size": 4096},
        )])
        self.assertEqual(query_summary, "Generated text")
