"""Appending new data to a populated store through every stage together (#798, #560 A).

A smoke test of the hand-offs between the stages; each stage's own tests cover its details.
The seeded fixture corpus is the existing corpus. ``fixtures/append_pipeline/chunks.jsonl``
holds a new document (*Karlínské listy*, one chunk without the optional ``end_paragraph``), a new
document missing from the Kramerius mirror (*Freudenthaler Zeitung*) and two chunks appended to
the seeded chronicle (``tests/append_pipeline.py``). The stages run in process in the order of
``docs/DATA_MAINTENANCE.md`` (*Chunk import*, *Afterwards*) and hand over through the import's
document list, as an operator does; ``metadata_sync`` reads an in-memory SQLite mirror with the
flags of the production sync (#259). The models are fakes. The test checks that the new public
chunks reach search, that the unresolved document stays out of anonymous reads and of the API
model (#785), that the existing corpus keeps its data, and that a replay of every stage writes
nothing.
"""
import json
from uuid import UUID

import pytest
import yaml
from httpx import ASGITransport

from semant_demo.bootstrap import load_search_vectors
from semant_demo.config import Config
from semant_demo.maintenance import chunk_summary_schema, metadata_sync
from tests.append_pipeline import FREUDENTHAL, INPUT, KARLIN, PROVENANCE, PROVENANCE_ID, UNPROCESSED, snapshot
from tests.fake_providers import create_fake_provider_app, fake_title
from tests.fakes import SECOND_VECTOR

pytestmark = pytest.mark.integration

NO_SUMMARY = {"search_title_generate": False, "search_summary_generate": False,
              "search_results_summary_generate": False}

async def annotations(client, names) -> dict:
    """Every annotation object, per tenant."""
    collection = client.collections.get(names.annotation_collection_name)
    stored = {}
    for tenant in await collection.tenants.get():
        async for o in collection.with_tenant(tenant).iterator():
            stored[(tenant, str(o.uuid))] = o.properties
    return stored


async def test_appended_data_runs_through_every_stage_and_a_replay_writes_nothing(
        seeded_store, collection_names, corpus, append_stages, tmp_path, api_app, api_client):
    names, stages = collection_names, append_stages
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
