"""The ``[doc N]`` citations of a RAG answer (#370).

An answer cites ``sources[N-1]`` of its own ``RagResponse`` by ``[doc N]`` (also ``[docN]``,
``[doc 1, doc 2]`` or ``[dokument N]``, as the chat page reads them). A pipeline numbers the
passages it shows the model in the order of the sources it returns; this module finds the
citations that have no such source. They are reported, never moved to another source: the
chat page leaves them as written.
"""
import logging
import re

logger = logging.getLogger(__name__)

_BRACKETS = re.compile(r"\[([^\[\]]+)\]")
_CITATION = re.compile(r"\b(?:doc|dokument)\s*(\d+)\b", re.IGNORECASE)


def cited_numbers(answer: str) -> list[int]:
    """The source numbers ``N`` of the answer's citations, in order of appearance."""
    return [int(number) for brackets in _BRACKETS.finditer(answer)
            for number in _CITATION.findall(brackets.group(1))]


def unresolved_citations(answer: str, source_count: int) -> list[int]:
    """The cited numbers without a source among ``source_count`` sources."""
    return [n for n in cited_numbers(answer) if not 1 <= n <= source_count]


def check_citations(answer: str, source_count: int, pipeline: str) -> None:
    """Logs (without content) how many citations of the answer have no source."""
    unresolved = unresolved_citations(answer, source_count)
    if unresolved:
        logger.warning("RAG answer cites sources it does not return",
                       extra={"rag.pipeline": pipeline, "rag.unresolved_citations": len(unresolved),
                              "rag.sources": source_count})
