"""The appended data and the stages of an import, shared by the tests over appended data (#798, #884).

``fixtures/append_pipeline/chunks.jsonl`` holds a new document (*Karlínské listy*, one chunk
without the optional ``end_paragraph``), a new document (*Freudenthaler Zeitung*) and two chunks
appended to the seeded chronicle. ``make_stages`` runs each stage of ``docs/DATA_MAINTENANCE.md``
(*Chunk import*, *Afterwards*) in process, as an operator does, on the test store with fake
models; ``metadata_sync`` reads an in-memory SQLite mirror with the flags of the production sync
(#259). The fixtures ``append_mirror`` and ``append_stages`` (``tests/integration/conftest.py``)
provide them; a test module overrides ``append_mirror`` for other mirror rows.
"""
import asyncio
import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

import httpx
import yaml
from httpx import ASGITransport
from openai import AsyncOpenAI
from sqlalchemy import create_engine, insert
from weaviate.classes.query import QueryReference

from semant_demo.adapters.llm.gateway import LlmGateway, ProviderSettings
from semant_demo.adapters.llm.models import ModelCatalog
from semant_demo.adapters.sql.kramerius_metadata import META_RECORDS
from semant_demo.features.documents.criteria import SUMMARIES_COMPUTED_AT
from semant_demo.maintenance import (
    chunk_document_public, chunk_ingest, chunk_summaries, chunk_titles, chunk_year, metadata_sync)
from semant_demo.maintenance.chunk_titles import UsageTotals
from tests.fake_providers import create_fake_provider_app
from tests.fakes import SECOND_VECTOR

sys.path.insert(0, str(Path(__file__).parents[2] / "data_tools" / "embedder"))
sys.path.insert(0, str(Path(__file__).parents[2] / "data_tools" / "meta_data_enrichment"))
from semantembedder.pipeline import EmbeddingPipeline  # noqa: E402
from semantmetaenricher.db import PROVENANCE, UNPROCESSED  # noqa: E402,F401  (for the tests)
from semantmetaenricher.pipeline import EnrichmentPipeline  # noqa: E402

INPUT = Path(__file__).parent / "fixtures" / "append_pipeline" / "chunks.jsonl"
KARLIN, FREUDENTHAL = "000b03e0-53d7-11ee-9c28-0050568d319f", "00246353-3566-4e72-80a6-4019d8f94d59"
CATALOG = {"tiers": {"tiny": {"provider": "ollama", "model": "fake-titles", "price_basis": "local_rate",
                              "input_price": 0, "output_price": 0}},
           "features": {"chunk_titles": {"default": "tiny", "limits": {"max_output_tokens": 64,
                                                                     "max_input_tokens": 4096}}}}
LABELS = {"communicative_mode": ["description"], "style": ["formal"]}
PROVENANCE_ID = "fake-classifier-v1"

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
CHRONICLE = "5e3a0000-0000-4000-8000-00000000d001"
"""The seeded chronicle (three chunks); the input appends two."""


@contextmanager
def mirror_connection(rows: list[dict]) -> Iterator:
    """A connection to an in-memory Kramerius mirror holding ``rows`` (``row``)."""
    engine = create_engine("sqlite://")
    META_RECORDS.metadata.create_all(engine)
    with engine.connect() as connection:
        connection.execute(insert(META_RECORDS), rows)
        yield connection
    engine.dispose()


def make_stages(seeded_store, names, corpus, store_endpoint, tmp_path: Path, mirror):
    """Each stage as the operator runs it, on the test store with the fake models; ``mirror`` is a
    connection to the Kramerius mirror (``mirror_connection``)."""
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
