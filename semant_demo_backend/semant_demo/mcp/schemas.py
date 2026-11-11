"""The MCP tools' answers (#635): small, citation-oriented projections of the feature services'
models, never their full responses (no ranked-id lists, no Weaviate types).

Text: search hits carry **display text** (``search.service.display_text``: hyphenated line breaks
joined, other breaks as spaces); passage context and page reads carry the **canonical stored
text**, the text span offsets refer to. ``text_form`` says which one a passage holds.
"""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from semant_demo.features.documents.criteria import ChunkFilters, DocumentFilters
from semant_demo.features.search.schemas import SearchType

MAX_PASSAGE_CHARS = 6000
"""Most characters of one passage's text in an answer; longer text is cut (``text_truncated``)."""


class DocumentRef(BaseModel):
    """A corpus document, as much as a citation needs. Unavailable fields are null."""
    document_id: UUID
    title: str | None
    subtitle: str | None
    authors: list[str]
    year: int | None
    """Publication year (``yearIssued``)."""
    language: str | None
    """The document's language (``Documents.language``), not necessarily that of each passage."""
    library: str | None
    """Source digital library code (e.g. ``mzk``)."""
    source_url: str | None
    """The original digitized document in its digital library (digitalniknihovna.cz); null when
    the library is not one that viewer serves, so no link can be verified."""
    semant_url: str | None
    """The document in semANT's public document view; null when the server has no public URL."""


class DocumentMetadata(DocumentRef):
    """Bibliographic metadata of a corpus document (``get_document``). Unavailable fields are null."""
    date_issued: str | None
    publisher: str | None
    place_of_publication: str | None
    part_number: str | None
    part_name: str | None
    series_name: str | None
    series_number: str | None
    edition: str | None
    document_type: str | None
    genre: str | None
    keywords: list[str]
    editors: list[str]
    translators: list[str]
    illustrators: list[str]
    description: str | None
    chunk_count: int
    """Number of text passages (chunks) of the document."""
    page_count: int | None
    """Pages in the document's page list; null when no page scans are available (text-only)."""


class Passage(BaseModel):
    """One text passage (chunk) of a document, with what a citation needs."""
    chunk_id: UUID
    document_id: UUID
    order: int | None
    """Position in the document (0-based, document order); null when unknown."""
    from_page: int
    to_page: int
    """Zero-based page indices (page-list order) the passage spans, as stored (coarse)."""
    start_page_id: UUID
    language: str | None
    """Language of this passage's text."""
    text: str
    text_form: Literal["display", "canonical"]
    """``display``: normalized for reading (search hits); ``canonical``: the stored text."""
    text_truncated: bool
    """The text was cut at ``MAX_PASSAGE_CHARS`` characters."""
    source_url: str | None
    """The original digitized document, opened at the passage's first page; null as for the document."""
    semant_url: str | None
    """The passage in semANT's public document view; null when the server has no public URL."""


class Criteria(BaseModel):
    """The filters a search applied, normalized (trimmed, de-duplicated, configured spelling)."""
    document_filters: DocumentFilters
    chunk_filters: ChunkFilters


class PassageHit(BaseModel):
    rank: int
    """1-based position in the ranking. No relevance score is reported: the search ranks without one."""
    passage: Passage
    document: DocumentRef


class PassageSearchResult(BaseModel):
    """The best passages for a text query, in rank order."""
    query: str
    mode: SearchType
    vector: str | None
    """The search vector used (null for ``text`` mode)."""
    criteria: Criteria
    hits: list[PassageHit]
    ranked_count: int
    """Passages the search ranked (at most ``retrieval_limit``); ``hits`` are the first of them."""
    retrieval_limit: int
    bounded: bool
    """True: the limit cut the ranking, more passages match; false: ``ranked_count`` is every match."""
    total_count: int | None
    """Every matching passage when not ``bounded``; otherwise null (unknown). Vector and hybrid search
    match every passage that passes the filters."""


class DocumentHitResult(BaseModel):
    rank: int
    """1-based position: in the ranking for a text query, in year order without one."""
    document: DocumentRef
    match: Literal["metadata", "text"] | None
    """For a text query: ``metadata`` (every query word is in one bibliographic field) or ``text``
    (a passage matches); null without a query."""
    best_passage: Passage | None
    """The document's best-matching passage (display text), when there is one; it need not satisfy
    the chunk filters."""


class DocumentSearchResult(BaseModel):
    """Documents matching a text query (ranked) or the filters alone (browsing by year)."""
    query: str | None
    order: Literal["year_asc", "metadata_then_text"]
    """``year_asc``: publication year, oldest first, undated last (filter-only browsing);
    ``metadata_then_text``: metadata matches first, then by best passage (text query)."""
    mode: SearchType | None
    """Retrieval mode of the text query; null without one."""
    vector: str | None
    criteria: Criteria
    hits: list[DocumentHitResult]
    offset: int
    next_offset: int | None
    """Offset of the next page of filter-only browsing; always null for a text query (its ranking
    cannot be paged here)."""
    eligible_count: int
    """Documents the filters admit; an upper bound on the matches of a text query, not their number."""
    total_count: int | None
    """Filter-only: every matching document. Text query: the number of ranked matching documents
    when no limit cut the ranking, otherwise null (unknown)."""
    ranked_count: int | None
    """Text query: documents in the (possibly bounded) ranking; null without a query."""
    bounded: bool
    """True: a retrieval limit cut the result, more documents match than can be listed."""


class PassageContext(BaseModel):
    """A passage and its neighbours in document order (canonical stored text)."""
    document: DocumentRef
    anchor_chunk_id: UUID
    passages: list[Passage]
    has_before: bool
    has_after: bool
    """Whether the document continues before the first / after the last returned passage."""
    total_chunks: int


class PageText(BaseModel):
    """The passages whose stored page range covers one page (canonical stored text). Not a page
    transcription: the ranges are coarse, so passages may begin before or continue after the page,
    and the text is OCR output."""
    document: DocumentRef
    page: int
    """Zero-based index in the document's page list, not the printed page label."""
    page_label: str | None
    """Printed page label from the page list, when available."""
    page_scans_available: bool
    """Whether the document has a page list with scans; without it, page indices come only from the
    passages' stored page ranges."""
    source_url: str | None
    """The original digitized document opened at this page; null without a page list or a served library."""
    passages: list[Passage]
    has_more: bool
    """More passages cover this page than were returned."""
