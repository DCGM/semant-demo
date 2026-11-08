"""API models (#208): one OpenAPI component per concept and representative serialization.

The OpenAPI document is built without connecting to any service. Response serialization
goes through the real routes with stand-in repositories, so ``response_model`` and
``response_model_exclude_none`` are applied as in production.
"""
from datetime import datetime, timezone
from uuid import UUID

from asgi_lifespan import LifespanManager
import pytest
from httpx import ASGITransport, AsyncClient

from semant_demo.config import MAX_PASSAGES_LIMIT, MAX_QUERY_RESULTS
from semant_demo.features.documents.criteria import NumberRange
from semant_demo.features.search.schemas import SearchRequest, SearchResponse, SearchResultChunk
from semant_demo.features.summarization.schemas import SummaryRequest
from semant_demo.main import create_app
from semant_demo.features.search.service import SearchBackends
from semant_demo.features.search.vectors import SearchVector, SearchVectors
from semant_demo.routes.dependencies import get_documents, get_search_backends
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
    """#284: each chunk read has its own owner-named component; renaming kept the wire fields.
    #541 added the optional ``layoutStart`` to the corpus and collection chunks."""
    schema = create_app(make_test_config(tmp_path)).openapi()
    components = schema["components"]["schemas"]
    stored = {"id", "text", "start_page_id", "from_page", "to_page", "document", "title", "end_paragraph",
              "language", "order", "layoutStart", "ner_P", "ner_T", "ner_A", "ner_G", "ner_I", "ner_M", "ner_O"}

    assert {"TextChunk", "Chunk", "TextChunkWithDocument", "DocumentDetailTextChunkWithUserCollectionInfo"}.isdisjoint(components)
    assert set(components["DocumentChunk"]["properties"]) == stored
    assert set(components["DocumentViewChunk"]["properties"]) == stored | {"in_user_collection"}
    assert set(components["SearchResultChunk"]["properties"]) == stored | {
        "query_title", "query_summary", "summary", "document_object", "metadata", "origin"}
    assert set(components["CollectionChunk"]["properties"]) == {
        "id", "text", "start_page_id", "from_page", "to_page", "end_paragraph", "title", "language", "order",
        "in_collection", "layoutStart"}
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
    ("get", "/api/user_collections/{collection_id}/attributes"),
    ("post", "/api/user_collections/{collection_id}/attributes"),
    ("patch", "/api/user_collections/{collection_id}/attributes/{attribute_id}"),
    ("delete", "/api/user_collections/{collection_id}/attributes/{attribute_id}"),
    ("post", "/api/user_collections/{collection_id}/attributes/{attribute_id}/values"),
    ("patch", "/api/user_collections/{collection_id}/attributes/{attribute_id}/values/{value_id}"),
    ("delete", "/api/user_collections/{collection_id}/attributes/{attribute_id}/values/{value_id}"),
    ("post", "/api/user_collections/{collection_id}/annotations/attributes/assign"),
    ("get", "/api/user_collections/{collection_id}/annotations/{annotation_id}/attribute-changes"),
    ("post", "/api/user_collections/{collection_id}/chunks/{chunk_id}"),
    ("delete", "/api/user_collections/{collection_id}/chunks/{chunk_id}"),
    ("get", "/api/user_collections/{collection_id}/documents"),
    ("get", "/api/user_collections/{collection_id}/documents/{document_id}"),
    ("post", "/api/user_collections/{collection_id}/documents/{document_id}"),
    ("delete", "/api/user_collections/{collection_id}/documents/{document_id}"),
    ("post", "/api/user_collections/{collection_id}/documents/{document_id}/summary"),
    ("post", "/api/user_collections/{collection_id}/documents/{document_id}/chat"),
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


class _RecordingDocuments(_Documents):
    calls: list[dict] = []

    async def browse(self, **kwargs):
        self.calls.append(kwargs)
        return await super().browse(**kwargs)


