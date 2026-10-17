"""Search use cases: authorized chunk retrieval and optional summaries.

``retrieve`` checks access, normalizes the request into a neutral ``ChunkQuery``, embeds
the query for vector/hybrid search with the embedder of the selected (or default) search
vector (``vectors.py``) and runs it through the search adapter against that vector. RAG
uses it directly, without summaries. ``search`` adds the optional summaries; when some or
all of them fail, the retrieved hits are still returned, with a warning.

Access (ADR 0007): a ``user_collection_id`` needs read access to that collection, and
every requested tag must belong to a collection the user can read (to that collection,
if one is given). Without either, search covers the public corpus, also anonymously.
Restrictions are applied inside the retrieval query, never by dropping hits afterwards.
"""
import logging
from dataclasses import dataclass
from functools import partial
from time import time
from typing import Awaitable, Callable, Protocol

from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.adapters.weaviate.search import ChunkSearchRepository
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.core.errors import InvalidRequestError
from semant_demo.features.user_collections import access
from semant_demo.features.user_collections.access import Principal
from semant_demo.features.search.filters import InvalidSearchFilterError, parse_and_validate_search_filters
from semant_demo.features.search.schemas import (
    ChunkQuery, FieldCondition, Op, SearchFiltersResponse, SearchRequest, SearchResponse, SearchType, TagFilter,
)
from semant_demo.features.search.vectors import SearchVector, SearchVectors

logger = logging.getLogger(__name__)

SUMMARY_FAILED_WARNING = "Some titles or summaries could not be generated."
SUMMARY_LIMITED_WARNING = "Titles and result summaries were generated only for the first results."

Retriever = Callable[[SearchRequest], Awaitable[SearchResponse]]


class Summarizer(Protocol):
    """Adds the titles and summaries ``request`` asks for to ``response`` in place
    (``features/summarization``); returns the kinds of the parts that failed."""

    async def __call__(self, request: SearchRequest, response: SearchResponse) -> list[str]: ...


@dataclass(frozen=True)
class SearchBackends:
    """What retrieval needs; built per request from the application's resources."""
    chunks: ChunkSearchRepository
    collections: UserCollectionRepository
    tags: TagRepository
    vectors: SearchVectors


async def retrieve(backends: SearchBackends, user: Principal | None, request: SearchRequest,
                   filter_definitions: SearchFiltersResponse | None = None) -> SearchResponse:
    """Authorized retrieval without summaries.

    ``filter_definitions`` validates ``request.filters``; without definitions or requested
    filters, the legacy ``min_year``/``max_year``/``language`` fields apply instead.
    """
    start = time()
    # An unknown vector is refused before any other work, also for text search.
    vector = backends.vectors.resolve(request.vector)
    collection_id = None
    if request.user_collection_id is not None:
        collection_id = (await access.require_collection_read(
            backends.collections, user, request.user_collection_id)).collection_id
    tag_ids = await access.require_readable_tags(
        backends.collections, backends.tags, user, request.tag_uuids, collection_id)

    query = ChunkQuery(
        text=request.query,
        mode=request.type,
        limit=request.limit,
        alpha=request.hybrid_search_alpha,
        collection_id=collection_id,
        tags=TagFilter(tuple(tag_ids), automatic=request.automatic, positive=request.positive)
        if tag_ids and (request.automatic or request.positive) else None,
        conditions=tuple(filter_conditions(request, filter_definitions)),
        vector=await _embed(vector, request),
        target_vector=None if request.type == SearchType.text else vector.target_vector,
    )
    hits = await backends.chunks.search(query)
    for hit in hits:
        hit.text = display_text(hit.text)

    elapsed = time() - start
    log_entry = f"Top {len(hits)} results for “{request.query}”. Retrieved in {elapsed:.2f} seconds:"
    # Content-free: RAG retrieves with the user's (rephrased) question.
    logger.info("Search returned %d results in %.2f s", len(hits), elapsed)
    return SearchResponse(results=hits, search_request=request, time_spent=elapsed, search_log=[log_entry],
                          vector=None if request.type == SearchType.text else vector.id)


async def search(backends: SearchBackends, summarizer: Summarizer, user: Principal | None,
                 request: SearchRequest, filter_definitions: SearchFiltersResponse | None = None) -> SearchResponse:
    """Retrieval plus the summaries the request asks for.

    When a title or summary cannot be generated (the summarizer reports it and keeps its
    fallback text) or the summarizer fails altogether, the hits and the summaries made so
    far are kept and ``SUMMARY_FAILED_WARNING`` is added. When only the first results got
    titles and summaries (the summarizer's ``results_limit``), ``SUMMARY_LIMITED_WARNING``
    is added. Retrieval errors propagate.
    """
    start = time()
    response = await retrieve(backends, user, request, filter_definitions)
    try:
        failed = await summarizer(request, response)
    except Exception as e:
        logger.error("Search summary generation failed: %s", type(e).__name__)
        failed = ["summarizer"]
    if "results_limit" in failed:
        response.warnings.append(SUMMARY_LIMITED_WARNING)
        failed = [kind for kind in failed if kind != "results_limit"]
    if failed:
        logger.warning("Search summaries failed: %s", ", ".join(sorted(set(failed))))
        response.warnings.append(SUMMARY_FAILED_WARNING)
    response.time_spent = time() - start
    return response


def public_retriever(backends: SearchBackends, vector: str | None = None) -> Retriever:
    """Retrieval over the public corpus for callers without a user (RAG).

    Requests with a collection or tags are refused like anonymous ones. With ``vector``,
    every request uses that search vector, whatever it selects itself; without it, the
    request's own selection (by default the default vector) applies.
    """
    if vector is None:
        return partial(retrieve, backends, None)

    async def run(request: SearchRequest) -> SearchResponse:
        return await retrieve(backends, None, request.model_copy(update={"vector": vector}))
    return run


def filter_conditions(request: SearchRequest,
                      filter_definitions: SearchFiltersResponse | None) -> list[FieldCondition]:
    conditions = None
    if filter_definitions is not None:
        try:
            conditions = parse_and_validate_search_filters(request.filters, filter_definitions)
        except InvalidSearchFilterError:
            raise
        except ValueError as e:
            raise InvalidRequestError(str(e)) from e
    if conditions is not None:
        return conditions

    # Legacy request fields, used when no filters were requested.
    conditions = []
    if request.min_year:
        conditions.append(FieldCondition("yearIssued", Op.greater_or_equal, request.min_year))
    if request.max_year:
        conditions.append(FieldCondition("yearIssued", Op.less_or_equal, request.max_year))
    if request.language:
        conditions.append(FieldCondition("language", Op.equal, request.language))
    return conditions


async def _embed(vector: SearchVector, request: SearchRequest) -> list[float] | None:
    if request.type == SearchType.text:
        return None
    if request.is_hyde:
        return await vector.embedder.embed_document(request.query)
    return await vector.embedder.embed_query(request.query)


def display_text(text: str) -> str:
    """Chunk text as search shows it: hyphenated line breaks joined, other breaks as spaces.

    Display only; stored text and its offsets are unchanged.
    """
    return text.replace("-\n", "").replace("\n", " ")
