"""The read-only import status report over appended data (#884, #560 D).

The appended data and the stages are those of ``tests/append_pipeline.py``, except that the
mirror has a row for the *Freudenthaler Zeitung* with ``public=false``: a resolved document that
is not public. ``chunk_titles`` defers its chunks, and the fake classifier is an API model
(``remote``), which skips them.
"""
import json
from pathlib import Path
from uuid import UUID

import pytest

from semant_demo.maintenance import chunk_summary_schema, import_status, metadata_sync
from tests.append_pipeline import CHRONICLE, FREUDENTHAL, INPUT, KARLIN, mirror_connection, quiet, row, snapshot
from tests.fakes import SECOND_VECTOR

pytestmark = pytest.mark.integration

LINES = [json.loads(line) for line in INPUT.read_text(encoding="utf-8").splitlines()]
RESTRICTED = [UUID(c["id"]) for c in LINES if c["document"] == FREUDENTHAL]
PUBLIC_CHUNKS = [UUID(c["id"]) for c in LINES if c["document"] != FREUDENTHAL]
APPENDED = [UUID(c["id"]) for c in LINES if c["document"] == CHRONICLE]
API_CLASSIFIER = {"classifier_includes_restricted": False}
"""The options matching the fake classifier, an API model that skips documents that are not public."""


@pytest.fixture
def append_mirror():
    """The new documents and the chronicle; the Freudenthaler Zeitung resolves as not public."""
    with mirror_connection([row(KARLIN, "mzk", title="Karlínské listy", date="1904"),
                            row(FREUDENTHAL, "mzk", title="Freudenthaler Zeitung", public=False),
                            row(CHRONICLE, "nkp", title="Kronika obce Lhota")]) as connection:
        yield connection


@pytest.fixture
async def prepared(seeded_store, collection_names):
    """The summary properties declared, as on production (#561)."""
    await chunk_summary_schema.update(seeded_store, collection_names, apply=True)
    return seeded_store


async def run_stages(stages, *, leave_out: str | None = None) -> list[UUID]:
    """Import and then every stage of *Afterwards* in order, but ``leave_out``; the document list."""
    _, code, document_list = await stages.ingest()
    assert code == 0
    if leave_out != "metadata":
        await stages.metadata(document_list)
    if leave_out != "year":
        await stages.year()
    if leave_out != "visibility":
        await stages.visibility(document_list)
    if leave_out != "titles":
        await stages.titles_run()
    if leave_out != "vectors":
        await stages.embed()
    if leave_out != "classification":
        await stages.classify()
    if leave_out != "summaries":
        await stages.summaries()
    return metadata_sync.read_document_ids(document_list)


async def report(client, names, tmp_path: Path, ids: list[UUID], **options) -> dict:
    return await import_status.run(client, names, report=tmp_path / "status.json", document_ids=ids, endpoint="test",
                                   vector_name=SECOND_VECTOR, progress=quiet, **options)


def incomplete_ids(result: dict, stage: str) -> set[UUID]:
    return {UUID(e["id"]) for e in result["stages"][stage]["incomplete_ids"]}


async def test_after_every_stage_the_import_is_complete_but_for_the_restricted_documents_gaps(
        prepared, collection_names, append_stages, tmp_path):
    ids = await run_stages(append_stages)
    before = await snapshot(prepared, collection_names)

    result = await report(prepared, collection_names, tmp_path, ids, **API_CLASSIFIER)

    assert import_status.exit_code(result) == 0 and result["complete"] is True
    assert json.loads((tmp_path / "status.json").read_text(encoding="utf-8")) == result
    assert (result["documents_listed"], result["chunks_examined"]) == (3, 3 + len(LINES))   # the chronicle's 3
    stages = result["stages"]
    assert {name: stage["incomplete"] for name, stage in stages.items()} == dict.fromkeys(import_status.STAGES, 0)
    assert {name: stage["complete"] for name, stage in stages.items() if stage["unit"] == "documents"} == {
        "chunks": 3, "metadata": 3, "summaries": 3}
    assert stages["titles"]["expected_gap_reasons"] == {"deferred_restricted_document": len(RESTRICTED)}
    assert stages["classification"]["expected_gap_reasons"] == {   # the chronicle's seeded chunks: no status
        "skipped_restricted_document": len(RESTRICTED), "stored_before_status": 3}
    assert stages["visibility"]["complete"] == result["chunks_examined"]
    index = result["index"]
    assert (index["candidates"], index["sampled"], index["self_in_top_k"], index["retried"],
            index["found_by_id_filter"], index["missed"]) == (10, 10, 10, 0, 10, 0)
    assert await snapshot(prepared, collection_names) == before   # read-only


