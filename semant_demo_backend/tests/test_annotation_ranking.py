"""Ranked annotation retrieval (#664): semantic, hybrid and Find similar, with in-memory fakes.

Every filter of the annotation query (#663) applies before ranking; at most ``k`` annotations
return in relevance order, then id, paged within that set; the page says it is a top ``k``,
whether more could be ranked and how many matching annotations have a current vector. Find
similar uses the source's stored vector (no provider call), excludes the source unless asked,
and refuses a source without a current vector. Authorization and validation precede any
embedding call. The Weaviate queries themselves: tests/integration/test_annotation_ranking.py.
"""
import math
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from semant_demo.core.errors import InvalidRequestError, NotFoundError, ServiceUnavailableError
from semant_demo.features.annotations import service
from semant_demo.features.annotations.enrichment import AnnotationVector, AnnotationVectorSettings, Enrichment
from semant_demo.features.annotations.schemas import (
    MAX_TOP_K, AnnotationFilters, AnnotationIdsRequest, AnnotationRanking, AnnotationSort,
    ResultKind, RetrievalMode, SpanType, TextScope, VectorStatus,
)
from semant_demo.features.annotations.service import AnnotationStore
from semant_demo.features.documents.criteria import DocumentFilters
from semant_demo.features.user_collections.access import ResourceNotFound
from tests.test_annotation_concordance import (
    COLLECTION, DOC_A, DOC_B, OTHER, OTHER_TAG, OWNER, SHARED, TAG, FakeCollections, FakeDocuments, FakeSpans, row,
)

CONFIG_ID = "fake-context-v1"
SEMANTIC = AnnotationRanking(mode=RetrievalMode.semantic)
HYBRID = AnnotationRanking(mode=RetrievalMode.hybrid)


class FakeEmbedder:
    """Query embeddings fixed per text; ``fail`` makes the provider unreachable."""

    def __init__(self):
        self.queries: list[str] = []
        self.fail = False

    async def embed_query(self, text):
        self.queries.append(text)
        if self.fail:
            raise TimeoutError("embedding service timed out")
        return [1.0, 0.0]

    async def embed_document(self, text):
        raise AssertionError("ranking never embeds documents")


class RankingSpans(FakeSpans):
    """``FakeSpans`` with stored contextual vectors and ``SpanRepository``'s ranked queries."""

    def __init__(self):
        super().__init__()
        self.vectors: dict[UUID, list[float]] = {}
        self.rankings: list[tuple] = []

    def _match(self, query, document_ids):
        rows = super()._match(query, document_ids)
        if query.vector_config is None:
            return rows
        return [r for r in rows if r.vectorStatus == VectorStatus.ready and r.vectorConfig == query.vector_config
                and r.enrichmentStatus == "ready" and r.derivationVersion == query.derivation_version]

    async def rank(self, cid, query, ranking, *, document_ids=None, limit):
        self.rankings.append((ranking, limit))
        candidates = [r for r in self._match(query, document_ids) if r.id != ranking.exclude]
        distance = {r.id: math.dist(self.vectors[r.id], ranking.vector) for r in candidates}
        if ranking.text is None:
            ordered = sorted(candidates, key=lambda r: distance[r.id])  # Weaviate leaves ties unordered
            return [r.model_copy(update={"distance": distance[r.id]}) for r in ordered][:limit]
        # Hybrid: a score that rewards the text in the searched fields and closeness.
        def score(r):
            text = " ".join(getattr(r, f) or "" for f in ranking.fields).lower()
            return round((1 - ranking.alpha) * (ranking.text.lower() in text) + ranking.alpha / (1 + distance[r.id]), 6)
        ordered = sorted(candidates, key=lambda r: -score(r))
        return [r.model_copy(update={"score": score(r)}) for r in ordered][:limit]

    async def read_rows_by_id(self, cid, ids):
        self.queries += 1
        return {r.id: r for r in self.rows if r.id in ids}

    async def read_vector(self, cid, span_id, target_vector):
        if cid != COLLECTION:
            return None
        for r in self.rows:
            if r.id == span_id:
                return r, self.vectors.get(r.id)
        return None


