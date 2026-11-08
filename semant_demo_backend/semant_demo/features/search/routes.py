from fastapi import APIRouter, Depends, HTTPException

from semant_demo.adapters.weaviate.criteria import UnavailableFilter
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.config import MAX_QUERY_RESULTS, Config
from semant_demo.features.documents.criteria import ChunkVocabulary
from semant_demo.features.search.schemas import (
    DocumentReadRequest, DocumentReadResponse, DocumentSearchRequest, DocumentSearchResponse, PassageReadRequest, PassageReadResponse, PassageSearchRequest, PassageSearchResponse, SearchFiltersResponse,
    SearchRequest, SearchResponse,
    SearchVectorsResponse)

from semant_demo.features.quota.principal import get_allowance_budget
from semant_demo.features.quota.service import AllowanceBudget
from semant_demo.features.search import service
from semant_demo.features.search.service import DocumentLimits, SearchBackends
from semant_demo.features.search.vectors import SearchVectors
from semant_demo.routes.dependencies import (
    get_chunk_vocabulary, get_config, get_documents, get_search_backends, get_summarizer, get_search_filters,
    get_search_vectors)
from semant_demo.users.auth import current_active_optional_user
from semant_demo.users.models import User

exp_router = APIRouter()


@exp_router.get("/api/search/filters", response_model=SearchFiltersResponse)
async def get_available_search_filters(
    filters_response: SearchFiltersResponse = Depends(get_search_filters),
) -> SearchFiltersResponse:
    return filters_response


@exp_router.get("/api/search/vectors", response_model=SearchVectorsResponse)
async def get_available_search_vectors(vectors: SearchVectors = Depends(get_search_vectors)) -> SearchVectorsResponse:
    """The search vectors a search request may select, and the default one."""
    return vectors.describe()


@exp_router.post("/api/search", response_model=SearchResponse)
async def search(req: SearchRequest, backends: SearchBackends = Depends(get_search_backends),
                 summarizer: service.Summarizer = Depends(get_summarizer),
                 current_user: User | None = Depends(current_active_optional_user),
                 available_filters: SearchFiltersResponse = Depends(get_search_filters),
                 budget: AllowanceBudget = Depends(get_allowance_budget)) -> SearchResponse:
    """Retrieval, plus the titles and summaries asked for. Those are skipped with a warning
    (``quota_exhausted``) when the daily AI allowance has no room; the results are not.
    A document or chunk filter on a property this corpus database does not record is rejected
    (422), never answered with no results."""
    try:
        return await service.search(backends, summarizer, current_user, req, available_filters, budget)
    except UnavailableFilter as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@exp_router.post("/api/search/passages", response_model=PassageSearchResponse)
async def search_passages(req: PassageSearchRequest, backends: SearchBackends = Depends(get_search_backends),
                          current_user: User | None = Depends(current_active_optional_user),
                          available_filters: SearchFiltersResponse = Depends(get_search_filters),
                          config: Config = Depends(get_config)) -> PassageSearchResponse:
    """The passages matching the search criteria (#605, #611): the ids of the ranked chunks,
    every chunk filter holding on the chunk itself, at most ``SEARCH_PASSAGES_LIMIT``, with what
    they cover, and the first page of them in full. Later pages are read by id
    (``POST /api/search/passages/read``), not ranked again. No generated titles or summaries.
    A filter on a property this corpus database does not record is rejected (422)."""
    try:
        return await service.search_passages(backends, current_user, req, available_filters,
                                             config.SEARCH_PASSAGES_LIMIT)
    except UnavailableFilter as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@exp_router.post("/api/search/passages/read", response_model=PassageReadResponse)
async def read_passages(req: PassageReadRequest, backends: SearchBackends = Depends(get_search_backends),
                        current_user: User | None = Depends(current_active_optional_user),
                        available_filters: SearchFiltersResponse = Depends(get_search_filters),
                        ) -> PassageReadResponse:
    """A later page of a passage search (#611): the passages of up to 100 of its ranked ids, in
    that order, read under the search's criteria and collection again (access checked again);
    ids that do not match them, or whose chunk is gone, are left out. Nothing is ranked."""
    try:
        return await service.read_passages(backends, current_user, req, available_filters)
    except UnavailableFilter as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@exp_router.post("/api/search/documents", response_model=DocumentSearchResponse)
async def search_documents(req: DocumentSearchRequest, documents: DocumentRepository = Depends(get_documents),
                           backends: SearchBackends = Depends(get_search_backends),
                           vocabulary: ChunkVocabulary = Depends(get_chunk_vocabulary),
                           current_user: User | None = Depends(current_active_optional_user),
                           config: Config = Depends(get_config),
                           ) -> DocumentSearchResponse:
    """The documents matching search criteria, with the exact number of eligible documents. The
    filters select the same documents as ``GET /api/documents/browse`` and Analytics: chunk filters
    apply per dimension to the documents' chunk-value summaries.

    Without a text query (#606): one page, ordered by publication year (oldest first, then id;
    documents without a year last); only the first ``QUERY_MAXIMUM_RESULTS`` (10 000) can be
    paged through (``bounded``), and a page past them is refused (400).

    With a text query (#607): the ranking of distinct eligible documents, once, and its first
    page: the documents whose metadata holds every word of the query first, then the others by
    their best-matching chunk (which need not satisfy the chunk filters), each with that chunk
    as evidence. At most ``SEARCH_DOCUMENTS_METADATA_LIMIT`` metadata matches and
    ``SEARCH_DOCUMENTS_CHUNK_LIMIT`` ranked chunks (``bounded``, ``retrieval``); later pages
    are read by id (``POST /api/search/documents/read``).

    A filter on a property this corpus database does not record, also a chunk filter without the
    summaries, is rejected (422); an unconfigured chunk filter value is refused (400)."""
    limits = DocumentLimits(browse=MAX_QUERY_RESULTS, metadata=config.SEARCH_DOCUMENTS_METADATA_LIMIT,
                            chunks=config.SEARCH_DOCUMENTS_CHUNK_LIMIT)
    try:
        return await service.search_documents(documents, backends, current_user, req, vocabulary, limits)
    except UnavailableFilter as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@exp_router.post("/api/search/documents/read", response_model=DocumentReadResponse)
async def read_documents(req: DocumentReadRequest, documents: DocumentRepository = Depends(get_documents),
                         backends: SearchBackends = Depends(get_search_backends),
                         vocabulary: ChunkVocabulary = Depends(get_chunk_vocabulary),
                         current_user: User | None = Depends(current_active_optional_user),
                         ) -> DocumentReadResponse:
    """A later page of a text-query document search (#607): up to 100 of its ranked documents, in
    that order, with their evidence chunks, read under the search's criteria and collection again
    (access checked again); documents no longer eligible, or gone, are left out, and a chunk is
    returned only for its own document. Nothing is ranked."""
    try:
        return await service.read_documents(documents, backends, current_user, req, vocabulary)
    except UnavailableFilter as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
