"""Chunks with their stored positions (#463) for fakes of ``DocumentRepository``."""
from semant_demo.features.annotations.schemas import AnnotationChunk
from semant_demo.features.documents.positions import chunk_positions


def positioned(chunks: list[AnnotationChunk]) -> list[AnnotationChunk]:
    """The chunks with the positions the shared calculator gives them in their documents
    (each document's chunks taken in ``order``), in the given order."""
    positions = {}
    for document in {c.document_id for c in chunks}:
        ordered = sorted((c for c in chunks if c.document_id == document), key=lambda c: c.order)
        positions.update({c.id: p for c, p in zip(ordered, chunk_positions(c.text for c in ordered))})
    return [c.model_copy(update={"start_char": positions[c.id].start_char, "start_word": positions[c.id].start_word,
                                 "word_open_at_start": positions[c.id].word_open_at_start}) for c in chunks]


def in_range(chunks: list[AnnotationChunk], document_id, first: int, last: int) -> list[AnnotationChunk]:
    """``DocumentRepository.read_chunk_texts_in_range`` over ``chunks``."""
    return sorted((c for c in chunks if c.document_id == document_id and first <= c.order <= last),
                  key=lambda c: c.order)
