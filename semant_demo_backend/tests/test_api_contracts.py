"""API models (#208): one OpenAPI component per concept and representative serialization.

The OpenAPI document is built without connecting to any service. Response serialization
goes through the real routes with stand-in repositories, so ``response_model`` and
``response_model_exclude_none`` are applied as in production.
"""
from datetime import datetime, timezone
from uuid import UUID

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from semant_demo.features.search.schemas import SearchRequest, SearchResponse, SearchResultChunk
from semant_demo.features.summarization.schemas import SummaryRequest
from semant_demo.main import create_app
from semant_demo.routes.dependencies import get_documents
from semant_demo.features.documents.schemas import DocumentChunk, Document, DocumentBrowse
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
    assert _ref(components["SearchResultChunk"]["properties"]["document_object"]) == "Document"
    response = schema["paths"]["/api/document/{document_id}"]["get"]["responses"]["200"]
    assert _ref(response["content"]["application/json"]["schema"]) == "Document"
    assert components["Document"]["properties"]["author"]["anyOf"][0] == {"type": "array", "items": {"type": "string"}}


def test_chunk_projections_keep_their_names_and_wire_properties(tmp_path):
    """#284: each chunk read has its own owner-named component; renaming kept the wire fields."""
    schema = create_app(make_test_config(tmp_path)).openapi()
    components = schema["components"]["schemas"]
    stored = {"id", "text", "start_page_id", "from_page", "to_page", "document", "title", "end_paragraph",
              "language", "order", "ner_P", "ner_T", "ner_A", "ner_G", "ner_I", "ner_M", "ner_O"}

    assert {"TextChunk", "Chunk", "TextChunkWithDocument", "DocumentDetailTextChunkWithUserCollectionInfo"}.isdisjoint(components)
    assert set(components["DocumentChunk"]["properties"]) == stored
    assert set(components["DocumentViewChunk"]["properties"]) == stored | {"in_user_collection"}
    assert set(components["SearchResultChunk"]["properties"]) == stored | {
        "query_title", "query_summary", "summary", "document_object", "metadata"}
    assert set(components["CollectionChunk"]["properties"]) == {
        "id", "text", "start_page_id", "from_page", "to_page", "end_paragraph", "title", "language", "order",
        "in_collection"}
    assert _ref(components["DocumentDetail"]["properties"]["chunks"]["items"]) == "DocumentViewChunk"
    assert _ref(components["DocumentChunkWindow"]["properties"]["chunks"]["items"]) == "DocumentChunk"
    assert _ref(components["SearchResponse"]["properties"]["results"]["items"]) == "SearchResultChunk"
    collection_chunks = schema["paths"]["/api/user_collections/{collection_id}/documents/{document_id}/chunks"]["get"]
    assert _ref(collection_chunks["responses"]["200"]["content"]["application/json"]["schema"]["items"]) == "CollectionChunk"


class _Documents:
    async def read(self, document_id):
        return Document(id=document_id, **STORED)

    async def browse(self, **kwargs):
        return DocumentBrowse(items=[Document(id=DOC, **STORED)], has_more=False, total_count=1)

    async def count_chunks(self, document_id):
        return 3 if document_id == DOC else 0

    async def read_chunk(self, chunk_id):
        return _hit_chunk() if chunk_id == CHUNK else None

    async def read_adjacent_chunks(self, document_id, order, direction, limit):
        return []


USER_COLLECTION_ROUTES = {
    ("get", "/api/user_collections"),
    ("post", "/api/user_collections"),
    ("get", "/api/user_collections/{collection_id}"),
    ("patch", "/api/user_collections/{collection_id}"),
    ("delete", "/api/user_collections/{collection_id}"),
    ("patch", "/api/user_collections/{collection_id}/owner"),
    ("post", "/api/user_collections/{collection_id}/share"),
    ("delete", "/api/user_collections/{collection_id}/share/{user_id}"),
    ("get", "/api/user_collections/{collection_id}/members"),
    ("get", "/api/user_collections/{collection_id}/people"),
    ("get", "/api/user_collections/{collection_id}/stats"),
    ("get", "/api/user_collections/{collection_id}/tags"),
    ("get", "/api/user_collections/{collection_id}/annotations"),
    ("get", "/api/user_collections/{collection_id}/annotations/documents"),
    ("get", "/api/user_collections/{collection_id}/annotations/counts"),
    ("post", "/api/user_collections/{collection_id}/annotations/ids"),
    ("post", "/api/user_collections/{collection_id}/annotations/review"),
    ("post", "/api/user_collections/{collection_id}/annotations/restore"),
    ("post", "/api/user_collections/{collection_id}/annotations/chunk-tags/sync"),
    ("post", "/api/user_collections/{collection_id}/chunks/{chunk_id}"),
    ("delete", "/api/user_collections/{collection_id}/chunks/{chunk_id}"),
    ("get", "/api/user_collections/{collection_id}/documents"),
    ("get", "/api/user_collections/{collection_id}/documents/{document_id}"),
    ("post", "/api/user_collections/{collection_id}/documents/{document_id}"),
    ("delete", "/api/user_collections/{collection_id}/documents/{document_id}"),
    ("post", "/api/user_collections/{collection_id}/documents/{document_id}/summary"),
    ("get", "/api/user_collections/{collection_id}/documents/{document_id}/stats"),
    ("get", "/api/user_collections/{collection_id}/documents/{document_id}/chunks"),
    ("get", "/api/user_collections/{collection_id}/documents/{document_id}/chunks/range"),
    ("get", "/api/user_collections/{collection_id}/documents/{document_id}/chunks/neighbour"),
}


