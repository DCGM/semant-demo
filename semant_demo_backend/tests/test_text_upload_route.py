"""The text upload route (#785): authentication, the access check before the body is read,
size limits, multipart parsing and the response contract."""
from uuid import UUID, uuid4

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from semant_demo.features.search.vectors import SearchVector, SearchVectors
from semant_demo.main import create_app
from semant_demo.routes.dependencies import get_search_vectors, get_text_upload_store, get_user_collections
from tests.app_support import make_test_config, offline_weaviate
from tests.auth_support import auth_headers, register
from semant_demo.adapters.weaviate.text_upload import UploadSchema
from tests.test_text_upload import SCHEMA, Embedder, Store

URL = "/api/user_collections/{}/text_documents"
OWNER = {"email": "owner@example.com", "password": "OwnerPass1!", "username": "owner"}
OTHER = {"email": "other@example.com", "password": "OtherPass1!", "username": "other"}
COLLECTION = uuid4()


class Collections:
    link = "userCollection"

    def __init__(self, store):
        self.store = store
        self.owner: UUID | None = None

    async def read_access_record(self, cid):
        return (self.owner, set()) if cid == COLLECTION else None

    async def document_in_collection(self, document_id, cid):
        return cid in self.store.documents.get(document_id, {}).get("collections", set())


@pytest.fixture
async def setup(tmp_path):
    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    store = Store()
    collections = Collections(store)
    vectors = SearchVectors([SearchVector("main", "Main", "", "default", Embedder(), private_text=True),
                             SearchVector("small", "Small", "", "second", Embedder(dim=2), private_text=True)],
                            default="main")
    app.dependency_overrides[get_user_collections] = lambda: collections
    app.dependency_overrides[get_text_upload_store] = lambda: store
    app.dependency_overrides[get_search_vectors] = lambda: vectors
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for user in (OWNER, OTHER):
                assert (await register(client, **user)).status_code == 201
            owner = await auth_headers(client, OWNER["email"], OWNER["password"])
            other = await auth_headers(client, OTHER["email"], OTHER["password"])
            collections.owner = UUID((await client.get("/api/users/me", headers=owner)).json()["id"])
            yield client, store, owner, other


async def test_the_owner_uploads_files_with_metadata(setup):
    client, store, owner, _ = setup
    response = await client.post(URL.format(COLLECTION), headers=owner, files=[
        ("files", ("Kronika.txt", "Kronika obce.\n\nDruhý odstavec.".encode(), "text/plain")),
        ("files", ("b.txt", b"Second file.", "text/plain")),
        ("metadata", ("meta.csv", b"filename,title,yearIssued\nKronika.txt,Kronika obce Lhota,1925\n", "text/csv")),
    ])
    assert response.status_code == 200, response.text
    body = response.json()
    assert [(f["filename"], f["status"], f["title"]) for f in body["files"]] == [
        ("Kronika.txt", "completed", "Kronika obce Lhota"), ("b.txt", "completed", "b")]
    assert body["errors"] == []
    document = store.documents[UUID(body["files"][0]["document_id"])]
    assert document["properties"]["public"] is False and document["collections"] == {COLLECTION}


async def test_an_invalid_upload_is_reported_per_file(setup):
    client, store, owner, _ = setup
    response = await client.post(URL.format(COLLECTION), headers=owner, files=[
        ("files", ("a.txt", b"ok", "text/plain")), ("files", ("b.pdf", b"%PDF", "application/pdf"))])
    assert response.status_code == 200
    assert [f["status"] for f in response.json()["files"]] == ["not_written", "invalid"]
    assert not store.documents


async def test_anonymous_users_are_refused(setup):
    client, store, _, _ = setup
    response = await client.post(URL.format(COLLECTION), files=[("files", ("a.txt", b"x", "text/plain"))])
    assert response.status_code == 401 and not store.calls


async def test_other_users_get_not_found_before_the_body_is_read(setup):
    client, store, _, other = setup
    response = await client.post(URL.format(COLLECTION), headers=other,
                                 files=[("files", ("a.txt", b"x", "text/plain"))])
    assert response.status_code == 404 and not store.calls


async def test_a_too_large_request_is_refused_before_it_is_parsed(setup):
    client, store, owner, _ = setup
    body = b"--x\r\n" + b"0" * 100
    response = await client.post(URL.format(COLLECTION), content=body, headers={
        **owner, "Content-Type": "multipart/form-data; boundary=x", "Content-Length": str(25_000_000)})
    assert response.status_code == 413
    assert "create_document" not in store.calls and not store.documents


async def test_a_body_that_is_not_multipart_is_refused(setup):
    client, store, owner, _ = setup
    response = await client.post(URL.format(COLLECTION), headers=owner, json={"files": []})
    assert response.status_code == 400 and not store.documents


TXT = ("files", ("a.txt", b"ok", "text/plain"))
CSV = ("metadata", ("meta.csv", b"filename,title\na.txt,A\n", "text/csv"))


@pytest.mark.parametrize("parts, data, problem", [
    ([TXT], {"metadata": "filename,title\na.txt,A\n"}, "must be a CSV file"),
    ([TXT, CSV, ("metadata", ("other.csv", b"filename\n", "text/csv"))], None, "at most one 'metadata'"),
    ([TXT], {"files": "a text field"}, "Every 'files' part must be a file"),
    ([TXT, ("meta", ("meta.csv", b"filename\n", "text/csv"))], None, "Unexpected form part(s): meta"),
], ids=["metadata-as-text-field", "two-metadata-files", "files-as-text-field", "unknown-part"])
async def test_malformed_parts_are_refused_before_anything_is_written(setup, parts, data, problem):
    client, store, owner, _ = setup
    response = await client.post(URL.format(COLLECTION), headers=owner, files=parts, data=data)
    assert response.status_code == 400 and problem in response.json()["detail"]
    assert "create_document" not in store.calls and not store.documents


async def test_availability_is_answered_without_the_store_details(setup):
    client, store, _, _ = setup
    assert (await client.get("/api/text_documents/availability")).json() == {"available": True}
    store.schema_value = UploadSchema(SCHEMA.document_properties, SCHEMA.document_references, SCHEMA.chunk_properties,
                                      SCHEMA.chunk_references, frozenset({"default"}))
    response = await client.get("/api/text_documents/availability")
    assert response.status_code == 200 and response.json() == {
        "available": False, "message": "Uploading documents is not available: the database does not support it yet."}
    assert "create_document" not in store.calls


def test_the_operation_declares_the_multipart_body(openapi_schema):
    operation = openapi_schema["paths"]["/api/user_collections/{collection_id}/text_documents"]["post"]
    schema = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert schema["required"] == ["files"] and set(schema["properties"]) == {"files", "metadata"}
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("TextUploadResponse")
