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
from semant_demo.maintenance.chunk_titles import Refused, Selection, UsageTotals
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


async def titles(seeded_store, names, provider, models_config, **options):
    usage = UsageTotals()
    llm = LlmGateway(ModelCatalog.load(models_config),
                     ProviderSettings(ollama_base_url="http://fake/ollama", max_retries=0), usage,
                     http_transport=provider)
    return await chunk_titles.run(seeded_store, names, llm, endpoint="test", models_config=models_config,
                                  usage=usage, progress=quiet, **options)


@pytest.fixture
def chunk_run(seeded_store, collection_names, provider, models_config):
    async def go(**options):
        return await titles(seeded_store, collection_names, provider, models_config, **options)
    return go


async def stored(seeded_store, names, chunk_id):
    return await seeded_store.collections.get(names.chunks_collection_name).query.fetch_object_by_id(
        chunk_id, include_vector=True, return_references=QueryReference(link_on="document"))


async def title_of(seeded_store, names, chunk_id):
    return (await stored(seeded_store, names, chunk_id)).properties["title"]


def statuses(result) -> list[tuple[str, str]]:
    return [(line["id"], line["status"]) for line in result["reported_chunks"]]


async def untitle(seeded_store, names, *chunk_ids):
    chunks = seeded_store.collections.get(names.chunks_collection_name)
    for chunk_id in chunk_ids:
        await chunks.data.update(uuid=chunk_id, properties={"title": None})


async def test_check_write_touches_only_the_title_and_a_rerun_does_nothing(seeded_store, collection_names, corpus,
                                                                           chunk_run, provider):
    letters_2 = corpus.chunks["letters_2"]
    before = await stored(seeded_store, collection_names, letters_2["id"])

    check = await chunk_run(write=False)

    assert check["counts"] == chunk_titles._counts() | {"examined": 7, "has_title": 6, "generate": 1}
    assert check["languages"] == {"ces": 7} and check["selection"] == {"kind": "untitled"}
    assert check["complete"] and check["next_after"] is None and check["reported_chunks"] == []
    assert chunk_titles.exit_code(check) == 1 and provider.prompts == []   # a check makes no model call
    assert before.properties["title"] is None
    assert await title_of(seeded_store, collection_names, letters_2["id"]) is None

    written = await chunk_run(write=True)

    assert written["counts"]["written"] == 1 and written["complete"] and chunk_titles.exit_code(written) == 0
    assert written["provenance"]["model"] == "fake-titles" and written["provenance"]["prompt_version"] == "chunk-title-v1"
    assert written["usage"]["calls"] == 1 and written["usage"]["input_tokens"] > 0
    assert provider.prompts == ["Original Document Title:\nDopisy z Prahy\n\n"
                                f"Excerpt Text:\n{letters_2['text']}\n\nWrite the heading in Czech."]
    after = await stored(seeded_store, collection_names, letters_2["id"])
    assert after.properties == {**before.properties, "title": fake_title(letters_2["text"])}
    assert after.vector == before.vector
    assert [o.uuid for o in after.references["document"].objects] == [UUID(corpus.documents["letters"]["id"])]
    assert await title_of(seeded_store, collection_names, corpus.chunks["letters_1"]["id"]) == (
        corpus.chunks["letters_1"]["title"])

    again = await chunk_run(write=True)   # the store is the state: nothing is left
    assert again["counts"]["generate"] == 0 and again["counts"]["written"] == 0 and chunk_titles.exit_code(again) == 0
    assert len(provider.prompts) == 1


