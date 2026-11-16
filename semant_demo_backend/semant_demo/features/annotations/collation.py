"""Czech sort keys of annotations (#666): dictionary order for the KWIC sorts.

Weaviate sorts text properties by code point, so each annotation stores *collation keys*:
the ICU sort key of a few of its words under the Czech collation (``cs``: ``č`` after ``c``,
``ch`` after ``h``, case and diacritics deciding only ties), hex-encoded. Hex keeps the byte
order of the ICU key under code-point comparison, so Weaviate's sort of the keys is the
Czech order of the words. The Czech rules also apply to the occasional text in another
language (decided in #666).

``leftSortKey``
    The nearest ``CONTEXT_WORDS`` words of the left context, **from the annotation
    outwards** (the word just before the annotation first), joined by a space.
``rightSortKey``
    The first ``CONTEXT_WORDS`` words of the right context, in reading order.
``textSortKey``
    The first ``TEXT_WORDS`` words of the annotated text, in reading order.

Words follow the document word rule (``features/documents/positions.py``): runs of
letters, marks, digits and format characters; punctuation, hyphens and apostrophes
separate words and are not part of a key. Joined by a space (an ICU primary weight below
every letter), the key compares the first word entirely before the second (``ab`` <
``ab x`` < ``abc``), and case or diacritic differences decide only after all words are
equal at the primary level. A side without any word has the empty key ``""``.

``sort_key_version()`` names this policy and the collator (ICU version and the ``cs``
tailoring), stored as ``sortKeyVersion``; ``sortKeyRevision`` is the span revision the keys
were computed for (a release before #666 changes the text without them). Keys of another
version or revision are not current and the backfill (``maintenance/annotation_enrichment.py``)
recomputes them, so an ICU upgrade is a backfill run, not a silently mixed order.
"""
import hashlib
from dataclasses import dataclass
from functools import cache

import icu

from semant_demo.features.documents.positions import word_spans

CONTEXT_WORDS = 5
"""Words of each context in its key."""
TEXT_WORDS = 10
"""Words of the annotated text in its key (a longer annotation ties on the rest, then by id)."""
_POLICY = 1
"""Change with the word selection, the join or the encoding: every key must be recomputed."""


@cache
def _collator() -> icu.Collator:
    return icu.Collator.createInstance(icu.Locale("cs"))


@cache
def sort_key_version() -> str:
    """The version stored with every key (``sortKeyVersion``): the policy, the ICU version and a
    digest of the Czech tailoring rules, e.g. ``1:icu-76.1:3f9c2a1b``."""
    rules = _collator().getRules()
    return f"{_POLICY}:icu-{icu.ICU_VERSION}:{hashlib.sha256(rules.encode()).hexdigest()[:8]}"


def _words(text: str) -> list[str]:
    return [text[s:e] for s, e in word_spans(text)]


def collation_key(words: list[str]) -> str:
    """The hex-encoded Czech ICU sort key of ``words`` joined by a space; ``""`` for no words."""
    if not words:
        return ""
    return _collator().getSortKey(" ".join(words)).hex()


@dataclass(frozen=True)
class SortKeys:
    left: str
    right: str
    text: str
    version: str

    def properties(self, revision: int) -> dict:
        """The stored properties of keys computed for the span's ``revision``."""
        return {"leftSortKey": self.left, "rightSortKey": self.right, "textSortKey": self.text,
                "sortKeyVersion": self.version, "sortKeyRevision": revision}


def sort_keys(text: str, left_context: str, right_context: str) -> SortKeys:
    """The sort keys of an annotation's stored text and contexts (``derivation.DerivedText``)."""
    return SortKeys(left=collation_key(_words(left_context)[::-1][:CONTEXT_WORDS]),
                    right=collation_key(_words(right_context)[:CONTEXT_WORDS]),
                    text=collation_key(_words(text)[:TEXT_WORDS]),
                    version=sort_key_version())


NO_SORT_KEYS = {"leftSortKey": "", "rightSortKey": "", "textSortKey": "", "sortKeyVersion": ""}
"""The keys of an annotation without current text: none, and not current (``""`` version)."""
