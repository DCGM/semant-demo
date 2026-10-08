"""API models (#208): one OpenAPI component per concept and representative serialization.

The OpenAPI document is built without connecting to any service. Response serialization
goes through the real routes with stand-in repositories, so ``response_model`` and
``response_model_exclude_none`` are applied as in production.
"""
from datetime import datetime, timezone
from uuid import UUID

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from semant_demo.features.search.schemas import SearchRequest, SearchResponse, SummaryRequest, TextChunkWithDocument
from semant_demo.main import create_app
from semant_demo.routes.dependencies import get_documents
from semant_demo.schema.documents import Document, DocumentBrowse
from tests.app_support import make_test_config, offline_weaviate

DOC = UUID("5e3a0000-0000-4000-8000-00000000d002")
CHUNK = UUID("5e3a0000-0000-4000-8000-0000000d2c01")
PAGE = UUID("5e3a0000-0000-4000-8000-0000000d2f01")

# Properties as the store returns them: author is text[], url a uuid, dateIssued a datetime.
STORED = {
    "title": "Dopisy z Prahy", "author": ["Karel Pisatel", "Marie Pisatelová"], "yearIssued": 1902,
    "dateIssued": datetime(1902, 5, 1, tzinfo=timezone.utc), "url": PAGE, "partNumber": "2",
    "public": False, "editors": [],
}


def _ref(schema: dict) -> str:
    return schema["$ref"].rsplit("/", 1)[1]


def test_each_api_model_is_one_component(tmp_path):
    components = create_app(make_test_config(tmp_path)).openapi()["components"]["schemas"]

    # Name clashes give module-path names; differing request/response variants -Input/-Output.
    assert [name for name in components if "__" in name or name.endswith(("-Input", "-Output"))] == []


def test_every_document_read_uses_the_document_component(tmp_path):
    schema = create_app(make_test_config(tmp_path)).openapi()
    components = schema["components"]["schemas"]

    assert _ref(components["DocumentBrowse"]["properties"]["items"]["items"]) == "Document"
    assert _ref(components["DocumentDetail"]["properties"]["document"]) == "Document"
    assert _ref(components["TextChunkWithDocument"]["properties"]["document_object"]) == "Document"
    response = schema["paths"]["/api/document/{document_id}"]["get"]["responses"]["200"]
    assert _ref(response["content"]["application/json"]["schema"]) == "Document"
    assert components["Document"]["properties"]["author"]["anyOf"][0] == {"type": "array", "items": {"type": "string"}}


class _Documents:
    async def read(self, document_id):
        return Document(id=document_id, **STORED)

    async def browse(self, **kwargs):
        return DocumentBrowse(items=[Document(id=DOC, **STORED)], has_more=False, total_count=1)

    async def count_chunks(self, document_id):
        return 3 if document_id == DOC else 0


async def test_document_responses_serialize_stored_properties(tmp_path):
    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    app.dependency_overrides[get_documents] = _Documents
    expected = {
        "id": str(DOC), "title": "Dopisy z Prahy", "author": ["Karel Pisatel", "Marie Pisatelová"],
        "yearIssued": 1902, "dateIssued": "1902-05-01T00:00:00Z", "url": str(PAGE), "partNumber": "2",
        "public": False, "editors": [],
    }

    async with LifespanManager(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        document = await client.get(f"/api/document/{DOC}")
        browse = await client.get("/api/documents/browse")

    assert document.status_code == 200, document.text
    assert document.json() == expected  # absent properties stay absent
    assert browse.json()["items"] == [expected]


def test_chunk_count_keeps_its_public_contract(tmp_path):
    # Moved from the Collections router to the Documents feature in #210.
    operation = create_app(make_test_config(tmp_path)).openapi()["paths"]["/api/documents/{document_id}/chunks/count"]

    assert list(operation) == ["get"]
    assert operation["get"]["operationId"] == "count_document_chunks_api_documents__document_id__chunks_count_get"
    assert "security" not in operation["get"]
    assert [p["name"] for p in operation["get"]["parameters"]] == ["document_id"]
    assert operation["get"]["responses"]["200"]["content"]["application/json"]["schema"] == \
        {"type": "integer", "title": "Response Count Document Chunks Api Documents  Document Id  Chunks Count Get"}


async def test_chunk_count_is_answered_anonymously(tmp_path):
    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    app.dependency_overrides[get_documents] = _Documents

    async with LifespanManager(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        count = await client.get(f"/api/documents/{DOC}/chunks/count")
        malformed = await client.get("/api/documents/not-a-uuid/chunks/count")

    assert (count.status_code, count.json()) == (200, 3)
    assert malformed.status_code == 404


def test_search_response_is_accepted_back_as_summary_input():
    # The search page posts a search response to /api/summarize; both directions are one model.
    hit = TextChunkWithDocument(
        id=CHUNK, text="Milá Marie, píši Ti z Prahy.", start_page_id=PAGE, from_page=1, to_page=1,
        document=DOC, order=0, document_object=Document(id=DOC, library="mzk", **STORED))
    response = SearchResponse(
        results=[hit], search_request=SearchRequest(query="Praha", tag_uuids=[], positive=False, automatic=False),
        time_spent=0.1, search_log=[])

    wire = response.model_dump(mode="json")
    again = SummaryRequest.model_validate({"search_response": wire}).search_response

    assert wire["results"][0]["document_object"]["author"] == ["Karel Pisatel", "Marie Pisatelová"]
    assert again.model_dump(mode="json") == wire