async def test_documents_without_a_title_are_deferred_until_allowed(seeded_store, collection_names, corpus,
                                                                   chunk_run, provider):
    gazette, gazette_1 = corpus.documents["gazette"], corpus.chunks["gazette_1"]
    await seeded_store.collections.get(collection_names.document_collection_name).data.update(
        uuid=gazette["id"], properties={"title": None})
    await untitle(seeded_store, collection_names, gazette_1["id"])

    deferred = await chunk_run(write=True)

    assert deferred["counts"]["deferred_no_document_title"] == 1 and deferred["counts"]["written"] == 1  # letters_2
    assert deferred["complete"] and chunk_titles.exit_code(deferred) == 1
    assert deferred["reported_chunks"] == [{"id": gazette_1["id"], "status": "deferred_no_document_title",
                                            "document_ids": [gazette["id"]]}]
    assert await title_of(seeded_store, collection_names, gazette_1["id"]) is None

    selection = Selection(True, documents=(UUID(gazette["id"]),))
    allowed = await chunk_run(write=True, selection=selection, allow_missing_document_title=True)

    assert allowed["counts"] == chunk_titles._counts() | {"examined": 2, "has_title": 1, "generate": 1,
                                                               "written": 1}
    assert chunk_titles.exit_code(allowed) == 0
    assert provider.prompts[-1] == f"Excerpt Text:\n{gazette_1['text']}\n\nWrite the heading in Czech."
    assert await title_of(seeded_store, collection_names, gazette_1["id"]) == fake_title(gazette_1["text"])

    # Titles are redone only for an explicit selection.
    chunks = seeded_store.collections.get(collection_names.chunks_collection_name)
    await chunks.data.update(uuid=gazette_1["id"], properties={"title": "Stale"})
    with pytest.raises(Refused, match="explicit selection"):
        await chunk_run(write=True, regenerate=True)
    redone = await chunk_run(write=True, selection=Selection(True, chunks=(UUID(gazette_1["id"]),)), regenerate=True,
                             allow_missing_document_title=True)
    assert redone["counts"]["examined"] == 1 and redone["counts"]["written"] == 1
    assert await title_of(seeded_store, collection_names, gazette_1["id"]) == fake_title(gazette_1["text"])


async def test_a_failed_model_call_is_reported_and_taken_up_by_a_rerun(seeded_store, collection_names, corpus,
                                                                       chunk_run, provider):
    letters_2 = corpus.chunks["letters_2"]
    provider.failing = letters_2["text"]

    failed = await chunk_run(write=True)

    assert failed["counts"]["model_failed"] == 1 and failed["counts"]["written"] == 0
    assert failed["complete"] and chunk_titles.exit_code(failed) == 1
    assert failed["reported_chunks"] == [{"id": letters_2["id"], "status": "model_failed", "reason": "ResponseError"}]
    assert await title_of(seeded_store, collection_names, letters_2["id"]) is None

    provider.failing = None
    rerun = await chunk_run(write=True)

    assert rerun["counts"]["model_failed"] == 0 and rerun["counts"]["written"] == 1 and chunk_titles.exit_code(rerun) == 0


async def test_limited_runs_progress_past_titled_and_failing_chunks(seeded_store, collection_names, corpus,
                                                                    chunk_run, provider):
    # Untitled in id order: chronicle_2, letters_2, gazette_2; chronicle_2 keeps failing.
    chronicle_2, letters_1, letters_2, gazette_1, gazette_2 = (
        corpus.chunks[key] for key in ("chronicle_2", "letters_1", "letters_2", "gazette_1", "gazette_2"))
    await untitle(seeded_store, collection_names, chronicle_2["id"], gazette_2["id"])
    provider.failing = chronicle_2["text"]

    first = await chunk_run(write=True, limit=1)
    assert statuses(first) == [(chronicle_2["id"], "model_failed")]
    # Titled chunks are passed over without counting toward the limit, up to the next chunk to title.
    assert not first["complete"] and first["next_after"] == letters_1["id"] and chunk_titles.exit_code(first) == 1
    assert first["counts"]["examined"] == 4 and first["counts"]["has_title"] == 3

    # Without --after the run starts again and the failing chunk takes the limit again.
    again = await chunk_run(write=True, limit=1)
    assert statuses(again) == [(chronicle_2["id"], "model_failed")] and again["next_after"] == letters_1["id"]

    # --after continues past it.
    second = await chunk_run(write=True, limit=1, after=UUID(first["next_after"]))
    assert second["counts"] == chunk_titles._counts() | {"examined": 2, "generate": 1, "written": 1, "has_title": 1}
    assert second["next_after"] == gazette_1["id"] and not second["complete"]
    assert await title_of(seeded_store, collection_names, letters_2["id"]) == fake_title(letters_2["text"])
    third = await chunk_run(write=True, limit=1, after=UUID(second["next_after"]))
    assert third["counts"]["written"] == 1 and third["complete"] and third["next_after"] is None
    assert chunk_titles.exit_code(third) == 0   # nothing failed after letters_1
    assert await title_of(seeded_store, collection_names, gazette_2["id"]) == fake_title(gazette_2["text"])

    # A whole run reports the chunk still failing; once it succeeds the store is complete.
    whole = await chunk_run(write=True)
    assert statuses(whole) == [(chronicle_2["id"], "model_failed")] and chunk_titles.exit_code(whole) == 1
    provider.failing = None
    done = await chunk_run(write=True, limit=1)
    assert done["counts"]["written"] == 1 and done["complete"] and chunk_titles.exit_code(done) == 0


