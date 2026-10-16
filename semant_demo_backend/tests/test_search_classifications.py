"""Classifications of a search hit (#177): stored chunk properties -> ``metadata``."""
from semant_demo.adapters.weaviate.search import classifications
from semant_demo.features.search.filters import TASK_CLASSES


def test_only_populated_classifications_are_returned_in_definition_order():
    stored = {
        "text": "Roku 1848 přijel do Lhoty hejtman.",
        "language": "ces",
        "ner_P": ["Jan Novák"],
        "subject_domain": ["ddc_900_history_geography", "news_and_current_affairs"],
        "style": ["formal"],
        "communicative_mode": ["narration"],
        "complexity": [],
        "emotional_tone": None,
        "unrelated_enrichment": ["x"],
    }

    result = classifications(stored)

    assert result == {
        "communicative_mode": ["narration"],
        "style": ["formal"],
        "subject_domain": ["ddc_900_history_geography", "news_and_current_affairs"],
    }
    assert list(result) == [name for name in TASK_CLASSES if name in result]


def test_legacy_and_untidy_values_are_normalized():
    stored = {"style": "formal", "complexity": "", "documentary_role": ["", None, "legal", "legal", "reference"]}

    assert classifications(stored) == {"style": ["formal"], "documentary_role": ["legal", "reference"]}


def test_stored_properties_are_not_mutated():
    stored = {"style": ["formal", "formal"], "text": "t"}

    classifications(stored)

    assert stored == {"style": ["formal", "formal"], "text": "t"}


def test_chunk_without_classifications_has_none():
    assert classifications({"text": "t", "language": "ces"}) == {}


def test_scalar_values_become_one_element_lists():
    stored = {"communicative_mode": "narration", "complexity": 3, "style": True, "documentary_role": 0}

    assert classifications(stored) == {
        "communicative_mode": ["narration"],
        "complexity": ["3"],
        "documentary_role": ["0"],
        "style": ["True"],
    }
