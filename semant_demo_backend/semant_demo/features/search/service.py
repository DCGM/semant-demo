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

Documents (``search_documents``, #606, #607): the filters decide which documents are eligible
(chunk filters per dimension, on the documents' chunk-value summaries); a text query ranks them,
metadata matches first, then by their best chunk, which need not satisfy the chunk filters.
"""
import asyncio
import logging
from dataclasses import dataclass
from functools import partial
from time import time
from typing import Awaitable, Callable, Protocol
from uuid import UUID

from semant_demo.adapters.llm.usage import OperationBudget
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.adapters.weaviate.search import ChunkSearchRepository
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.core.errors import InvalidRequestError
from semant_demo.features.quota.schemas import QuotaExhaustedResponse
from semant_demo.features.quota.service import QuotaExhausted
from semant_demo.features.user_collections import access
from semant_demo.features.user_collections.access import Principal
from semant_demo.features.documents import service as document_service
from semant_demo.features.documents.criteria import (
    ChunkFilters, ChunkVocabulary, Condition, DocumentFilters, SearchCriteria, chunk_conditions, document_conditions,
    validate_chunk_filters)
from semant_demo.features.search.filters import (
    InvalidSearchFilterError, chunk_vocabulary, parse_and_validate_search_filters)
from semant_demo.features.search.schemas import (
    ChunkQuery, DocumentHit, DocumentReadRequest, DocumentReadResponse, DocumentRetrieval, DocumentSearchRequest,
    DocumentSearchResponse, FieldCondition, RankedDocument, Op, PassageReadRequest, PassageReadResponse, PassageSearchRequest, PassageSearchResponse,
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


@dataclass(frozen=True)
class DocumentLimits:
    """The technical bounds of document search (``config.py``)."""
    browse: int
    """Most documents a search without a text query can page through (``QUERY_MAXIMUM_RESULTS``)."""
    metadata: int
    """``SEARCH_DOCUMENTS_METADATA_LIMIT``."""
    chunks: int
    """``SEARCH_DOCUMENTS_CHUNK_LIMIT``."""


async def search_documents(documents: DocumentRepository, backends: SearchBackends, user: Principal | None,
                           request: DocumentSearchRequest, vocabulary: ChunkVocabulary,
                           limits: DocumentLimits) -> DocumentSearchResponse:
    """Documents matching search criteria (#606, #607), with what the result covers.

    The filters decide which documents are eligible, as for document browsing and Analytics
    (``documents.service.browse_scope``): document filters on the document, chunk filters per
    dimension on its chunk-value summaries. Without a text query those are the results, paged in
    a stable order (``_browse_documents``); with one, they are ranked (``_rank_documents``).
    """
    start = time()
    criteria = request.criteria
    chunk_filters = criteria.chunk_filters
    if not chunk_filters.is_empty():
        chunk_filters = validate_chunk_filters(chunk_filters, vocabulary)
    criteria = criteria.model_copy(update={"chunk_filters": chunk_filters})
    if criteria.text_query is None:
        response = await _browse_documents(documents, backends.collections, user, request, criteria, vocabulary,
                                           limits.browse)
    else:
        response = await _rank_documents(documents, backends, user, request, criteria, vocabulary, limits)
    response.time_spent = time() - start
    return response


async def _browse_documents(documents: DocumentRepository, collections: UserCollectionRepository,
                            user: Principal | None, request: DocumentSearchRequest, criteria: SearchCriteria,
                            vocabulary: ChunkVocabulary, retrieval_limit: int) -> DocumentSearchResponse:
    """Without a text query (#606): one page in a stable order (``documents.service.browse_by_year``),
    with the exact number of matching documents. Only the first ``retrieval_limit`` documents in
    that order can be read (Weaviate's ``QUERY_MAXIMUM_RESULTS``): a page past it is refused, and
    ``bounded`` says when more match."""
    if request.offset + request.limit > retrieval_limit:
        raise InvalidRequestError(
            f"Only the first {retrieval_limit} matching documents can be listed; narrow the filters to reach others.")
    page = await document_service.browse_by_year(
        documents, collections, user, request.user_collection_id, filters=criteria.document_filters,
        chunk_filters=criteria.chunk_filters, vocabulary=vocabulary, limit=request.limit, offset=request.offset)
    end = request.offset + request.limit
    return DocumentSearchResponse(
        items=[DocumentHit(document=document) for document in page.items],
        offset=request.offset,
        next_offset=end if end < min(page.total_count, retrieval_limit) else None,
        total_count=page.total_count,
        eligible_count=page.total_count,
        retrieval_limit=retrieval_limit,
        bounded=page.total_count > retrieval_limit,
        order="year_asc",
        criteria=criteria,
        time_spent=0,
    )


async def _rank_documents(documents: DocumentRepository, backends: SearchBackends, user: Principal | None,
                          request: DocumentSearchRequest, criteria: SearchCriteria, vocabulary: ChunkVocabulary,
                          limits: DocumentLimits) -> DocumentSearchResponse:
    """A text query (#607): one ranking of distinct eligible documents, and its first page.

    Eligibility restricts both retrievals inside the query, before any limit applies; the text
    query only ranks. First the documents whose metadata holds every word of the query, by BM25
    relevance (``DocumentRepository.metadata_ranked_ids``, at most ``limits.metadata``). Then the
    other eligible documents in the order of their best chunk in the chunk ranking (BM25, vector or
    hybrid, as for passages): the best ``limits.chunks`` chunks of eligible documents, whatever
    the chunk filters say of the chunk itself (``ChunkSearchRepository.ranked_documents``), each
    document where it first appears. No score fusion. Both read one more than their limit, to tell
    whether it cut them; then ``total_count`` is unknown. A ranking of chunks rather than
    Weaviate's ``group_by``, which does not group BM25 or hybrid results by a reference (1.40.1).
    Later pages are slices of the ranking (``read_documents``), never rankings of their own, as
    for passages (#611).
    """
    vector = backends.vectors.resolve(request.vector)
    scope, conditions = await document_service.browse_scope(
        backends.collections, user, request.user_collection_id, criteria.document_filters, criteria.chunk_filters,
        vocabulary)
    text = criteria.text_query or ""
    chunk_query = ChunkQuery(
        text=text, mode=request.type, limit=limits.chunks + 1, alpha=request.hybrid_search_alpha,
        document_collection_id=scope, document_conditions=tuple(conditions),
        vector=await _embed_text(vector, request.type, text),
        target_vector=None if request.type == SearchType.text else vector.target_vector)
    eligible, metadata_ids, chunk_pairs = await asyncio.gather(
        documents.count(scope, conditions),
        documents.metadata_ranked_ids(text, limits.metadata + 1, scope, conditions),
        backends.chunks.ranked_documents(chunk_query))
    metadata_bounded = len(metadata_ids) > limits.metadata
    chunk_bounded = len(chunk_pairs) > limits.chunks
    chunk_pairs = chunk_pairs[:limits.chunks]
    best_chunk: dict[UUID, UUID] = {}
    for chunk_id, document_id in chunk_pairs:
        best_chunk.setdefault(document_id, chunk_id)
    metadata = list(dict.fromkeys(metadata_ids[:limits.metadata]))
    matched = set(metadata)
    ranked = [RankedDocument(id=d, match="metadata", chunk_id=best_chunk.get(d)) for d in metadata]
    ranked += [RankedDocument(id=d, match="text", chunk_id=c) for d, c in best_chunk.items() if d not in matched]
    bounded = metadata_bounded or chunk_bounded
    read_count = min(request.limit, len(ranked))
    items = await _read_ranked(documents, backends.chunks, ranked[:read_count], scope, conditions)
    return DocumentSearchResponse(
        items=items,
        offset=0,
        next_offset=None,
        total_count=None if bounded else len(ranked),
        eligible_count=eligible,
        retrieval_limit=limits.metadata + limits.chunks,
        bounded=bounded,
        order="metadata_then_text",
        ranked=ranked,
        read_count=read_count,
        retrieval=DocumentRetrieval(
            metadata_limit=limits.metadata, metadata_bounded=metadata_bounded, chunk_limit=limits.chunks,
            chunk_bounded=chunk_bounded, ranked_chunks=len(chunk_pairs), type=request.type,
            vector=None if request.type == SearchType.text else vector.id),
        criteria=criteria,
        time_spent=0,
    )


async def read_documents(documents: DocumentRepository, backends: SearchBackends, user: Principal | None,
                         request: DocumentReadRequest, vocabulary: ChunkVocabulary) -> DocumentReadResponse:
    """Documents of an earlier text-query document search by their ranking entries (#607): a later
    page of its ``ranked``. The entries come from the client, so nothing about them is trusted:
    access and the criteria are checked again, and documents and chunks are read under the
    search's eligibility (``_read_ranked``). Nothing is ranked or embedded."""
    start = time()
    criteria = request.criteria
    scope, conditions = await document_service.browse_scope(
        backends.collections, user, request.user_collection_id, criteria.document_filters, criteria.chunk_filters,
        vocabulary)
    items = await _read_ranked(documents, backends.chunks, request.ranked, scope, conditions)
    return DocumentReadResponse(items=items, time_spent=time() - start)


async def _read_ranked(documents: DocumentRepository, chunks: ChunkSearchRepository, entries: list[RankedDocument],
                       scope: UUID | None, conditions: list[Condition]) -> list[DocumentHit]:
    """The ranked documents that are (still) eligible, in the order of ``entries``, each once,
    with their evidence chunk: read only among the chunks of eligible documents and kept only when
    it belongs to the entry's document; a chunk gone meanwhile leaves the document without one."""
    first: dict[UUID, RankedDocument] = {}
    for entry in entries:
        first.setdefault(entry.id, entry)
    entries = list(first.values())
    found = await documents.read_eligible([entry.id for entry in entries], scope, conditions)
    chunk_ids = [entry.chunk_id for entry in entries if entry.chunk_id is not None and entry.id in found]
    hits = await chunks.read_hits(chunk_ids, ChunkQuery(
        text="", mode=SearchType.text, limit=len(chunk_ids), document_collection_id=scope,
        document_conditions=tuple(conditions)))
    by_id = {hit.id: hit for hit in hits}
    items = []
    for entry in entries:
        document = found.get(entry.id)
        if document is None:
            continue
        chunk = by_id.get(entry.chunk_id) if entry.chunk_id is not None else None
        if chunk is not None and chunk.document != entry.id:
            chunk = None
        if chunk is not None:
            chunk.text = display_text(chunk.text)
        items.append(DocumentHit(document=document, match=entry.match, chunk=chunk))
    return items


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
    if request.is_hyde and request.type != SearchType.text:
        return await vector.embedder.embed_document(request.query)
    return await _embed_text(vector, request.type, request.query)


async def _embed_text(vector: SearchVector, mode: SearchType, text: str) -> list[float] | None:
    """The query embedding of vector and hybrid search; None for text search."""
    if mode == SearchType.text:
        return None
    return await vector.embedder.embed_query(text)


def display_text(text: str) -> str:
    """Chunk text as search shows it: hyphenated line breaks joined, other breaks as spaces.

    Display only; stored text and its offsets are unchanged.
    """
    return text.replace("-\n", "").replace("\n", " ")
