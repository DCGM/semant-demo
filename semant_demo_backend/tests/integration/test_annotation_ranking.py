"""Ranked annotation retrieval against real Weaviate (#664), with fixed vectors.

Semantic, hybrid and Find similar rank only the annotations of the authorized tenant that
match every filter of the annotation query, including the shared document filters; the top
``k`` is paged in relevance order, then id; vector coverage counts the matching annotations
without a current vector, including one whose ``ready`` vector belongs to an older revision.
Find similar excludes its source unless asked and does not find a source of another
collection. The service rules with fakes: tests/test_annotation_ranking.py.
"""
import math
from types import SimpleNamespace
from uuid import UUID

import pytest

from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.adapters.weaviate.spans import SpanRepository
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.core.errors import NotFoundError
from semant_demo.features.annotations import service
from semant_demo.features.annotations.enrichment import AnnotationVector, AnnotationVectorSettings, Enrichment
from semant_demo.features.annotations.schemas import (
    AnnotationFilters, AnnotationIdsRequest, AnnotationRanking, PostSpan, ResultKind, RetrievalMode, SpanType,
)
from semant_demo.features.annotations.service import AnnotationStore
from semant_demo.features.documents.criteria import DocumentFilters
from tests.fakes import FAKE_EMBEDDING_DIM, fake_embedding

pytestmark = pytest.mark.integration

CONFIG_ID = "fake-context-v1"


def direction(angle: float) -> list[float]:
    """A unit vector ``angle`` radians from the query vector ``direction(0)``."""
    return [math.cos(angle), math.sin(angle)] + [0.0] * (FAKE_EMBEDDING_DIM - 2)


class Embedder:
    def __init__(self):
        self.queries: list[str] = []

    async def embed_document(self, text):
        return fake_embedding(text)

    async def embed_query(self, text):
        self.queries.append(text)
        return direction(0)


@pytest.fixture
def embedder():
    return Embedder()


@pytest.fixture
def store(seeded_store, collection_names, embedder) -> AnnotationStore:
    spans = SpanRepository(seeded_store, collection_names)
    documents = DocumentRepository(seeded_store, collection_names)
    documents.positions = True
    vector = AnnotationVector(AnnotationVectorSettings.model_validate(
        {"id": CONFIG_ID, "embedding": {"provider": "embedding_service"}}), embedder)
    return AnnotationStore(collections=UserCollectionRepository(seeded_store, collection_names, spans),
                           tags=TagRepository(seeded_store, collection_names, spans), spans=spans,
                           documents=documents, enrichment=Enrichment(True, vector))


@pytest.fixture
def owner(ids):
    return SimpleNamespace(id=UUID(ids.user["owner"]), is_superuser=False)


async def create(store, owner, ids, chunk, start, end, angle, collection="chronicles", tag="person") -> UUID:
    """A derived annotation whose contextual vector is then replaced by ``direction(angle)``."""
    result = await service.create_span(store, owner, PostSpan(chunkId=ids.chunk[chunk], tagId=ids.tag[tag],
                                                              start=start, end=end, type=SpanType.pos))
    assert result.outcome == "complete"
    sid = UUID(result.id)
    await store.spans._tenant(UUID(ids.col[collection])).data.update(uuid=sid, vector={"contextual": direction(angle)})
    return sid


@pytest.fixture
async def ranked(store, owner, ids, corpus):
    """Annotations at known angles from the query: three in the chronicle (1851), two in the letters (1902)."""
    letter = corpus.chunks["letters_2"]["text"]
    karel = letter.index("Karel")
    return SimpleNamespace(
        novak=await create(store, owner, ids, "chronicle_1", 34, 43, 0.5),  # "Jan Novák"
        lhota=await create(store, owner, ids, "chronicle_1", 20, 25, 0.1),
        brno=await create(store, owner, ids, "chronicle_2", 29, 33, 1.2, tag="place"),
        zdenka=await create(store, owner, ids, "letters_2", 10, 16, 0.3),
        karel=await create(store, owner, ids, "letters_2", karel, karel + 5, 0.2),
    )


async def query(store, owner, ids, filters, ranking, **kwargs):
    return await service.query_annotations(store, owner, ids.col["chronicles"], filters, ranking=ranking, **kwargs)


def semantic(k=100):
    return AnnotationRanking(mode=RetrievalMode.semantic, k=k)


def ids_of(page):
    return [r.id for r in page.rows]


