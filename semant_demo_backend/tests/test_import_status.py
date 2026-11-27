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


def outcome(chunk_: ImportedChunk, document_: ImportedDocument, **options) -> dict[str, tuple]:
    """Per chunk stage: (complete, incomplete reasons, expected gap reasons)."""
    stages = {name: import_status.Stage("chunks") for name in import_status.CHUNK_STAGES}
    import_status.check_chunk(chunk_, document_, "v", stages, **options)
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
def test_the_chunks_of_a_document_that_is_not_public_follow_the_stages_defaults(public):
    """``chunk_titles`` defers them; the repository's local classifier classifies them."""
    restricted = chunk(documentPublic=False, title=None, classification_provenance="UNPROCESSED")
    result = outcome(restricted, document(public))
    assert result["visibility"] == (1, {}, {})
    assert result["titles"] == (0, {}, {"deferred_restricted_document": 1})
    assert result["classification"] == (0, {"unprocessed": 1}, {})
    assert outcome(chunk(), document(public))["visibility"] == (0, {"differs": 1}, {})

    result = outcome(restricted, document(public), titles_include_restricted=True,
                     classifier_includes_restricted=False)
    assert result["titles"] == (0, {"untitled": 1}, {})
    assert result["classification"] == (0, {}, {"skipped_restricted_document": 1})


def test_a_public_documents_chunk_without_title_vector_or_classification_is_incomplete():
    result = outcome(chunk(title=" ", haveVector=["other"], classification_provenance="UNPROCESSED",
                           documentPublic=None), document(True))
    assert result["titles"] == (0, {"untitled": 1}, {})
    assert result["vectors"] == (0, {"not_listed": 1}, {})
    assert result["classification"] == (0, {"unprocessed": 1}, {})
    assert result["visibility"] == (0, {"absent": 1}, {})


def test_a_chunk_stored_before_the_classification_status_is_not_counted_as_incomplete():
    assert outcome(chunk(classification_provenance=None), document(True))["classification"] == (
        0, {}, {"stored_before_status": 1})


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


@pytest.mark.parametrize("sample, k", [(-1, 10), (100, 0)])
async def test_an_invalid_index_check_size_is_refused_before_reading_the_store(tmp_path, sample, k):
    with pytest.raises(import_status.Refused, match="--coverage-sample must be 0 or more"):
        await import_status.run(None, None, report=tmp_path / "status.json", document_ids=[DOCUMENT],
                                endpoint="test", coverage_sample=sample, coverage_k=k)
    assert not (tmp_path / "status.json").exists()


class FakeIndex:
    """The index reads of ``check_index``: ``top`` maps a chunk to its rank by its own vector
    (None: not found at any K); ``unfiltered`` lists the chunks the id filter does not find."""

    def __init__(self, vectors: dict[UUID, list[float] | None], top: dict[UUID, int | None],
                 unfiltered: set[UUID] = frozenset()):
        self.vectors, self.top, self.unfiltered = vectors, top, unfiltered
        self.asked_k: list[int] = []

    async def read_vectors(self, client, collection, ids, vector):
        return {i: self.vectors[i] for i in ids}

    async def self_in_top_k(self, client, collection, chunk_id, vector, vector_name, k):
        self.asked_k.append(k)
        rank = self.top[chunk_id]
        return rank is not None and rank <= k

    async def found_by_id_filter(self, client, collection, chunk_id, vector, vector_name):
        return chunk_id not in self.unfiltered


async def test_a_chunk_missing_from_the_top_k_is_queried_again_with_a_larger_k(monkeypatch):
    first, duplicate, lost, unstored, unfiltered = (uuid4() for _ in range(5))
    fake = FakeIndex({first: [1.0], duplicate: [1.0], lost: [1.0], unstored: None, unfiltered: [1.0]},
                     {first: 1, duplicate: 12, lost: None, unstored: None, unfiltered: 1}, {unfiltered})
    for name in ("read_vectors", "self_in_top_k", "found_by_id_filter"):
        monkeypatch.setattr(import_status.store, name, getattr(fake, name))

    index = await import_status.check_index(None, "Chunks", [first, duplicate, lost, unstored, unfiltered], "v",
                                            sample=10, k=10, seed=1)

    assert (index["sampled"], index["self_in_top_k"], index["retried"], index["self_in_retry_k"],
            index["found_by_id_filter"], index["missed"], index["retry_k"]) == (5, 2, 2, 1, 3, 3, 100)
    assert {e["id"]: e["reason"] for e in index["missed_ids"]} == {
        str(lost): "not_in_top_k", str(unstored): "no_stored_vector", str(unfiltered): "not_found_by_id_filter"}
    assert set(index["retried_ids"]) == {str(duplicate), str(lost)}
    assert sorted(set(fake.asked_k)) == [10, 100]
