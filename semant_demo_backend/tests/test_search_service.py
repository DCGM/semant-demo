"""Search service (features/search/service.py) called directly, with fake stores and providers.

Covers embedding choice, filter normalization into neutral conditions, authorization of
the collection and of every requested tag before retrieval, and optional summaries.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from semant_demo.core.errors import InvalidRequestError, NotFoundError
from semant_demo.features.collections.access import AuthenticationRequired
from semant_demo.features.search import service
from semant_demo.features.search.filters import InvalidSearchFilterError, generate_default_filters
from semant_demo.features.search.schemas import ChunkQuery, FieldCondition, Op, TagFilter
from semant_demo.features.search.service import SearchBackends
from semant_demo.llm_api import APIOutput
from semant_demo.schemas import Document, SearchFilterInput, SearchRequest, SearchType, TextChunkWithDocument
from semant_demo.summarization.templated import ModelOptions, TemplatedSearchResultsSummarizer
from tests.fakes import FakeChatAPI

OWNER, SHARED, OTHER = (SimpleNamespace(id=uuid4(), name=n, is_superuser=False) for n in ("Owner", "Shared", "Other"))
COLLECTION, SECOND, FOREIGN = uuid4(), uuid4(), uuid4()
"""COLLECTION (shared with SHARED) and SECOND belong to OWNER; FOREIGN belongs to OTHER."""
TAG, SECOND_TAG, FOREIGN_TAG, ORPHAN_TAG = uuid4(), uuid4(), uuid4(), uuid4()
DEFINITIONS = generate_default_filters(min_year=1800, max_year=1950, languages=["ces", "deu"])


class FakeCollections:
    def __init__(self):
        self.records = {COLLECTION: (OWNER.id, {SHARED.id}), SECOND: (OWNER.id, set()), FOREIGN: (OTHER.id, set())}

    async def read_access_record(self, cid):
        return self.records.get(cid)


class FakeTags:
    def __init__(self):
        self.owners = {TAG: [COLLECTION], SECOND_TAG: [SECOND], FOREIGN_TAG: [FOREIGN], ORPHAN_TAG: []}

    async def read_collection_ids(self, ids):
        return {i: self.owners[i] for i in ids if i in self.owners}


class FakeChunks:
    def __init__(self, hits=None):
        self.queries: list[ChunkQuery] = []
        self.hits = hits if hits is not None else [hit("Roz-\ndělené\nřádky")]

    async def search(self, query):
        self.queries.append(query)
        return [h.model_copy() for h in self.hits]


class FakeEmbeddings:
    def __init__(self):
        self.calls = []

    async def embed_query(self, text):
        self.calls.append(("query", text))
        return [0.1, 0.2]

    async def embed_document(self, text):
        self.calls.append(("document", text))
        return [0.3, 0.4]


class FailingSummarizer:
    def __init__(self, titles_done=1):
        self.titles_done = titles_done

    async def __call__(self, request, response):
        for r in response.results[:self.titles_done]:
            r.query_title = "title"
        raise RuntimeError("summary provider down")


class RecordingSummarizer:
    def __init__(self, failures=()):
        self.calls = 0
        self.failures = list(failures)

    async def __call__(self, request, response):
        self.calls += 1
        response.results_summary = "summary"
        return self.failures


def hit(text) -> TextChunkWithDocument:
    doc = uuid4()
    return TextChunkWithDocument(id=uuid4(), title="t", text=text, start_page_id=uuid4(), from_page=1, to_page=1,
                                 order=0, language="ces", document=doc,
                                 document_object=Document(id=doc, library="mzk"))


def backends(chunks=None, embeddings=None) -> SearchBackends:
    return SearchBackends(chunks=chunks or FakeChunks(), collections=FakeCollections(), tags=FakeTags(),
                          embeddings=embeddings or FakeEmbeddings())


def request(**kwargs) -> SearchRequest:
    return SearchRequest(**{"query": "Novák", "type": "text", "tag_uuids": [], "positive": False,
                            "automatic": False, **kwargs})


async def run(req, user=OWNER, definitions=None, chunks=None, embeddings=None) -> ChunkQuery:
    chunks = chunks or FakeChunks()
    await service.retrieve(backends(chunks, embeddings), user, req, definitions)
    [query] = chunks.queries
    return query


#############
# Embedding #
#############

@pytest.mark.parametrize("search_type, is_hyde, expected", [
    ("text", False, []),
    ("text", True, []),
    ("vector", False, [("query", "Novák")]),
    ("hybrid", False, [("query", "Novák")]),
    ("vector", True, [("document", "Novák")]),
    ("hybrid", True, [("document", "Novák")]),
])
async def test_embedding_is_requested_only_for_vector_modes(search_type, is_hyde, expected):
    embeddings = FakeEmbeddings()
    query = await run(request(type=search_type, is_hyde=is_hyde, hybrid_search_alpha=0.7), embeddings=embeddings)

    assert embeddings.calls == expected
    assert query.mode == SearchType(search_type)
    assert query.vector == ({"query": [0.1, 0.2], "document": [0.3, 0.4]}[expected[0][0]] if expected else None)
    assert query.alpha == 0.7 and query.limit == 10 and query.text == "Novák"


async def test_embedding_failure_propagates_without_retrieval():
    class Down(FakeEmbeddings):
        async def embed_query(self, text):
            raise RuntimeError("embedding service down")
    chunks = FakeChunks()

    with pytest.raises(RuntimeError):
        await service.retrieve(backends(chunks, Down()), OWNER, request(type="hybrid"))
    assert chunks.queries == []


###########
# Filters #
###########

async def test_no_filters_means_no_conditions():
    query = await run(request(), definitions=DEFINITIONS)

    assert query.conditions == () and query.collection_id is None and query.tags is None


async def test_legacy_fields_become_conditions_when_no_filters_are_requested():
    req = request(min_year=1850, max_year=1900, language="ces")
    expected = (
        FieldCondition("yearIssued", Op.greater_or_equal, 1850),
        FieldCondition("yearIssued", Op.less_or_equal, 1900),
        FieldCondition("language", Op.equal, "ces"),
    )

    assert (await run(req, definitions=DEFINITIONS)).conditions == expected
    # RAG calls without filter definitions.
    assert (await run(req)).conditions == expected


async def test_requested_filters_are_validated_and_replace_legacy_fields():
    req = request(min_year=1000, language="deu", filters=[
        SearchFilterInput(id="year_range", min_value=1850, max_value=1900),
        SearchFilterInput(id="language", values=["Czech", "deu"]),
        SearchFilterInput(id="style", values=["formal"]),
    ])

    assert (await run(req, definitions=DEFINITIONS)).conditions == (
        FieldCondition("yearIssued", Op.greater_or_equal, 1850),
        FieldCondition("yearIssued", Op.less_or_equal, 1900),
        FieldCondition("language", Op.contains_any, ["ces", "deu"]),
        FieldCondition("style", Op.contains_any, ["formal"]),
    )


@pytest.mark.parametrize("filters", [
    [SearchFilterInput(id="unknown", values=["x"])],
    [SearchFilterInput(id="language", values=["Klingon"])],
    [SearchFilterInput(id="year_range", min_value=1900, max_value=1800)],
    [SearchFilterInput(id="year_range")],
    [SearchFilterInput(id="language", values=["ces"]), SearchFilterInput(id="language", values=["deu"])],
])
async def test_invalid_filters_are_a_bad_request_before_retrieval(filters):
    chunks, embeddings = FakeChunks(), FakeEmbeddings()

    with pytest.raises(InvalidSearchFilterError) as error:
        await service.retrieve(backends(chunks, embeddings), OWNER, request(type="hybrid", filters=filters), DEFINITIONS)
    assert isinstance(error.value, InvalidRequestError)
    assert chunks.queries == [] and embeddings.calls == []


@pytest.mark.parametrize("automatic, positive", [(True, False), (False, True), (True, True)])
async def test_tag_filter_matches_the_requested_kinds(automatic, positive):
    req = request(tag_uuids=[str(TAG), str(TAG)], automatic=automatic, positive=positive)

    assert (await run(req)).tags == TagFilter((TAG,), automatic=automatic, positive=positive)


async def test_tags_without_a_kind_do_not_filter_but_are_still_authorized():
    assert (await run(request(tag_uuids=[str(TAG)]))).tags is None
    with pytest.raises(NotFoundError):
        await run(request(tag_uuids=[str(FOREIGN_TAG)]))


#################
# Authorization #
#################

async def test_public_search_needs_no_login():
    query = await run(request(), user=None)

    assert query.collection_id is None and query.tags is None


@pytest.mark.parametrize("user", [OWNER, SHARED])
async def test_collection_scope_is_passed_to_retrieval(user):
    query = await run(request(user_collection_id=str(COLLECTION), tag_uuids=[str(TAG)], positive=True), user=user)

    assert query.collection_id == COLLECTION
    assert query.tags == TagFilter((TAG,), automatic=False, positive=True)


@pytest.mark.parametrize("user, collection, error", [
    (None, COLLECTION, AuthenticationRequired),
    (OTHER, COLLECTION, NotFoundError),
    (SHARED, SECOND, NotFoundError),
    (OWNER, uuid4(), NotFoundError),
    (OWNER, "not-a-uuid", NotFoundError),
])
async def test_unreadable_collection_is_refused_before_retrieval(user, collection, error):
    chunks, embeddings = FakeChunks(), FakeEmbeddings()

    with pytest.raises(error):
        await service.retrieve(backends(chunks, embeddings), user, request(type="hybrid", user_collection_id=str(collection)))
    assert chunks.queries == [] and embeddings.calls == []


async def test_tags_of_several_readable_collections_are_allowed_without_collection_scope():
    query = await run(request(tag_uuids=[str(TAG), str(SECOND_TAG)], automatic=True))

    assert set(query.tags.tag_ids) == {TAG, SECOND_TAG}
    assert query.collection_id is None


TAG_DENIALS = [
    # (user, collection scope, requested tags)
    (OWNER, None, [FOREIGN_TAG]),               # another user's tag
    (OWNER, None, [TAG, FOREIGN_TAG]),          # permitted mixed with inaccessible
    (OWNER, None, [uuid4()]),                   # unknown tag
    (OWNER, None, [ORPHAN_TAG]),                # tag of no collection
    (OWNER, None, ["not-a-uuid"]),              # malformed id
    (SHARED, None, [SECOND_TAG]),               # owner's tag in a collection not shared with the user
    (OWNER, COLLECTION, [SECOND_TAG]),          # readable tag, but of another collection than the scope
    (OWNER, COLLECTION, [TAG, FOREIGN_TAG]),
    (OWNER, COLLECTION, [uuid4()]),
]


@pytest.mark.parametrize("user, scope, tag_ids", TAG_DENIALS)
async def test_inaccessible_tags_are_refused_before_retrieval(user, scope, tag_ids):
    chunks, embeddings = FakeChunks(), FakeEmbeddings()
    req = request(type="hybrid", tag_uuids=[str(t) for t in tag_ids], automatic=True, positive=True,
                  user_collection_id=str(scope) if scope else None)

    with pytest.raises(NotFoundError) as error:
        await service.retrieve(backends(chunks, embeddings), user, req)
    # One answer for unknown and inaccessible tags: existence of private tags is not revealed.
    assert str(error.value) == "Tag not found"
    assert chunks.queries == [] and embeddings.calls == []


async def test_anonymous_tag_filter_needs_login():
    chunks = FakeChunks()

    with pytest.raises(AuthenticationRequired):
        await service.retrieve(backends(chunks), None, request(tag_uuids=[str(TAG)], positive=True))
    assert chunks.queries == []


async def test_public_retriever_searches_the_public_corpus_only():
    chunks = FakeChunks()
    retrieve = service.public_retriever(backends(chunks))

    response = await retrieve(request())
    assert len(response.results) == 1
    with pytest.raises(AuthenticationRequired):
        await retrieve(request(user_collection_id=str(COLLECTION)))
    assert len(chunks.queries) == 1


#####################
# Results, summaries #
#####################

async def test_retrieval_returns_display_text_and_log():
    response = await service.retrieve(backends(), OWNER, request())

    assert [r.text for r in response.results] == ["Rozdělené řádky"]
    assert response.search_log[0].startswith("Top 1 results for “Novák”")
    assert response.warnings == [] and response.results_summary is None


async def test_search_adds_requested_summaries():
    summarizer = RecordingSummarizer()

    response = await service.search(backends(), summarizer, OWNER, request())

    assert summarizer.calls == 1 and response.results_summary == "summary" and response.warnings == []


async def test_summary_failure_keeps_the_results_and_warns():
    chunks = FakeChunks(hits=[hit("a"), hit("b")])

    response = await service.search(backends(chunks), FailingSummarizer(titles_done=1), OWNER, request())

    assert [r.text for r in response.results] == ["a", "b"]
    assert [r.query_title for r in response.results] == ["title", None]
    assert response.warnings == [service.SUMMARY_FAILED_WARNING]


async def test_reported_summary_failures_keep_the_results_and_warn():
    response = await service.search(backends(), RecordingSummarizer(failures=["title", "results_summary"]), OWNER,
                                    request())

    assert len(response.results) == 1 and response.results_summary == "summary"
    assert response.warnings == [service.SUMMARY_FAILED_WARNING]


async def test_provider_errors_in_the_templated_summarizer_are_reported():
    class FailingTitles(FakeChatAPI):
        async def process_single_request(self, request):
            if request.custom_id == "gen_title":
                return APIOutput(custom_id=request.custom_id, response=None, error="provider down")
            return await super().process_single_request(request)

    summarizer = TemplatedSearchResultsSummarizer(
        api=FailingTitles(default_reply="ok"), gen_title_model_options=ModelOptions(),
        gen_results_summary_model_options=ModelOptions(), gen_query_summary_model_options=ModelOptions())
    chunks = FakeChunks(hits=[hit("a"), hit("b")])

    response = await service.search(backends(chunks), summarizer, OWNER, request())

    assert [r.query_title for r in response.results] == ["N/A", "N/A"]   # configured fallback, as before
    assert [r.query_summary for r in response.results] == ["ok", "ok"]
    assert response.results_summary == "ok"
    assert response.warnings == [service.SUMMARY_FAILED_WARNING]


async def test_denied_search_never_summarizes():
    summarizer = RecordingSummarizer()

    with pytest.raises(NotFoundError):
        await service.search(backends(), summarizer, OWNER, request(tag_uuids=[str(FOREIGN_TAG)], positive=True))
    assert summarizer.calls == 0


async def test_retrieval_failure_propagates():
    class Broken(FakeChunks):
        async def search(self, query):
            raise RuntimeError("store down")

    with pytest.raises(RuntimeError):
        await service.search(backends(Broken()), RecordingSummarizer(), OWNER, request())

