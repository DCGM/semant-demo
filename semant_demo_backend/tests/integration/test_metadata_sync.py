"""Kramerius metadata synchronization against the real test store (#257).

The mirror is an in-memory SQLite ``meta_records`` table. The fixture store, like the local
snapshot, declares no ``library`` property: it is added (``add_text_property``) and the
source library comes from a library map. Applied metadata is read back through the document
repository and the search adapter's year filter.
"""
import json
from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy import create_engine, insert

from semant_demo.adapters.sql.kramerius_metadata import META_RECORDS
from semant_demo.adapters.weaviate.document_metadata import add_text_property, document_property_types
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.adapters.weaviate.search import ChunkSearchRepository
from semant_demo.features.search.schemas import ChunkQuery, FieldCondition, Op, SearchType
from semant_demo.maintenance.metadata_sync import apply_exit_code, apply_report, build_report

pytestmark = pytest.mark.integration


@pytest.fixture
def source():
    engine = create_engine("sqlite://")
    META_RECORDS.metadata.create_all(engine)
    with engine.connect() as connection:
        yield connection
    engine.dispose()


def row(document_id: str, library: str, **values) -> dict:
    return {"id": UUID(document_id), "library": library, "public": False, "in_library": True,
            "record_type": None, "title": None, "date": None, "start_date": None, "end_date": None,
            "metadata_json": None, **values}


async def test_report_apply_and_read_back(seeded_store, collection_names, corpus, source):
    gazette, chronicle, letters = (corpus.documents[k]["id"] for k in ("gazette", "chronicle", "letters"))
    source.execute(insert(META_RECORDS), [
        row(gazette, "mzk", date="12.5.1899", public=True,
            metadata_json={"Publisher": [["Pražský tisk"], ["Parent publisher"]], "SeriesNumber": [["IV"]]}),
        # Another library's fuller record of the same document is never used.
        row(gazette, "nkp", date="1.1.1950", public=True, metadata_json={"Author": [["Someone Else"]]}),
        row(chronicle, "nkp", title="Never used"),
    ])
    library_map = {UUID(gazette): "mzk", UUID(letters): "mzk"}
    assert "library" not in await document_property_types(seeded_store, collection_names)
    await add_text_property(seeded_store, collection_names, "library")

    report = json.loads(json.dumps(await build_report(
        seeded_store, collection_names, source, endpoint="test", source_name="sqlite", library_map=library_map)))

    by_id = {e["id"]: e for e in report["documents"]}
    assert by_id[gazette]["changes"] == {
        "library": {"old": None, "new": "mzk"},
        "dateIssued": {"old": None, "new": "1899-05-12T00:00:00+00:00"},
        "yearIssued": {"old": None, "new": 1899},
        "publisher": {"old": None, "new": "Pražský tisk"},
        "seriesNumber": {"old": None, "new": "IV"},
    }
    assert "public" not in by_id[gazette]["changes"]  # stored public absent: still an access change
    assert by_id[gazette]["held"]["public"]["new"] is True
    assert by_id[chronicle]["kind"] == "no_library"
    assert by_id[letters]["kind"] == "no_source_row"
    assert report["counts"]["unresolved"] == {"no_library": 1, "no_source_row": 1}

    with pytest.raises(LookupError):  # unresolved documents need explicit acceptance
        await apply_report(seeded_store, collection_names, report)
    result = await apply_report(seeded_store, collection_names, report, accept_incomplete=True)
    assert (result["eligible"], result["applied"], result["verified"], result["unresolved"]) == (1, 1, 1, 2)
    assert apply_exit_code(result) == 0

    document = await DocumentRepository(seeded_store, collection_names).read(UUID(gazette))
    assert document.library == "mzk"
    documents = seeded_store.collections.get(collection_names.document_collection_name)
    library = next(p for p in (await documents.config.get()).properties if p.name == "library")
    assert library.tokenization.value == "field"
    assert document.yearIssued == 1899
    assert document.dateIssued == datetime(1899, 5, 12, tzinfo=timezone.utc)
    assert document.publisher == "Pražský tisk" and document.seriesNumber == "IV"
    assert document.author is None and document.public is None
    assert document.title == corpus.documents["gazette"]["properties"]["title"]

    hits = await ChunkSearchRepository(seeded_store, collection_names).search(ChunkQuery(
        text="Slavia trh", mode=SearchType.text, limit=10,
        conditions=(FieldCondition("yearIssued", Op.greater_or_equal, 1890),
                    FieldCondition("yearIssued", Op.less_or_equal, 1900))))
    assert {str(h.document) for h in hits} == {gazette}

    again = await apply_report(seeded_store, collection_names, report, accept_incomplete=True)
    assert again["already_applied"] == 1 and apply_exit_code(again) == 0
