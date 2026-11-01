"""Search criteria (#526, features/documents/criteria.py): normalization and validation of the
shared filters, their predicates, and the Weaviate filters they become
(adapters/weaviate/criteria.py). The store's matching is checked in
tests/integration/test_search_criteria.py; the DocumentFilters rules in test_corpus_analytics.py.
"""
import pytest
from pydantic import ValidationError
from weaviate.classes.query import Filter

from semant_demo.adapters.weaviate.criteria import UnavailableFilter, parts, where, word_supersets
from semant_demo.core.errors import InvalidRequestError
from semant_demo.features.documents.criteria import (
    AnyOf, CategoryIn, ChunkFilters, ChunkVocabulary, ContainsWords, DocumentFilters, InvalidChunkFilterError,
    NumberRange, SearchCriteria, chunk_conditions, document_chunk_conditions, document_conditions,
    document_level_conditions, validate_chunk_filters)
from semant_demo.features.search.filters import TASK_CLASSES, chunk_vocabulary, generate_default_filters

VOCABULARY = ChunkVocabulary(languages=("ces", "deu"), classifications={
    "complexity": ("very_easy", "easy", "moderate"), "style": ("formal", "informal")})


##########
# Models #
##########

def test_chunk_filters_are_trimmed_deduplicated_and_sorted():
    filters = ChunkFilters(languages=[" deu", "ces", "deu"],
                           classifications={"style": ["informal ", "formal", "formal"], " complexity": ["easy"]})

    assert filters.languages == ["ces", "deu"]
    assert filters.classifications == {"complexity": ["easy"], "style": ["formal", "informal"]}
    assert ChunkFilters().is_empty() and not filters.is_empty()


@pytest.mark.parametrize("data, message", [
    ({"classifications": {"style": []}}, "needs at least one value"),
    ({"languages": [" "]}, "must be non-empty"),
    ({"languages": [f"l{i}" for i in range(51)]}, "at most 50 items"),
    ({"classifications": {"style": [f"s{i}" for i in range(51)]}}, "at most 50 values"),
    ({"year_min": 1900}, "Extra inputs are not permitted"),     # no year among chunk filters
    ({"unknown": ["x"]}, "Extra inputs are not permitted"),     # no "missing value" either
])
def test_invalid_chunk_filters_are_rejected(data, message):
    with pytest.raises(ValidationError) as error:
        ChunkFilters.model_validate(data)
    assert message in str(error.value)


def test_chunk_filters_from_query_parameters_group_values_by_classification():
    filters = ChunkFilters.from_query(["deu", " ces"], ["style:formal", "complexity: easy", "style:informal"])

    assert filters == ChunkFilters(languages=["ces", "deu"],
                                   classifications={"complexity": ["easy"], "style": ["formal", "informal"]})
    assert ChunkFilters.from_query([], []).is_empty()


@pytest.mark.parametrize("item", ["complexity", "complexity:", ":easy", " :easy"])
def test_chunk_filters_from_query_need_a_classification_and_a_value(item):
    with pytest.raises(ValueError, match="<classification>:<value>"):
        ChunkFilters.from_query([], [item])


def test_search_criteria_have_an_optional_text_query_and_both_filter_kinds():
    assert SearchCriteria(text_query="  ") == SearchCriteria()
    criteria = SearchCriteria(text_query=" Lhota ", document_filters={"libraries": ["mzk"]},
                              chunk_filters={"languages": ["ces"]})

    assert criteria.text_query == "Lhota"
    assert criteria.document_filters == DocumentFilters(libraries=["mzk"])
    assert criteria.chunk_filters == ChunkFilters(languages=["ces"])
    with pytest.raises(ValidationError):
        SearchCriteria(limit=10)  # retrieval settings belong to the endpoint's request


##############
# Validation #
##############

def test_chunk_filters_get_the_configured_spelling():
    filters = ChunkFilters(languages=["CES"], classifications={"complexity": ["Easy", "easy"]})

    assert validate_chunk_filters(filters, VOCABULARY) == \
        ChunkFilters(languages=["ces"], classifications={"complexity": ["easy"]})


