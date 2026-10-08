"""
Span discussion chat (``POST /api/ai/discuss_span``).

Builds a system prompt around a single :class:`TagSpan` (its tag definition and
examples, the host document's metadata and the chunk text with surrounding context)
and streams the assistant's reply from the configured chat provider. The frontend
re-sends the full history each turn, so nothing is stored.

``prepare_discussion`` validates the request and checks collection read access before
anything is streamed, so a denied request makes no provider call. Context reads go
through the repositories; the provider is injected (``adapters/llm/responses.py``).
"""
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from semant_demo.core.errors import InvalidRequestError
from semant_demo.features.annotations.schemas import DiscussSpanRequest, SpanChatMessage, Tag, TagSpan
from semant_demo.features.annotations.service import AnnotationStore
from semant_demo.features.collections import access
from semant_demo.features.collections.access import Principal
from semant_demo.schema.chunks import ChunkText
from semant_demo.schema.documents import Document

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "You are an expert annotation assistant helping a human reviewer decide "
    "whether a highlighted span of text in a historical / scholarly document "
    "is correctly tagged.\n\n"
    "Always respond in the same language as the user's last message.\n\n"
    "You will be given:\n"
    "- the document's bibliographic metadata (title, author, year, language, ...),\n"
    "- the tag's name, definition and example usages,\n"
    "- the highlighted span (delimited with <<<SPAN>>> and <<<END_SPAN>>> markers)\n"
    "  shown inside its surrounding chunk text and a window of neighbouring\n"
    "  chunk text from the same document so you can see the wider context.\n\n"
    "Your job is to help the user decide whether the span fits the tag.\n"
    "Be concrete: cite specific words from the span, the surrounding context\n"
    "or the tag's definition / examples to back up your reasoning. Discuss\n"
    "ambiguity (e.g. polysemy: 'houba' meaning a forest mushroom vs. a board\n"
    "eraser) by leaning on the document context to disambiguate.\n\n"
    "When the user asks open-ended questions, give arguments both for and\n"
    "against the span fitting the tag, then give a tentative recommendation.\n"
    "If the user asks for a verdict, finish with one of:\n"
    "  - 'Recommendation: KEEP' — the span clearly fits.\n"
    "  - 'Recommendation: REMOVE' — the span does not fit.\n"
    "  - 'Recommendation: UNCERTAIN' — genuinely ambiguous; explain why.\n"
    "Do not invent facts about the document; if a metadata field is missing,\n"
    "say so. Keep replies focused and reasonably concise (a few short\n"
    "paragraphs at most)."
)

# Following chunks read at once when a span continues past its first chunk.
_FOLLOWING_CHUNKS = 8


class ChatProvider(Protocol):
    def stream(self, instructions: str, messages: list[dict[str, str]]) -> AsyncIterator[str]: ...


def _format_metadata(doc: Document | None) -> str:
    """Render document metadata as a compact bullet list."""
    if doc is None:
        return "(document metadata unavailable)"

    fields: list[tuple[str, Any]] = [
        ("Title", doc.title),
        ("Subtitle", doc.subtitle),
        ("Author(s)", ", ".join(doc.author) if doc.author else None),
        ("Editor(s)", ", ".join(doc.editors) if doc.editors else None),
        ("Translator(s)", ", ".join(doc.translators) if doc.translators else None),
        ("Publisher", doc.publisher),
        ("Place of publication", doc.placeOfPublication),
        ("Year", doc.yearIssued),
        ("Language", doc.language),
        ("Document type", doc.documentType),
        ("Series", doc.seriesName),
        ("Edition", doc.edition),
        ("Keywords", ", ".join(doc.keywords) if doc.keywords else None),
    ]
    lines = [f"- {label}: {value}" for label, value in fields if value]
    return "\n".join(lines) if lines else "(no metadata fields populated)"


