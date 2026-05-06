"""
Span discussion chat.

Builds a rich system prompt around a single :class:`TagSpan` (its tag
definition + examples, host document metadata and the chunk text with a few
hundred characters of surrounding context) and streams the assistant's reply
from an OpenAI-compatible Chat Completions endpoint.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from openai import AsyncOpenAI
from weaviate.classes.query import Filter, QueryReference, Sort

from semant_demo import schemas
from semant_demo.config import config
from semant_demo.schema.ai_assistance import SpanChatMessage
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction

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


def _format_metadata(doc) -> str:
    """Render :class:`Document` metadata as a compact bullet list."""
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


async def _fetch_chunk_with_doc(
    searcher: WeaviateAbstraction, chunk_id: str
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Returns ``(chunk_props, document_id)``. Both can be ``None`` if the chunk
    isn't found or has no document reference.
    """
    chunks_collection = searcher.client.collections.get(
        searcher.collectionNames.chunks_collection_name
    )
    obj = await chunks_collection.query.fetch_object_by_id(
        uuid=chunk_id,
        return_properties=["text", "order", "title"],
        return_references=[QueryReference(link_on="document")],
    )
    if obj is None or not obj.properties:
        return None, None

    document_id: str | None = None
    if obj.references and "document" in obj.references:
        doc_objs = obj.references["document"].objects
        if doc_objs:
            document_id = str(doc_objs[0].uuid)

    return dict(obj.properties), document_id


async def _fetch_chunks_in_range(
    searcher: WeaviateAbstraction,
    document_id: str,
    min_order: int,
    max_order: int,
) -> list[dict[str, Any]]:
    """
    Fetch chunks from the same document whose ``order`` falls in the
    inclusive ``[min_order, max_order]`` range, ordered ascending. Returns a
    list of ``{order, text}`` dicts.
    """
    if max_order < min_order:
        return []
    chunks_collection = searcher.client.collections.get(
        searcher.collectionNames.chunks_collection_name
    )
    f = (
        Filter.by_ref("document").by_id().equal(document_id)
        & Filter.by_property("order").greater_or_equal(min_order)
        & Filter.by_property("order").less_or_equal(max_order)
    )
    response = await chunks_collection.query.fetch_objects(
        filters=f,
        limit=max_order - min_order + 1,
        sort=Sort.by_property("order", ascending=True),
        return_properties=["text", "order"],
    )
    return [
        {"order": obj.properties.get("order"), "text": obj.properties.get("text") or ""}
        for obj in response.objects
    ]


async def _fetch_neighbour_chunks(
    searcher: WeaviateAbstraction,
    document_id: str,
    centre_order: int,
    radius: int,
) -> list[dict[str, Any]]:
    """
    Fetch chunks from the same document with order in
    ``[centre_order - radius, centre_order + radius]`` (excluding the centre
    itself), ordered ascending.
    """
    if radius <= 0:
        return []
    chunks = await _fetch_chunks_in_range(
        searcher, document_id, centre_order - radius, centre_order + radius
    )
    return [c for c in chunks if c.get("order") != centre_order]


async def _assemble_chunks_covering_span(
    searcher: WeaviateAbstraction,
    *,
    document_id: str | None,
    first_chunk_text: str,
    first_chunk_order: int | None,
    span_end: int,
) -> tuple[str, list[int]]:
    """
    Build a contiguous string from the chunks the span occupies. Starts at
    the first chunk (referenced by ``span.chunkId``) and keeps appending
    consecutive following chunks until the running length covers ``span_end``
    (a cross-chunk span's ``end`` is an offset measured across the
    concatenation of all spanned chunks).

    The returned text contains the span itself plus whatever lies before it
    in the first chunk and after it in the last spanned chunk — the caller
    slices the actual span / surrounding window out of this string.

    Returns ``(assembled_text, consumed_orders)`` where ``consumed_orders``
    lists the orders of all chunks that contributed (including the first).
    """
    consumed: list[int] = []
    if first_chunk_order is not None:
        consumed.append(first_chunk_order)
    assembled = first_chunk_text

    if (
        span_end <= len(assembled)
        or document_id is None
        or first_chunk_order is None
    ):
        return assembled, consumed

    # Pull a generous batch of following chunks in one go; chunk lengths vary
    # but 8 is plenty for typical multi-chunk spans.
    BATCH = 8
    next_chunks = await _fetch_chunks_in_range(
        searcher,
        document_id,
        min_order=first_chunk_order + 1,
        max_order=first_chunk_order + BATCH,
    )
    for c in next_chunks:
        order = c.get("order")
        if order is None:
            continue
        assembled += c.get("text") or ""
        consumed.append(order)
        if len(assembled) >= span_end:
            break
    return assembled, consumed


def _trim_context(text: str, span_start: int, span_end: int, window: int) -> tuple[str, str]:
    """
    Slice ``window`` characters before/after the span out of the chunk's text.
    Returns ``(before, after)``.
    """
    if window <= 0:
        return "", ""
    before_start = max(0, span_start - window)
    after_end = min(len(text), span_end + window)
    return text[before_start:span_start], text[span_end:after_end]


