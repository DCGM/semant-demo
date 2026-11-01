"""Document chunk-value summaries (#529) against the real test store: the schema command, the
full recomputation and the per-dimension chunk filters of document browsing and Analytics.

Fixture documents (tests/fixtures/corpus.json): chronicle (1851; chronicle_1..3), letters
(1902; letters_1, letters_2) and gazette (no year; gazette_1, gazette_2); every chunk is "ces".
Classifications: chronicle_1 (narration, moderate, formal), letters_1 (interaction, informal).
The seeded ``Documents`` lack the summary properties, as a store before #529 does.
"""
import json
from uuid import UUID

import pytest
from weaviate.classes.data import DataObject

from semant_demo.adapters.weaviate import chunk_summaries as store
from semant_demo.adapters.weaviate.analytics import CorpusAnalyticsRepository
from semant_demo.adapters.weaviate.criteria import UnavailableFilter
from semant_demo.features.analytics import service as analytics
from semant_demo.features.documents.criteria import ChunkFilters, DocumentFilters, document_level_conditions
from semant_demo.features.search.filters import chunk_vocabulary, generate_default_filters
from semant_demo.maintenance import chunk_summaries, chunk_summary_schema
from tests.fakes import fake_embedding

pytestmark = pytest.mark.integration

VOCABULARY = chunk_vocabulary(generate_default_filters(languages=["ces", "deu"]))
ORPHAN = UUID("5e3a0000-0000-4000-8000-0000000c5501")


def quiet(line: str) -> None:
    pass


@pytest.fixture
def update(seeded_store, collection_names, corpus):
    """Changes stored properties of a fixture chunk or document, by key."""
    async def run(key, **properties):
        if key in corpus.chunks:
            uuid, name = corpus.chunks[key]["id"], collection_names.chunks_collection_name
        else:
            uuid, name = corpus.documents[key]["id"], collection_names.document_collection_name
        await seeded_store.collections.get(name).data.update(uuid=uuid, properties=properties)
    return run


@pytest.fixture
def recompute(seeded_store, collection_names, tmp_path):
    runs = iter(range(100))

    async def run(write=True):
        report = tmp_path / f"run{next(runs)}.json"
        return await chunk_summaries.run(seeded_store, collection_names, report=report, endpoint="test", write=write,
                                         progress=quiet)
    return run


@pytest.fixture
async def summarized(seeded_store, collection_names):
    """``seeded_store`` with the summary properties declared (never recomputed)."""
    await chunk_summary_schema.update(seeded_store, collection_names, apply=True)
    return seeded_store


@pytest.fixture
def select(seeded_store, collection_names, documents, corpus):
    """The keys of the documents that browsing selects; Analytics must count as many."""
    key_of = {d["id"]: key for key, d in corpus.documents.items()}

    async def run(chunk_filters: ChunkFilters, filters: DocumentFilters = DocumentFilters()) -> set[str]:
        _, conditions = document_level_conditions(filters, chunk_filters, VOCABULARY)
        browsed = await documents.browse(conditions=conditions, limit=50)
        counted = await analytics.corpus_distributions(
            CorpusAnalyticsRepository(seeded_store, collection_names), filters, chunk_filters, VOCABULARY)
        assert browsed.total_count == counted.total_documents == len(browsed.items)
        return {key_of[str(d.id)] for d in browsed.items}
    return run


def classified(**values) -> ChunkFilters:
    return ChunkFilters(classifications=values)


async def test_the_schema_command_adds_the_properties_once_through_an_alias(seeded_store, collection_names):
    alias = "ChunkSummaryDocumentsAlias"
    await seeded_store.alias.create(alias_name=alias, target_collection=collection_names.document_collection_name)
    try:
        through_alias = collection_names.model_copy(update={"document_collection_name": alias})
        checked = await chunk_summary_schema.update(seeded_store, through_alias, apply=False)
        assert checked["documents"] == collection_names.document_collection_name
        assert set(checked["missing"]) == set(checked["expected"]) and checked["added"] == []
        assert "chunk_complexity" in checked["expected"] and "chunk_summaries_computed_at" in checked["expected"]

        applied = await chunk_summary_schema.update(seeded_store, through_alias, apply=True)
        again = await chunk_summary_schema.update(seeded_store, through_alias, apply=True)
    finally:
        await seeded_store.alias.delete(alias_name=alias)

    assert set(applied["added"]) == set(checked["expected"]) and applied["missing"] == []
    assert again["added"] == again["missing"] == []
    declared = await store.declared_properties(seeded_store, collection_names.document_collection_name)
    assert declared["chunk_style"] == store.DeclaredProperty("text[]", "field", True)
    assert declared["chunk_summaries_computed_at"].data_type == "date"