async def _chunks_in_range(store: AnnotationStore, document_id: UUID, min_order: int,
                           max_order: int) -> list[ChunkText]:
    """Chunks of the document with ``min_order <= order <= max_order``, ascending."""
    if max_order < min_order:
        return []
    chunks = await store.documents.read_following_chunk_texts(document_id, min_order - 1,
                                                              max_order - min_order + 1)
    return [c for c in chunks if c.order <= max_order]


async def _assemble_chunks_covering_span(
    store: AnnotationStore,
    *,
    document_id: UUID | None,
    first_chunk_text: str,
    first_chunk_order: int | None,
    span_end: int,
) -> tuple[str, list[int]]:
    """
    Build a contiguous string from the chunks the span occupies. Starts at the first
    chunk (``span.chunkId``) and appends consecutive following chunks until the running
    length covers ``span_end`` (a cross-chunk span's ``end`` is measured across the
    concatenation of the chunks it spans, ADR 0006).

    Returns ``(assembled_text, consumed_orders)`` where ``consumed_orders`` lists the
    orders of all chunks that contributed (including the first).
    """
    consumed: list[int] = []
    if first_chunk_order is not None:
        consumed.append(first_chunk_order)
    assembled = first_chunk_text

    if span_end <= len(assembled) or document_id is None or first_chunk_order is None:
        return assembled, consumed

    next_chunks = await _chunks_in_range(store, document_id, first_chunk_order + 1,
                                         first_chunk_order + _FOLLOWING_CHUNKS)
    for c in next_chunks:
        assembled += c.text
        consumed.append(c.order)
        if len(assembled) >= span_end:
            break
    return assembled, consumed


def _trim_context(text: str, span_start: int, span_end: int, window: int) -> tuple[str, str]:
    """``window`` characters of ``text`` before and after the span."""
    if window <= 0:
        return "", ""
    before_start = max(0, span_start - window)
    after_end = min(len(text), span_end + window)
    return text[before_start:span_start], text[span_end:after_end]


async def build_context_message(store: AnnotationStore, *, span: TagSpan, context_chars: int) -> str:
    """
    The per-conversation context block (document metadata, tag and the span in its
    surrounding text) added to the instructions. Missing tag, document or neighbour
    chunks are stated in the block instead of failing the chat.
    """
    tag: Tag | None = None
    if span.tagId:
        try:
            tag = await store.tags.read(UUID(span.tagId))
        except Exception as e:
            logger.warning("Failed to load tag %s: %s", span.tagId, e)

    chunk = await store.documents.read_chunk_text(UUID(span.chunkId))
    document_id = chunk.document_id if chunk is not None else None
    first_chunk_text = chunk.text if chunk is not None else ""
    chunk_order = chunk.order if chunk is not None else None

    document: Document | None = None
    if document_id:
        try:
            document = await store.documents.read(document_id)
        except Exception as e:
            logger.warning("Failed to load document %s: %s", document_id, e)

    assembled_text, consumed_orders = await _assemble_chunks_covering_span(
        store,
        document_id=document_id,
        first_chunk_text=first_chunk_text,
        first_chunk_order=chunk_order,
        span_end=span.end,
    )

    # Defensive bounds: fall back to whatever text could be read.
    s_start = max(0, min(span.start, len(assembled_text)))
    s_end = max(s_start, min(span.end, len(assembled_text)))
    span_text = assembled_text[s_start:s_end]

    window_chars = max(0, context_chars)
    before, after = _trim_context(assembled_text, s_start, s_end, window_chars)

    # Neighbouring chunks (outside the span) when the in-text window is too short.
    neighbours: list[ChunkText] = []
    needs_prev = s_start < window_chars
    needs_next = len(assembled_text) - s_end < window_chars
    if document_id and chunk_order is not None and (needs_prev or needs_next):
        try:
            last_consumed = consumed_orders[-1] if consumed_orders else chunk_order
            chunks = await _chunks_in_range(store, document_id, chunk_order - 2, last_consumed + 2)
            consumed_set = set(consumed_orders)
            neighbours = [c for c in chunks if c.order not in consumed_set]
        except Exception as e:
            logger.warning("Failed to fetch neighbour chunks: %s", e)

    prev_text = " ".join(
        n.text for n in neighbours if n.order < chunk_order
    )[-window_chars:] if neighbours else ""
    last_consumed = consumed_orders[-1] if consumed_orders else chunk_order
    next_text = " ".join(
        n.text for n in neighbours if last_consumed is not None and n.order > last_consumed
    )[:window_chars] if neighbours else ""

    parts: list[str] = []
    parts.append("DOCUMENT METADATA:")
    parts.append(_format_metadata(document))
    parts.append("")
    parts.append("TAG:")
    if tag is None:
        parts.append("- (tag could not be loaded)")
    else:
        parts.append(f"- Name: {tag.name}")
        if tag.shorthand:
            parts.append(f"- Shorthand: {tag.shorthand}")
        if tag.definition:
            parts.append(f"- Definition: {tag.definition}")
        if tag.examples:
            parts.append("- Examples:")
            for ex in tag.examples:
                parts.append(f"  * {ex}")
    parts.append("")
    parts.append(f"SPAN TEXT (verbatim, {len(span_text)} chars): \"{span_text}\"")
    parts.append("")
    parts.append("SPAN IN CONTEXT (markers <<<SPAN>>>...<<<END_SPAN>>> wrap the span):")
    if prev_text:
        parts.append(f"[earlier in document, ~{len(prev_text)} chars] ...{prev_text}")
    parts.append(f"{before}<<<SPAN>>>{span_text}<<<END_SPAN>>>{after}")
    if next_text:
        parts.append(f"[later in document, ~{len(next_text)} chars] {next_text}...")

    return "\n".join(parts)