async def test_semantic_ranks_the_filtered_annotations_by_distance_with_their_coverage(store, owner, ids, ranked,
                                                                                         embedder):
    filters = AnnotationFilters(q="dopis", document_filters=DocumentFilters(year_min=1900))
    page = await query(store, owner, ids, filters, semantic())
    lexical = await service.query_annotations(store, owner, ids.col["chronicles"],
                                              AnnotationFilters(document_filters=DocumentFilters(year_min=1900)))

    assert ids_of(page) == [ranked.karel, ranked.zdenka] and embedder.queries == ["dopis"]
    assert page.result.kind == ResultKind.top_k and not page.result.truncated
    # The seeded annotations of the letters have no derived text or vector: matching, not ranked.
    assert page.result.coverage.matching == lexical.total > 2
    assert page.result.coverage.with_vector == 2
    assert page.rows[0].documentTitle == "Dopisy z Prahy" and page.rows[0].text == "Karel"


async def test_the_top_k_is_paged_in_relevance_order_and_reports_truncation(store, owner, ids, ranked):
    full = await query(store, owner, ids, AnnotationFilters(q="x"), semantic(k=4), limit=200)
    pages = [await query(store, owner, ids, AnnotationFilters(q="x"), semantic(k=4), limit=3, offset=o)
             for o in (0, 3)]

    assert ids_of(full) == [ranked.lhota, ranked.karel, ranked.zdenka, ranked.novak]
    assert ids_of(pages[0]) + ids_of(pages[1]) == ids_of(full) and full.total == 4
    assert full.result.truncated  # "Brno" could have been ranked too


async def test_tag_and_title_filters_apply_before_ranking(store, owner, ids, ranked):
    by_tag = await query(store, owner, ids, AnnotationFilters(q="x", tag_ids=[ids.tag["place"]]), semantic(k=1))
    by_title = await query(store, owner, ids, AnnotationFilters(
        q="x", document_filters=DocumentFilters(title_contains=["kronika"])), semantic(k=2))

    assert ids_of(by_tag) == [ranked.brno] and not by_tag.result.truncated
    assert ids_of(by_title) == [ranked.lhota, ranked.novak] and by_title.result.truncated


async def test_a_ready_vector_of_an_older_revision_is_not_ranked_and_counted_as_uncovered(store, owner, ids, ranked):
    before = await query(store, owner, ids, AnnotationFilters(q="x"), semantic())
    await store.spans._tenant(UUID(ids.col["chronicles"])).data.update(uuid=ranked.lhota, properties={"revision": 2})

    after = await query(store, owner, ids, AnnotationFilters(q="x"), semantic())

    assert ids_of(after) == [i for i in ids_of(before) if i != ranked.lhota]
    assert after.result.coverage.with_vector == before.result.coverage.with_vector - 1


async def test_hybrid_combines_the_vector_with_bm25_of_the_text_scope(store, owner, ids, ranked):
    vector_only = await query(store, owner, ids, AnnotationFilters(q="Novák"), semantic(k=1))
    hybrid = await query(store, owner, ids, AnnotationFilters(q="Novák"),
                         AnnotationRanking(mode=RetrievalMode.hybrid, k=2))

    assert ids_of(vector_only) == [ranked.lhota]
    assert ids_of(hybrid)[0] == ranked.novak and hybrid.result.mode == RetrievalMode.hybrid


async def test_find_similar_ranks_from_the_stored_vector_without_its_source(store, owner, ids, ranked, embedder):
    similar = AnnotationRanking(mode=RetrievalMode.similar, similar_to=ranked.zdenka, k=2)

    page = await query(store, owner, ids, AnnotationFilters(), similar)
    included = await query(store, owner, ids, AnnotationFilters(),
                           similar.model_copy(update={"include_source": True}))
    resolved = await service.resolve_annotation_ids(store, owner, ids.col["chronicles"],
                                                    AnnotationIdsRequest(ranking=similar))

    assert ids_of(page) == [ranked.karel, ranked.lhota] and embedder.queries == []
    assert ids_of(included) == [ranked.zdenka, ranked.karel]
    assert resolved.ids == ids_of(page) and resolved.result.kind == ResultKind.top_k


async def test_a_source_of_another_collection_is_not_found(store, owner, ids, ranked):
    elsewhere = await create(store, owner, ids, "chronicle_3", 0, 5, 0.0, collection="newspapers",
                           tag="event")

    with pytest.raises(NotFoundError):
        await query(store, owner, ids, AnnotationFilters(),
                    AnnotationRanking(mode=RetrievalMode.similar, similar_to=elsewhere))
    ranked_here = await query(store, owner, ids, AnnotationFilters(q="x"), semantic())
    assert elsewhere not in ids_of(ranked_here)
