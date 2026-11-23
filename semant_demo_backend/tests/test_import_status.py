"""The import status report's rules without a store (#884); the store tests are in
``tests/integration/test_import_status.py``."""
from uuid import UUID, uuid4

import pytest

from semant_demo.adapters.weaviate.import_status import ImportedChunk, ImportedDocument
from semant_demo.maintenance import import_status

DOCUMENT = UUID("000b03e0-53d7-11ee-9c28-0050568d319f")
OTHER = UUID("00246353-3566-4e72-80a6-4019d8f94d59")


def test_the_document_list_is_read_as_chunk_ingest_writes_it(tmp_path):
    path = tmp_path / "ids.txt"
    path.write_text(f"# the import\n{DOCUMENT}\n\n{OTHER}  # second\n{DOCUMENT}\n")
    assert import_status.read_document_ids(path) == [DOCUMENT, OTHER]
    for text, message in (("# nothing\n", "lists no documents"), ("not-a-uuid\n", "ids.txt:1 is not a document UUID")):
        path.write_text(text)
        with pytest.raises(import_status.Refused, match=message):
            import_status.read_document_ids(path)
    with pytest.raises(import_status.Refused, match="Cannot read"):
        import_status.read_document_ids(tmp_path / "missing.txt")


def document(public, year=1904) -> ImportedDocument:
    return ImportedDocument(DOCUMENT, {"public": public, "library": "mzk", "title": "T", "yearIssued": year}, {}, None)


def chunk(**properties) -> ImportedChunk:
    stored = {"yearIssued": 1904, "documentPublic": True, "title": "A title", "haveVector": ["v"],
              "classification_provenance": "model-v1"}
    return ImportedChunk(uuid4(), {**stored, **properties})


def outcome(chunk_: ImportedChunk, document_: ImportedDocument) -> dict[str, tuple]:
    """Per chunk stage: (complete, incomplete reasons, expected gap reasons)."""
    stages = {name: import_status.Stage("chunks") for name in import_status.CHUNK_STAGES}
    import_status.check_chunk(chunk_, document_, "v", stages)
    return {name: (s.complete, dict(s.incomplete), dict(s.expected)) for name, s in stages.items()}


def test_a_complete_chunk_of_a_public_document_is_complete_in_every_stage():
    assert outcome(chunk(), document(True)) == dict.fromkeys(import_status.CHUNK_STAGES, (1, {}, {}))


@pytest.mark.parametrize("stored, year, reason", [
    (None, 1904, "absent"), (1903, 1904, "differs"), (1904, None, "extra"), (1904, "1904?", "invalid_document_year")])
def test_the_chunk_year_must_equal_the_document_year(stored, year, reason):
    assert outcome(chunk(yearIssued=stored), document(True, year))["year"] == (0, {reason: 1}, {})


def test_a_document_without_a_year_leaves_its_chunks_without_one():
    assert outcome(chunk(yearIssued=None), document(True, None))["year"] == (1, {}, {})


@pytest.mark.parametrize("public", [False, None])
def test_the_chunks_of_a_document_that_is_not_public_are_hidden_and_their_gaps_expected(public):
    result = outcome(chunk(documentPublic=False, title=None, classification_provenance="UNPROCESSED"),
                     document(public))
    assert result["visibility"] == (1, {}, {})
    assert result["titles"] == result["classification"] == (0, {}, {"deferred_restricted_document": 1})
    assert outcome(chunk(), document(public))["visibility"] == (0, {"differs": 1}, {})


def test_a_public_documents_chunk_without_title_vector_or_classification_is_incomplete():
    result = outcome(chunk(title=" ", haveVector=["other"], classification_provenance="UNPROCESSED",
                           documentPublic=None), document(True))
    assert result["titles"] == (0, {"untitled": 1}, {})
    assert result["vectors"] == (0, {"not_listed": 1}, {})
    assert result["classification"] == (0, {"unprocessed": 1}, {})
    assert result["visibility"] == (0, {"absent": 1}, {})


def test_a_chunk_stored_before_the_classification_status_is_not_counted_as_incomplete():
    assert outcome(chunk(classification_provenance=None), document(True))["classification"] == (
        0, {}, {"no_provenance": 1})


def test_a_document_is_resolved_with_a_public_flag_and_a_library():
    stage, without = import_status.Stage("documents"), import_status.Counter()
    import_status.check_metadata(document(True), stage, without)
    import_status.check_metadata(ImportedDocument(OTHER, {"public": None, "library": "mzk", "title": None,
                                                          "yearIssued": None}, {}, None), stage, without)
    import_status.check_metadata(ImportedDocument(OTHER, {"public": False, "library": "", "title": "T",
                                                          "yearIssued": 1}, {}, None), stage, without)
    assert (stage.complete, dict(stage.incomplete), dict(without)) == (
        1, {"unresolved": 1, "no_library": 1}, {"title": 1, "yearIssued": 1})


def test_incomplete_ids_are_bounded_but_counted():
    stage = import_status.Stage("chunks")
    for _ in range(import_status.ID_LIMIT + 5):
        stage.missing(uuid4(), "untitled")
    summary = stage.summary()
    assert (summary["incomplete"], len(summary["incomplete_ids"]), summary["incomplete_ids_truncated"]) == (
        import_status.ID_LIMIT + 5, import_status.ID_LIMIT, True)