async def test_by_default_unclassified_restricted_chunks_are_incomplete_and_untitled_ones_a_gap(
        prepared, collection_names, append_stages, tmp_path):
    """The defaults follow the repository's local classifier, which classifies them, and
    ``chunk_titles``, which defers them; the options say when a run did otherwise."""
    ids = await run_stages(append_stages)

    result = await report(prepared, collection_names, tmp_path, ids)
    assert import_status.exit_code(result) == 1
    assert incomplete_ids(result, "classification") == set(RESTRICTED)
    assert result["stages"]["titles"]["incomplete"] == 0

    (tmp_path / "status.json").unlink()
    result = await report(prepared, collection_names, tmp_path, ids, titles_include_restricted=True, **API_CLASSIFIER)
    assert incomplete_ids(result, "titles") == set(RESTRICTED)
    assert result["stages"]["classification"]["incomplete"] == 0


@pytest.mark.parametrize("stage, expected", [
    ("metadata", {UUID(KARLIN), UUID(FREUDENTHAL), UUID(CHRONICLE)}),   # unresolved, or no library yet
    ("year", set(PUBLIC_CHUNKS)),   # the Freudenthaler Zeitung has no year
    ("visibility", set(APPENDED)),   # the chronicle's appended chunks; metadata_sync made the new ones public
    ("titles", set(PUBLIC_CHUNKS)),
    ("vectors", set(PUBLIC_CHUNKS + RESTRICTED)),
    ("classification", set(PUBLIC_CHUNKS)),
    ("summaries", {UUID(KARLIN), UUID(FREUDENTHAL), UUID(CHRONICLE)}),
])
async def test_a_stage_left_out_is_reported_incomplete(prepared, collection_names, append_stages, tmp_path, stage,
                                                       expected):
    ids = await run_stages(append_stages, leave_out=stage)

    result = await report(prepared, collection_names, tmp_path, ids, **API_CLASSIFIER)

    assert import_status.exit_code(result) == 1 and result["complete"] is False
    assert incomplete_ids(result, stage) == expected
    assert result["stages"][stage]["incomplete"] == len(expected)


async def test_a_listed_vector_that_is_not_stored_misses_the_index_check(prepared, collection_names, append_stages,
                                                                         tmp_path):
    ids = await run_stages(append_stages, leave_out="vectors")
    chunks = prepared.collections.get(collection_names.chunks_collection_name)
    await chunks.data.update(uuid=APPENDED[0], properties={"haveVector": [SECOND_VECTOR]})

    result = await report(prepared, collection_names, tmp_path, ids)

    assert result["index"]["missed_ids"] == [{"id": str(APPENDED[0]), "reason": "no_stored_vector"}]
    assert import_status.exit_code(result) == 1


async def test_an_unknown_document_or_an_existing_report_is_refused(prepared, collection_names, append_stages,
                                                                    tmp_path):
    ids = await run_stages(append_stages)
    unknown = UUID("00000000-0000-4000-8000-000000000884")

    with pytest.raises(import_status.Refused, match=str(unknown)):
        await report(prepared, collection_names, tmp_path, [*ids, unknown])
    assert not (tmp_path / "status.json").exists()

    (tmp_path / "status.json").write_text("{}")
    with pytest.raises(import_status.Refused, match="exists"):
        await report(prepared, collection_names, tmp_path, ids)


async def test_the_named_vector_must_exist(prepared, collection_names, tmp_path):
    with pytest.raises(import_status.Refused, match="no named vector missing"):
        await import_status.run(prepared, collection_names, report=tmp_path / "status.json",
                                document_ids=[UUID(CHRONICLE)], endpoint="test", vector_name="missing",
                                progress=quiet)
