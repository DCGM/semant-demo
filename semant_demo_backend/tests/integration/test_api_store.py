"""The HTTP application wired to the real test store and corpus users."""
import pytest

from tests.auth_support import auth_headers

pytestmark = pytest.mark.integration


async def login_as(api_client, corpus, key):
    user = corpus.users[key]
    return await auth_headers(api_client, user["username"], user["password"])


@pytest.mark.parametrize("user", ["owner", "annotator", "outsider", "admin"])
async def test_corpus_users_can_log_in(api_client, corpus, user):
    headers = await login_as(api_client, corpus, user)

    response = await api_client.get("/api/users/me", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["id"] == corpus.users[user]["id"]
    assert response.json()["is_superuser"] is corpus.users[user]["is_superuser"]


async def test_shared_user_lists_shared_collection(api_client, corpus):
    headers = await login_as(api_client, corpus, "annotator")

    response = await api_client.get("/api/user_collections", headers=headers)

    assert response.status_code == 200, response.text
    [collection] = response.json()
    assert collection["id"] == corpus.collections["chronicles"]["id"]
    assert collection["is_shared_with_me"] is True
    assert collection["owner"] == corpus.users["owner"]["name"]


async def test_document_view_data_for_collection(api_client, corpus):
    headers = await login_as(api_client, corpus, "owner")
    collection_id = corpus.collections["chronicles"]["id"]
    chunk = corpus.chunks["chronicle_1"]

    chunks = await api_client.get(
        f"/api/collections/{collection_id}/documents/{corpus.documents['chronicle']['id']}", headers=headers)
    spans = await api_client.post(
        "/api/tag_spans/batch", json={"chunk_ids": [chunk["id"]], "collection_id": collection_id}, headers=headers)

    assert chunks.status_code == 200, chunks.text
    assert [c["text"] for c in chunks.json()] == [chunk["text"], corpus.chunks["chronicle_2"]["text"]]
    assert spans.status_code == 200, spans.text
    assert {s["id"] for s in spans.json()[chunk["id"]]} == {
        corpus.spans["novak_manual"]["id"], corpus.spans["lhota_automatic"]["id"]}