async def test_a_property_declared_differently_is_refused_before_anything_is_added(
        seeded_store, collection_names, recompute):
    from weaviate.classes.config import DataType, Property
    documents = seeded_store.collections.get(collection_names.document_collection_name)
    await documents.config.add_property(Property(name="chunk_style", data_type=DataType.TEXT_ARRAY))  # word-tokenized

    with pytest.raises(chunk_summaries.Refused, match="chunk_style"):
        await chunk_summary_schema.update(seeded_store, collection_names, apply=True)
    with pytest.raises(chunk_summaries.Refused, match="chunk_summary_schema --apply first"):
        await recompute(write=True)

    declared = await store.declared_properties(seeded_store, collection_names.document_collection_name)
    assert "chunk_complexity" not in declared


async def test_chunk_filters_need_the_summary_properties(seeded_store, select, recompute):
    with pytest.raises(UnavailableFilter, match=r"chunk values \(chunk_language\)"):
        await select(ChunkFilters(languages=["ces"]))
    with pytest.raises(chunk_summaries.Refused, match="chunk_summary_schema --apply first"):
        await recompute(write=True)


async def test_documents_never_recomputed_match_no_chunk_filter(summarized, select, recompute):
    assert await select(ChunkFilters(languages=["ces"])) == set()

    dry = await recompute(write=False)

    assert dry["counts"]["documents"] == {"examined": 3, "never_computed": 3, "changed": 0, "unchanged": 0,
                                        "without_values": 0, "written": 0, "failed": 0, "missing_documents": 0}
    assert chunk_summaries.exit_code(dry) == 1
    assert await select(ChunkFilters(languages=["ces"])) == set()  # a dry run writes nothing


async def test_recomputation_stores_the_distinct_values_of_each_document(summarized, recompute, collection_names,
                                                                        corpus, update):
    await update("chronicle_2", style=["informal"], complexity=["easy", "moderate"])
    chunks = summarized.collections.get(collection_names.chunks_collection_name)
    inserted = await chunks.data.insert_many([DataObject(
        uuid=ORPHAN, properties={"text": "Bez dokumentu", "language": "deu"}, vector={"default": fake_embedding("o")})])
    assert not inserted.errors

    result = await recompute()

    assert result["counts"]["chunks"] == {"examined": 8, "no_document": 1, "several_documents": 0}
    assert result["counts"]["documents"]["written"] == 3 and chunk_summaries.exit_code(result) == 0
    stored = await store.read_documents(summarized, collection_names.document_collection_name,
                                        [UUID(d["id"]) for d in corpus.documents.values()], chunk_summaries.DIMENSIONS)
    chronicle = stored[UUID(corpus.documents["chronicle"]["id"])]
    gazette = stored[UUID(corpus.documents["gazette"]["id"])]
    assert chronicle.values["style"] == ("formal", "informal")
    assert chronicle.values["complexity"] == ("easy", "moderate")
    assert chronicle.values["language"] == ("ces",)
    assert gazette.values["language"] == ("ces",) and gazette.values["style"] == ()
    assert chronicle.computed_at is not None and chronicle.computed_at.isoformat() == result["computed_at"]
    manifest = [json.loads(line) for line in open(result["manifest"], encoding="utf-8")]
    assert manifest == [{"id": str(ORPHAN), "kind": "chunk", "status": "no_document", "document_ids": []}]
    assert result["distinct_values"]["language"] == 1  # the orphan's "deu" is not counted for any document


