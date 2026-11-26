"""The generator's prompts (#726), the parsing of their replies and the automated text checks.

Every prompt has a version; changing its wording changes the version, the manifest records the
version and SHA-256 of each, and cached model calls of another version are not reused
(``CallCache`` keys include the version).
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

from semant_demo.benchmarks.search_relevance.languages import name as language_name
from semant_demo.benchmarks.search_relevance.llm import InvalidReply

INTENT_PROMPT_VERSION = "search-benchmark-intent-v1"
TRANSLATION_PROMPT_VERSION = "search-benchmark-translation-v1"
JUDGE_PROMPT_VERSION = "search-benchmark-judge-v1"

STYLES = {
    "keywords": "2 to 5 search keywords, as typed into a search box (no question, no sentence)",
    "question": "a short, specific factual question that the passage answers",
    "entity": "a named person, place, organisation or event of the passage, with a word or two of context",
    "long_question": "a longer natural-language question (15 to 30 words) describing what the user wants to find, "
                     "with some context",
    "paraphrase": "a sentence describing the topic of the passage in other words than the passage uses",
    "ocr": "2 to 6 search words in the old spelling or the OCR-distorted forms the passage itself uses "
           "(as a user copying a word from a scan would type them)",
}
"""Query styles and how the intent prompt describes them; a configuration may add its own."""

INTENT_SYSTEM = (
    "You write test queries for a search engine over a historical library corpus (newspapers, books, "
    "periodicals; texts may have old spelling and OCR errors). Given a passage, you write one information "
    "need that the passage satisfies and one query a user with that need would type. The need is one "
    "English sentence that a person who has not seen the passage can judge other passages against. The "
    "query must make sense without seeing the passage and must not copy a phrase of more than a few words "
    "from it. Reply with JSON only.")

INTENT_REQUEST = "Write one information need and one query of this style:"
"""A line of every intent request (the fake provider recognises it)."""

INTENT_USER = """Document title: {document_title}

Passage:
<<<
{text}
>>>

""" + INTENT_REQUEST + """ {style}: {style_description}
Write the query in {language} ({code}).{avoid}

Reply with this JSON and nothing else:
{{"need": "<the information need, one English sentence>", "query": "<the query in {language}>"}}"""

AVOID_LINE = "\nThe query must not contain this phrase of the passage: \"{phrase}\"."

TRANSLATION_SYSTEM = (
    "You translate search queries for testing a search engine over a historical library corpus. Translate "
    "the query so that a native speaker with the same information need would type it: keep its style "
    "(keywords stay keywords, a question stays a question), keep names as that language writes them, "
    "translate the need rather than word by word. Reply with JSON only.")

TRANSLATION_REQUEST = "Translate this search query into"
"""A line of every translation request."""

TRANSLATION_USER = """Information need: {need}
Query style: {style}
Query ({source_language}):
<<<
{query}
>>>

""" + TRANSLATION_REQUEST + """ {language} ({code}).
Reply with this JSON and nothing else:
{{"translation": "<the query in {language}>"}}"""

JUDGE_SYSTEM = (
    "You judge search results for a historical library corpus. Given an information need, the query a user "
    "typed for it and one retrieved passage, grade how relevant the passage is to the need, whatever their "
    "languages:\n"
    "2 = relevant: the passage satisfies the need or is clearly about what it asks for;\n"
    "1 = partly relevant: the passage touches the topic or gives part of the answer;\n"
    "0 = not relevant.\n"
    "The passage may have old spelling and OCR errors. Reply with the single digit only.")

JUDGE_USER = """Information need: {need}
Query: {query}

Document title: {document_title}

Passage{cut}:
<<<
{text}
>>>

