"""Appending new data to a populated store through every stage together (#798, #560 A).

A smoke test of the hand-offs between the stages; each stage's own tests cover its details.
The seeded fixture corpus is the existing corpus. ``fixtures/append_pipeline/chunks.jsonl``
holds a new document (*Karlínské listy*, one chunk without the optional ``end_paragraph``), a new
document missing from the Kramerius mirror (*Freudenthaler Zeitung*) and two chunks appended to
the seeded chronicle. The stages run in process in the order of ``docs/DATA_MAINTENANCE.md``
(*Chunk import*, *Afterwards*) and hand over through the import's document list, as an operator
does; ``metadata_sync`` reads an in-memory SQLite mirror with the flags of the production sync
(#259). The models are fakes. The test checks that the new public chunks reach search, that the
unresolved document stays out of anonymous reads and of the API model (#785), that the existing
corpus keeps its data, and that a replay of every stage writes nothing.
"""
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

import httpx
import pytest
import yaml
from httpx import ASGITransport
from openai import AsyncOpenAI
from sqlalchemy import create_engine, insert
from weaviate.classes.query import QueryReference

from semant_demo.adapters.llm.gateway import LlmGateway, ProviderSettings
from semant_demo.adapters.llm.models import ModelCatalog
from semant_demo.adapters.sql.kramerius_metadata import META_RECORDS
from semant_demo.bootstrap import load_search_vectors
from semant_demo.config import Config
from semant_demo.features.documents.criteria import SUMMARIES_COMPUTED_AT
from semant_demo.maintenance import (
    chunk_document_public, chunk_ingest, chunk_summaries, chunk_summary_schema, chunk_titles, chunk_year,
    metadata_sync)
from semant_demo.maintenance.chunk_titles import UsageTotals
from tests.fake_providers import create_fake_provider_app, fake_title
from tests.fakes import SECOND_VECTOR

sys.path.insert(0, str(Path(__file__).parents[3] / "data_tools" / "embedder"))
sys.path.insert(0, str(Path(__file__).parents[3] / "data_tools" / "meta_data_enrichment"))
from semantembedder.pipeline import EmbeddingPipeline  # noqa: E402
from semantmetaenricher.db import PROVENANCE, UNPROCESSED  # noqa: E402
from semantmetaenricher.pipeline import EnrichmentPipeline  # noqa: E402

pytestmark = pytest.mark.integration

INPUT = Path(__file__).parents[1] / "fixtures" / "append_pipeline" / "chunks.jsonl"
KARLIN, FREUDENTHAL = "000b03e0-53d7-11ee-9c28-0050568d319f", "00246353-3566-4e72-80a6-4019d8f94d59"
CATALOG = {"tiers": {"tiny": {"provider": "ollama", "model": "fake-titles", "price_basis": "local_rate",
                              "input_price": 0, "output_price": 0}},
           "features": {"chunk_titles": {"default": "tiny", "limits": {"max_output_tokens": 64,
                                                                     "max_input_tokens": 4096}}}}
LABELS = {"communicative_mode": ["description"], "style": ["formal"]}
PROVENANCE_ID = "fake-classifier-v1"
NO_SUMMARY = {"search_title_generate": False, "search_summary_generate": False,
              "search_results_summary_generate": False}


def quiet(_line: str) -> None:
    pass


def row(document_id: str, library: str, **values) -> dict:
    return {"id": UUID(document_id), "library": library, "parent_id": None, "parent_library": None,
            "public": True, "in_library": True, "record_type": None, "title": None, "date": None,
            "start_date": None, "end_date": None, "metadata_json": None, **values}


class RemoteModel:
    """A fake API model (``remote``: its provider would receive the text) answering ``LABELS``.
    ``asked`` records the classified texts."""
    remote = True

    def __init__(self):
        self.asked: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def labels(self, task):
        return LABELS.get(task)

    def fingerprint(self):
        return {"cls": "RemoteModel"}

    def generate_batch(self, records, tasks):
        self.asked.extend(r["text"] for r in records)
        return [{t: list(LABELS[t]) for t in tasks} for r in records]