@pytest.mark.parametrize("filters, message", [
    (ChunkFilters(classifications={"emotion": ["x"]}), "'emotion' is not a configured classification"),
    (ChunkFilters(classifications={"style": ["casual"]}), "'casual' is not a valid option for 'style'"),
    (ChunkFilters(languages=["Czech"]), "'Czech' is not a valid option for 'languages'"),  # codes only
])
def test_unconfigured_chunk_filters_are_a_bad_request(filters, message):
    with pytest.raises(InvalidChunkFilterError) as error:
        validate_chunk_filters(filters, VOCABULARY)
    assert isinstance(error.value, InvalidRequestError)  # 400
    assert message in str(error.value)


def test_the_vocabulary_is_the_configured_chunk_language_and_classification_filters():
    vocabulary = chunk_vocabulary(generate_default_filters(min_year=1800, max_year=1950, languages=["ces", "deu"]))

    assert vocabulary.languages == ("ces", "deu")
    assert set(vocabulary.classifications) == set(TASK_CLASSES)   # the year range is not a chunk filter
    assert vocabulary.classifications["complexity"] == tuple(TASK_CLASSES["complexity"])


##############
# Predicates #
##############

def test_document_filters_become_document_predicates():
    filters = DocumentFilters(year_min=1850, year_max=1900, title_contains=["Kronika obce", "listy"],
                              libraries=["nkp", "mzk"], languages=["ces"])

    assert document_conditions(filters) == [
        NumberRange("yearIssued", 1850, 1900),
        ContainsWords("title", (("Kronika", "obce"), ("listy",))),
        AnyOf("library", ("mzk", "nkp")),
        AnyOf("language", ("ces",)),
    ]
    assert document_conditions(DocumentFilters()) == []


def test_chunk_filters_become_exact_category_predicates_with_the_other_values():
    filters = validate_chunk_filters(
        ChunkFilters(languages=["ces"], classifications={"complexity": ["easy", "moderate"]}), VOCABULARY)

    assert chunk_conditions(filters, VOCABULARY) == [
        CategoryIn("language", ("ces",), others=("deu",)),
        CategoryIn("complexity", ("easy", "moderate"), others=("very_easy",)),
    ]


def test_document_level_chunk_filters_are_predicates_on_the_document_summaries_per_dimension():
    filters = validate_chunk_filters(
        ChunkFilters(languages=["ces"], classifications={"complexity": ["easy"], "style": ["formal"]}), VOCABULARY)

    # One predicate per dimension, each on its own summary: different chunks may meet them (#529).
    assert document_chunk_conditions(filters, VOCABULARY) == [
        CategoryIn("chunk_language", ("ces",), others=("deu",)),
        CategoryIn("chunk_complexity", ("easy",), others=("very_easy", "moderate")),
        CategoryIn("chunk_style", ("formal",), others=("informal",)),
    ]


def test_document_level_conditions_combine_document_and_chunk_filters():
    chunks, conditions = document_level_conditions(
        DocumentFilters(libraries=["mzk"]), ChunkFilters(classifications={"complexity": ["EASY"]}), VOCABULARY)

    assert chunks == ChunkFilters(classifications={"complexity": ["easy"]})  # the configured spelling
    assert conditions == [AnyOf("library", ("mzk",)),
                          CategoryIn("chunk_complexity", ("easy",), others=("very_easy", "moderate"))]
    assert document_level_conditions(None, None, None) == (ChunkFilters(), [])
    assert document_level_conditions(DocumentFilters(year_min=1900), ChunkFilters(), None) == \
        (ChunkFilters(), [NumberRange("yearIssued", 1900, None)])


def test_document_level_chunk_filters_need_the_configured_vocabulary():
    with pytest.raises(InvalidChunkFilterError, match="'casual' is not a valid option for 'style'"):
        document_level_conditions(None, ChunkFilters(classifications={"style": ["casual"]}), VOCABULARY)
    with pytest.raises(InvalidRequestError, match="Chunk filters are not available"):
        document_level_conditions(None, ChunkFilters(languages=["ces"]), None)


