"""Text document upload (#785) over HTTP into the real test store.

An uploaded document is private (``public`` false): readable through its collection by the
owner and the shared user, with all its chunks, as text without pages; never by anyone
else, never without the collection, never in unscoped search. Its chunks carry their
positions, ``UNPROCESSED`` and both named vectors of the store, so collection-scoped vector
search finds them. A failed upload leaves a document that no reader shows.
"""
from uuid import UUID

import pytest
from weaviate.classes.query import Filter, QueryReference

from semant_demo.adapters.weaviate.search import ChunkSearchRepository
from semant_demo.features.documents.positions import chunk_positions
from semant_demo.features.search.schemas import ChunkQuery, SearchType
from semant_demo.features.search.vectors import SearchVector, SearchVectors
from semant_demo.routes.dependencies import get_search_vectors
from tests.fakes import SECOND_VECTOR, fake_embedding, second_embedding

pytestmark = pytest.mark.integration

TEXT = ("Kronika rodu Zahrádků.\n\nRoku 1925 se v obci Hradiště konala pouť a přijel cirkus Kludský.\n\n"
        + "Dlouhý odstavec o počasí, úrodě a cenách obilí na trhu v Hradišti. " * 30 + "\n\nKonec zápisu.\n")
WORD = "Kludský"


class _Embedder:
    def __init__(self, embed, fail=False):
        self.embed, self.fail = embed, fail

    async def embed_query(self, text):
        return self.embed(text)

    async def embed_document(self, text):
        return self.embed(text)

    async def embed_documents(self, texts):
        if self.fail:
            raise TimeoutError("embedding")
        return [self.embed(t) for t in texts]


@pytest.fixture
def vectors(api_app):
    """The store's two named vectors with the deterministic fake embeddings, approved for private text."""
    def install(fail=False):
        search_vectors = SearchVectors([
            SearchVector("main", "Main", "", "default", _Embedder(fake_embedding, fail), private_text=True),
            SearchVector("small", "Small", "", SECOND_VECTOR, _Embedder(second_embedding), private_text=True)],
            default="main")
        api_app.dependency_overrides[get_search_vectors] = lambda: search_vectors
    install()
    return install


async def _upload(api_client, headers, collection, files, metadata=None):
    parts = [("files", (name, data, "text/plain")) for name, data in files]
    if metadata is not None:
        parts.append(("metadata", ("metadata.csv", metadata, "text/csv")))
    return await api_client.post(f"/api/user_collections/{collection}/text_documents", headers=headers, files=parts)


async def _passages(api_client, headers, collection=None):
    body = {"criteria": {"text_query": WORD}, "type": "text", "limit": 50}
    if collection:
        body["user_collection_id"] = collection
    response = await api_client.post("/api/search/passages", headers=headers, json=body)
    assert response.status_code == 200, response.text
    return response.json()["ranked_ids"]