def test_collection_routes_are_one_route_family(tmp_path):
    """#287: collection-scoped routes live under /api/user_collections only; old aliases are gone."""
    paths = create_app(make_test_config(tmp_path)).openapi()["paths"]
    routes = {(method, path) for path, operations in paths.items() for method in operations}

    assert {r for r in routes if r[1].startswith("/api/user_collections")} == USER_COLLECTION_ROUTES
    assert [path for path in paths if "{collection_id}" in path and not path.startswith("/api/user_collections/")] == []
    assert [path for path in paths if path.startswith(("/api/collections", "/api/user_collection/"))] == []


def _hit_chunk() -> DocumentChunk:
    return DocumentChunk(id=CHUNK, text="Milá Marie, píši Ti z Prahy.", start_page_id=PAGE, from_page=1, to_page=1,
                     document=DOC, order=0)


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


async def test_chunk_window_is_answered_anonymously_and_bounded(tmp_path):
    # #244: the search page shows a hit in its document context without a login.
    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    app.dependency_overrides[get_documents] = _Documents
    path = f"/api/documents/{DOC}/chunks/{CHUNK}/window"

    async with LifespanManager(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        window = await client.get(path, params={"before": 2, "after": 2})
        too_wide = await client.get(path, params={"before": 51})
        unknown = await client.get(f"/api/documents/{DOC}/chunks/{PAGE}/window")

    assert window.status_code == 200, window.text
    body = window.json()
    assert ([c["id"] for c in body["chunks"]], body["anchor_chunk_id"]) == ([str(CHUNK)], str(CHUNK))
    assert (body["has_before"], body["has_after"], body["total_chunks"]) == (False, False, 3)
    assert body["document"]["title"] == "Dopisy z Prahy"
    assert too_wide.status_code == 422
    assert unknown.status_code == 404


async def test_adjacent_chunks_are_answered_anonymously_and_validated(tmp_path):
    # #244: extending a passage reads only the neighbours.
    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    app.dependency_overrides[get_documents] = _Documents
    path = f"/api/documents/{DOC}/chunks/{CHUNK}/adjacent"

    async with LifespanManager(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        adjacent = await client.get(path, params={"direction": "after", "limit": 5})
        sideways = await client.get(path, params={"direction": "sideways"})
        too_many = await client.get(path, params={"direction": "before", "limit": 51})

    assert (adjacent.status_code, adjacent.json()) == (200, {"chunks": [], "has_more": False})
    assert (sideways.status_code, too_many.status_code) == (422, 422)


def test_search_response_is_accepted_back_as_summary_input():
    # The search page posts a search response to /api/summarize; both directions are one model.
    hit = SearchResultChunk(
        id=CHUNK, text="Milá Marie, píši Ti z Prahy.", start_page_id=PAGE, from_page=1, to_page=1,
        document=DOC, order=0, document_object=Document(id=DOC, library="mzk", **STORED))
    response = SearchResponse(
        results=[hit], search_request=SearchRequest(query="Praha", tag_uuids=[], positive=False, automatic=False),
        time_spent=0.1, search_log=[])

    wire = response.model_dump(mode="json")
    again = SummaryRequest.model_validate({"search_response": wire}).search_response

    assert wire["results"][0]["document_object"]["author"] == ["Karel Pisatel", "Marie Pisatelová"]
    assert again.model_dump(mode="json") == wire


def test_search_hit_classifications_are_optional_and_round_trip(tmp_path):
    hit_schema = create_app(make_test_config(tmp_path)).openapi()["components"]["schemas"]["SearchResultChunk"]
    assert "metadata" not in hit_schema.get("required", [])
    assert hit_schema["properties"]["metadata"]["additionalProperties"] == {"type": "array", "items": {"type": "string"}}

    hit = SearchResultChunk(
        id=CHUNK, text="Milá Marie.", start_page_id=PAGE, from_page=1, to_page=1, document=DOC, order=0,
        document_object=Document(id=DOC, **STORED), metadata={"style": ["informal", "literary"]})
    wire = hit.model_dump(mode="json")
    assert SearchResultChunk.model_validate(wire).metadata == {"style": ["informal", "literary"]}

    # A client that does not know the field (e.g. an older search page posting results back).
    del wire["metadata"]
    assert SearchResultChunk.model_validate(wire).metadata == {}