def ranked_row(document, distance, text="slovo", *, vector=True, rid=None, **kwargs):
    """A current row whose vector lies ``distance`` from the query vector [1, 0]."""
    r = row(document, int(distance * 100), text, rid=rid, **kwargs)
    if vector:
        r = r.model_copy(update={"vectorStatus": VectorStatus.ready, "vectorConfig": CONFIG_ID, "vectorRevision": 1})
    return r, [1.0, distance]


@pytest.fixture
def embedder():
    return FakeEmbedder()


@pytest.fixture
def store(embedder):
    vector = AnnotationVector(AnnotationVectorSettings.model_validate(
        {"id": CONFIG_ID, "embedding": {"provider": "embedding_service"}}), embedder)
    return AnnotationStore(collections=FakeCollections(), tags=None, spans=RankingSpans(), chunk_tags=None,
                           documents=FakeDocuments(), enrichment=Enrichment(derived=True, vector=vector))


def put(store, *rows):
    for r, v in rows:
        store.spans.rows.append(r)
        store.spans.vectors[r.id] = v
    return [r.id for r, _ in rows]


async def ranked(store, filters=None, ranking=SEMANTIC, user=OWNER, **kwargs):
    return await service.query_annotations(store, user, COLLECTION, filters or AnnotationFilters(q="hejtman"),
                                           ranking=ranking, **kwargs)


def ids(page):
    return [r.id for r in page.rows]


# ── Ranking ───────────────────────────────────────────────────────────────

async def test_semantic_ranks_by_distance_and_describes_a_top_k(store, embedder):
    far, near, middle = put(store, ranked_row(DOC_A, 0.9), ranked_row(DOC_B, 0.1), ranked_row(DOC_A, 0.5))

    page = await ranked(store, ranking=AnnotationRanking(mode=RetrievalMode.semantic, k=2))

    assert ids(page) == [near, middle] and page.total == 2
    assert page.result.kind == ResultKind.top_k and page.result.mode == RetrievalMode.semantic
    assert (page.result.k, page.result.truncated) == (2, True)
    assert (page.result.coverage.matching, page.result.coverage.with_vector) == (3, 3)
    assert embedder.queries == ["hejtman"]
    # q ranks; it filters nothing (none of the rows contains "hejtman")
    assert store.spans.rankings[0][0].text is None and store.spans.rankings[0][1] == 3


async def test_lexical_pages_describe_a_complete_result(store, embedder):
    put(store, ranked_row(DOC_A, 0.1))
    page = await service.query_annotations(store, OWNER, COLLECTION)
    assert page.result.kind == ResultKind.complete and page.result.coverage is None and page.total == 1
    assert embedder.queries == []


async def test_every_filter_applies_before_ranking(store):
    wanted = put(store, ranked_row(DOC_A, 0.8, "Novák"))
    put(store, ranked_row(DOC_B, 0.1, "Novák"),  # another year
        ranked_row(DOC_A, 0.1, "Novák", tag=OTHER_TAG), ranked_row(DOC_A, 0.1, "Novák", type=SpanType.neg))
    filters = AnnotationFilters(q="hejtman", tag_ids=[TAG], document_filters=DocumentFilters(year_min=1900))

    page = await ranked(store, filters, AnnotationRanking(mode=RetrievalMode.semantic, k=1))

    assert ids(page) == wanted and not page.result.truncated
    assert page.result.coverage.matching == 1
    assert page.rows[0].documentTitle == "Almanach"


