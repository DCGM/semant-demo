"""Search use cases: authorized chunk retrieval and optional summaries.

``retrieve`` checks access, normalizes the request into a neutral ``ChunkQuery``, embeds
the query for vector/hybrid search with the embedder of the selected (or default) search
vector (``vectors.py``) and runs it through the search adapter against that vector. RAG
uses it directly, without summaries. ``search`` adds the optional summaries; when some or
all of them fail, the retrieved hits are still returned, with a warning. The summaries are
one AI operation admitted against the caller's daily allowance; when it has no room, they
are skipped and the hits are returned with a quota warning, never a 429.

Access (ADR 0007): a ``user_collection_id`` needs read access to that collection, and
every requested tag must belong to a collection the user can read (to that collection,
if one is given). Without either, search covers the public corpus, also anonymously.
Restrictions are applied inside the retrieval query, never by dropping hits afterwards.

Filters: the shared search criteria (``document_filters``, ``chunk_filters``;
``features/documents/criteria.py``) or, for existing clients, the older ``filters`` and
``min_year``/``max_year``/``language`` fields; a request mixing them is refused. Chunk filters
must all hold on the returned chunk (same-chunk), and document filters on its document.
"""
import logging
from dataclasses import dataclass
from functools import partial
from time import time
from typing import Awaitable, Callable, Protocol

from semant_demo.adapters.llm.usage import OperationBudget
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.adapters.weaviate.search import ChunkSearchRepository
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.core.errors import InvalidRequestError
from semant_demo.features.quota.schemas import QuotaExhaustedResponse
from semant_demo.features.quota.service import QuotaExhausted
from semant_demo.features.user_collections import access
from semant_demo.features.user_collections.access import Principal
from semant_demo.features.documents.criteria import (
    ChunkFilters, Condition, DocumentFilters, SearchCriteria, chunk_conditions, document_conditions,
    validate_chunk_filters)
from semant_demo.features.search.filters import (
    InvalidSearchFilterError, chunk_vocabulary, parse_and_validate_search_filters)
from semant_demo.features.search.schemas import (
    ChunkQuery, FieldCondition, Op, PassageReadRequest, PassageReadResponse, PassageSearchRequest, PassageSearchResponse,
    SearchFiltersResponse, SearchRequest,
    SearchResponse, SearchType, TagFilter,
)
from semant_demo.features.search.vectors import SearchVector, SearchVectors

logger = logging.getLogger(__name__)

SUMMARY_FAILED_WARNING = "Some titles or summaries could not be generated."
SUMMARY_LIMITED_WARNING = "Titles and result summaries were generated only for the first results."
SUMMARY_QUOTA_WARNING = "Titles and summaries were not generated. "
"""Followed by the ``QuotaExhausted`` message (the reset time)."""

Retriever = Callable[[SearchRequest], Awaitable[SearchResponse]]


