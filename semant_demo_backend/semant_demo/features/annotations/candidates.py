"""Candidate chunks of optimized AI suggestions (#792).

Optimized mode sends Topicer only the chunks of the document, in the collection, that are
most similar to a tag. semANT ranks them itself, so Topicer needs no database and one Topicer
serves every instance. The ranking copies the one Topicer's database stream used: a hybrid
search (``alpha`` 0.5) whose keyword part is the tag's name and whose vector part embeds the
tag's name, definition and examples as a query with the default search vector. Topicer also
left out chunks at a vector distance above 1.0 (negative cosine similarity); that cut is not
applied here, because Qwen text embeddings practically never reach it.
"""
from dataclasses import dataclass
from uuid import UUID

from semant_demo.adapters.topicer.client import TopicerTag
from semant_demo.features.search.schemas import ChunkQuery, SearchType
from semant_demo.features.search.service import SearchBackends

HYBRID_ALPHA = 0.5


@dataclass(frozen=True)
class Candidates:
    """The best chunks for a tag, best first."""
    ids: list[str]
    truncated: bool
    """More eligible chunks may have existed than the limit allowed: the search filled all its
    ``limit + 1`` places (duplicates count, so it is never missed)."""


def vector_text(tag: TopicerTag) -> str:
    """The text whose query embedding ranks chunks for ``tag``."""
    return "\n".join([tag.name, *([tag.definition] if tag.definition else []), *tag.examples])


async def rank_candidates(backends: SearchBackends, tag: TopicerTag, collection_id: UUID, document_id: UUID,
                          limit: int) -> Candidates:
    """At most ``limit`` chunks of the document in the collection for ``tag``, best first.

    The caller has checked access to the collection and the document. Embedding and search
    errors propagate.
    """
    vector = backends.vectors.resolve(None)
    query = ChunkQuery(text=tag.name, mode=SearchType.hybrid, limit=limit + 1, alpha=HYBRID_ALPHA,
                       vector=await vector.embedder.embed_query(vector_text(tag)),
                       target_vector=vector.target_vector, collection_id=collection_id, document_id=document_id)
    ranked = [str(i) for i in await backends.chunks.ranked_ids(query)]
    # Once each, best rank kept (as the passage search does), so a chunk is never sent twice.
    ids = list(dict.fromkeys(ranked))
    return Candidates(ids=ids[:limit], truncated=len(ranked) > limit)
