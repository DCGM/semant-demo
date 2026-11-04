"""Chunk title generation against the real test store (#575).

The fixture corpus: chronicle (chronicle_1-3), letters (letters_1-2) and gazette (gazette_1-2),
each document with a title; every chunk but letters_2 has a title, and every chunk's language
is ``ces``. The model is the HTTP fake provider (in process), served through the real gateway
with a model catalog written for the run; it titles an excerpt with its first four words.
"""
import json
from uuid import UUID

import httpx
import pytest
import yaml
from httpx import ASGITransport
from weaviate.classes.config import DataType, Property
from weaviate.classes.query import QueryReference

from semant_demo.adapters.llm.gateway import LlmGateway, ProviderSettings
from semant_demo.adapters.llm.models import ModelCatalog
from semant_demo.maintenance import chunk_titles
from semant_demo.maintenance.chunk_titles import Refused, Selection, UsageTotals, read_uuids
from tests.fake_providers import create_fake_provider_app, fake_title

pytestmark = pytest.mark.integration

CATALOG = {"tiers": {"tiny": {"provider": "ollama", "model": "fake-titles", "price_basis": "local_rate",
                              "input_price": 0, "output_price": 0}},
           "features": {"chunk_titles": {"default": "tiny", "limits": {"max_output_tokens": 64,
                                                                     "max_input_tokens": 4096}}}}


def quiet(line: str) -> None:
    pass


class Provider(httpx.AsyncBaseTransport):
    """The fake provider; records the user messages and fails the requests whose excerpt holds ``failing``."""

    def __init__(self, corpus):
        self.inner = ASGITransport(app=create_fake_provider_app(corpus))
        self.prompts: list[str] = []
        self.failing: str | None = None

    async def handle_async_request(self, request):
        prompt = json.loads(request.content)["messages"][-1]["content"]
        self.prompts.append(prompt)
        if self.failing and self.failing in prompt:
            return httpx.Response(503, json={"error": "unavailable"})
        return await self.inner.handle_async_request(request)


@pytest.fixture
def models_config(tmp_path):
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump(CATALOG))
    return path


@pytest.fixture
def provider(corpus):
    return Provider(corpus)


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(chunk_titles, "BACKOFF", 0)


async def titles(seeded_store, names, provider, models_config, checkpoint, **options):
    usage = UsageTotals()
    llm = LlmGateway(ModelCatalog.load(models_config),
                     ProviderSettings(ollama_base_url="http://fake/ollama", max_retries=0), usage,
                     http_transport=provider)
    return await chunk_titles.run(seeded_store, names, llm, checkpoint=checkpoint, endpoint="test",
                                  models_config=models_config, usage=usage, progress=quiet, **options)


@pytest.fixture
def chunk_run(seeded_store, collection_names, provider, models_config):
    async def go(checkpoint, **options):
        return await titles(seeded_store, collection_names, provider, models_config, checkpoint, **options)
    return go


async def stored(seeded_store, names, chunk_id):
    return await seeded_store.collections.get(names.chunks_collection_name).query.fetch_object_by_id(
        chunk_id, include_vector=True, return_references=QueryReference(link_on="document"))