async def build_context_message(
    searcher: WeaviateAbstraction,
    *,
    span: schemas.TagSpan,
) -> str:
    """
    Assemble the per-conversation context block (document metadata + tag info
    + span text in surrounding context) that's prepended as a system message.
    """
    # Tag
    tag = None
    if span.tagId:
        try:
            tag = await searcher.tag.read(UUID(span.tagId))
        except Exception as e:
            logger.warning("Failed to load tag %s: %s", span.tagId, e)

    # Chunk + document
    chunk_props, document_id = await _fetch_chunk_with_doc(searcher, span.chunkId)
    first_chunk_text: str = (chunk_props or {}).get("text") or ""
    chunk_order: int | None = (chunk_props or {}).get("order")

    document = None
    if document_id:
        try:
            document = await searcher.document.read(document_id)
        except Exception as e:
            logger.warning("Failed to load document %s: %s", document_id, e)

    # Cross-chunk spans are stored as ``chunkId = first chunk`` with ``end``
    # measured across the concatenation of consecutive chunks. Build that
    # concatenation (only fetching extra chunks when actually needed).
    assembled_text, consumed_orders = await _assemble_chunks_covering_span(
        searcher,
        document_id=document_id,
        first_chunk_text=first_chunk_text,
        first_chunk_order=chunk_order,
        span_end=span.end,
    )

    # Span text (defensive bounds — fall back to whatever we managed to fetch)
    s_start = max(0, min(span.start, len(assembled_text)))
    s_end = max(s_start, min(span.end, len(assembled_text)))
    span_text = assembled_text[s_start:s_end]

    # Surrounding context within the assembled (possibly multi-chunk) text
    window_chars = max(0, config.SPAN_CHAT_CONTEXT_CHARS)
    before, after = _trim_context(assembled_text, s_start, s_end, window_chars)

    # Optionally pull in neighbouring chunks (outside the span itself) if the
    # in-text window doesn't provide enough characters on either side.
    neighbours: list[dict[str, Any]] = []
    needs_prev = s_start < window_chars
    needs_next = len(assembled_text) - s_end < window_chars
    if document_id and chunk_order is not None and (needs_prev or needs_next):
        try:
            last_consumed = consumed_orders[-1] if consumed_orders else chunk_order
            min_o = chunk_order - 2
            max_o = last_consumed + 2
            chunks = await _fetch_chunks_in_range(
                searcher, document_id, min_o, max_o
            )
            consumed_set = set(consumed_orders)
            neighbours = [c for c in chunks if c.get("order") not in consumed_set]
        except Exception as e:
            logger.warning("Failed to fetch neighbour chunks: %s", e)

    prev_text = " ".join(
        n["text"] for n in neighbours if n["order"] is not None and n["order"] < chunk_order
    )[-window_chars:] if neighbours else ""
    last_consumed = consumed_orders[-1] if consumed_orders else chunk_order
    next_text = " ".join(
        n["text"] for n in neighbours
        if n["order"] is not None and last_consumed is not None and n["order"] > last_consumed
    )[:window_chars] if neighbours else ""

    # Build the prompt block
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


def _truncate_history(messages: list[SpanChatMessage]) -> list[SpanChatMessage]:
    limit = max(1, config.SPAN_CHAT_HISTORY_LIMIT)
    if len(messages) <= limit:
        return list(messages)
    # Keep the most recent ``limit`` messages — older context is summarised
    # implicitly via the system prompt.
    return list(messages[-limit:])


async def stream_span_discussion(
    searcher: WeaviateAbstraction,
    *,
    span_id: str,
    messages: list[SpanChatMessage],
) -> AsyncGenerator[str, None]:
    """
    Async generator yielding plain text deltas (no NDJSON wrapping — the
    route layer wraps each delta as it pleases).

    Raises :class:`ValueError` if the span / required context cannot be
    resolved up-front so the route can return a 4xx instead of an opaque
    streaming error.
    """
    if not messages:
        raise ValueError("messages must not be empty")
    if messages[-1].role != "user":
        raise ValueError("last message must be from the user")

    span = await searcher.span.read(span_id)
    if span is None:
        raise ValueError(f"span {span_id} not found")

    context_block = await build_context_message(searcher, span=span)

    # The Responses API takes a single ``instructions`` blob for the
    # system-level behaviour and a list of conversation turns in ``input``.
    # We fold the static system prompt + per-span context block into the
    # instructions so the input only carries actual user/assistant turns.
    instructions = f"{SYSTEM_PROMPT}\n\n---\n\n{context_block}"
    input_items: list[dict[str, str]] = [
        {"role": m.role, "content": m.content}
        for m in _truncate_history(messages)
    ]

    if not config.SPAN_CHAT_API_KEY:
        raise ValueError(
            "SPAN_CHAT_API_KEY (or OPENAI_API_KEY) is not configured on the server"
        )

    client = AsyncOpenAI(
        api_key=config.SPAN_CHAT_API_KEY,
        base_url=config.SPAN_CHAT_API_URL,
    )

    stream = await client.responses.create(
        model=config.SPAN_CHAT_MODEL,
        instructions=instructions,
        input=input_items,
        temperature=config.SPAN_CHAT_TEMPERATURE,
        max_output_tokens=config.SPAN_CHAT_MAX_TOKENS,
        stream=True,
    )

    async for event in stream:
        # Responses API streams a series of typed events; we only care about
        # incremental output text. Other events (response.created,
        # response.output_text.done, response.completed, ...) are ignored.
        event_type = getattr(event, "type", None)
        if event_type == "response.output_text.delta":
            delta = getattr(event, "delta", None)
            if delta:
                yield delta
        elif event_type == "response.error":
            err = getattr(event, "error", None)
            message = getattr(err, "message", None) or str(err) or "unknown error"
            raise RuntimeError(f"Responses API error: {message}")