async def test_a_limited_check_counts_what_it_would_title(seeded_store, collection_names, corpus, chunk_run):
    await untitle(seeded_store, collection_names, corpus.chunks["chronicle_2"]["id"], corpus.chunks["gazette_2"]["id"])
    check = await chunk_run(write=False, limit=2)
    assert check["counts"]["generate"] == 2 and check["next_after"] == corpus.chunks["gazette_1"]["id"]
    assert not check["complete"] and chunk_titles.exit_code(check) == 1

    # --after an id that no longer exists (a chunk deleted since) continues after its place.
    deleted = UUID("5e3a0000-0000-4000-8000-0000000d2c00")   # between chronicle_3 and letters_1
    rest = await chunk_run(write=False, after=deleted)
    assert rest["counts"]["examined"] == 4 and rest["counts"]["generate"] == 2 and rest["complete"]


async def test_failed_or_interrupted_writes_are_taken_up_by_a_rerun(seeded_store, collection_names, corpus,
                                                                    chunk_run, provider, monkeypatch):
    letters_2 = corpus.chunks["letters_2"]
    set_chunk_title = chunk_titles.store.set_chunk_title

    async def unavailable(*args):
        raise ConnectionError("store unavailable")
    monkeypatch.setattr(chunk_titles.store, "set_chunk_title", unavailable)
    failed = await chunk_run(write=True)

    assert statuses(failed) == [(letters_2["id"], "write_failed")] and chunk_titles.exit_code(failed) == 1
    assert "store unavailable" in failed["reported_chunks"][0]["reason"]
    assert await title_of(seeded_store, collection_names, letters_2["id"]) is None
    monkeypatch.setattr(chunk_titles.store, "set_chunk_title", set_chunk_title)

    class Interrupted(Exception):
        pass

    async def interrupted(self, titles):
        raise Interrupted
    store_titles = chunk_titles._Run.store_titles
    monkeypatch.setattr(chunk_titles._Run, "store_titles", interrupted)
    with pytest.raises(Interrupted):
        await chunk_run(write=True)
    assert await title_of(seeded_store, collection_names, letters_2["id"]) is None
    monkeypatch.setattr(chunk_titles._Run, "store_titles", store_titles)

    rerun = await chunk_run(write=True)

    assert len(provider.prompts) == 3   # generated again by each run
    assert rerun["counts"]["written"] == 1 and chunk_titles.exit_code(rerun) == 0
    assert await title_of(seeded_store, collection_names, letters_2["id"]) == fake_title(letters_2["text"])


async def test_absent_chunks_are_reported_and_the_schema_is_never_changed(seeded_store, collection_names, corpus,
                                                                          chunk_run, provider, tmp_path):
    absent = UUID("7171e000-0000-4000-8000-0000000000ff")
    reported = await chunk_run(write=True,
                               selection=Selection(True, chunks=(absent, UUID(corpus.chunks["letters_2"]["id"]))))
    assert reported["counts"]["absent"] == 1 and reported["counts"]["written"] == 1
    assert statuses(reported) == [(str(absent), "absent")] and chunk_titles.exit_code(reported) == 1

    bare = "ChunkTitlesWithoutTitle"
    await seeded_store.collections.create(bare, properties=[Property(name="text", data_type=DataType.TEXT)])
    try:
        names = collection_names.model_copy(update={"chunks_collection_name": bare})
        with pytest.raises(Refused, match="not declared"):
            await titles(seeded_store, names, provider, tmp_path / "models.yaml", write=True)
        config = await seeded_store.collections.get(bare).config.get()
        assert [p.name for p in config.properties] == ["text"]
    finally:
        await seeded_store.collections.delete(bare)


async def test_document_titles_are_read_only_for_chunks_that_may_get_a_title(corpus, chunk_run, monkeypatch):
    read_document_titles, asked = chunk_titles.store.read_document_titles, []

    async def recording(client, collection, ids, with_title=True):
        asked.append(sorted(map(str, ids)))
        return await read_document_titles(client, collection, ids, with_title)
    monkeypatch.setattr(chunk_titles.store, "read_document_titles", recording)
    await chunk_run(write=False)

    assert asked == [[corpus.documents["letters"]["id"]]]   # the document of the only untitled chunk
