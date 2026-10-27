"""The append-only chunk import without a store (#313): input validation and the plan.

The plan decides from what is stored: a new document starts at ``DOCUMENT_START``, an
append continues from the stored tail with the shared position calculator, a replay
writes nothing, and anything that would change, interleave or skip stored chunks is
rejected.
"""
import json
from uuid import UUID

import pytest

from semant_demo.adapters.weaviate.chunk_ingest import StoredChunk
from semant_demo.adapters.weaviate.chunk_positions import OrderStats
from semant_demo.features.documents.positions import ChunkPosition, chunk_positions
from semant_demo.maintenance import chunk_ingest
from semant_demo.maintenance.chunk_ingest import InputChunk, plan, read_input

DOC, OTHER = UUID(int=1), UUID(int=2)
TEXTS = ["hel", "lo world", "", ", ſtará 18", "48­"]


def cid(i: int, document: UUID = DOC) -> UUID:
    return UUID(int=document.int * 1000 + i)


def line(i: int, document: UUID = DOC, **extra) -> dict:
    return {"id": str(cid(i, document)), "document": str(document), "order": i, "text": TEXTS[i % len(TEXTS)],
            **extra}


def write_jsonl(path, records) -> list:
    path.write_text("".join((r if isinstance(r, str) else json.dumps(r)) + "\n" for r in records), encoding="utf-8")
    return [path]


def chunks(orders, document: UUID = DOC) -> list[InputChunk]:
    return [InputChunk(cid(i, document), document, i, TEXTS[i % len(TEXTS)], {}, f"in:{i}") for i in orders]


def stored(orders, positions=True, document: UUID = DOC, text=None, fields=None) -> list[StoredChunk]:
    """Stored chunks equal to the input ``chunks(range(0, ...))`` with the calculator's positions."""
    every = list(range(max(orders) + 1))
    computed = list(chunk_positions(TEXTS[i % len(TEXTS)] for i in every))
    return [StoredChunk(cid(i, document), document, i, text or TEXTS[i % len(TEXTS)], fields or {},
                        computed[i] if positions else None) for i in orders]


# ── Input ────────────────────────────────────────────────────────────────


def test_valid_lines_are_grouped_by_document(tmp_path):
    data = read_input(write_jsonl(tmp_path / "a.jsonl", [line(0), line(1, OTHER), line(1), line(2, OTHER)]))
    assert [c.order for c in data.documents[DOC]] == [0, 1]
    assert [c.order for c in data.documents[OTHER]] == [1, 2]
    assert not data.invalid and not data.unattributed and data.lines == 4


def test_source_fields_are_kept_and_legacy_document_metadata_and_vectors_ignored(tmp_path):
    data = read_input(write_jsonl(tmp_path / "a.jsonl", [
        line(0, start_page_id="p1", from_page=3, to_page=4, end_paragraph=True, language="ces",
             title="Kronika", year=1920, author="X", vector_index=7),
        line(1, vector=[0.1, 0.2])]))
    assert data.documents[DOC][0].fields == {"start_page_id": "p1", "from_page": 3, "to_page": 4,
                                             "end_paragraph": True, "language": "ces"}
    assert data.ignored == {"title": 1, "year": 1, "author": 1, "vector_index": 1, "vector": 1}
    assert not data.invalid


def test_files_are_read_in_path_order(tmp_path):
    write_jsonl(tmp_path / "b.jsonl", [line(1)])
    write_jsonl(tmp_path / "a.jsonl", [line(0)])
    data = read_input([tmp_path / "b.jsonl", tmp_path / "a.jsonl"])
    assert [c.order for c in data.documents[DOC]] == [0, 1] and not data.invalid


@pytest.mark.parametrize("record, reason", [
    (line(0, unknown=1), "unknown field 'unknown'"),
    (line(0, startChar=0), "positions are computed by the import"),
    ({**line(0), "order": "1"}, "'order' is not int"),
    ({**line(0), "order": True}, "'order' is not int"),
    ({**line(0), "text": None}, "'text' is not text"),
    ({**line(0), "id": "x"}, "'id' is not a UUID"),
    ({k: v for k, v in line(0).items() if k != "text"}, "missing 'text'"),
    (line(0, from_page="3"), "'from_page' is not int"),
    (line(0, end_paragraph=1), "'end_paragraph' is not boolean"),
])
def test_an_invalid_line_rejects_its_document(tmp_path, record, reason):
    data = read_input(write_jsonl(tmp_path / "a.jsonl", [record, line(1)]))
    assert reason in data.invalid[DOC]


def test_lines_without_a_document_are_reported(tmp_path):
    data = read_input(write_jsonl(tmp_path / "a.jsonl", ["not json", "[1]", {"order": 0}, line(0)]))
    assert len(data.unattributed) == 3 and DOC in data.documents


@pytest.mark.parametrize("orders", [[0, 2], [1, 0], [0, 1, 1]])
def test_input_orders_must_be_consecutive(tmp_path, orders):
    records = [{**line(i), "id": str(UUID(int=500 + n))} for n, i in enumerate(orders)]
    data = read_input(write_jsonl(tmp_path / "a.jsonl", records))
    assert "orders must be consecutive" in data.invalid[DOC]