##################
# Weaviate filter #
##################

CHUNK_TYPES = {"language": "text", "complexity": "text[]", "style": "text[]", "yearIssued": "int"}


def _leaves(f):
    """(target, operator, value) of every comparison, depth first; ``not`` marks a negation."""
    name = type(f).__name__
    if name == "_FilterNot":
        return [("not", _leaves(f.filters if not isinstance(f.filters, list) else f.filters[0]))]
    if hasattr(f, "filters"):
        return [leaf for child in f.filters for leaf in _leaves(child)]
    return [(f.target, f.operator.value, f.value)]


def test_with_word_tokenization_a_value_excludes_the_values_containing_its_words():
    # ``word`` matching finds "easy" in "very_easy" (verified in the integration tests).
    f = where([CategoryIn("complexity", ("easy",), others=("very_easy", "moderate"))], CHUNK_TYPES, {"complexity": "word"})

    assert type(f).__name__ == "_FilterAnd"
    assert _leaves(f) == [("complexity", "ContainsAny", ["easy"]),
                          ("not", [("complexity", "ContainsAny", ["very_easy"])])]


def test_with_field_tokenization_values_are_matched_whole():
    f = where([CategoryIn("complexity", ("easy", "moderate"), others=("very_easy",))], CHUNK_TYPES,
              {"complexity": "field"})

    assert _leaves(f) == [("complexity", "ContainsAny", ["easy", "moderate"])]


def test_values_without_confusable_others_are_plain_alternatives():
    f = where([CategoryIn("complexity", ("very_easy", "moderate"), others=("easy",))], CHUNK_TYPES)

    assert type(f).__name__ == "_FilterOr"
    assert _leaves(f) == [("complexity", "ContainsAny", ["very_easy"]), ("complexity", "ContainsAny", ["moderate"])]


def test_confusable_values_are_those_containing_every_word():
    assert word_supersets("easy", ["very_easy", "moderate", "EASY"]) == ["very_easy"]
    assert word_supersets("national", ["multi_national_or_continental", "regional"]) == \
        ["multi_national_or_continental"]
    assert word_supersets("very_easy", ["easy"]) == []


def test_document_predicates_can_target_a_reference():
    by_document = parts([AnyOf("library", ("mzk",))], {"library": "text"},
                        target=lambda prop: Filter.by_ref(link_on="document").by_property(prop))

    [library] = by_document
    assert (library.target.link_on, library.target.target) == ("document", "library")


@pytest.mark.parametrize("condition, reason", [
    (CategoryIn("emotion", ("calm",)), "missing"),
    (CategoryIn("yearIssued", ("1900",)), "unsupported_type"),
])
def test_a_chunk_predicate_on_a_property_the_store_cannot_filter_is_refused(condition, reason):
    with pytest.raises(UnavailableFilter) as refused:
        where([condition], CHUNK_TYPES, records="Chunks")
    assert (refused.value.prop, refused.value.reason) == (condition.prop, reason)
    assert str(refused.value).startswith(f"Chunks cannot be filtered by {condition.prop}")


def test_document_summaries_are_matched_whole_with_their_field_tokenization():
    types = {"chunk_complexity": "text[]"}
    f = where([CategoryIn("chunk_complexity", ("easy",), others=("very_easy",))], types, {"chunk_complexity": "field"})

    assert _leaves(f) == [("chunk_complexity", "ContainsAny", ["easy"])]


def test_chunk_filters_on_a_store_without_document_summaries_are_refused():
    with pytest.raises(UnavailableFilter) as refused:
        where([CategoryIn("chunk_complexity", ("easy",))], {"title": "text"})
    assert str(refused.value) == ("Documents cannot be filtered by chunk values (chunk_complexity): this corpus "
                                  "database has no chunk-value summaries of its documents.")