async def test_coverage_counts_the_matching_annotations_that_cannot_be_ranked(store):
    with_vector = put(store, ranked_row(DOC_A, 0.3), ranked_row(DOC_A, 0.2))
    put(store, ranked_row(DOC_A, 0.1, vector=False), ranked_row(DOC_B, 0.1, vector=False))
    store.spans.rows[2] = store.spans.rows[2].model_copy(update={"vectorStatus": VectorStatus.failed,
                                                                 "vectorConfig": CONFIG_ID})
    put(store, (ranked_row(DOC_A, 0.1)[0].model_copy(update={"vectorConfig": "older-model"}), [1.0, 0.1]))

    page = await ranked(store)

    assert ids(page) == with_vector[::-1] and not page.result.truncated
    assert (page.result.coverage.matching, page.result.coverage.with_vector) == (5, 2)


async def test_a_ready_vector_of_an_older_revision_is_skipped_and_counted_as_uncovered(store):
    rows = put(store, *(ranked_row(DOC_A, d / 10) for d in range(1, 6)))
    stale = rows[:3]
    for i, r in enumerate(store.spans.rows):
        if r.id in stale:  # edited since; Weaviate cannot compare vectorRevision with revision
            store.spans.rows[i] = r.model_copy(update={"revision": 2, "enrichedRevision": 2})

    page = await ranked(store, ranking=AnnotationRanking(mode=RetrievalMode.semantic, k=1))

    assert ids(page) == [rows[3]] and page.result.truncated  # rows[4] is the second current one
    assert [limit for _, limit in store.spans.rankings] == [2, 4, 8]  # read on until k + 1 current ones or all
    assert (page.result.coverage.matching, page.result.coverage.with_vector) == (5, 2)


async def test_pages_partition_the_top_k_in_relevance_then_id_order(store):
    # Equal distances: the order must not depend on the order Weaviate returns ties in.
    tied = sorted(put(store, *(ranked_row(DOC_A, 0.5) for _ in range(4))), key=str)
    first = put(store, ranked_row(DOC_B, 0.1))
    put(store, ranked_row(DOC_A, 0.9))
    store.spans.rows.reverse()
    ranking = AnnotationRanking(mode=RetrievalMode.semantic, k=5)

    pages = [await ranked(store, ranking=ranking, limit=2, offset=o) for o in (0, 2, 4, 6)]

    assert [i for p in pages for i in ids(p)] == first + tied
    assert [p.total for p in pages] == [5] * 4 and ids(pages[3]) == []
    assert all(p.result.truncated for p in pages)


async def test_hybrid_ranks_by_score_with_bm25_on_the_fields_of_the_text_scope(store):
    plain, named = put(store, ranked_row(DOC_A, 0.1, "slovo"), ranked_row(DOC_A, 0.6, "hejtman"))
    filters = AnnotationFilters(q="  hejtman ", text_scope=TextScope.annotation)

    page = await ranked(store, filters, HYBRID)

    assert ids(page) == [named, plain] and page.result.mode == RetrievalMode.hybrid
    used, _ = store.spans.rankings[0]
    assert (used.text, used.fields, used.alpha) == ("hejtman", ("text",), 0.5)
    await ranked(store, AnnotationFilters(q="hejtman", text_scope=TextScope.both), HYBRID)
    assert store.spans.rankings[1][0].fields == ("text", "leftContext", "rightContext")


# ── Find similar ──────────────────────────────────────────────────────────

def similar(source, **kwargs):
    return AnnotationRanking(mode=RetrievalMode.similar, similar_to=source, **kwargs)


async def test_find_similar_ranks_by_the_source_vector_without_it_and_without_a_provider(store, embedder):
    source, near, far = put(store, ranked_row(DOC_A, 0.3), ranked_row(DOC_A, 0.35), ranked_row(DOC_A, 0.9))

    page = await ranked(store, AnnotationFilters(), similar(source))
    included = await ranked(store, AnnotationFilters(), similar(source, include_source=True))

    assert ids(page) == [near, far] and ids(included) == [source, near, far]
    assert page.result.mode == RetrievalMode.similar and embedder.queries == []
    assert store.spans.rankings[0][0].vector == [1.0, 0.3] and store.spans.rankings[0][0].exclude == source
    assert store.spans.rankings[1][0].exclude is None


