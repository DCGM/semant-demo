"""HTTP behavior of the document, tag and collection routes on the repositories (#202).

Error mapping (NotFoundError -> 404, InvalidRequestError -> 400), tag PATCH validation,
idempotent removal, and the SQL user lookups used by sharing and owner changes.
"""
import pytest

pytestmark = pytest.mark.integration

UNKNOWN = "5e3a0000-0000-4000-8000-00000000ffff"


@pytest.mark.parametrize("body", [{}, {"name": None}, {"name": None, "examples": None}],
                         ids=["empty", "null", "all-null"])
async def test_tag_patch_without_values_is_rejected(api_client, login, ids, store, body):
    before = await store.tag(ids.tag["person"])

    response = await api_client.patch(f"/api/tags/{ids.tag['person']}", headers=await login("owner"), json=body)

    assert response.status_code == 422
    assert await store.tag(ids.tag["person"]) == before


async def test_tag_patch_keeps_null_fields_and_drops_blank_examples(api_client, login, ids, corpus):
    response = await api_client.patch(f"/api/tags/{ids.tag['person']}", headers=await login("owner"),
                                      json={"name": None, "color": "#000000", "examples": ["Karel IV.", "  "]})

    assert response.status_code == 200, response.text
    tag = response.json()
    assert (tag["name"], tag["color"], tag["examples"]) == (corpus.tags["person"]["name"], "#000000", ["Karel IV."])


async def test_removing_a_chunk_twice_succeeds(api_client, login, ids, store):
    c, chunk = ids.col["chronicles"], ids.chunk["chronicle_1"]
    headers = await login("owner")

    responses = [await api_client.delete(f"/api/user_collection/{c}/chunks/{chunk}", headers=headers)
                 for _ in range(2)]

    assert [r.status_code for r in responses] == [200, 200]
    assert c not in await store.collections_of_chunk(chunk)


@pytest.mark.parametrize("method, path", [
    ("DELETE", "/api/user_collection/{c}/chunks/{unknown}"),
    ("POST", "/api/user_collection/{c}/chunks/{unknown}"),
    ("POST", "/api/collections/{c}/documents/{unknown}"),
    ("DELETE", "/api/collections/{c}/documents/{unknown}"),
    ("GET", "/api/document/{unknown}"),
    ("GET", "/api/document/not-a-uuid"),
    ("GET", "/api/documents/not-a-uuid/chunks/count"),
])
async def test_unknown_objects_are_not_found(api_client, login, ids, method, path):
    response = await api_client.request(method, path.format(c=ids.col["chronicles"], unknown=UNKNOWN),
                                        headers=await login("owner"))

    assert response.status_code == 404, response.text


async def test_public_document_reads(api_client, ids, corpus):
    document = await api_client.get(f"/api/document/{ids.doc['chronicle']}")
    count = await api_client.get(f"/api/documents/{ids.doc['chronicle']}/chunks/count")

    assert document.json()["title"] == corpus.documents["chronicle"]["properties"]["title"]
    assert count.json() == 3


async def test_sharing_looks_up_users_in_sql(api_client, login, ids, corpus):
    c = ids.col["newspapers"]
    headers = await login("owner")

    with_owner = await api_client.post(f"/api/collections/{c}/share", headers=headers,
                                       json={"user_id": ids.user["owner"]})
    with_unknown = await api_client.post(f"/api/collections/{c}/share", headers=headers, json={"user_id": UNKNOWN})
    shared = await api_client.post(f"/api/collections/{c}/share", headers=headers,
                                   json={"user_id": ids.user["outsider"]})
    members = await api_client.get(f"/api/collections/{c}/members", headers=headers)

    assert with_owner.status_code == 400
    assert with_unknown.status_code == 404
    assert shared.status_code == 200, shared.text
    assert members.json() == [{"id": ids.user["outsider"], "username": corpus.users["outsider"]["username"],
                               "name": corpus.users["outsider"]["name"]}]
    assert (await api_client.get(f"/api/user_collections/{c}", headers=await login("outsider"))).status_code == 200


async def test_admin_owner_change_to_unknown_user_is_not_found(api_client, login, ids, store):
    c = ids.col["newspapers"]
    before = await store.collection(c)

    response = await api_client.patch(f"/api/collections/{c}/owner", headers=await login("admin"),
                                      json={"user_id": UNKNOWN})

    assert response.status_code == 404
    assert await store.collection(c) == before


async def test_created_collection_is_owned_by_the_caller(api_client, login, corpus):
    headers = await login("annotator")

    created = await api_client.post("/api/user_collections", headers=headers,
                                    json={"name": "Moje", "description": None, "color": "green"})

    assert created.status_code == 201, created.text
    assert created.json()["owner"] == corpus.users["annotator"]["name"]
    listed = await api_client.get("/api/user_collections", headers=headers)
    assert created.json()["id"] in {c["id"] for c in listed.json()}
