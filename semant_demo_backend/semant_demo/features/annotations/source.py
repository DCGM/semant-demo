"""The source chunks of a span (#463): what checking and deriving it reads.

A span is checked and derived from its anchor chunk (read by id) and the chunks next to it
(read by narrow ``order`` ranges of its document, ``NEIGHBOR_PAGE`` orders per query, no
server-side sort): the chunks it covers and as many before and after it as its context
needs (``derivation.SpanSource``). The work therefore depends on the span and its context,
never on the length of the document. The anchor's stored position tells whether text
precedes it (``startChar`` 0: the document start); a range with fewer chunks than orders
after the span is the document end.

A ``ChunkSource`` keeps what it read (source text does not change), so the many spans of
an AI suggestion run or a backfill read shared chunks once; the cache is bounded and
simply emptied when full.
"""
from uuid import UUID

from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.features.annotations import derivation
from semant_demo.features.annotations.derivation import SpanSource, position_of
from semant_demo.features.annotations.offsets import InvalidSpanRange, code_point_offset
from semant_demo.features.annotations.schemas import AnnotationChunk
from semant_demo.features.documents.positions import text_length

NEIGHBOR_PAGE = 4
"""Chunk orders read per query before or after a span."""

CACHE_LIMIT = 4096
"""Chunks a ``ChunkSource`` keeps at most."""


class InvalidDocumentChunks(Exception):
    """The chunk orders around a span are not consecutive (a gap or a duplicate order): the
    document violates the text model and its spans are not derived (``derive_annotation``)."""


def _consecutive(chunks: list[AnnotationChunk]) -> bool:
    return all(b.order == a.order + 1 for a, b in zip(chunks, chunks[1:]))


def _run_after(chunk: AnnotationChunk, page: list[AnnotationChunk]) -> list[AnnotationChunk]:
    """The chunks of ``page`` that follow ``chunk`` without a gap or a duplicate order."""
    run = []
    for c in page:
        if c.order != (run[-1] if run else chunk).order + 1:
            break
        run.append(c)
    return run


class ChunkSource:
    def __init__(self, documents: DocumentRepository, cache_limit: int = CACHE_LIMIT):
        self.documents = documents
        self.cache_limit = cache_limit
        self._by_id: dict[UUID, AnnotationChunk] = {}
        self._by_order: dict[tuple[UUID, int], AnnotationChunk | None] = {}
        """``None``: the document has no chunk with this order."""

    def _remember(self, chunks: list[AnnotationChunk]) -> None:
        if len(self._by_id) + len(self._by_order) + len(chunks) > self.cache_limit:
            self._by_id.clear()
            self._by_order.clear()
        for chunk in chunks:
            self._by_id[chunk.id] = chunk

    async def chunk(self, chunk_id: UUID) -> AnnotationChunk | None:
        """The chunk with its document, order, text and position, or None if it does not exist."""
        if chunk_id not in self._by_id:
            chunk = await self.documents.read_chunk_text(chunk_id)
            if chunk is None:
                return None
            self._remember([chunk])
        return self._by_id[chunk_id]

    async def range(self, document_id: UUID, first: int, last: int) -> list[AnnotationChunk]:
        """The document's chunks with ``first <= order <= last``, in order (duplicate orders
        included)."""
        keys = [(document_id, order) for order in range(first, last + 1)]
        if all(key in self._by_order for key in keys):
            return [c for key in keys if (c := self._by_order[key]) is not None]
        chunks = await self.documents.read_chunk_texts_in_range(document_id, first, last)
        if len({c.order for c in chunks}) == len(chunks):
            self._remember(chunks)
            found = {c.order: c for c in chunks}
            self._by_order.update({key: found.get(key[1]) for key in keys})
        return chunks

    async def covering(self, anchor: AnnotationChunk, end: int) -> list[AnnotationChunk]:
        """The anchor and the following chunks until ``end`` UTF-16 units from the anchor
        start are covered or the chunks end (also at a gap, as read: ``check_span_range``
        tells a gap from the document end)."""
        chunks, covered = [anchor], text_length(anchor.text)
        while covered < end and anchor.document_id is not None:
            page = await self.range(anchor.document_id, chunks[-1].order + 1, chunks[-1].order + NEIGHBOR_PAGE)
            chunks += page
            covered += sum(text_length(c.text) for c in page)
            if len(page) < NEIGHBOR_PAGE or not _consecutive(chunks):
                break
        return chunks

    async def span_source(self, anchor: AnnotationChunk, start: int, end: int) -> SpanSource:
        """The chunks deriving the span anchored on ``anchor`` reads (``derivation.SpanSource``).

        Raises ``InvalidSpanRange`` when the span itself crosses a gap,
        ``InvalidDocumentChunks`` when its context does, and ``MissingChunkPositions`` when
        a chunk before the anchor has no position.
        """
        document_id = anchor.document_id
        if document_id is None:
            raise InvalidSpanRange("missing_anchor", "The span's chunk belongs to no document")
        position_of(anchor)
        after, at_end = [anchor], False
        while True:
            local = "".join(c.text for c in after)
            if text_length(local) >= end and len(local) - code_point_offset(local, end) > derivation.CONTEXT_CHARS:
                break
            last = after[-1].order
            page = await self.range(document_id, last + 1, last + NEIGHBOR_PAGE)
            run = _run_after(after[-1], page)
            if run != page:
                if text_length(local + "".join(c.text for c in run)) < end:
                    raise InvalidSpanRange("gap", "Span crosses a gap between the document's chunks")
                raise InvalidDocumentChunks(f"The chunk orders of document {document_id} after {last} are not "
                                            "consecutive")
            after += page
            if len(page) < NEIGHBOR_PAGE:
                at_end = True
                break

        before: list[AnnotationChunk] = []
        a = code_point_offset(anchor.text, start)
        while position_of(before[0] if before else anchor).start_char > 0 \
                and sum(len(c.text) for c in before) + a <= derivation.CONTEXT_CHARS:
            first = (before[0] if before else anchor).order
            page = await self.range(document_id, first - NEIGHBOR_PAGE, first - 1)
            if not page or not _consecutive([*page, before[0] if before else anchor]):
                raise InvalidDocumentChunks(f"The chunk orders of document {document_id} before {first} are not "
                                            "consecutive")
            before = page + before
        at_start = position_of(before[0] if before else anchor).start_char == 0
        return SpanSource(before + after, len(before), at_start, at_end)