async def test_find_similar_keeps_the_lexical_filters(store):
    source, other = put(store, ranked_row(DOC_A, 0.3, "Praha"), ranked_row(DOC_A, 0.3, "Brno"))
    wanted = put(store, ranked_row(DOC_A, 0.9, "Prahou"))

    page = await ranked(store, AnnotationFilters(q="prah"), similar(source))

    assert ids(page) == wanted and other not in ids(page)


async def test_find_similar_refuses_a_source_without_a_current_vector(store, embedder):
    [pending] = put(store, ranked_row(DOC_A, 0.1, vector=False))
    [stale] = put(store, ranked_row(DOC_A, 0.1))
    store.spans.rows[-1] = store.spans.rows[-1].model_copy(update={"revision": 2, "enrichedRevision": 2})

    for source in (pending, stale):
        with pytest.raises(InvalidRequestError, match="no current vector"):
            await ranked(store, AnnotationFilters(), similar(source))
    assert store.spans.rankings == [] and embedder.queries == []


async def test_a_source_of_another_collection_is_not_found(store):
    with pytest.raises(NotFoundError):
        await ranked(store, AnnotationFilters(), similar(uuid4()))


# ── Provider, authorization and validation ────────────────────────────────

async def test_no_provider_call_before_authorization_and_validation(store, embedder):
    put(store, ranked_row(DOC_A, 0.1))
    with pytest.raises(ResourceNotFound):
        await ranked(store, user=OTHER)
    with pytest.raises(InvalidRequestError, match="Enter a text"):
        await ranked(store, AnnotationFilters(q="  "))
    with pytest.raises(InvalidRequestError, match="cannot be sorted"):
        await ranked(store, sort=AnnotationSort.text)
    with pytest.raises(InvalidRequestError, match="cannot be sorted"):
        await ranked(store, descending=True)
    with pytest.raises(InvalidRequestError):
        await ranked(store, AnnotationFilters(q="hejtman", attribute_values=["malformed"]))
    with pytest.raises(ResourceNotFound):
        await service.resolve_annotation_ids(store, OTHER, COLLECTION, AnnotationIdsRequest(q="x", ranking=SEMANTIC))
    assert embedder.queries == [] and store.spans.rankings == []


async def test_an_unreachable_provider_fails_ranked_text_modes_only(store, embedder):
    [source] = put(store, ranked_row(DOC_A, 0.1))
    put(store, ranked_row(DOC_A, 0.2))
    embedder.fail = True

    for ranking in (SEMANTIC, HYBRID):
        with pytest.raises(ServiceUnavailableError, match="Lexical search and Find similar still work"):
            await ranked(store, ranking=ranking)
    assert len(ids(await ranked(store, AnnotationFilters(), similar(source)))) == 1
    assert (await service.query_annotations(store, OWNER, COLLECTION)).total == 2


async def test_without_a_configured_vector_ranked_modes_are_unavailable_and_lexical_works(store, embedder):
    [source] = put(store, ranked_row(DOC_A, 0.1))
    store.enrichment = Enrichment(derived=True)

    for ranking in (SEMANTIC, HYBRID, similar(source)):
        with pytest.raises(ServiceUnavailableError, match="not configured"):
            await ranked(store, ranking=ranking)
    assert (await service.query_annotations(store, OWNER, COLLECTION)).total == 1
    assert embedder.queries == []


@pytest.mark.parametrize("fields", [
    {"mode": "similar"}, {"mode": "semantic", "similar_to": str(uuid4())}, {"mode": "semantic", "include_source": True},
    {"mode": "semantic", "k": 0}, {"mode": "semantic", "k": MAX_TOP_K + 1}, {"mode": "nearest"}, {"rank": 1},
])
def test_malformed_rankings_are_refused_by_the_model(fields):
    with pytest.raises(ValidationError):
        AnnotationRanking.model_validate(fields)