def manifest(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


async def test_check_write_touches_only_the_title_and_a_rerun_does_nothing(seeded_store, collection_names, corpus,
                                                                           chunk_run, provider, tmp_path):
    letters_2 = corpus.chunks["letters_2"]
    before = await stored(seeded_store, collection_names, letters_2["id"])

    check = await chunk_run(tmp_path / "check.json", write=False)

    assert check["counts"] == chunk_titles._counts() | {"examined": 7, "has_title": 6, "generate": 1}
    assert check["languages"] == {"ces": 7} and check["selection"] == {"kind": "untitled"}
    assert chunk_titles.exit_code(check) == 1 and provider.prompts == []   # a check makes no model call
    assert (await stored(seeded_store, collection_names, letters_2["id"])).properties["title"] is None

    with pytest.raises(Refused, match="mode"):   # a check checkpoint is not resumed as a write
        await chunk_run(tmp_path / "check.json", write=True)
    written = await chunk_run(tmp_path / "write.json", write=True)

    assert written["counts"]["written"] == 1 and written["to_retry"] == 0 and chunk_titles.exit_code(written) == 0
    assert written["provenance"]["model"] == "fake-titles" and written["provenance"]["prompt_version"] == "chunk-title-v1"
    assert written["usage"]["calls"] == 1 and written["usage"]["input_tokens"] > 0
    assert provider.prompts == ["Language code:\nces\n\nOriginal Document Title:\nDopisy z Prahy\n\n"
                                f"Excerpt Text:\n{letters_2['text']}"]
    after = await stored(seeded_store, collection_names, letters_2["id"])
    assert after.properties == {**before.properties, "title": fake_title(letters_2["text"])}
    assert after.vector == before.vector
    assert [o.uuid for o in after.references["document"].objects] == [UUID(corpus.documents["letters"]["id"])]
    assert read_uuids(tmp_path / "write.json.titled.uuids") == [UUID(letters_2["id"])]
    others = await stored(seeded_store, collection_names, corpus.chunks["letters_1"]["id"])
    assert others.properties["title"] == corpus.chunks["letters_1"]["title"]

    again = await chunk_run(tmp_path / "again.json", write=True)
    assert again["counts"]["generate"] == 0 and again["counts"]["written"] == 0 and chunk_titles.exit_code(again) == 0
    assert len(provider.prompts) == 1   # nothing generated again
    with pytest.raises(Refused, match="finished run"):
        await chunk_run(tmp_path / "write.json", write=True)


async def test_documents_without_a_title_are_deferred_until_allowed(seeded_store, collection_names, corpus,
                                                                   chunk_run, provider, tmp_path):
    gazette, gazette_1 = corpus.documents["gazette"], corpus.chunks["gazette_1"]
    await seeded_store.collections.get(collection_names.document_collection_name).data.update(
        uuid=gazette["id"], properties={"title": None})
    chunks = seeded_store.collections.get(collection_names.chunks_collection_name)
    await chunks.data.update(uuid=gazette_1["id"], properties={"title": None})

    deferred = await chunk_run(tmp_path / "deferred.json", write=True)

    assert deferred["counts"]["deferred_no_document_title"] == 1 and deferred["counts"]["written"] == 1  # letters_2
    assert chunk_titles.exit_code(deferred) == 1
    assert {(m["id"], m["status"]) for m in manifest(tmp_path / "deferred.json.manifest.jsonl")} == {
        (gazette_1["id"], "deferred_no_document_title")}
    assert (await stored(seeded_store, collection_names, gazette_1["id"])).properties["title"] is None

    selection = Selection(True, documents=(UUID(gazette["id"]),))
    allowed = await chunk_run(tmp_path / "allowed.json", write=True, selection=selection,
                              allow_missing_document_title=True)

    assert allowed["counts"] == chunk_titles._counts() | {"examined": 2, "has_title": 1, "generate": 1,
                                                               "written": 1}
    assert chunk_titles.exit_code(allowed) == 0
    assert provider.prompts[-1] == f"Language code:\nces\n\nExcerpt Text:\n{gazette_1['text']}"
    assert (await stored(seeded_store, collection_names, gazette_1["id"])).properties["title"] == fake_title(
        gazette_1["text"])

    # one run's titles are redone exactly: its .uuids file selects them
    await chunks.data.update(uuid=gazette_1["id"], properties={"title": "Stale"})
    with pytest.raises(Refused, match="explicit selection"):
        await chunk_run(tmp_path / "everything.json", write=True, regenerate=True)
    redo = Selection(True, chunks=tuple(read_uuids(tmp_path / "allowed.json.titled.uuids")))
    redone = await chunk_run(tmp_path / "redo.json", write=True, selection=redo, regenerate=True,
                             allow_missing_document_title=True)
    assert redone["counts"]["examined"] == 1 and redone["counts"]["written"] == 1
    assert (await stored(seeded_store, collection_names, gazette_1["id"])).properties["title"] == fake_title(
        gazette_1["text"])


async def test_a_failed_model_call_is_retried_by_the_same_command(seeded_store, collection_names, corpus,
                                                                  chunk_run, provider, tmp_path):
    letters_2 = corpus.chunks["letters_2"]
    provider.failing = letters_2["text"]

    failed = await chunk_run(tmp_path / "write.json", write=True)

    assert failed["counts"]["model_failed"] == 1 and failed["to_retry"] == 1 and chunk_titles.exit_code(failed) == 1
    assert [(m["status"], m["reason"]) for m in manifest(tmp_path / "write.json.manifest.jsonl")] == [
        ("model_failed", "ResponseError")]
    assert (await stored(seeded_store, collection_names, letters_2["id"])).properties["title"] is None

    provider.failing = None
    retried = await chunk_run(tmp_path / "write.json", write=True)

    assert retried["counts"]["model_failed"] == 0 and retried["counts"]["written"] == 1
    assert retried["to_retry"] == 0 and chunk_titles.exit_code(retried) == 0
    assert read_uuids(tmp_path / "write.json.titled.uuids") == [UUID(letters_2["id"])]


async def test_chunks_that_keep_failing_are_retried_once_per_run_within_the_limit(
        seeded_store, collection_names, corpus, chunk_run, provider, tmp_path):
    letters = [UUID(corpus.chunks[key]["id"]) for key in ("letters_1", "letters_2")]
    provider.failing = "Excerpt Text"   # every title request
    options = {"write": True, "regenerate": True, "selection": Selection(True, (), tuple(letters))}

    failed = await chunk_run(tmp_path / "write.json", **options)
    assert failed["counts"]["model_failed"] == 2 and failed["to_retry"] == 2
    assert len(provider.prompts) == 2 * chunk_titles.ATTEMPTS

    limited = await chunk_run(tmp_path / "write.json", limit=1, **options)
    assert len(provider.prompts) == 3 * chunk_titles.ATTEMPTS   # one chunk retried: the limit counts retries
    assert limited["counts"]["model_failed"] == 2 and limited["to_retry"] == 2

    again = await chunk_run(tmp_path / "write.json", **options)   # ends: each retried once, still failing
    assert len(provider.prompts) == 5 * chunk_titles.ATTEMPTS
    assert again["counts"]["model_failed"] == 2 and again["to_retry"] == 2 and chunk_titles.exit_code(again) == 1


async def test_a_failed_write_is_retried_with_its_title_without_a_model_call(seeded_store, collection_names, corpus,
                                                                            chunk_run, provider, tmp_path,
                                                                            monkeypatch):
    letters_2 = corpus.chunks["letters_2"]
    set_chunk_title = chunk_titles.store.set_chunk_title

    async def unavailable(*args):
        raise ConnectionError("store unavailable")
    monkeypatch.setattr(chunk_titles.store, "set_chunk_title", unavailable)
    failed = await chunk_run(tmp_path / "write.json", write=True)

    assert failed["counts"]["write_failed"] == 1 and failed["to_retry"] == 1 and len(provider.prompts) == 1
    assert json.loads((tmp_path / "write.json").read_text())["unwritten"] == {
        letters_2["id"]: fake_title(letters_2["text"])}
    assert (await stored(seeded_store, collection_names, letters_2["id"])).properties["title"] is None

    monkeypatch.setattr(chunk_titles.store, "set_chunk_title", set_chunk_title)
    retried = await chunk_run(tmp_path / "write.json", write=True)

    assert len(provider.prompts) == 1   # the recorded title is written, not generated again
    assert retried["counts"]["write_failed"] == 0 and retried["counts"]["written"] == 1
    assert retried["to_retry"] == 0 and chunk_titles.exit_code(retried) == 0
    assert (await stored(seeded_store, collection_names, letters_2["id"])).properties["title"] == fake_title(
        letters_2["text"])
    assert read_uuids(tmp_path / "write.json.titled.uuids") == [UUID(letters_2["id"])]


async def test_an_interrupted_write_is_completed_without_new_model_calls(seeded_store, collection_names, corpus,
                                                                        chunk_run, provider, tmp_path, monkeypatch):
    letters_2 = corpus.chunks["letters_2"]
    flush = chunk_titles._Run.flush

    class Interrupted(Exception):
        pass

    async def interrupted(self):
        if self.state["in_flight"]:
            raise Interrupted
        await flush(self)
    monkeypatch.setattr(chunk_titles._Run, "flush", interrupted)
    with pytest.raises(Interrupted):
        await chunk_run(tmp_path / "write.json", write=True)
    state = json.loads((tmp_path / "write.json").read_text())
    assert state["in_flight"] == {letters_2["id"]: fake_title(letters_2["text"])} and len(provider.prompts) == 1
    assert (await stored(seeded_store, collection_names, letters_2["id"])).properties["title"] is None

    monkeypatch.setattr(chunk_titles._Run, "flush", flush)
    resumed = await chunk_run(tmp_path / "write.json", write=True)

    assert len(provider.prompts) == 1   # the recorded title is written, not generated again
    assert resumed["counts"]["written"] == 1 and chunk_titles.exit_code(resumed) == 0
    assert (await stored(seeded_store, collection_names, letters_2["id"])).properties["title"] == fake_title(
        letters_2["text"])
    assert read_uuids(tmp_path / "write.json.titled.uuids") == [UUID(letters_2["id"])]


async def test_absent_chunks_are_reported_and_the_schema_is_never_changed(seeded_store, collection_names, corpus,
                                                                          chunk_run, provider, tmp_path):
    absent = UUID("7171e000-0000-4000-8000-0000000000ff")
    reported = await chunk_run(tmp_path / "absent.json", write=True,
                               selection=Selection(True, chunks=(absent, UUID(corpus.chunks["letters_2"]["id"]))))
    assert reported["counts"]["absent"] == 1 and reported["counts"]["written"] == 1
    assert chunk_titles.exit_code(reported) == 1

    bare = "ChunkTitlesWithoutTitle"
    await seeded_store.collections.create(bare, properties=[Property(name="text", data_type=DataType.TEXT)])
    try:
        names = collection_names.model_copy(update={"chunks_collection_name": bare})
        with pytest.raises(Refused, match="not declared"):
            await titles(seeded_store, names, provider, tmp_path / "models.yaml", tmp_path / "bare.json", write=True)
        config = await seeded_store.collections.get(bare).config.get()
        assert [p.name for p in config.properties] == ["text"]
    finally:
        await seeded_store.collections.delete(bare)