def _truncate_history(messages: list[SpanChatMessage], history_limit: int) -> list[SpanChatMessage]:
    # Keep the most recent messages; the span context is in the instructions anyway.
    limit = max(1, history_limit)
    return list(messages[-limit:])


@dataclass
class SpanDiscussion:
    """An authorized span discussion; ``deltas()`` reads its context and streams the reply."""
    store: AnnotationStore
    provider: ChatProvider
    span_id: UUID
    messages: list[SpanChatMessage]
    context_chars: int
    history_limit: int

    async def deltas(self) -> AsyncGenerator[str, None]:
        """Plain text deltas of the reply; raises if the span or the provider fails."""
        span = await self.store.spans.read(self.span_id)
        if span is None:
            raise ValueError(f"span {self.span_id} not found")

        context_block = await build_context_message(self.store, span=span, context_chars=self.context_chars)
        # The static system prompt and the span context form the instructions; the
        # input carries only the user/assistant turns.
        instructions = f"{SYSTEM_PROMPT}\n\n---\n\n{context_block}"
        turns = [{"role": m.role, "content": m.content}
                 for m in _truncate_history(self.messages, self.history_limit)]
        async for delta in self.provider.stream(instructions, turns):
            yield delta


async def prepare_discussion(store: AnnotationStore, user: Principal | None, request: DiscussSpanRequest,
                             provider: ChatProvider, *, context_chars: int,
                             history_limit: int) -> SpanDiscussion:
    """
    Validate the request and check that the user may read the span's collection
    (404/401 otherwise) before anything is streamed.
    """
    if not request.messages:
        raise InvalidRequestError("messages must not be empty")
    if request.messages[-1].role != "user":
        raise InvalidRequestError("last message must be from the user")
    collection_id = await access.collection_of_spans(store.spans, store.tags, [request.span_id])
    await access.require_collection_read(store.collections, user, collection_id)
    return SpanDiscussion(store=store, provider=provider, span_id=access.parse_id(request.span_id, "Span"),
                          messages=list(request.messages), context_chars=context_chars,
                          history_limit=history_limit)