# ── Selection ─────────────────────────────────────────────────────────────

async def test_select_all_in_a_ranked_mode_resolves_exactly_the_top_k(store):
    rows = put(store, *(ranked_row(DOC_A, d / 10) for d in range(1, 8)))
    ranking = AnnotationRanking(mode=RetrievalMode.semantic, k=3)

    resolved = await service.resolve_annotation_ids(store, SHARED, COLLECTION,
                                                    AnnotationIdsRequest(q="hejtman", ranking=ranking))
    page = await ranked(store, ranking=ranking)
    within = await service.resolve_annotation_ids(store, OWNER, COLLECTION, AnnotationIdsRequest(
        q="hejtman", ranking=ranking, within=[rows[0], rows[5]]))

    assert resolved.ids == rows[:3] == ids(page)
    assert resolved.result.kind == ResultKind.top_k and resolved.result.k == 3 and resolved.result.truncated
    assert set(resolved.versions) == set(rows[:3])
    assert within.ids == [rows[0]]  # within is matched against the top k, not ranked on its own


async def test_ranked_routes_parse_the_mode_and_answer_unavailable_with_503(tmp_path, store, embedder, monkeypatch):
    from asgi_lifespan import LifespanManager
    from httpx import ASGITransport, AsyncClient

    from semant_demo.main import create_app
    from semant_demo.routes.dependencies import get_annotation_store
    from tests.app_support import make_test_config, offline_weaviate
    from tests.auth_support import auth_headers, register

    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    app.dependency_overrides[get_annotation_store] = lambda: store
    source, near, far = put(store, ranked_row(DOC_A, 0.3), ranked_row(DOC_A, 0.35), ranked_row(DOC_B, 0.9))
    path = f"/api/user_collections/{COLLECTION}/annotations"
    async with LifespanManager(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await register(client, email="rank@example.com", password="StrongPassw0rd!")).status_code == 201
        headers = await auth_headers(client, "rank@example.com", "StrongPassw0rd!")
        monkeypatch.setattr(OWNER, "id", UUID((await client.get("/api/users/me", headers=headers)).json()["id"]))

        semantic = await client.get(path, headers=headers, params={"mode": "semantic", "q": "hejtman", "k": 2})
        found = await client.get(path, headers=headers, params={"mode": "similar", "similar_to": str(source)})
        resolved = await client.post(f"{path}/ids", headers=headers, json={
            "ranking": {"mode": "similar", "similar_to": str(source), "k": 1}})
        bad = [await client.get(path, headers=headers, params=params)
               for params in ({"mode": "semantic", "k": 501}, {"mode": "similar"},
                              {"mode": "semantic", "similar_to": str(source)}, {"mode": "semantic", "q": "x", "sort": "text"},
                              {"mode": "semantic"})]
        embedder.fail = True
        unavailable = await client.get(path, headers=headers, params={"mode": "hybrid", "q": "hejtman"})

    assert semantic.status_code == 200, semantic.text
    body = semantic.json()
    assert [r["id"] for r in body["rows"]] == [str(source), str(near)] and body["total"] == 2
    assert body["result"] == {"kind": "top_k", "mode": "semantic", "k": 2, "truncated": True,
                              "coverage": {"matching": 3, "with_vector": 3}}
    assert [r["id"] for r in found.json()["rows"]] == [str(near), str(far)]
    assert resolved.json()["ids"] == [str(near)] and resolved.json()["result"]["kind"] == "top_k"
    assert [r.status_code for r in bad] == [422, 422, 422, 400, 400]
    assert unavailable.status_code == 503 and "Find similar still work" in unavailable.json()["detail"]
