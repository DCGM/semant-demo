"""Appending new data to a populated store through every stage together (#798, #560 A).

The seeded fixture corpus is the existing corpus: public documents whose chunks have vectors,
titles (but letters_2), some classifications and no ``classification_provenance``, like
production. ``fixtures/append_pipeline/chunks.jsonl`` holds four new documents and two chunks
appended to the chronicle. The stages run in process in the order of ``docs/DATA_MAINTENANCE.md``
(*Chunk import*, *Afterwards*) and hand over through the import's document list, as an operator
does. The Kramerius mirror is an in-memory SQLite ``meta_records`` table, read with the library
flags of the production sync (#259):

- the Reichenberg *Mittheilungen* (kvkli, German): rows in kvkli and nkp, its start pages in
  kvkli only, so the pages decide (``page_ancestry``);
- *Karlínské listy* (mzk, Czech): rows in nkp and mzk, only mzk with MODS metadata
  (``mirror_metadata``, before the priority ``nkp,mzk``);
- the Prague *Intelligenzblatt* (nacr, German) and the chronicle: one row each (``mirror_unique``);
- the *Freudenthaler Zeitung* (German): no row. It stays unresolved, without ``public``, so its
  chunks stay out of anonymous reads and its text goes to no model that may not receive it (#785).

The models are fakes: titles from the fake provider (an excerpt's first four words), embeddings
of the second vector from its OpenAI-compatible endpoint, classifications from a fake remote
(API) model. Nothing goes beyond the test store: no Weaviate client looks up its version on
pypi.org. One chunk is imported without the optional ``end_paragraph``; search and document
reads still answer. Every stage then runs again on the same input and writes nothing.
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
from weaviate.connect.v4 import _ConnectionBase

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
from semant_demo.features.documents.positions import chunk_positions
from tests.fakes import SECOND_VECTOR, second_embedding
from tests.seed import position_properties

sys.path.insert(0, str(Path(__file__).parents[3] / "data_tools" / "embedder"))
sys.path.insert(0, str(Path(__file__).parents[3] / "data_tools" / "meta_data_enrichment"))
from semantembedder.pipeline import EmbeddingPipeline  # noqa: E402
from semantmetaenricher.db import PROVENANCE, UNPROCESSED  # noqa: E402
from semantmetaenricher.pipeline import EnrichmentPipeline  # noqa: E402

pytestmark = pytest.mark.integration

INPUT = Path(__file__).parents[1] / "fixtures" / "append_pipeline" / "chunks.jsonl"
KVKLI, KARLIN, PRAGUE, FREUDENTHAL = (
    "00094a56-54af-4bd4-9559-c5601d81b15d", "000b03e0-53d7-11ee-9c28-0050568d319f",
    "000070c8-2b2a-46f9-8052-1ce4b7dac249", "00246353-3566-4e72-80a6-4019d8f94d59")
RESOLVED = (KVKLI, KARLIN, PRAGUE)
YEARS = {KVKLI: 1906, KARLIN: 1904, PRAGUE: 1839}
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


def page_row(page_id: str, library: str, parent: str) -> dict:
    return row(page_id, library, parent_id=UUID(parent), parent_library=library, record_type="page")


class TitleProvider(httpx.AsyncBaseTransport):
    """The fake provider; fails the requests whose excerpt holds ``failing``."""

    def __init__(self, corpus):
        self.inner = ASGITransport(app=create_fake_provider_app(corpus))
        self.failing: str | None = None

    async def handle_async_request(self, request):
        if self.failing and self.failing in json.loads(request.content)["messages"][-1]["content"]:
            return httpx.Response(503, json={"error": "unavailable"})
        return await self.inner.handle_async_request(request)


class RemoteModel:
    """A fake API model (``remote``: its provider would receive the text): answers ``LABELS``;
    ``failing`` texts get no label. ``asked`` records the classified texts."""
    remote = True

    def __init__(self):
        self.failing: set[str] = set()
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
        return [{t: None if r["text"] in self.failing else list(LABELS[t]) for t in tasks} for r in records]


@pytest.fixture(autouse=True)
def no_version_lookup(monkeypatch):
    """The test needs no network beyond the test store: no Weaviate client (the backend's, the
    embedder's or the classifier's) may look up its latest version on pypi.org."""
    def refuse(*args, **kwargs):
        raise AssertionError("a Weaviate client looked up its version on pypi.org")
    monkeypatch.setattr(_ConnectionBase, "_check_package_version", refuse)


@pytest.fixture
def mirror():
    """The Kramerius mirror of the new documents and the chronicle (see the module docstring)."""
    lines = [json.loads(line) for line in INPUT.read_text(encoding="utf-8").splitlines()]
    kvkli_pages = sorted({c["start_page_id"] for c in lines if c["document"] == KVKLI})
    engine = create_engine("sqlite://")
    META_RECORDS.metadata.create_all(engine)
    with engine.connect() as connection:
        connection.execute(insert(META_RECORDS), [
            row(KVKLI, "kvkli", title="Mittheilungen aus dem Vereine der Naturfreunde in Reichenberg", date="1906"),
            row(KVKLI, "nkp", title="Mittheilungen (nkp)"),
            *[page_row(page, "kvkli", KVKLI) for page in kvkli_pages],
            row(KARLIN, "nkp", title="Karlínské listy (nkp)"),
            row(KARLIN, "mzk", title="Karlínské listy", date="1904", metadata_json={"Publisher": [["Karlín"]]}),
            row(PRAGUE, "nacr", title="Intelligenzblatt zur Prager Zeitung", date="1839"),
            row("5e3a0000-0000-4000-8000-00000000d001", "nkp", title="Kronika obce Lhota"),  # the chronicle
        ])
        yield connection
    engine.dispose()


@pytest.fixture
def stages(seeded_store, collection_names, corpus, store_endpoint, tmp_path, mirror):
    """Each stage as the operator runs it, on the test store with the fake models."""
    names = collection_names
    runs = iter(range(1000))
    titles_provider = TitleProvider(corpus)
    classifier_model = RemoteModel()
    models_config = tmp_path / "models.yaml"
    models_config.write_text(yaml.safe_dump(CATALOG))
    connection = {"weaviate_host": store_endpoint.host, "weaviate_port": store_endpoint.rest_port,
                  "weaviate_grpc_port": store_endpoint.grpc_port, "weaviate_api_key": None,
                  "weaviate_headers": None}

    def fresh(name: str) -> Path:
        return tmp_path / f"{name}-{next(runs)}.json"

    class Stages:
        titles = titles_provider
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
            reported: list[dict] = []
            result = await chunk_titles.run(seeded_store, names, llm, endpoint="test", write=True,
                                            models_config=models_config, usage=usage, progress=quiet,
                                            reported=reported.append)
            return result, reported, chunk_titles.exit_code(result)

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
    new = {c["id"]: c for c in lines}
    of = {doc: [c for c in lines if c["document"] == doc] for doc in dict.fromkeys(c["document"] for c in lines)}
    chronicle = corpus.documents["chronicle"]["id"]
    appended = [c["id"] for c in of[chronicle]]
    hidden = [c["id"] for c in of[FREUDENTHAL]]
    await chunk_summary_schema.update(seeded_store, names, apply=True)  # declared as on production (#561)
    existing, existing_annotations = await snapshot(seeded_store, names), await annotations(seeded_store, names)

    # Import: four new documents and the chronicle's two appended chunks, none of them public yet.
    imported, code, document_list = await stages.ingest()
    assert code == 0 and {k: imported["counts"][k] for k in ("new", "append", "chunks_inserted")} == {
        "new": 4, "append": 1, "chunks_inserted": 14}
    assert set(metadata_sync.read_document_ids(document_list)) == {UUID(d) for d in of}

    # An API model run straight after the import selects none of them: they are not public yet.
    early = await stages.classify()
    assert (early.selected, early.restricted_by) == (0, "documentPublic") and stages.classifier.asked == []

    # Metadata, with the library inferred as in the production sync; the missing document stays unresolved.
    report, applied, code = await stages.metadata(document_list)
    by_id = {e["id"]: e for e in report["documents"]}
    assert {d: by_id[d].get("library_from") for d in (KVKLI, KARLIN, PRAGUE, chronicle)} == {
        KVKLI: "page_ancestry", KARLIN: "mirror_metadata", PRAGUE: "mirror_unique", chronicle: "mirror_unique"}
    assert report["counts"]["unresolved"] == {"no_library": 1} and by_id[FREUDENTHAL]["kind"] == "no_library"
    assert by_id[chronicle]["changes"] == {"library": {"old": None, "new": "nkp"}}   # its public stays true
    assert (applied["applied"], applied["verified"], applied["chunks_pending"], code) == (4, 4, [], 0)

    years, code = await stages.year()
    assert (years["counts"]["set"], years["counts"]["written"], code) == (12, 12, 0)

    # The new public documents' chunks became public with metadata_sync; the appended ones only now.
    visible, code = await stages.visibility(document_list)
    assert {k: visible["counts"][k] for k in ("public", "not_public", "written")} == {
        "public": 4, "not_public": 1, "written": 2} and code == 0

    # Titles: a failed model call is reported and taken up by a rerun; the unresolved document's
    # chunks are deferred (not public). letters_2 is the existing corpus' untitled chunk.
    failing = of[KARLIN][0]
    stages.titles.failing = failing["text"]
    titled, reported, code = await stages.titles_run()
    assert {k: titled["counts"][k] for k in ("generate", "written", "model_failed", "deferred_restricted_document")} \
        == {"generate": 13, "written": 12, "model_failed": 1, "deferred_restricted_document": 2} and code == 1
    assert {(r["id"], r["status"]) for r in reported} == {
        (failing["id"], "model_failed"), *((c, "deferred_restricted_document") for c in hidden)}
    stages.titles.failing = None
    before_rerun = await snapshot(seeded_store, names)
    titled, reported, code = await stages.titles_run()
    assert changed(before_rerun, await snapshot(seeded_store, names)) == {failing["id"]: {"title"}}
    assert (titled["counts"]["written"], titled["counts"]["deferred_restricted_document"], code) == (1, 2, 1)

    embedded = await stages.embed()
    assert (embedded.selected, embedded.embedded, embedded.already_stored, embedded.scanned) == (14, 14, 0, 0)

    # The classification: a failure is retried by the next run; the unresolved document's chunks
    # wait for an explicit decision (``include_restricted_documents``).
    stages.classifier.failing = {of[PRAGUE][0]["text"]}
    classified = await stages.classify()
    assert (classified.selected, classified.classified, len(classified.failed)) == (12, 11, 1)
    stages.classifier.failing = set()
    before_rerun = await snapshot(seeded_store, names)
    classified = await stages.classify()
    assert changed(before_rerun, await snapshot(seeded_store, names)) == {of[PRAGUE][0]["id"]: {*LABELS, PROVENANCE}}
    assert (classified.selected, classified.classified, classified.failed) == (1, 1, [])
    assert not {c["text"] for c in of[FREUDENTHAL]} & set(stages.classifier.asked)

    summarized, code = await stages.summaries()
    assert code == 0 and summarized["counts"]["documents"]["failed"] == 0

    # The new chunks and documents. A new document starts at the document start, the appended
    # chunks continue after the chronicle's stored tail.
    after = await snapshot(seeded_store, names)
    seeded_chronicle = sorted((c for c in corpus.chunks.values() if c["document"] == "chronicle"),
                              key=lambda c: c["order"])
    positions = {}
    for document, chunks in of.items():
        before_them = [c["text"] for c in seeded_chronicle] if document == chronicle else []
        computed = list(chunk_positions([*before_them, *(c["text"] for c in chunks)]))[len(before_them):]
        positions |= {c["id"]: position_properties(p) for c, p in zip(chunks, computed)}
    for chunk_id, line in new.items():
        properties, references, vectors = after[chunk_id]
        document = line["document"]
        public = document != FREUDENTHAL
        assert references["document"] == [document]
        assert {k: properties[k] for k in ("text", "order", "language", "start_page_id")} == {
            k: line[k] for k in ("text", "order", "language", "start_page_id")}
        assert properties["end_paragraph"] == line.get("end_paragraph")   # one chunk is imported without it
        assert {k: properties[k] for k in ("startChar", "startWord", "wordOpenAtStart")} == positions[chunk_id]
        assert properties["documentPublic"] is public
        assert properties["haveVector"] == [SECOND_VECTOR]
        assert vectors[SECOND_VECTOR] == pytest.approx(second_embedding(line["text"]))
        assert properties["title"] == (fake_title(line["text"]) if public else None)
        assert properties[PROVENANCE] == (PROVENANCE_ID if public else UNPROCESSED)
        assert {t: properties[t] for t in LABELS} == (LABELS if public else dict.fromkeys(LABELS))
        expected_year = YEARS.get(document, corpus.documents["chronicle"]["properties"]["yearIssued"]
                                  if document == chronicle else None)
        assert properties.get("yearIssued") == expected_year
    for document in RESOLVED:
        properties = after[document][0]
        assert (properties["library"], properties["yearIssued"], properties["public"]) == (
            {KVKLI: "kvkli", KARLIN: "mzk", PRAGUE: "nacr"}[document], YEARS[document], True)
        assert sorted(properties["chunk_language"]) == [of[document][0]["language"]]
    assert after[KARLIN][0]["publisher"] == "Karlín" and after[KARLIN][0]["title"] == "Karlínské listy"
    # Nothing invented for the unresolved document: only the summaries of its chunks.
    assert {k: v for k, v in after[FREUDENTHAL][0].items() if v not in (None, []) and not k.startswith("chunk_")} \
        == {} and after[FREUDENTHAL][0]["chunk_language"] == ["deu"]

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
    assert (imported["counts"]["replayed"], imported["counts"]["chunks_inserted"], code) == (5, 0, 0)
    report, applied, code = await stages.metadata(document_list)
    # A new report finds them unchanged; applying it writes nothing (exit 1: nothing was eligible).
    assert (report["counts"]["unchanged"], report["counts"]["unresolved"]) == (4, {"no_library": 1})
    assert (applied["eligible"], applied["applied"], code) == (0, 0, 1)
    years, code = await stages.year()
    assert (years["counts"]["written"], code) == (0, 0)
    visible, code = await stages.visibility(document_list)
    assert (visible["counts"]["written"], code) == (0, 0)
    titled, reported, code = await stages.titles_run()
    assert (titled["counts"]["written"], titled["counts"]["deferred_restricted_document"]) == (0, 2)
    assert (await stages.embed()).selected == 0
    assert (await stages.classify()).selected == 0
    summarized, code = await stages.summaries()
    assert (summarized["counts"]["documents"]["changed"], code) == (0, 0)
    assert await snapshot(seeded_store, names) == before


def changed(before: dict, after: dict) -> dict[str, set[str]]:
    """The properties that differ, by object id (references and vectors must not)."""
    assert before.keys() == after.keys()
    differ = {}
    for object_id, (properties, references, vectors) in before.items():
        assert (after[object_id][1], after[object_id][2]) == (references, vectors), object_id
        keys = {k for k in properties.keys() | after[object_id][0].keys()
                if properties.get(k) != after[object_id][0].get(k)}
        if keys:
            differ[object_id] = keys
    return differ


def corpus_document_ids(corpus) -> set[str]:
    return {d["id"] for d in corpus.documents.values()}


async def users_see_the_new_documents(api_app, api_client, corpus, tmp_path, of, chronicle):
    """Anonymous search, filters, browsing and counts include the new public documents and the
    appended chunks, and nothing of the unresolved document (#279)."""
    path = tmp_path / "search_vectors.yaml"   # the vector the embedder filled, as SEARCH_VECTORS_CONFIG lists it
    path.write_text(yaml.safe_dump({"default": "small", "vectors": [
        {"id": "small", "name": "Small", "target_vector": SECOND_VECTOR,
         "embedding": {"provider": "openai", "base_url": "http://fake/openai/v1", "model": "fake-small"}}]}))
    api_app.state.resources.search_vectors = load_search_vectors(
        Config(environ={"SEARCH_VECTORS_CONFIG": str(path)}), ASGITransport(app=create_fake_provider_app(corpus)))
    hidden = {c["id"] for c in of[FREUDENTHAL]}

    async def search(text: str, kind: str) -> list[str]:
        response = await api_client.post("/api/search", json={"query": text, "type": kind, "limit": 50,
                                                              "vector": "small", **NO_SUMMARY})
        assert response.status_code == 200, response.text
        return [r["id"] for r in response.json()["results"]]

    for kind in ("vector", "hybrid"):
        for chunk in (of[KARLIN][1], of[KVKLI][2], of[chronicle][1]):
            assert (await search(chunk["text"], kind))[0] == chunk["id"], (kind, chunk["id"])
        assert not hidden & set(await search(of[FREUDENTHAL][0]["text"], kind))
    assert of[chronicle][1]["id"] in await search("tesaři z Brna", "text")
    assert not hidden & set(await search(of[FREUDENTHAL][0]["text"], "text"))

    async def browse(**filters) -> set[str]:
        response = await api_client.get("/api/documents/browse", params={"limit": 200, **filters})
        assert response.status_code == 200, response.text
        return {d["id"] for d in response.json()["items"]}

    seeded = {d["id"] for d in corpus.documents.values()}
    letters = corpus.documents["letters"]["id"]
    assert await browse() == seeded | set(RESOLVED)
    assert await browse(year_min=1900, year_max=1910) == {KVKLI, KARLIN, letters}
    assert await browse(libraries=["kvkli", "nkp"]) == {KVKLI, chronicle}
    assert await browse(chunk_languages=["deu"]) == {KVKLI, PRAGUE}
    assert await browse(chunk_classifications=["communicative_mode:description"]) == {*RESOLVED, chronicle}
    overview = (await api_client.get("/api/analytics/corpus/overview")).json()
    assert overview["total_documents"] == len(seeded) + len(RESOLVED)
    assert (await api_client.get(f"/api/document/{FREUDENTHAL}")).status_code == 404

    # Reading a new document around its chunk imported without ``end_paragraph`` (#798).
    bare = of[KARLIN][1]
    assert "end_paragraph" not in bare
    window = await api_client.get(f"/api/documents/{KARLIN}/chunks/{bare['id']}/window")
    assert window.status_code == 200, window.text
    assert [c["id"] for c in window.json()["chunks"]] == [c["id"] for c in of[KARLIN]]
    assert {c["id"]: c["end_paragraph"] for c in window.json()["chunks"]}[bare["id"]] is True
    page = await api_client.get(f"/api/documents/{KARLIN}/chunks/by_page", params={"page": bare["from_page"]})
    assert page.status_code == 200, page.text
