"""The anchor step of the page import (#542) against the real test store.

It writes ``layoutStart`` alone: text, the other properties and the vectors are kept; a
repeated run writes nothing; a plan without an anchor clears a stored one.
"""
import json
from uuid import UUID

import pytest

from semant_demo.adapters.filesystem.page_assets import ManifestPage, PageAssetStore, PageManifest, write_atomically
from semant_demo.adapters.weaviate.layout_anchors import declare_layout_start, read_document_chunks
from semant_demo.maintenance.page_import import run
from semant_demo.maintenance.page_import.__main__ import WeaviateAnchors
from semant_demo.maintenance.page_import.assets import plan_path, text_sha

pytestmark = pytest.mark.integration

PARAMS = {"lineConfidence": 0.6, "minChunkChars": 768, "maxChunkChars": 1152}


def _plan(store: PageAssetStore, document_id: UUID, chunks, anchors) -> None:
    pages = sorted({a["pageId"] for a in anchors if a})
    store.write_manifest(PageManifest(documentId=document_id, params=PARAMS, pages=[
        ManifestPage(pageId=UUID(p), order=i, layout=True) for i, p in enumerate(pages)]))
    lines = [{"documentId": str(document_id), "chunkId": c["id"], "order": c["order"], "layoutStart": a,
              "reason": "exact" if a else "not_found", "params": PARAMS, "textSha256": text_sha(c["text"])}
             for c, a in zip(chunks, anchors)]
    write_atomically(plan_path(store, document_id), "".join(json.dumps(l) + "\n" for l in lines).encode())


async def test_anchor_writes_keep_text_and_vectors_and_are_repeatable(seeded_store, collection_names, corpus,
                                                                      tmp_path):
    names = collection_names.chunks_collection_name
    document = UUID(corpus.documents["chronicle"]["id"])
    chunks = sorted((c for c in corpus.chunks.values() if c["key"].startswith("chronicle_")), key=lambda c: c["order"])
    anchors = [{"pageId": c["start_page_id"], "lineId": f"r1-l{c['order']}", "offset": c["order"], "match": "exact"}
               for c in chunks]
    store = PageAssetStore(tmp_path / "assets")
    _plan(store, document, chunks, anchors)
    collection = seeded_store.collections.get(names)
    before = {c["id"]: await collection.query.fetch_object_by_id(UUID(c["id"]), include_vector=True) for c in chunks}
    await declare_layout_start(seeded_store, names)
    weaviate = WeaviateAnchors(seeded_store, names, with_anchor=True)

    async def anchors_run(name, write=True):
        summary = await run.run_anchors(store, [document], weaviate, write, 4, tmp_path / name, "test",
                                        progress=lambda m: None)
        return summary, json.loads((tmp_path / f"{name}.documents.jsonl").read_text())["counts"]

    check, counts = await anchors_run("check.json", write=False)
    assert counts == {"set": 3} and run.anchors_exit_code(check) == 1
    assert all(c.layout_start is None for c in await read_document_chunks(seeded_store, names, document, True))

    written, counts = await anchors_run("write.json")
    assert counts == {"set": 3, "write_failed": 0, "written": 3} and run.anchors_exit_code(written) == 0
    for c, anchor in zip(chunks, anchors):
        after = await collection.query.fetch_object_by_id(UUID(c["id"]), include_vector=True)
        old = before[c["id"]]
        assert after.properties["layoutStart"] == anchor
        assert {k: v for k, v in after.properties.items() if k != "layoutStart"} == old.properties
        assert after.vector == old.vector

    again, counts = await anchors_run("again.json")
    assert counts == {"unchanged": 3} and run.anchors_exit_code(again) == 0

    _plan(store, document, chunks, [anchors[0], None, anchors[2]])
    cleared, counts = await anchors_run("clear.json")
    assert counts == {"clear": 1, "unchanged": 2, "write_failed": 0, "written": 1}
    stored = {str(c.id): c.layout_start for c in await read_document_chunks(seeded_store, names, document, True)}
    assert stored[chunks[1]["id"]] is None and stored[chunks[0]["id"]] == anchors[0]
