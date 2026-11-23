"""The read-only import status report over appended data (#884, #560 D).

The appended data and the stages are those of ``test_append_pipeline.py``, except that the
mirror has a row for the *Freudenthaler Zeitung* with ``public=false``: a resolved document that
is not public, whose chunks are the expected gaps (no title, no classification by the API model).
"""
import json
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import create_engine, insert

from semant_demo.adapters.sql.kramerius_metadata import META_RECORDS
from semant_demo.maintenance import chunk_summary_schema, import_status, metadata_sync
from tests.fakes import SECOND_VECTOR
from tests.integration.test_append_pipeline import (  # noqa: F401  (``stages`` is a fixture)
    FREUDENTHAL, INPUT, KARLIN, quiet, row, snapshot, stages)

pytestmark = pytest.mark.integration

LINES = [json.loads(line) for line in INPUT.read_text(encoding="utf-8").splitlines()]
RESTRICTED = [UUID(c["id"]) for c in LINES if c["document"] == FREUDENTHAL]
PUBLIC_CHUNKS = [UUID(c["id"]) for c in LINES if c["document"] != FREUDENTHAL]
APPENDED = [UUID(c["id"]) for c in LINES if c["document"] not in (KARLIN, FREUDENTHAL)]
CHRONICLE = UUID("5e3a0000-0000-4000-8000-00000000d001")   # seeded with 3 chunks; the input appends 2


@pytest.fixture
def mirror():
    """The Kramerius mirror of the new documents and the chronicle; the Freudenthaler Zeitung
    resolves as not public."""
    engine = create_engine("sqlite://")
    META_RECORDS.metadata.create_all(engine)
    with engine.connect() as connection:
        connection.execute(insert(META_RECORDS), [
            row(KARLIN, "mzk", title="Karlínské listy", date="1904"),
            row(FREUDENTHAL, "mzk", title="Freudenthaler Zeitung", public=False),
            row(str(CHRONICLE), "nkp", title="Kronika obce Lhota"),
        ])
        yield connection
    engine.dispose()


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
        prepared, collection_names, stages, tmp_path):
    ids = await run_stages(stages)
    before = await snapshot(prepared, collection_names)

    result = await report(prepared, collection_names, tmp_path, ids)

    assert import_status.exit_code(result) == 0 and result["complete"] is True
    assert json.loads((tmp_path / "status.json").read_text(encoding="utf-8")) == result
    assert (result["documents_listed"], result["chunks_examined"]) == (3, 3 + 2 + 5)
    stages_ = result["stages"]
    assert {name: stage["incomplete"] for name, stage in stages_.items()} == dict.fromkeys(import_status.STAGES, 0)
    assert {name: stage["complete"] for name, stage in stages_.items() if stage["unit"] == "documents"} == {
        "chunks": 3, "metadata": 3, "summaries": 3}
    assert stages_["titles"]["expected_gap_reasons"] == {"deferred_restricted_document": len(RESTRICTED)}
    assert stages_["classification"]["expected_gap_reasons"] == {   # the chronicle's seeded chunks: no status
        "deferred_restricted_document": len(RESTRICTED), "no_provenance": 3}
    assert stages_["visibility"]["complete"] == result["chunks_examined"]
    index = result["index"]
    assert (index["candidates"], index["sampled"], index["self_in_top_k"], index["found_by_id_filter"],
            index["missed"]) == (10, 10, 10, 10, 0)
    assert await snapshot(prepared, collection_names) == before   # read-only


@pytest.mark.parametrize("stage, expected", [
    ("metadata", {UUID(KARLIN), UUID(FREUDENTHAL), CHRONICLE}),   # unresolved, or no library yet
    ("year", set(PUBLIC_CHUNKS)),   # the Freudenthaler Zeitung has no year
    ("visibility", set(APPENDED)),   # the chronicle's appended chunks; metadata_sync made the new ones public
    ("titles", set(PUBLIC_CHUNKS)),
    ("vectors", set(PUBLIC_CHUNKS + RESTRICTED)),
    ("classification", set(PUBLIC_CHUNKS)),
    ("summaries", {UUID(KARLIN), UUID(FREUDENTHAL), CHRONICLE}),
])
async def test_a_stage_left_out_is_reported_incomplete(prepared, collection_names, stages, tmp_path, stage,
                                                       expected):
    ids = await run_stages(stages, leave_out=stage)

    result = await report(prepared, collection_names, tmp_path, ids)

    assert import_status.exit_code(result) == 1 and result["complete"] is False
    assert incomplete_ids(result, stage) == expected
    assert result["stages"][stage]["incomplete"] == len(expected)


async def test_a_listed_vector_that_is_not_stored_misses_the_index_check(prepared, collection_names, stages, tmp_path):
    ids = await run_stages(stages, leave_out="vectors")
    chunks = prepared.collections.get(collection_names.chunks_collection_name)
    await chunks.data.update(uuid=APPENDED[0], properties={"haveVector": [SECOND_VECTOR]})

    result = await report(prepared, collection_names, tmp_path, ids)

    assert result["index"]["missed_ids"] == [{"id": str(APPENDED[0]), "reason": "no_stored_vector"}]
    assert import_status.exit_code(result) == 1


async def test_an_unknown_document_or_an_existing_report_is_refused(prepared, collection_names, stages, tmp_path):
    ids = await run_stages(stages)
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
                                document_ids=[CHRONICLE], endpoint="test", vector_name="missing", progress=quiet)
