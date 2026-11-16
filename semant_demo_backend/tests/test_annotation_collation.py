"""Czech sort keys of annotations (#666): ``features/annotations/collation.py``.

The keys are compared as Weaviate compares text, by code point; sorting by them must give
Czech dictionary order. Weaviate's sort itself: tests/integration/test_annotation_sorting.py.
"""
import pytest

from semant_demo.features.annotations.collation import (
    CONTEXT_WORDS, NO_SORT_KEYS, TEXT_WORDS, collation_key, sort_key_version, sort_keys,
)


def ordered(*phrases: str) -> list[str]:
    """``phrases`` sorted by their keys as code-point strings (Weaviate's text sort)."""
    return sorted(phrases, key=lambda p: collation_key(p.split()))


def test_czech_letters_follow_their_base_letters():
    assert ordered("hrad", "chata", "cesta", "čas", "d", "h", "i", "c") == \
        ["c", "cesta", "čas", "d", "h", "hrad", "chata", "i"]
    assert ordered("řeka", "rak", "s", "šašek", "zima", "žena") == ["rak", "řeka", "s", "šašek", "zima", "žena"]


def test_case_and_diacritics_decide_only_ties():
    # Primary differences win over an earlier case or accent difference...
    assert ordered("Hrad", "hrát", "hrad") == ["hrad", "Hrad", "hrát"]
    assert ordered("Abc", "abd") == ["Abc", "abd"]
    # ...and case-only or accent-only differences still give a fixed order.
    assert ordered("Kos", "kos") == ["kos", "Kos"]
    assert ordered("sál", "sal") == ["sal", "sál"]
    assert collation_key(["kos"]) != collation_key(["Kos"])


def test_the_first_word_is_compared_entirely_before_the_next():
    assert ordered("abc", "ab x", "ab", "abd a") == ["ab", "ab x", "abc", "abd a"]
    # A case or accent difference in the first word decides only when every word is equal otherwise.
    assert ordered("Praha zima", "praha léto") == ["praha léto", "Praha zima"]


def test_keys_are_hex_and_keep_the_order_of_the_icu_bytes():
    key = collation_key(["čas"])
    assert key and set(key) <= set("0123456789abcdef") and len(key) % 2 == 0
    assert collation_key([]) == ""


def test_left_keys_start_from_the_word_next_to_the_annotation():
    near_b = sort_keys("X", "zzz aaa b", "").left
    near_a = sort_keys("X", "aaa zzz a", "").left
    assert near_a < near_b  # "a" (nearest) before "b", whatever the words further away
    # Then the second-nearest word decides.
    assert sort_keys("X", "beta a", "").left < sort_keys("X", "gama a", "").left
    assert sort_keys("X", "one two three", "").left == collation_key(["three", "two", "one"])


def test_right_and_text_keys_are_in_reading_order():
    keys = sort_keys("Jan Novák", "", " přijel včera")
    assert keys.right == collation_key(["přijel", "včera"])
    assert keys.text == collation_key(["Jan", "Novák"])


def test_punctuation_hyphens_and_apostrophes_separate_words_and_are_not_keyed():
    assert sort_keys("Frýdek-Místek", "", "").text == collation_key(["Frýdek", "Místek"])
    assert sort_keys("X", "", " d'Artagnan, (pan)").right == collation_key(["d", "Artagnan", "pan"])
    assert sort_keys("X", "„Ano!“ ", "").left == collation_key(["Ano"])


def test_a_side_without_words_has_the_empty_key():
    keys = sort_keys("Kronika", "", ".")  # start of the document, only punctuation after
    assert (keys.left, keys.right) == ("", "")
    assert sort_keys("—", "a", "b").text == ""


def test_only_the_nearest_words_are_keyed():
    many = " ".join(f"w{i}" for i in range(20))
    keys = sort_keys(many, many, many)
    words = many.split()
    assert keys.left == collation_key(words[::-1][:CONTEXT_WORDS])
    assert keys.right == collation_key(words[:CONTEXT_WORDS])
    assert keys.text == collation_key(words[:TEXT_WORDS])


def test_a_word_split_by_a_chunk_boundary_is_one_word():
    # The stored contexts are the document text, chunk boundaries removed: keys see whole words.
    assert sort_keys("X", "", " Bratislava").right == collation_key(["Bratislava"])


def test_the_version_names_the_policy_and_the_collator():
    version = sort_key_version()
    policy, icu_version, rules = version.split(":")
    assert policy == "1" and icu_version.startswith("icu-") and len(rules) == 8
    assert sort_keys("a", "b", "c").version == version
    assert NO_SORT_KEYS["sortKeyVersion"] == ""


@pytest.mark.parametrize("composed, decomposed", [("čas", "c\u030cas"), ("Ýdy", "Y\u0301dy")])
def test_canonically_equivalent_text_has_the_same_key(composed, decomposed):
    assert collation_key([composed]) == collation_key([decomposed])
