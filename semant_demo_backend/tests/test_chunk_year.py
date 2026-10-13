"""Year filters on the chunk's own ``yearIssued`` and its reconciliation with the document (#153)."""
from uuid import UUID

import pytest

from semant_demo.adapters.weaviate.chunk_year import ChunkYear
from semant_demo.adapters.weaviate.search import _condition
from semant_demo.features.search.schemas import FieldCondition, Op
from semant_demo.maintenance.chunk_year import canonical_year, check_ranges, exit_code, expected_year, plan

DOC, OTHER, CHUNK = (UUID(f"5e3a0000-0000-4000-8000-00000000c00{n}") for n in range(1, 4))


@pytest.mark.parametrize("op", [Op.greater_or_equal, Op.less_or_equal, Op.equal])
def test_year_conditions_filter_the_chunk_property(op):
    target = _condition(FieldCondition("yearIssued", op, 1900)).target
    assert target == "yearIssued"  # not through the document reference


def test_other_document_conditions_still_use_the_reference():
    target = _condition(FieldCondition("dateIssued", Op.greater_or_equal, "1900-01-01T00:00:00Z")).target
    assert (target.link_on, target.target) == ("document", "dateIssued")
    assert _condition(FieldCondition("language", Op.equal, "ces")).target == "language"


@pytest.mark.parametrize("value, year", [(None, None), (1902, 1902), (1902.0, 1902)])
def test_canonical_year(value, year):
    assert canonical_year(value) == year


@pytest.mark.parametrize("value", [1902.5, True, "1902", [1902]])
def test_canonical_year_rejects_values_that_are_not_whole_years(value):
    with pytest.raises(ValueError):
        canonical_year(value)


def chunk(year=None, *documents) -> ChunkYear:
    return ChunkYear(CHUNK, year, tuple(documents))


@pytest.mark.parametrize("stored, document_year, expected", [
    (None, 1902, ("set", 1902)),
    (1902, 1902.0, ("consistent", 1902)),
    (1850, 1902, ("change", 1902)),
    (1902, None, ("clear", None)),           # a removed document year does not survive on the chunk
    (None, None, ("no_year", None)),
    (1902, 1902.5, ("invalid_year", None)),  # never rounded
])
def test_plan_follows_the_document_year(stored, document_year, expected):
    assert plan(chunk(stored, DOC), {DOC: document_year}) == expected


def test_chunks_without_a_single_known_document_are_reported_and_untouched():
    years = {DOC: 1902, OTHER: 1902}
    assert plan(chunk(1850), years) == ("no_document", None)
    assert plan(chunk(1850, UUID(int=1)), years) == ("missing_document", None)
    assert plan(chunk(1850, DOC, OTHER), years) == ("several_documents", None)
    assert expected_year("no_document", None, chunk(1850)) == 1850   # it keeps its stored year
    assert expected_year("clear", None, chunk(1850, DOC)) is None


def test_check_ranges_cover_whole_issue_quarter_and_common_ranges():
    histogram = {1850: 10, 1902: 30, 1941: 5, 1950: 5}
    ranges = check_ranges(histogram)
    assert ranges[0] == (1850, 1950) and (1940, 1952) in ranges and (1902, 1902) in ranges
    quarters = [r for r in ranges if r not in ((1850, 1950), (1940, 1952), (1902, 1902))]
    assert quarters == [(1850, 1902), (1941, 1950)]  # 1902 takes the running count past three quarters
    assert len(ranges) == len(set(ranges))
    assert check_ranges({}) == []
    assert (1940, 1952) not in check_ranges({1850: 1})


def result(mode="check", done=True, to_retry=0, ranges=(), **counts):
    return {"mode": mode, "done": done, "to_retry": to_retry, "ranges": list(ranges),
            "counts": {"set": 0, "change": 0, "clear": 0, **counts}}


def test_exit_code():
    match, mismatch = {"match": True}, {"match": False}
    assert exit_code(result(ranges=[match], no_document=3)) == 0      # reported chunks do not fail
    assert exit_code(result(ranges=[match], set=1)) == 1              # a check that finds work
    assert exit_code(result(mode="write", ranges=[match], set=1)) == 0
    assert exit_code(result(mode="write", ranges=[mismatch])) == 1
    assert exit_code(result(mode="write", to_retry=1, ranges=[match])) == 1
    assert exit_code(result(done=False, ranges=[match])) == 1
    assert exit_code({**result(), "ranges": None}) == 1               # the property is not declared
