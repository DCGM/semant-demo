"""Document summarization (#249): a summary of a whole document's chunks.

Deliberately not a subclass of ``SearchResultsSummarizer`` (``features/summarization/base.py``):
every one of its abstract methods takes a search ``query`` as a required first argument, and a
document summary has none. Forcing one through that contract would mean inventing a fake query
string. It shares its prompt-selection and single-call LLM generation with
``TemplatedSearchResultsSummarizer`` (``templated.py``) via ``TemplateGenerationMixin``, and
otherwise follows the same ``_generate``/``_generate_or_fallback`` pattern.
"""
import logging
from typing import Callable, Optional, Sequence

from classconfig import ConfigurableFactory, ConfigurableMixin, ConfigurableValue
from classconfig.configurable import CreatableMixin
from ruamel.yaml.scalarstring import LiteralScalarString

from semant_demo.adapters.llm.gateway import LlmGateway
from semant_demo.features.documents.schemas import DocumentChunk
from semant_demo.features.summarization.templated import ModelOptions, TemplateGenerationMixin
from semant_demo.utils.template import Template, TemplateTransformer


class TemplatedDocumentSummarizer(TemplateGenerationMixin, ConfigurableMixin, CreatableMixin):
    """
    Summarizes a document from a (possibly truncated) sequence of its chunks. Prompts and
    options come from the configuration; the model is the ``document_summary`` feature's
    tier of ``llm``, set after construction (see :func:`load_document_summarizer`).

    Chunks are labelled ``[docN]`` in the prompt (N = 1-based position in ``chunks``), the
    same citation convention ``TemplatedSearchResultsSummarizer`` uses (and the one the e2e
    fake LLM provider recognizes): the caller builds citations from the same chunk order it
    passed in, so citation N always refers to ``chunks[N - 1]``.
    """

    chunk_limit: int = ConfigurableValue(
        user_default=40,
        desc="Maximum number of chunks summarized for one document. The caller truncates "
             "longer documents to their first chunk_limit chunks, in document order, before "
             "calling the summarizer."
    )

    gen_summary_model_options: ModelOptions = ConfigurableFactory(
        ModelOptions,
        desc="Model options for document summary generation."
    )
    gen_summary_error_summary: str = ConfigurableValue(
        user_default="N/A",
        desc="Summary to use when document summary generation fails."
    )
    gen_summary_system_prompt: Template = ConfigurableValue(
        user_default=LiteralScalarString("""Jsi asistent pro sumarizaci historických dokumentů.
Dostaneš úryvky (chunky) jednoho dokumentu v pořadí, v jakém se v dokumentu vyskytují; každý je označen unikátním ID jako [doc1], [doc2], … [docN].
Tvým úkolem je vytvořit jediný, souvislý souhrn celého dokumentu, který pokryje jeho klíčové body.
Po každém faktu, který z úryvku získáš, připoj ID daného úryvku v hranatých závorkách – například: „Obec byla založena v roce 1850 [doc2].“
Pokud stejný fakt podporuje více úryvků, uveď všechna jejich ID: „Kronikář zaznamenal neúrodu [doc1][doc3].“
Nikdy neslučuj více id do jednoho, jako [doc2-4] nebo [doc2, doc3, doc4], ale vždy je uváděj jednotlivě.
Nevymýšlej žádná fakta, která v úryvcích nejsou. Pokud je dokument zkrácen jen na jeho první úryvky, shrň pouze to, co je v nich obsaženo, a nepředstírej znalost zbytku dokumentu.
Piš přehledně a stručně.
Odpověz pouze souhrnem, bez dalších komentářů nebo úvodních frází.
"""),
        desc="System prompt for document summary generation.",
        transform=TemplateTransformer()
    )
    gen_summary_prompt: Template = ConfigurableValue(
        user_default=LiteralScalarString("""Vytvoř souhrn následujícího dokumentu{% if document_title %} s názvem "{{ document_title }}"{% endif %}.

{% for chunk in chunks %}
[doc{{ loop.index }}] {{ chunk.text }}
{% endfor %}
"""),
        desc="Prompt for document summary generation.",
        transform=TemplateTransformer()
    )

    async def _generate(self, system_prompt: Template, prompt: Template, values: dict,
                        options: ModelOptions) -> str:
        """The generated text; raises when the model call fails."""
        return await self._complete("document_summary", system_prompt, prompt, values, options)

    async def _generate_or_fallback(self, kind: str, fallback: str,
                                    on_error: Optional[Callable[[str, Exception], None]], *args) -> str:
        try:
            return await self._generate(*args)
        except Exception as e:
            # Content-free: the provider error may quote the request (chunk text/prompts).
            logging.error("Document %s generation failed: %s", kind, type(e).__name__)
            if on_error is not None:
                # The caller decides what a failure means for its API contract (#358 review):
                # the search summarizer's callers keep partial results with a warning, but a
                # document summary has only this one generated part, so its caller
                # (features.summarization.service.summarize_document) turns this into a
                # failed request rather than returning the fallback text as if it were a
                # successful summary. The exception itself, not just its kind, is passed
                # through so the caller can keep a safe, server-authored LlmNotConfigured
                # message (as answer_question does) instead of a generic one.
                on_error(kind, e)
            return fallback

    async def gen_document_summary(self, chunks: Sequence[DocumentChunk], document_title: Optional[str] = None,
                                   on_error: Optional[Callable[[str, Exception], None]] = None) -> str:
        """
        Creates an overall summary of a document from ``chunks`` (already truncated by the
        caller to ``chunk_limit``, in document order).

        Unlike the search-results summarizer, there is no caller-supplied prompt override here:
        nothing in the document-summary API lets a client set one (#358 review — it was
        speculative generality, added for symmetry rather than an actual need).

        :param chunks: the document's chunks to summarize, in document order; labelled
            ``[docN]`` (1-based) in the prompt
        :param document_title: optional document title given to the model for context
        :param on_error: called with ("summary", the exception) if generation fails
        :return: the generated summary, or the configured fallback text on failure
        """
        return await self._generate_or_fallback(
            "summary", self.gen_summary_error_summary, on_error,
            self.gen_summary_system_prompt, self.gen_summary_prompt,
            {"chunks": chunks, "document_title": document_title}, self.gen_summary_model_options)


def load_document_summarizer(path: str, llm: LlmGateway) -> TemplatedDocumentSummarizer:
    """The document summarizer configured in the YAML file at ``path``, generating with ``llm``."""
    summarizer = TemplatedDocumentSummarizer.create(path)
    summarizer.llm = llm
    return summarizer
