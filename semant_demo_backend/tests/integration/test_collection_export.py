"""Collection export against real Weaviate (#656, docs/EXPORT_FORMAT.md).

Through the API: a ticket is requested for collections the user can read, the ZIP is
downloaded once with it, and every annotation can be cut from the exported chunks, also one
that continues into a chunk outside the collection.
"""
import io
import json
import zipfile

import pytest

from semant_demo.features.documents.positions import text_length

pytestmark = pytest.mark.integration


def _cut(chunks_by_id: dict, chunks_by_order: dict, annotation: dict) -> str:
    """The annotation's text from the exported chunks (UTF-16 offsets, continuing by order)."""
    anchor = chunks_by_id[annotation["chunk_id"]]
    text, order = anchor["text"], anchor["order"]
    while text_length(text) < annotation["end"]:
        order += 1
        text += chunks_by_order[(anchor["document_id"], order)]["text"]
    units = text.encode("utf-16-le")
    return units[2 * annotation["start"]:2 * annotation["end"]].decode("utf-16-le")


async def _export(api_client, headers, collection_ids) -> zipfile.ZipFile:
    ticket = await api_client.post("/api/exports/collections", headers=headers,
                                   json={"collection_ids": collection_ids})
    assert ticket.status_code == 200, ticket.text
    response = await api_client.get(ticket.json()["download_path"])
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"].startswith('attachment; filename="semant-export-')
    return zipfile.ZipFile(io.BytesIO(response.content))


async def test_export_holds_every_annotation_and_the_text_to_cut_it(api_client, login, ids, corpus):
    owner = await login("owner")
    chronicles = ids.col["chronicles"]
    # A span from the end of chronicle_2 (in the collection) into chronicle_3 (not in it).
    second = corpus.chunks["chronicle_2"]["text"]
    crossing = await api_client.post("/api/tag_spans", headers=owner, json={
        "chunkId": ids.chunk["chronicle_2"], "tagId": ids.tag["person"], "type": "auto",
        "start": text_length(second) - len("odjel ráno."), "end": text_length(second) + len("Požár")})
    assert crossing.status_code in (200, 201), crossing.text
    crossing_id = crossing.json()["id"]

    archive = await _export(api_client, owner, [chronicles, ids.col["newspapers"]])

    manifest = json.loads(archive.read("manifest.json"))
    # Every entry is dated at the export (zipfile would date a bare name 1980).
    assert {info.date_time[0] for info in archive.infolist()} == {int(manifest["exported_at"][:4])}
    assert manifest["format_version"] == 1
    assert manifest["exported_by"]["id"] == ids.user["owner"]
    assert [c["id"] for c in manifest["collections"]] == [chronicles, ids.col["newspapers"]]
    assert sorted(archive.namelist()) == sorted(["manifest.json", *(c["file"] for c in manifest["collections"])])

    entry = manifest["collections"][0]
    data = json.loads(archive.read(entry["file"]))
    assert set(data) == {"metadata", "tags", "attributes", "annotations", "chunks", "people"}
    assert (entry["annotations"], entry["chunks"]) == (len(data["annotations"]), len(data["chunks"]))
    assert (entry["missing_chunks"], entry["broken_continuations"]) == (0, 0)
    assert data["metadata"]["id"] == chronicles
    assert {t["id"] for t in data["tags"]} == {ids.tag["person"], ids.tag["place"]}

    chunks = {c["id"]: c for c in data["chunks"]}
    by_order = {(c["document_id"], c["order"]): c for c in data["chunks"]}
    assert chunks[ids.chunk["chronicle_1"]]["in_collection"] is True
    assert chunks[ids.chunk["chronicle_3"]]["in_collection"] is False  # only continued into
    assert chunks[ids.chunk["chronicle_3"]]["document_id"] == ids.doc["chronicle"]

    annotations = {a["id"]: a for a in data["annotations"]}
    seeded = {s["id"]: s for s in corpus.spans.values() if corpus.tags[s["tag"]]["collection"] == "chronicles"}
    assert set(annotations) == {*seeded, crossing_id}
    for span_id, span in seeded.items():
        assert annotations[span_id]["type"] == span["type"]
        assert _cut(chunks, by_order, annotations[span_id]) == span["quote"]
    assert {a["type"] for a in annotations.values()} == {"pos", "neg", "auto"}
    assert _cut(chunks, by_order, annotations[crossing_id]) == "odjel ráno.Požár"

    created = annotations[crossing_id]
    assert (created["origin"], created["created_by"], created["edit_version"]) == ("manual", ids.user["owner"], 0)
    assert created["tag_id"] == ids.tag["person"] and created["attributes"] == {}
    assert "text" not in created and "leftContext" not in created

    people = {p["id"]: p for p in data["people"]}
    assert people[ids.user["owner"]]["role"] == "owner"
    assert (people[ids.user["annotator"]]["role"], people[ids.user["annotator"]]["username"]) == ("member", "annotator")

    # The second collection: its own chunks and annotations.
    newspapers = json.loads(archive.read(manifest["collections"][1]["file"]))
    assert {a["id"] for a in newspapers["annotations"]} == {ids.span["pozar_manual"]}
    assert all(c["in_collection"] for c in newspapers["chunks"])


async def test_export_needs_read_access_and_a_ticket_is_used_once(api_client, login, ids):
    owner, annotator, outsider = await login("owner"), await login("annotator"), await login("outsider")
    chronicles = ids.col["chronicles"]
    body = {"collection_ids": [chronicles]}

    assert (await api_client.post("/api/exports/collections", json=body)).status_code == 401
    refused = await api_client.post("/api/exports/collections", headers=outsider, json=body)
    assert refused.status_code == 404
    # Readable for a member; one collection the user cannot read refuses the whole export.
    mixed = await api_client.post("/api/exports/collections", headers=annotator,
                                  json={"collection_ids": [chronicles, ids.col["outsider_notes"]]})
    assert mixed.status_code == 404

    path = (await api_client.post("/api/exports/collections", headers=annotator, json=body)).json()["download_path"]
    assert (await api_client.get(path)).status_code == 200
    assert (await api_client.get(path)).status_code == 404  # used
    assert (await api_client.get("/api/exports/collections/not-a-ticket")).status_code == 404

    # The download finished, so the next export of the same user may start; an unused ticket
    # is replaced by a newer one.
    first = (await api_client.post("/api/exports/collections", headers=owner, json=body)).json()["download_path"]
    second = (await api_client.post("/api/exports/collections", headers=owner, json=body)).json()["download_path"]
    assert (await api_client.get(first)).status_code == 404
    assert (await api_client.get(second)).status_code == 200


async def test_access_is_checked_again_when_the_download_starts(api_client, login, ids):
    owner, annotator = await login("owner"), await login("annotator")
    chronicles = ids.col["chronicles"]
    path = (await api_client.post("/api/exports/collections", headers=annotator,
                                  json={"collection_ids": [chronicles]})).json()["download_path"]
    unshared = await api_client.delete(f"/api/user_collections/{chronicles}/share/{ids.user['annotator']}",
                                       headers=owner)
    assert unshared.status_code in (200, 204)
    assert (await api_client.get(path)).status_code == 404
    # The refused download does not leave the user's export running.
    again = await api_client.post("/api/exports/collections", headers=owner, json={"collection_ids": [chronicles]})
    assert again.status_code == 200
