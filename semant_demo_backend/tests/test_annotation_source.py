"""The chunks a span's check and derivation read (#463, features/annotations/source.py).

A span reads its anchor by id and the chunks next to it by narrow order ranges: the same
queries and rows whatever the length of its document, and the derived data equals the
derivation from the whole text.
"""
import asyncio
from uuid import UUID

import pytest

from semant_demo.features.annotations import derivation
from semant_demo.features.annotations.derivation import MissingChunkPositions, derive
from semant_demo.features.annotations.offsets import InvalidSpanRange
from semant_demo.features.annotations.schemas import AnnotationChunk
from semant_demo.features.annotations.source import NEIGHBOR_PAGE, ChunkSource, InvalidDocumentChunks
from semant_demo.features.documents.positions import chunk_positions
from tests.test_annotation_derivation import _whole_document

DOCUMENT = UUID(int=1000)


def document(texts, first_order=0):
    return [AnnotationChunk(id=UUID(int=i + 1), document_id=DOCUMENT, order=first_order + i, text=t,
                            start_char=p.start_char, start_word=p.start_word, word_open_at_start=p.word_open_at_start)
            for i, (t, p) in enumerate(zip(texts, chunk_positions(texts)))]


class FakeDocuments:
    """Chunk reads by id and by order range, counting queries and returned rows."""

    def __init__(self, chunks):
        self.chunks = chunks
        self.queries = 0
        self.rows = 0

    async def read_chunk_text(self, chunk_id):
        self.queries += 1
        found = [c for c in self.chunks if c.id == chunk_id]
        self.rows += len(found)
        return found[0] if found else None

    async def read_chunk_texts_in_range(self, document_id, first, last):
        self.queries += 1
        found = sorted((c for c in self.chunks if c.document_id == document_id and first <= c.order <= last),
                       key=lambda c: c.order)
        self.rows += len(found)
        return found


def _derive(chunks, anchor, start, end, documents=None):
    documents = documents or FakeDocuments(chunks)

    async def run():
        source = ChunkSource(documents)
        chunk = await source.chunk(chunks[anchor].id)
        return derive(await source.span_source(chunk, start, end), start, end)
    return asyncio.run(run()), documents


@pytest.mark.parametrize("size", [10, 500, 7000])
def test_reads_do_not_grow_with_the_document(size):
    texts = [f"Odstavec {i} má nějaký text. " * 3 for i in range(size)]
    chunks = document(texts, first_order=5)
    middle = size // 2

    single, single_reads = _derive(chunks, middle, 3, 20)
    # A span over three chunks.
    across, across_reads = _derive(chunks, middle, 3, len(texts[middle]) * 2 + 5)

    assert single == _whole_document(chunks, middle, 3, 20)
    assert across == _whole_document(chunks, middle, 3, len(texts[middle]) * 2 + 5)
    assert (single_reads.queries, single_reads.rows) == (3, 1 + 2 * NEIGHBOR_PAGE)
    assert (across_reads.queries, across_reads.rows) == (3, 1 + 2 * NEIGHBOR_PAGE)


def test_context_at_the_document_boundaries_reads_no_further():
    chunks = document(["Roku 1848 ", "přijel ", "do Brna."], first_order=-3)

    first, first_reads = _derive(chunks, 0, 0, 4)
    last, _ = _derive(chunks, 2, 3, 7)

    assert (first.left_context, first.right_context) == ("", " 1848 přijel do Brna.")
    # The anchor starts at 0: nothing before it is read.
    assert first_reads.queries == 2
    assert (last.text, last.left_context, last.right_context) == ("Brna", "Roku 1848 přijel do ", ".")


def test_a_long_context_reads_more_pages(monkeypatch):
    monkeypatch.setattr(derivation, "CONTEXT_CHARS", 30)
    chunks = document(["ab "] * 40)

    derived, reads = _derive(chunks, 20, 0, 2)

    assert derived == _whole_document(chunks, 20, 0, 2)
    assert reads.queries == 1 + 3 + 3


def test_a_gap_inside_the_span_is_invalid_and_around_it_fails():
    chunks = document(["abc", "def", "ghi", "jkl"])
    chunks[2] = chunks[2].model_copy(update={"order": 7})

    with pytest.raises(InvalidSpanRange) as e:
        _derive(chunks, 0, 1, 8)
    assert e.value.code == "gap"
    with pytest.raises(InvalidDocumentChunks):
        _derive(chunks, 0, 1, 4)


def test_a_duplicate_order_fails():
    chunks = document(["abc", "def", "ghi"])
    chunks.append(chunks[1].model_copy(update={"id": UUID(int=99)}))

    with pytest.raises(InvalidDocumentChunks):
        _derive(chunks, 0, 1, 2)


def test_a_preceding_chunk_without_a_position_fails():
    chunks = document(["abc", "def", "ghi"])
    chunks[0] = chunks[0].model_copy(update={"start_char": None})

    with pytest.raises(MissingChunkPositions):
        _derive(chunks, 1, 0, 2)


def test_an_anchor_without_a_position_fails_without_reading_the_document():
    chunks = document(["abc"] * 50)
    chunks[25] = chunks[25].model_copy(update={"start_char": None, "start_word": None, "word_open_at_start": None})

    with pytest.raises(MissingChunkPositions):
        _derive(chunks, 25, 0, 2)


def test_chunks_read_once_are_reused():
    chunks = document(["Jan Novák ", "z Brna ", "a Marie ", "z Prahy."])
    documents = FakeDocuments(chunks)

    _derive(chunks, 1, 0, 6, documents)
    queries = documents.queries
    source = ChunkSource(documents)
    assert queries > 0

    async def twice():
        for _ in range(2):
            anchor = await source.chunk(chunks[2].id)
            await source.span_source(anchor, 0, 7)
    asyncio.run(twice())
    assert documents.queries - queries == 3


def test_covering_stops_at_the_end_of_the_span():
    chunks = document(["ab"] * 20)
    documents = FakeDocuments(chunks)

    covered = asyncio.run(ChunkSource(documents).covering(chunks[3], 9))

    assert [c.order for c in covered] == [3, 4, 5, 6, 7]
    assert documents.queries == 1