async def test_an_uploaded_document_is_private_complete_and_searchable_in_its_collection(
        api_client, login, ids, seeded_store, collection_names, vectors):
    owner, annotator, outsider = await login("owner"), await login("annotator"), await login("outsider")
    collection = ids.col["chronicles"]
    response = await _upload(api_client, owner, collection, [("Kronika Zahrádků.txt", TEXT.encode())],
                             "filename,author,yearIssued,language\nKronika Zahrádků.txt,Jan Zahrádka,1925,ces\n"
                             .encode())
    assert response.status_code == 200, response.text
    [result] = response.json()["files"]
    assert result["status"] == "completed", result
    document_id = result["document_id"]

    # Stored: private, the CSV metadata, ordered chunks with positions, UNPROCESSED and both vectors.
    stored = await seeded_store.collections.get(collection_names.document_collection_name).query.fetch_object_by_id(
        UUID(document_id))
    assert stored.properties["public"] is False and stored.properties["title"] == "Kronika Zahrádků"
    assert stored.properties["author"] == ["Jan Zahrádka"] and stored.properties["yearIssued"] == 1925
    chunks = (await seeded_store.collections.get(collection_names.chunks_collection_name).query.fetch_objects(
        filters=Filter.by_ref("document").by_id()
        .equal(UUID(document_id)), limit=100, include_vector=["default", SECOND_VECTOR])).objects
    chunks.sort(key=lambda o: o.properties["order"])
    assert len(chunks) == result["chunks"] > 1
    assert "".join(o.properties["text"] for o in chunks) == TEXT
    assert [o.properties["startChar"] for o in chunks] == [p.start_char for p in chunk_positions(
        o.properties["text"] for o in chunks)]
    assert {o.properties["classification_provenance"] for o in chunks} == {"UNPROCESSED"}
    assert {o.properties["yearIssued"] for o in chunks} == {1925}
    assert all(len(o.vector["default"]) == 16 and len(o.vector[SECOND_VECTOR]) == 8 for o in chunks)

    [match] = [o for o in chunks if WORD in o.properties["text"]]

    # Readable through the collection by its owner and shared user, as text without pages.
    for headers in (owner, annotator):
        listed = (await api_client.get(f"/api/user_collections/{collection}/documents", headers=headers)).json()
        assert document_id in {d["id"] for d in listed}
        read = await api_client.get(f"/api/user_collections/{collection}/documents/{document_id}/chunks",
                                    headers=headers)
        assert read.status_code == 200
        assert "".join(c["text"] for c in read.json()) == TEXT
        assert all("from_page" not in c and "start_page_id" not in c for c in read.json())
        meta = await api_client.get(f"/api/document/{document_id}?collection_id={collection}", headers=headers)
        assert meta.status_code == 200 and meta.json()["public"] is False
        window = await api_client.get(
            f"/api/documents/{document_id}/chunks/{chunks[1].uuid}/window?collection_id={collection}&before=1&after=1",
            headers=headers)
        assert window.status_code == 200 and window.json()["chunks"][0].get("start_page_id") is None
        pages = await api_client.get(f"/api/documents/{document_id}/pages?collection_id={collection}", headers=headers)
        assert pages.status_code == 200 and pages.json()["available"] is False
        assert str(match.uuid) in await _passages(api_client, headers, collection)

    # Nobody reads it without the collection, and others not at all.
    for headers in ({}, owner, annotator, outsider):
        assert (await api_client.get(f"/api/document/{document_id}", headers=headers)).status_code == 404
        assert str(match.uuid) not in await _passages(api_client, headers)
    for headers in ({}, outsider):
        response = await api_client.get(f"/api/document/{document_id}?collection_id={collection}", headers=headers)
        assert response.status_code in (401, 404)
    assert (await api_client.get(f"/api/document/{document_id}?collection_id={ids.col['outsider_notes']}",
                                 headers=outsider)).status_code == 404

    # Vector search finds a chunk by its own text's embedding only within the collection.
    search = ChunkSearchRepository(seeded_store, collection_names)
    text = chunks[1].properties["text"]
    for target, embed in (("default", fake_embedding), (SECOND_VECTOR, second_embedding)):
        query = dict(text=text, mode=SearchType.vector, limit=3, vector=embed(text), target_vector=target)
        scoped = await search.search(ChunkQuery(**query, document_collection_id=UUID(collection),
                                                readable_collection_id=UUID(collection)))
        assert scoped[0].id == chunks[1].uuid
        assert chunks[1].uuid not in {c.id for c in await search.search(ChunkQuery(**query))}


async def test_shared_users_and_outsiders_cannot_upload(api_client, login, ids, vectors):
    collection = ids.col["chronicles"]
    response = await _upload(api_client, await login("annotator"), collection, [("a.txt", b"x")])
    assert response.status_code == 403
    response = await _upload(api_client, await login("outsider"), collection, [("a.txt", b"x")])
    assert response.status_code == 404
    response = await _upload(api_client, {}, collection, [("a.txt", b"x")])
    assert response.status_code == 401
    listed = (await api_client.get(f"/api/user_collections/{collection}/documents", headers=await login("owner")))
    assert {d["id"] for d in listed.json()} == {ids.doc["chronicle"], ids.doc["letters"]}


async def test_a_failed_upload_is_reported_and_never_shown(api_client, login, ids, seeded_store, collection_names,
                                                           vectors):
    vectors(fail=True)
    owner = await login("owner")
    collection = ids.col["chronicles"]
    response = await _upload(api_client, owner, collection, [("a.txt", TEXT.encode())])
    [result] = response.json()["files"]
    assert result["status"] == "failed" and "upload the file again" in result["error"]

    stored = await seeded_store.collections.get(collection_names.document_collection_name).query.fetch_object_by_id(
        UUID(result["document_id"]), return_references=[
            QueryReference(link_on="collection")])
    assert stored.properties["public"] is False and not (stored.references or {}).get("collection")
    listed = (await api_client.get(f"/api/user_collections/{collection}/documents", headers=owner)).json()
    assert result["document_id"] not in {d["id"] for d in listed}
    read = await api_client.get(f"/api/document/{result['document_id']}?collection_id={collection}", headers=owner)
    assert read.status_code == 404