@pytest.fixture
def mirror():
    """The Kramerius mirror: one row of the new document and of the chronicle; none of the
    Freudenthaler Zeitung."""
    engine = create_engine("sqlite://")
    META_RECORDS.metadata.create_all(engine)
    with engine.connect() as connection:
        connection.execute(insert(META_RECORDS), [
            row(KARLIN, "mzk", title="Karlínské listy", date="1904"),
            row("5e3a0000-0000-4000-8000-00000000d001", "nkp", title="Kronika obce Lhota"),  # the chronicle
        ])
        yield connection
    engine.dispose()


@pytest.fixture
def stages(seeded_store, collection_names, corpus, store_endpoint, tmp_path, mirror):
    """Each stage as the operator runs it, on the test store with the fake models."""
    names = collection_names
    runs = iter(range(1000))
    titles_provider = ASGITransport(app=create_fake_provider_app(corpus))
    classifier_model = RemoteModel()
    models_config = tmp_path / "models.yaml"
    models_config.write_text(yaml.safe_dump(CATALOG))
    connection = {"weaviate_host": store_endpoint.host, "weaviate_port": store_endpoint.rest_port,
                  "weaviate_grpc_port": store_endpoint.grpc_port, "weaviate_api_key": None,
                  "weaviate_headers": None}

    def fresh(name: str) -> Path:
        return tmp_path / f"{name}-{next(runs)}.json"

    class Stages:
        classifier = classifier_model

        @staticmethod
        async def ingest():
            """The run's summary, exit code and document list (``CHECKPOINT.documents.txt``)."""
            checkpoint = fresh("ingest")
            result = await chunk_ingest.run(seeded_store, names, [INPUT], checkpoint=checkpoint, endpoint="test",
                                            write_=True, backup={"offline_backup": "test copy"}, progress=quiet)
            return result, chunk_ingest.exit_code(result), Path(f"{checkpoint}.documents.txt")

        @staticmethod
        async def metadata(document_list: Path):
            report = json.loads(json.dumps(await metadata_sync.build_report(
                seeded_store, names, mirror, endpoint="test", source_name="sqlite",
                document_ids=metadata_sync.read_document_ids(document_list),
                infer_from_pages=True, infer_from_mirror=True, distrusted=frozenset({"mzk"}),
                priority=("nkp", "mzk"), prefer_metadata=True)))
            applied = await metadata_sync.apply_report(seeded_store, names, report, accept_incomplete=True)
            return report, applied, metadata_sync.apply_exit_code(applied)

        @staticmethod
        async def year():
            result = await chunk_year.run(seeded_store, names, checkpoint=fresh("year"), endpoint="test", write=True,
                                          progress=quiet)
            return result, chunk_year.exit_code(result)

        @staticmethod
        async def visibility(document_list: Path):
            result = await chunk_document_public.run_documents(
                seeded_store, names, metadata_sync.read_document_ids(document_list), checkpoint=fresh("visibility"),
                endpoint="test", write=True, progress=quiet)
            return result, chunk_document_public.documents_exit_code(result)

        @staticmethod
        async def titles_run():
            usage = UsageTotals()
            llm = LlmGateway(ModelCatalog.load(models_config),
                             ProviderSettings(ollama_base_url="http://fake/ollama", max_retries=0), usage,
                             http_transport=titles_provider)
            return await chunk_titles.run(seeded_store, names, llm, endpoint="test", write=True,
                                          models_config=models_config, usage=usage, progress=quiet)

        @staticmethod
        async def embed():
            path = tmp_path / "embedder.yaml"
            path.write_text(yaml.safe_dump({
                **connection, "collection": names.chunks_collection_name, "vector_name": SECOND_VECTOR,
                "create_vector": False, "vector_index_type": "hnsw", "distance_metric": "cosine",
                "return_properties": None, "max_records": None, "scan_batch_size": 5, "embed_batch_size": 4,
                "max_concurrent_requests": 2, "max_concurrent_writes": 4, "max_retries": 1, "retry_delay": 0.0,
                "embedder": {"cls": "VLLMEmbedder", "config": {
                    "base_url": "http://fake/openai/v1", "api_key": "test-key", "model_name": "fake-small",
                    "input_template": "{{ text }}", "dimensions": None, "truncate_prompt_tokens": None,
                    "extra_body": None, "timeout": 10.0, "max_retries": 0}}}))
            pipeline = EmbeddingPipeline.create(str(path))
            pipeline.embedder._client = AsyncOpenAI(
                api_key="test-key", base_url="http://fake/openai/v1", max_retries=0,
                http_client=httpx.AsyncClient(transport=ASGITransport(app=create_fake_provider_app(corpus))))
            return await pipeline.run_async()

        @staticmethod
        async def classify():
            """The classifier with its defaults for an API model (``include_restricted_documents`` unset)."""
            path = tmp_path / "classifier.yaml"
            path.write_text(yaml.safe_dump({
                **connection, "collection": names.chunks_collection_name, "provenance": PROVENANCE_ID,
                "field_tasks": {task: task for task in LABELS}, "filters": [], "batch_size": 4,
                "max_records": None, "max_consecutive_failures": 5, "max_failures": 100, "max_retries": 0,
                "retry_delay": 0.0,
                "model": {"cls": "LocalHFClassifierModel", "config": {
                    "model_path": "unused/", "device": "cpu", "input_prompt": "{{ text }}", "threshold": 0.5}}}))
            pipeline = EnrichmentPipeline.create(str(path))
            pipeline.model = classifier_model
            return await asyncio.to_thread(pipeline.run)   # the tool's synchronous client

        @staticmethod
        async def summaries():
            result = await chunk_summaries.run(seeded_store, names, report=fresh("summaries"), endpoint="test",
                                               write=True, progress=quiet)
            return result, chunk_summaries.exit_code(result)

    return Stages