class Summarizer(Protocol):
    """Adds the titles and summaries ``request`` asks for to ``response`` in place
    (``features/summarization``) as one operation admitted by ``budget``; returns the kinds
    of the parts that failed."""

    async def __call__(self, request: SearchRequest, response: SearchResponse,
                       budget: OperationBudget | None = None) -> list[str]: ...


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

    ``filter_definitions`` (the configured search filters) validate ``request.chunk_filters``
    and ``request.filters``; without definitions or requested ``filters``, the legacy
    ``min_year``/``max_year``/``language`` fields apply instead. The response echoes the
    request with its criteria filters normalized.
    """
    start = time()
    request, query, vector = await _authorized_query(backends, user, request, filter_definitions)
    hits = await backends.chunks.search(query)
    for hit in hits:
        hit.text = display_text(hit.text)

    elapsed = time() - start
    log_entry = f"Top {len(hits)} results for “{request.query}”. Retrieved in {elapsed:.2f} seconds:"
    # Content-free: RAG retrieves with the user's (rephrased) question.
    logger.info("Search returned %d results in %.2f s", len(hits), elapsed)
    return SearchResponse(results=hits, search_request=request, time_spent=elapsed, search_log=[log_entry],
                          vector=None if request.type == SearchType.text else vector.id)


async def _authorized_query(backends: SearchBackends, user: Principal | None, request: SearchRequest,
                            filter_definitions: SearchFiltersResponse | None,
                            ) -> tuple[SearchRequest, ChunkQuery, SearchVector]:
    """The request with normalized criteria filters, its neutral query (embedded) and the
    search vector used; access and filters are checked first, before any embedding."""
    request, criteria = criteria_conditions(request, filter_definitions)
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
        conditions=() if criteria is not None else tuple(filter_conditions(request, filter_definitions)),
        document_conditions=tuple(criteria[0]) if criteria is not None else (),
        chunk_conditions=tuple(criteria[1]) if criteria is not None else (),
        vector=await _embed(vector, request),
        target_vector=None if request.type == SearchType.text else vector.target_vector,
    )
    return request, query, vector


async def search(backends: SearchBackends, summarizer: Summarizer, user: Principal | None,
                 request: SearchRequest, filter_definitions: SearchFiltersResponse | None = None,
                 budget: OperationBudget | None = None) -> SearchResponse:
    """Retrieval plus the summaries the request asks for.

    When a title or summary cannot be generated (the summarizer reports it and keeps its
    fallback text) or the summarizer fails altogether, the hits and the summaries made so
    far are kept and ``SUMMARY_FAILED_WARNING`` is added. When only the first results got
    titles and summaries (the summarizer's ``results_limit``), ``SUMMARY_LIMITED_WARNING``
    is added. When ``budget`` refuses the summaries (``QuotaExhausted``), none are generated:
    ``quota_exhausted`` is set and ``SUMMARY_QUOTA_WARNING`` added. Retrieval errors propagate.
    """
    start = time()
    response = await retrieve(backends, user, request, filter_definitions)
    try:
        failed = await summarizer(request, response, budget)
    except QuotaExhausted as e:
        failed = []
        response.quota_exhausted = QuotaExhaustedResponse.model_validate(e.body())
        response.warnings.append(SUMMARY_QUOTA_WARNING + str(e))
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


async def search_passages(backends: SearchBackends, user: Principal | None, request: PassageSearchRequest,
                          filter_definitions: SearchFiltersResponse | None, retrieval_limit: int,
                          ) -> PassageSearchResponse:
    """A passage search (#605, #611): its ranking, once, and its first page; access, vector
    selection and filter validation as in ``retrieve``.

    The ranking is the ids of the best ``retrieval_limit`` passages (one more, to tell whether
    the limit cut it), read without properties; only the first ``request.limit`` of them are
    read in full. Later pages are slices of these ids (``read_passages``), never rankings of
    their own: Weaviate's hybrid ranking depends on the limit and hybrid ``offset`` does not
    reach past its first results (measured on 1.40.1), which would skip or repeat passages, and
    ranking again for every page repeats the costliest step. Passages whose chunk is gone or
    has no document by the time they are read are left out of the page.
    """
    start = time()
    criteria = request.criteria
    normalized, query, vector = await _passage_query(
        backends, user, criteria, request.user_collection_id, filter_definitions, limit=retrieval_limit + 1,
        type=request.type, hybrid_search_alpha=request.hybrid_search_alpha, vector=request.vector)
    ranked = list(dict.fromkeys(await backends.chunks.ranked_ids(query)))  # each once, in rank order
    bounded = len(ranked) > retrieval_limit
    ranked = ranked[:retrieval_limit]
    read_count = min(request.limit, len(ranked))
    items = await backends.chunks.read_hits(ranked[:read_count], query)
    for item in items:
        item.text = display_text(item.text)
    return PassageSearchResponse(
        ranked_ids=ranked,
        items=items,
        read_count=read_count,
        retrieval_limit=retrieval_limit,
        bounded=bounded,
        total_count=None if bounded else len(ranked),
        criteria=criteria.model_copy(update={"document_filters": normalized.document_filters,
                                             "chunk_filters": normalized.chunk_filters}),
        vector=None if request.type == SearchType.text else vector.id,
        time_spent=time() - start,
    )


async def read_passages(backends: SearchBackends, user: Principal | None, request: PassageReadRequest,
                        filter_definitions: SearchFiltersResponse | None) -> PassageReadResponse:
    """Passages of an earlier passage search by id (#611): a later page of its ``ranked_ids``.

    The ids come from the client, so nothing about them is trusted: access to the collection
    is checked again, the criteria are validated again, and the passages are read under the
    same restrictions (collection, document and same-chunk filters) as the search's ranking.
    An id the search could not have returned, also one of a deleted chunk or one that no
    longer matches, is left out. Nothing is ranked or embedded.
    """
    start = time()
    _, query, _ = await _passage_query(backends, user, request.criteria, request.user_collection_id,
                                       filter_definitions, limit=len(request.ids), type=SearchType.text)
    items = await backends.chunks.read_hits(list(dict.fromkeys(request.ids)), query)
    for item in items:
        item.text = display_text(item.text)
    return PassageReadResponse(items=items, time_spent=time() - start)


async def _passage_query(backends: SearchBackends, user: Principal | None, criteria: SearchCriteria,
                         user_collection_id: str | None, filter_definitions: SearchFiltersResponse | None,
                         limit: int, **options) -> tuple[SearchRequest, ChunkQuery, SearchVector]:
    """``_authorized_query`` for the criteria of a passage search: no tags, no summaries."""
    return await _authorized_query(backends, user, SearchRequest(
        query=criteria.text_query or "",
        limit=limit,
        user_collection_id=user_collection_id,
        document_filters=criteria.document_filters,
        chunk_filters=criteria.chunk_filters,
        tag_uuids=[], positive=False, automatic=False,
        search_title_generate=False, search_summary_generate=False, search_results_summary_generate=False,
        **options,
    ), filter_definitions)


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


def criteria_conditions(request: SearchRequest, filter_definitions: SearchFiltersResponse | None,
                        ) -> tuple[SearchRequest, tuple[list[Condition], list[Condition]] | None]:
    """The request with normalized criteria filters, and their (document, chunk) predicates;
    ``None`` when the request uses the older filter fields. Raises ``InvalidRequestError`` for
    a request with both kinds, and for chunk filters that are not configured (or cannot be
    checked, without ``filter_definitions``)."""
    if request.document_filters is None and request.chunk_filters is None:
        return request, None
    if request.filters or any(value is not None for value in (
            request.min_year, request.max_year, request.min_date, request.max_date, request.language)):
        raise InvalidRequestError("Use either document_filters and chunk_filters or the older filters, min_year, "
                                  "max_year, min_date, max_date and language fields, not both.")
    documents = request.document_filters or DocumentFilters()
    chunks = request.chunk_filters or ChunkFilters()
    chunk_predicates = []
    if not chunks.is_empty():
        if filter_definitions is None:
            raise InvalidRequestError("Chunk filters are not available for this search.")
        vocabulary = chunk_vocabulary(filter_definitions)
        chunks = validate_chunk_filters(chunks, vocabulary)
        chunk_predicates = chunk_conditions(chunks, vocabulary)
    request = request.model_copy(update={"document_filters": documents, "chunk_filters": chunks})
    return request, (document_conditions(documents), chunk_predicates)


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