async def _browse(tmp_path, params):
    _RecordingDocuments.calls = []
    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    app.dependency_overrides[get_documents] = _RecordingDocuments
    async with LifespanManager(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get("/api/documents/browse", params=params)


async def test_browse_applies_chunk_filters_per_dimension(tmp_path):
    response = await _browse(tmp_path, [("chunk_languages", "CES"), ("chunk_classifications", "complexity:easy"),
                                        ("chunk_classifications", "complexity:moderate"), ("year_min", "1900")])

    assert response.status_code == 200, response.text
    [call] = _RecordingDocuments.calls
    year, language, complexity = call["conditions"]
    assert year == NumberRange("yearIssued", 1900, None)
    assert (language.prop, language.values) == ("chunk_language", ("ces",))  # the configured spelling
    assert (complexity.prop, complexity.values) == ("chunk_complexity", ("easy", "moderate"))


@pytest.mark.parametrize("params, message", [
    ({"chunk_languages": "Czech"}, "'Czech' is not a valid option for 'languages'"),
    ({"chunk_classifications": "emotion:calm"}, "'emotion' is not a configured classification"),
])
async def test_browse_rejects_unconfigured_chunk_filters(tmp_path, params, message):
    response = await _browse(tmp_path, params)

    assert response.status_code == 400, response.text
    assert message in response.json()["detail"]
    assert _RecordingDocuments.calls == []


@pytest.mark.parametrize("params, field", [
    ({"chunk_classifications": "complexity"}, "chunk_classifications"),
    ({"chunk_classifications": ":easy"}, "chunk_classifications"),
    ({"chunk_languages": " "}, "chunk_languages"),
])
async def test_browse_rejects_malformed_chunk_filters(tmp_path, params, field):
    response = await _browse(tmp_path, params)

    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"][:2] == ["query", field]
    assert _RecordingDocuments.calls == []


async def test_browse_without_chunk_filters_is_unchanged(tmp_path):
    response = await _browse(tmp_path, {"limit": 5})

    assert response.status_code == 200, response.text
    assert len(_RecordingDocuments.calls) == 1


def test_browse_documents_its_chunk_filter_parameters(tmp_path):
    operation = create_app(make_test_config(tmp_path)).openapi()["paths"]["/api/documents/browse"]["get"]
    parameters = {p["name"]: p for p in operation["parameters"]}

    assert parameters["chunk_languages"]["schema"]["type"] == "array"
    assert parameters["chunk_classifications"]["schema"]["type"] == "array"
    assert "<classification>:<value>" in operation["description"]


class _PassageChunks:
    """Three ranked hits; records the queries and the scopes of the reads."""
    queries: list = []
    reads: list = []
    hits = [SearchResultChunk(id=UUID(int=i + 1), text=f"Milá Marie {i}.", start_page_id=PAGE, from_page=1, to_page=1,
                              document=DOC, order=i, document_object=Document(id=DOC, **STORED)) for i in range(3)]

    async def ranked_ids(self, query):
        self.queries.append(query)
        return [h.id for h in self.hits[:query.limit]]

    async def read_hits(self, ids, scope):
        self.reads.append(scope)
        return [h for h in self.hits if h.id in ids]


async def _passages(tmp_path, body, path="/api/search/passages", **config):
    _PassageChunks.queries, _PassageChunks.reads = [], []
    app = create_app(make_test_config(tmp_path, **config), weaviate_connector=offline_weaviate)
    vectors = SearchVectors([SearchVector("main", "Main", "", "default", None)], default="main")
    app.dependency_overrides[get_search_backends] = lambda: SearchBackends(
        chunks=_PassageChunks(), collections=None, tags=None, vectors=vectors)
    async with LifespanManager(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(path, json=body)


async def test_passages_answer_a_page_with_its_coverage_anonymously(tmp_path):
    response = await _passages(tmp_path, {"criteria": {"text_query": "Marie", "chunk_filters": {"languages": ["CES"]}},
                                          "type": "text", "limit": 1}, SEARCH_PASSAGES_LIMIT="2")

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["text"] for item in body["items"]] == ["Milá Marie 0."]
    assert body["items"][0]["document_object"]["title"] == "Dopisy z Prahy"
    # The limit of 2 cut the three matches: bounded; the first page is one of the two ranked.
    assert body["ranked_ids"] == [str(UUID(int=1)), str(UUID(int=2))]
    assert {k: body[k] for k in ("read_count", "retrieval_limit", "bounded", "total_count")} == {
        "read_count": 1, "retrieval_limit": 2, "bounded": True, "total_count": None}
    assert body["criteria"]["chunk_filters"] == {"languages": ["ces"], "classifications": {}}
    assert body["vector"] is None


@pytest.mark.parametrize("body, status", [
    ({"criteria": {"text_query": " "}}, 422),                                       # filter-only is deferred
    ({"criteria": {"document_filters": {"year_min": 1900}}}, 422),
    ({"criteria": {"text_query": "Marie"}, "limit": 101}, 422),                     # page size
    ({"criteria": {"text_query": "Marie"}, "limit": 0}, 422),
    ({"criteria": {"text_query": "Marie"}, "offset": 20}, 422),                     # pages are read by id (#611)
    ({"criteria": {"text_query": "Marie"}, "query": "Marie"}, 422),                 # not the /api/search request
    ({"criteria": {"text_query": "Marie", "chunk_filters": {"languages": ["Czech"]}}}, 400),
])
async def test_invalid_passage_requests_are_refused_before_retrieval(tmp_path, body, status):
    response = await _passages(tmp_path, {"type": "text", **body})

    assert response.status_code == status, response.text
    assert _PassageChunks.queries == []


@pytest.mark.parametrize("value", ["0", "10000", "many"])
def test_the_passage_retrieval_limit_is_validated_at_startup(tmp_path, value):
    # 10000 is Weaviate's QUERY_MAXIMUM_RESULTS; a search ranks limit + 1 passages (#608 review).
    with pytest.raises(ValueError):
        make_test_config(tmp_path, SEARCH_PASSAGES_LIMIT=value)


def test_the_largest_passage_retrieval_limit_ranks_within_the_query_maximum(tmp_path):
    assert make_test_config(tmp_path, SEARCH_PASSAGES_LIMIT=str(MAX_PASSAGES_LIMIT)).SEARCH_PASSAGES_LIMIT == 9999


async def test_a_later_passage_page_is_read_by_id_without_ranking(tmp_path):
    ids = [str(UUID(int=3)), str(UUID(int=1))]
    response = await _passages(tmp_path, {"ids": ids, "criteria": {"text_query": "Marie",
                                                                   "chunk_filters": {"languages": ["CES"]}}},
                               path="/api/search/passages/read")

    assert response.status_code == 200, response.text
    assert [item["text"] for item in response.json()["items"]] == ["Milá Marie 0.", "Milá Marie 2."]
    assert _PassageChunks.queries == []
    [scope] = _PassageChunks.reads
    assert [(c.prop, c.values) for c in scope.chunk_conditions] == [("language", ("ces",))]


@pytest.mark.parametrize("body, status", [
    ({"ids": [], "criteria": {"text_query": "Marie"}}, 422),
    ({"ids": [str(UUID(int=i)) for i in range(101)], "criteria": {"text_query": "Marie"}}, 422),   # page size
    ({"ids": ["not-a-uuid"], "criteria": {"text_query": "Marie"}}, 422),
    ({"ids": [str(UUID(int=1))]}, 422),                                             # the search's criteria
    ({"ids": [str(UUID(int=1))], "criteria": {}, "vector": "main"}, 422),           # nothing is ranked
    ({"ids": [str(UUID(int=1))], "criteria": {"chunk_filters": {"languages": ["Czech"]}}}, 400),
])
async def test_invalid_passage_reads_are_refused_before_reading(tmp_path, body, status):
    response = await _passages(tmp_path, body, path="/api/search/passages/read")

    assert response.status_code == status, response.text
    assert _PassageChunks.reads == []


class _YearOrderedDocuments(_Documents):
    """``total`` matching documents in year order; records the browse calls."""
    calls: list[dict] = []
    total = 3

    async def browse_by_year(self, **kwargs):
        self.calls.append(kwargs)
        return DocumentBrowse(items=[Document(id=DOC, **STORED)], has_more=True, next_offset=1, total_count=self.total)


async def _documents(tmp_path, body, total=3):
    _YearOrderedDocuments.calls, _YearOrderedDocuments.total = [], total
    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    app.dependency_overrides[get_documents] = _YearOrderedDocuments
    async with LifespanManager(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/api/search/documents", json=body)


async def test_documents_answer_a_page_of_the_whole_matching_population_anonymously(tmp_path):
    response = await _documents(tmp_path, {"criteria": {"document_filters": {"year_min": 1900},
                                                        "chunk_filters": {"languages": ["CES"]}}, "limit": 1})

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["title"] for item in body["items"]] == ["Dopisy z Prahy"]
    assert {k: body[k] for k in ("offset", "next_offset", "total_count", "retrieval_limit", "bounded", "order")} == {
        "offset": 0, "next_offset": 1, "total_count": 3, "retrieval_limit": MAX_QUERY_RESULTS, "bounded": False,
        "order": "year_asc"}
    assert body["criteria"]["chunk_filters"] == {"languages": ["ces"], "classifications": {}}  # configured spelling
    [call] = _YearOrderedDocuments.calls
    assert (call["limit"], call["offset"], call["collection_id"]) == (1, 0, None)
    year, language = call["conditions"]
    assert year == NumberRange("yearIssued", 1900, None)
    assert (language.prop, language.values) == ("chunk_language", ("ces",))  # per dimension, from the summaries


@pytest.mark.parametrize("body, status", [
    ({"criteria": {"text_query": "Marie"}}, 422),                       # text-query ranking is #527
    ({"criteria": {}, "limit": 101}, 422),                               # page size
    ({"criteria": {}, "limit": 0}, 422),
    ({"criteria": {}, "offset": -1}, 422),
    ({"criteria": {}, "offset": MAX_QUERY_RESULTS - 10, "limit": 20}, 400),  # past the engine cap
    ({"criteria": {}, "type": "text"}, 422),                             # no retrieval options
    ({"criteria": {"chunk_filters": {"languages": ["Czech"]}}}, 400),    # not configured
    ({"criteria": {"chunk_filters": {"classifications": {"emotion": ["calm"]}}}}, 400),
])
async def test_invalid_document_requests_are_refused_before_browsing(tmp_path, body, status):
    response = await _documents(tmp_path, body)

    assert response.status_code == status, response.text
    assert _YearOrderedDocuments.calls == []


async def test_more_matching_documents_than_the_engine_cap_are_counted_but_not_paged_past_it(tmp_path):
    response = await _documents(tmp_path, {"criteria": {}, "offset": MAX_QUERY_RESULTS - 20, "limit": 20}, total=25_000)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["total_count"], body["bounded"], body["next_offset"]) == (25_000, True, None)