Grade (0, 1 or 2):"""

JUDGE_REQUEST = "Grade (0, 1 or 2):"
"""The last line of every judge request."""
CUT_NOTE = " (cut: only its first {chars} characters are shown)"


def _sha(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()


def prompt_provenance(styles: dict[str, str]) -> dict[str, dict[str, str]]:
    """Version and SHA-256 of each prompt, by role."""
    return {
        "intents": {"prompt_version": INTENT_PROMPT_VERSION,
                    "prompt_sha256": _sha(INTENT_PROMPT_VERSION, INTENT_SYSTEM, INTENT_USER, AVOID_LINE,
                                          json.dumps(styles, sort_keys=True))},
        "translation": {"prompt_version": TRANSLATION_PROMPT_VERSION,
                        "prompt_sha256": _sha(TRANSLATION_PROMPT_VERSION, TRANSLATION_SYSTEM, TRANSLATION_USER)},
        "judge": {"prompt_version": JUDGE_PROMPT_VERSION,
                  "prompt_sha256": _sha(JUDGE_PROMPT_VERSION, JUDGE_SYSTEM, JUDGE_USER, CUT_NOTE)},
    }


# ---- messages and replies -----------------------------------------------------------------

def intent_messages(text: str, document_title: str | None, style: str, style_description: str, language: str,
                    avoid: str | None = None) -> list[dict[str, str]]:
    user = INTENT_USER.format(document_title=document_title or "(unknown)", text=text, style=style,
                              style_description=style_description, language=language_name(language),
                              code=language, avoid=AVOID_LINE.format(phrase=avoid) if avoid else "")
    return [{"role": "system", "content": INTENT_SYSTEM}, {"role": "user", "content": user}]


def translation_messages(need: str, style: str, query: str, source_language: str, language: str
                         ) -> list[dict[str, str]]:
    user = TRANSLATION_USER.format(need=need, style=style, query=query, source_language=language_name(source_language),
                                   language=language_name(language), code=language)
    return [{"role": "system", "content": TRANSLATION_SYSTEM}, {"role": "user", "content": user}]


def judge_messages(need: str, query: str, text: str, document_title: str | None, max_chars: int
                   ) -> list[dict[str, str]]:
    cut = len(text) > max_chars
    user = JUDGE_USER.format(need=need, query=query, document_title=document_title or "(unknown)",
                             cut=CUT_NOTE.format(chars=max_chars) if cut else "",
                             text=text[:max_chars] + " …" if cut else text)
    return [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": user}]


def _json_object(reply: str) -> dict[str, Any]:
    text = reply.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise InvalidReply("not JSON") from None
    if not isinstance(data, dict):
        raise InvalidReply("not a JSON object")
    return data


def _one_line(value: Any) -> str:
    return " ".join(str(value).split()) if isinstance(value, str) else ""


MAX_QUERY_CHARS = 400


def parse_intent(reply: str) -> dict[str, str]:
    """``{"need", "query"}``, both non-empty single lines; raises ``InvalidReply``."""
    data = _json_object(reply)
    need, query = _one_line(data.get("need")), _one_line(data.get("query"))
    if not need:
        raise InvalidReply("no need")
    if not query:
        raise InvalidReply("no query")
    if len(query) > MAX_QUERY_CHARS:
        raise InvalidReply("query too long")
    return {"need": need, "query": query}


def parse_translation(reply: str) -> str:
    data = _json_object(reply)
    translation = _one_line(data.get("translation"))
    if not translation:
        raise InvalidReply("no translation")
    if len(translation) > MAX_QUERY_CHARS:
        raise InvalidReply("translation too long")
    return translation


def parse_grade(reply: str) -> int:
    """The grade of a judge reply (``0``, ``1`` or ``2`` alone); raises ``InvalidReply``."""
    text = reply.strip().strip("*`'\".").strip()
    if text not in ("0", "1", "2"):
        raise InvalidReply("not a single grade" if len(text) != 1 else "grade out of range")
    return int(text)


# ---- automated checks ---------------------------------------------------------------------

def words(text: str) -> list[str]:
    """Lower-case words without accents' combining marks removed (comparison only)."""
    return re.findall(r"\w+", unicodedata.normalize("NFKC", text).lower())


def longest_copied_run(query: str, passage: str) -> tuple[int, str]:
    """The longest run of consecutive words of ``query`` that occurs in ``passage``, and that phrase."""
    q, p = words(query), words(passage)
    best, end = 0, 0
    previous = [0] * (len(p) + 1)
    for i in range(1, len(q) + 1):
        current = [0] * (len(p) + 1)
        for j in range(1, len(p) + 1):
            if q[i - 1] == p[j - 1]:
                current[j] = previous[j - 1] + 1
                if current[j] > best:
                    best, end = current[j], i
        previous = current
    return best, " ".join(q[end - best:end])


def is_near_copy(query: str, passage: str, max_copied_words: int) -> str | None:
    """The copied phrase when ``query`` repeats more than ``max_copied_words`` consecutive words of
    ``passage``, or is (almost) all of the passage; None otherwise."""
    run, phrase = longest_copied_run(query, passage)
    if run > max_copied_words:
        return phrase
    passage_words = words(passage)
    if passage_words and run >= max(3, int(0.8 * len(passage_words))):
        return phrase
    return None


_STOPWORDS = {
    "ces": {"a", "je", "se", "v", "na", "o", "z", "do", "že", "ve", "jak", "kdy", "kde", "co", "proč", "který",
            "která", "které", "byl", "byla", "bylo", "pro", "od", "po", "s", "k", "u", "jaký", "jaká", "kdo"},
    "eng": {"the", "and", "of", "in", "a", "to", "was", "is", "what", "when", "where", "who", "how", "why", "which",
            "for", "on", "by", "with", "did", "does", "from", "at"},
    "deu": {"der", "die", "das", "und", "in", "von", "zu", "im", "mit", "ist", "war", "wie", "wann", "wo", "wer",
            "was", "warum", "welche", "welcher", "den", "dem", "des", "ein", "eine", "auf", "für", "bei"},
}
_LETTERS = {"ces": set("čřěůšžťďňý"), "deu": set("äöüß")}


def language_signal(text: str) -> dict[str, int]:
    """A cheap language score of a short text for ces/eng/deu: stopwords and letters typical of
    the language (Czech and German diacritics). Empty when nothing points anywhere."""
    found: dict[str, int] = {}
    tokens = words(text)
    for code, stop in _STOPWORDS.items():
        score = sum(1 for t in tokens if t in stop)
        score += 2 * sum(1 for ch in text.lower() if ch in _LETTERS.get(code, ()))
        if score:
            found[code] = score
    return found


def language_doubtful(text: str, language: str) -> bool:
    """True when the heuristic clearly points to another of its languages than ``language``: some
    language scores at least 2 and more than twice ``language``'s score (an unknown language,
    or no signal at all, is never doubtful)."""
    if language not in _STOPWORDS:
        return False
    signal = language_signal(text)
    if not signal:
        return False
    best = max(signal.values())
    return best >= 2 and 2 * signal.get(language, 0) < best


def word_overlap(a: str, b: str) -> float:
    """Jaccard similarity of the word sets (back-translation consistency)."""
    x, y = set(words(a)), set(words(b))
    return len(x & y) / len(x | y) if x | y else 1.0