def test_a_chunk_id_used_twice_rejects_both_documents(tmp_path):
    data = read_input(write_jsonl(tmp_path / "a.jsonl", [line(0), {**line(0, OTHER), "id": str(cid(0))}]))
    assert set(data.invalid) == {DOC, OTHER}


# ── Plan ─────────────────────────────────────────────────────────────────


def none() -> OrderStats:
    return OrderStats(0, None, None)


def test_a_new_document_starts_at_the_document_start_and_may_start_at_any_order():
    result = plan(chunks([5, 6]), none(), {}, [], document_exists=False)
    assert result.action == "new" and result.create_document
    assert [p for _, p in result.inserts] == list(chunk_positions(TEXTS[i] for i in (5 % 5, 6 % 5)))


def test_an_existing_empty_document_gets_its_chunks_without_being_created():
    result = plan(chunks([0, 1]), none(), {}, [], document_exists=True)
    assert result.action == "new" and not result.create_document and len(result.inserts) == 2


def test_an_append_continues_from_the_stored_tail():
    result = plan(chunks([3, 4]), OrderStats(3, 0, 2), {}, stored([2]), document_exists=True)
    everything = list(chunk_positions(TEXTS[i] for i in range(5)))
    assert result.action == "append" and result.replayed == 0
    assert [(c.order, p) for c, p in result.inserts] == [(3, everything[3]), (4, everything[4])]


def test_a_replay_of_the_stored_chunks_plus_new_ones_inserts_only_the_new_ones():
    result = plan(chunks(range(5)), OrderStats(3, 0, 2), {cid(i): stored([i])[0] for i in range(3)}, stored(range(3)),
                  document_exists=True)
    assert result.action == "append" and result.replayed == 3 and [c.order for c, _ in result.inserts] == [3, 4]


def test_a_complete_replay_writes_nothing():
    result = plan(chunks(range(3)), OrderStats(3, 0, 2), {cid(i): stored([i])[0] for i in range(3)}, stored(range(3)),
                  document_exists=True)
    assert result.action == "replayed" and not result.inserts and result.replayed == 3


@pytest.mark.parametrize("input_orders, stats, reason", [
    ([4], OrderStats(3, 0, 2), "gap"),
    ([0], OrderStats(2, 1, 2), "before_start"),
    ([3], OrderStats(2, 0, 2), "nonconsecutive_store"),
])
def test_gaps_inserts_before_the_stored_chunks_and_nonconsecutive_stores_are_rejected(input_orders, stats, reason):
    result = plan(chunks(input_orders), stats, {}, stored([stats.last]), document_exists=True)
    assert result.action == "rejected" and result.reason.startswith(reason) and not result.inserts


def test_a_changed_text_of_a_stored_chunk_is_a_conflict():
    result = plan(chunks(range(3)), OrderStats(2, 0, 1), {}, stored(range(2), text="other"), document_exists=True)
    assert result.action == "rejected" and "stores another text" in result.reason


def test_a_changed_source_field_is_a_conflict():
    result = plan(chunks(range(3)), OrderStats(2, 0, 1), {}, stored(range(2), fields={"language": "ces"}),
                  document_exists=True)
    assert result.action == "rejected" and "language" in result.reason


def test_a_stored_position_other_than_the_computed_one_is_a_conflict():
    rows = stored(range(2))
    rows[1] = StoredChunk(rows[1].id, DOC, 1, rows[1].text, {}, ChunkPosition(99, 0, False))
    result = plan(chunks(range(3)), OrderStats(2, 0, 1), {}, rows, document_exists=True)
    assert result.action == "rejected" and "position" in result.reason


def test_a_tail_without_positions_is_refused():
    result = plan(chunks([2]), OrderStats(2, 0, 1), {}, stored([1], positions=False), document_exists=True)
    assert result.action == "rejected" and result.reason.startswith("positions_missing")


def test_an_input_id_stored_elsewhere_is_a_conflict():
    elsewhere = StoredChunk(cid(0), OTHER, 0, TEXTS[0], {}, None)
    result = plan(chunks([0]), none(), {cid(0): elsewhere}, [], document_exists=False)
    assert result.action == "rejected" and result.reason.startswith("conflict")


def test_chunks_of_a_missing_document_object_are_refused():
    result = plan(chunks([3]), OrderStats(3, 0, 2), {}, stored([2]), document_exists=False)
    assert result.action == "rejected" and result.reason.startswith("dangling_document")


def test_exit_code():
    done = {"done": True, "blocked": 0, "invalid_lines": 0, "counts": {"rejected": 0}}
    assert chunk_ingest.exit_code(done) == 0
    for change in ({"done": False}, {"blocked": 1}, {"invalid_lines": 1}, {"counts": {"rejected": 1}}):
        assert chunk_ingest.exit_code(done | change) == 1


@pytest.mark.parametrize("argv", [
    ["--check", "c.json", "--offline-backup", "note", "in.jsonl"],
    ["--check", "c.json", "--backup-id", "b", "in.jsonl"],
    ["--check", "c.json", "--bulk", "in.jsonl"],
])
async def test_a_check_with_a_backup_option_is_refused(argv):
    assert await chunk_ingest._main(argv) == 2