async def test_a_document_matches_when_each_dimension_is_met_by_some_chunk(summarized, recompute, select, update):
    await update("chronicle_2", style=["informal"])  # chronicle_1 is narration and formal
    await recompute()

    # Different chunks of chronicle meet the two dimensions (no passage meets both).
    assert await select(classified(communicative_mode=["narration"], style=["informal"])) == {"chronicle"}
    assert await select(classified(communicative_mode=["interaction"], style=["informal"])) == {"letters"}
    assert await select(classified(communicative_mode=["narration"], complexity=["expert"])) == set()
    assert await select(ChunkFilters(languages=["ces"])) == {"chronicle", "letters", "gazette"}
    assert await select(ChunkFilters(languages=["deu"])) == set()


async def test_values_of_one_dimension_are_alternatives(summarized, recompute, select):
    await recompute()

    assert await select(classified(communicative_mode=["narration", "interaction"])) == {"chronicle", "letters"}


async def test_chunk_filters_and_document_filters_must_all_hold(summarized, recompute, select):
    await recompute()

    assert await select(classified(style=["formal", "informal"]), DocumentFilters(year_max=1900)) == {"chronicle"}
    assert await select(classified(style=["informal"]), DocumentFilters(year_max=1900)) == set()
    assert await select(ChunkFilters(languages=["ces"]), DocumentFilters(title_contains=["věstník"])) == {"gazette"}


async def test_summary_values_match_exactly(summarized, recompute, select, update):
    await update("chronicle_3", complexity=["easy"])
    await update("gazette_1", complexity=["very_easy"])
    await recompute()

    assert await select(classified(complexity=["easy"])) == {"chronicle"}
    assert await select(classified(complexity=["very_easy"])) == {"gazette"}
    assert await select(classified(complexity=["easy", "very_easy"])) == {"chronicle", "gazette"}


async def test_a_new_run_replaces_the_summaries_and_removes_values_that_no_longer_occur(
        summarized, recompute, select, update):
    await update("chronicle_2", style=["informal"])
    first = await recompute()
    assert await select(classified(style=["informal"])) == {"chronicle", "letters"}

    unchanged = await recompute(write=False)
    assert unchanged["counts"]["documents"]["unchanged"] == 3 and chunk_summaries.exit_code(unchanged) == 0

    await update("chronicle_2", style=["formal"])
    changed = await recompute(write=False)
    assert changed["counts"]["documents"]["changed"] == 1 and chunk_summaries.exit_code(changed) == 1
    assert await select(classified(style=["informal"])) == {"chronicle", "letters"}  # stale until rewritten

    second = await recompute()
    assert second["computed_at"] >= first["computed_at"]
    assert await select(classified(style=["informal"])) == {"letters"}
    assert await select(classified(style=["formal"])) == {"chronicle"}


########
# HTTP #
########

async def test_browse_and_analytics_apply_chunk_filters_over_http(summarized, recompute, update, api_client):
    await update("chronicle_2", style=["informal"])
    await recompute()

    browsed = await api_client.get("/api/documents/browse", params=[
        ("chunk_classifications", "communicative_mode:narration"), ("chunk_classifications", "style:Informal"),
        ("chunk_languages", "ces")])
    counted = await api_client.post("/api/analytics/corpus/distributions", json={
        "chunk_filters": {"languages": ["ces"], "classifications": {"communicative_mode": ["narration"],
                                                                    "style": ["Informal"]}}})

    assert browsed.status_code == 200, browsed.text
    assert [d["title"] for d in browsed.json()["items"]] == ["Kronika obce Lhota"]
    assert counted.status_code == 200, counted.text
    assert counted.json()["total_documents"] == browsed.json()["total_count"] == 1
    assert counted.json()["chunk_filters"]["classifications"]["style"] == ["informal"]


async def test_document_endpoints_reject_chunk_filters_without_the_summaries(api_client):
    browsed = await api_client.get("/api/documents/browse", params={"chunk_classifications": "complexity:easy"})
    counted = await api_client.post("/api/analytics/corpus/library-years",
                                    json={"chunk_filters": {"languages": ["ces"]}})

    for response in (browsed, counted):
        assert response.status_code == 422
        assert "has no chunk-value summaries" in response.json()["detail"]