async def snapshot(client, names) -> dict:
    """Every chunk and document: properties, references and vectors (the time of the summaries
    left out: a recomputation stamps it)."""
    objects = {}
    for name, refs in ((names.chunks_collection_name, ["document", names.user_collection_link_name]),
                       (names.document_collection_name, [])):
        async for o in client.collections.get(name).iterator(
                include_vector=True, return_references=[QueryReference(link_on=r) for r in refs] or None):
            properties = {k: v for k, v in o.properties.items() if k != SUMMARIES_COMPUTED_AT}
            references = {r: sorted(str(x.uuid) for x in o.references[r].objects)
                          for r in refs if o.references and r in o.references}
            objects[str(o.uuid)] = (properties, references, o.vector)
    return objects


async def annotations(client, names) -> dict:
    """Every annotation object, per tenant."""
    collection = client.collections.get(names.annotation_collection_name)
    stored = {}
    for tenant in await collection.tenants.get():
        async for o in collection.with_tenant(tenant).iterator():
            stored[(tenant, str(o.uuid))] = o.properties
    return stored


async def test_appended_data_runs_through_every_stage_and_a_replay_writes_nothing(
        seeded_store, collection_names, corpus, stages, tmp_path, api_app, api_client):
    names = collection_names
    lines = [json.loads(line) for line in INPUT.read_text(encoding="utf-8").splitlines()]
    of = {doc: [c for c in lines if c["document"] == doc] for doc in dict.fromkeys(c["document"] for c in lines)}
    chronicle = corpus.documents["chronicle"]["id"]
    shown = [c["id"] for c in lines if c["document"] != FREUDENTHAL]
    hidden = [c["id"] for c in of[FREUDENTHAL]]
    await chunk_summary_schema.update(seeded_store, names, apply=True)  # declared as on production (#561)
    existing, existing_annotations = await snapshot(seeded_store, names), await annotations(seeded_store, names)

    # Import: two new documents and the chronicle's two appended chunks, none of them public yet.
    imported, code, document_list = await stages.ingest()
    assert code == 0 and {k: imported["counts"][k] for k in ("new", "append", "chunks_inserted")} == {
        "new": 2, "append": 1, "chunks_inserted": len(lines)}
    assert set(metadata_sync.read_document_ids(document_list)) == {UUID(d) for d in of}

    # An API model run straight after the import selects none of them: they are not public yet.
    assert (await stages.classify()).selected == 0 and stages.classifier.asked == []

    report, applied, code = await stages.metadata(document_list)
    assert report["counts"]["unresolved"] == {"no_library": 1} and (applied["applied"], code) == (2, 0)
    years, code = await stages.year()
    assert code == 0
    visible, code = await stages.visibility(document_list)
    assert code == 0 and visible["counts"]["written"] == len(of[chronicle])   # the appended chunks
    titled = await stages.titles_run()
    assert titled["counts"]["deferred_restricted_document"] == len(hidden)
    embedded = await stages.embed()
    assert embedded.embedded == len(lines)
    classified = await stages.classify()
    assert (classified.selected, classified.classified) == (len(shown), len(shown))
    summarized, code = await stages.summaries()
    assert code == 0

    # What each stage hands over: the new public chunks are complete, the unresolved document's
    # chunks have a vector but stay hidden, untitled and unclassified.
    after = await snapshot(seeded_store, names)
    for chunk in lines:
        properties = after[chunk["id"]][0]
        public = chunk["document"] != FREUDENTHAL
        assert properties["documentPublic"] is public, chunk["id"]
        assert properties["haveVector"] == [SECOND_VECTOR], chunk["id"]
        assert (properties["title"] is not None) is public, chunk["id"]
        assert properties[PROVENANCE] == (PROVENANCE_ID if public else UNPROCESSED), chunk["id"]
        assert (properties.get("yearIssued") is not None) is public, chunk["id"]
    assert (after[KARLIN][0]["library"], after[KARLIN][0]["public"]) == ("mzk", True)
    assert not {c["text"] for c in of[FREUDENTHAL]} & set(stages.classifier.asked)

    # The existing corpus: unchanged but for what the stages define.
    for object_id, (properties, references, vectors) in existing.items():
        expected = dict(properties)
        if object_id == corpus.chunks["letters_2"]["id"]:
            expected["title"] = fake_title(corpus.chunks["letters_2"]["text"])   # every untitled chunk
        if object_id in corpus_document_ids(corpus):
            expected = {k: v for k, v in expected.items() if not k.startswith("chunk_")}
            stored = {k: v for k, v in after[object_id][0].items() if not k.startswith("chunk_")}
            if object_id == chronicle:
                expected["library"] = "nkp"
            assert (stored, after[object_id][1], after[object_id][2]) == (expected, references, vectors), object_id
            continue
        assert after[object_id] == (expected, references, vectors), object_id
    assert await annotations(seeded_store, names) == existing_annotations

    await users_see_the_new_documents(api_app, api_client, corpus, tmp_path, of, chronicle)

    # Replay: every stage again on the same input writes nothing.
    before = await snapshot(seeded_store, names)
    imported, code, document_list = await stages.ingest()
    assert (imported["counts"]["chunks_inserted"], code) == (0, 0)
    report, applied, code = await stages.metadata(document_list)
    assert (applied["applied"], code) == (0, 1)   # exit 1: nothing eligible (documented)
    await stages.year()
    await stages.visibility(document_list)
    await stages.titles_run()
    assert (await stages.embed()).selected == 0
    assert (await stages.classify()).selected == 0
    await stages.summaries()
    assert await snapshot(seeded_store, names) == before


