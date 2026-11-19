"""Candidate chunks of optimized AI suggestions (features/annotations/candidates.py, #792)."""
from uuid import uuid4

from semant_demo.adapters.topicer.client import TopicerTag
from semant_demo.features.annotations.candidates import rank_candidates, vector_text
from semant_demo.features.search.schemas import SearchType
from semant_demo.features.search.service import SearchBackends
from semant_demo.features.search.vectors import SearchVector, SearchVectors

TAG = TopicerTag(id="t1", name="Osoba", definition="Jméno konkrétní osoby.", examples=["Jan Novák", "Marie"])


class Embedder:
    def __init__(self):
        self.queries: list[str] = []

    async def embed_query(self, text):
        self.queries.append(text)
        return [0.5, 0.5]

    async def embed_document(self, text):
        raise AssertionError("candidates are embedded as a query")


class Chunks:
    def __init__(self, ids):
        self.ids = ids
        self.queries = []

    async def ranked_ids(self, query):
        self.queries.append(query)
        return self.ids[:query.limit]


def backends(chunks, embedder):
    vectors = SearchVectors([SearchVector("other", "Other", "", "Other_Vector", Embedder()),
                             SearchVector("qwen", "Qwen", "", "Qwen3_Embedding_0_6B", embedder)], default="qwen")
    return SearchBackends(chunks=chunks, collections=None, vectors=vectors)


def test_the_vector_text_is_the_name_definition_and_examples():
    assert vector_text(TAG) == "Osoba\nJméno konkrétní osoby.\nJan Novák\nMarie"
    assert vector_text(TopicerTag(id="t", name="Místo", definition="", examples=[])) == "Místo"


async def test_a_hybrid_search_of_the_document_in_the_collection_ranks_the_candidates():
    collection, document, ids = uuid4(), uuid4(), [uuid4() for _ in range(3)]
    chunks, embedder = Chunks(ids), Embedder()

    candidates = await rank_candidates(backends(chunks, embedder), TAG, collection, document, limit=5)

    [query] = chunks.queries
    assert (query.text, query.mode, query.alpha, query.vector, query.target_vector) == (
        "Osoba", SearchType.hybrid, 0.5, [0.5, 0.5], "Qwen3_Embedding_0_6B")
    assert (query.collection_id, query.document_id, query.limit) == (collection, document, 6)
    assert embedder.queries == [vector_text(TAG)]
    assert (candidates.ids, candidates.truncated) == ([str(i) for i in ids], False)


async def test_a_chunk_ranked_twice_is_a_candidate_once():
    first, second = uuid4(), uuid4()

    candidates = await rank_candidates(backends(Chunks([first, second, first]), Embedder()), TAG, uuid4(), uuid4(),
                                       limit=2)

    assert (candidates.ids, candidates.truncated) == ([str(first), str(second)], False)


async def test_more_chunks_than_the_limit_are_cut_and_reported():
    ids = [uuid4() for _ in range(4)]

    exact = await rank_candidates(backends(Chunks(ids[:3]), Embedder()), TAG, uuid4(), uuid4(), limit=3)
    cut = await rank_candidates(backends(Chunks(ids), Embedder()), TAG, uuid4(), uuid4(), limit=3)

    assert (len(exact.ids), exact.truncated) == (3, False)
    assert (cut.ids, cut.truncated) == ([str(i) for i in ids[:3]], True)