def corpus_document_ids(corpus) -> set[str]:
    return {d["id"] for d in corpus.documents.values()}


async def users_see_the_new_documents(api_app, api_client, corpus, tmp_path, of, chronicle):
    """Anonymous search finds the new public chunks (one stored without ``end_paragraph``) by the
    vector the embedder filled; nothing of the unresolved document is readable (#279)."""
    path = tmp_path / "search_vectors.yaml"   # the vector the embedder filled, as SEARCH_VECTORS_CONFIG lists it
    path.write_text(yaml.safe_dump({"default": "small", "vectors": [
        {"id": "small", "name": "Small", "target_vector": SECOND_VECTOR,
         "embedding": {"provider": "openai", "base_url": "http://fake/openai/v1", "model": "fake-small"}}]}))
    api_app.state.resources.search_vectors = load_search_vectors(
        Config(environ={"SEARCH_VECTORS_CONFIG": str(path)}), ASGITransport(app=create_fake_provider_app(corpus)))
    hidden = {c["id"] for c in of[FREUDENTHAL]}

    async def search(text: str) -> list[str]:
        response = await api_client.post("/api/search", json={"query": text, "type": "vector", "limit": 50,
                                                              "vector": "small", **NO_SUMMARY})
        assert response.status_code == 200, response.text
        return [r["id"] for r in response.json()["results"]]

    for chunk in (of[KARLIN][1], of[chronicle][1]):
        assert (await search(chunk["text"]))[0] == chunk["id"]
    assert not hidden & set(await search(of[FREUDENTHAL][0]["text"]))
    browsed = await api_client.get("/api/documents/browse", params={"limit": 200})
    assert {d["id"] for d in browsed.json()["items"]} == {*corpus_document_ids(corpus), KARLIN}
    assert (await api_client.get(f"/api/document/{FREUDENTHAL}")).status_code == 404
