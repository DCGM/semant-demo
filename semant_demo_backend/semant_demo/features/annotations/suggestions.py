"""AI span suggestions: a request-scoped workflow with persistent results (ADR 0003).

A ``prepare_*`` function checks access and loads the tags and chunks (before anything is
streamed, so a denied request gets an HTTP error and makes no provider call) and returns a
``SuggestionRun``. Iterating ``SuggestionRun.events()`` calls Topicer, validates every
proposal against the request, saves each valid one as an ``auto`` span (chunk tag
included, ``service.save_span``) and yields a ``SuggestSpansChunkResult`` once it is
stored, then a final ``SuggestSpansRunEnd`` with the outcome.

- Concurrency: at most ``PROVIDER_CONCURRENCY`` Topicer calls of one run at a time;
  further chunks are started as earlier calls finish.
- Daily AI allowance (#408): each unit of Topicer work — a thorough chunk, an optimized
  tag stream, the selection — is one operation of the caller's allowance, admitted right
  before it is sent (the first one by ``prepare_*``, so a refusal is an HTTP 429) and
  settled with the usage Topicer reports when it ends. A refused admission starts no
  further unit; running units finish and the end event says ``quota_exhausted``. Usage
  that is missing (an error, a cancellation, an older Topicer's text answer) is unknown
  and charges at least the reservation; only a request Topicer certainly did not process
  (connection refused, 422) is free. A tag stream that ends normally without a usable
  usage summary is charged ``FALLBACK_SHARE`` of its reservation as a fallback estimate
  (cost source ``fallback``) and logged as a warning. The reservation is
  ``TOPICER_RESERVE_USD_PER_CHUNK`` per chunk the unit may evaluate (an optimized tag:
  ``TOPICER_MAX_CHUNKS_PER_TAG`` chunks).
- Validation (provider output is not trusted): the proposal's tag must be one of the
  request's tags, its chunk one of the document's chunks in the collection, and its
  offsets integers with ``0 <= start < end <= len(text sent)``. Topicer offsets are
  taken as Python string offsets (code points) into the text it was sent and stored in
  UTF-16 units (``offsets.py``, ADR 0006); they differ only after characters outside the
  BMP. Invalid proposals are rejected, not clamped.
- Best effort (ADR 0002): a failed provider call or write does not stop the run; saved
  spans are kept and failures are counted in the events and the summary. No rollback.
- Cancellation: closing the iterator (client disconnect) or cancelling its task cancels
  the running Topicer calls and waits for them to end; a span write in progress is
  finished first, so it is never cut between the span and its chunk tag. Saved spans
  remain. ``summary.outcome`` is then ``cancelled``.
- Duplicates: proposals are not compared with stored spans. Running suggestions again
  stores a second ``auto`` span for a proposal identical to an existing span (of any
  type, also an approved or rejected one), and Topicer may return the same proposal
  twice in one run. Approved/rejected spans are never changed or deleted by a run.
  Settle the regeneration policy before adding retries (ADR 0003).
"""
import asyncio
import logging
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Iterable
from contextlib import aclosing, nullcontext
from dataclasses import dataclass, field
from typing import Any, AsyncContextManager, Literal, TypeVar
from uuid import UUID

import anyio

from semant_demo.features.annotations.schemas import SpanType, TagSpan, AnnotationChunk
from semant_demo.adapters.sql.quota import CallRecord
from semant_demo.adapters.topicer.client import (
    TopicerClient, TopicerError, TopicerStreamSummary, TopicerTag, TopicerUsage,
)
from semant_demo.adapters.weaviate.writes import step_failure
from semant_demo.core.errors import InvalidRequestError, NotFoundError, ServiceUnavailableError
from semant_demo.features.annotations import service
from semant_demo.features.annotations.derivation import DocumentText
from semant_demo.features.annotations.offsets import code_point_offset, text_length, utf16_offset
from semant_demo.features.annotations.schemas import (
    PostSpan, SuggestionRunOutcome, SuggestSpansChunkResult, SuggestSpansRequest, SuggestSpansRunEnd,
    SuggestSpansSelectionRequest, SuggestTagLimit,
)
from semant_demo.features.annotations.service import AnnotationStore
from semant_demo.features.quota.schemas import QuotaExhaustedResponse
from semant_demo.features.quota.service import AllowanceBudget, QuotaExhausted, unfinished_call
from semant_demo.features.user_collections import access
from semant_demo.features.user_collections.access import Principal
from semant_demo.features.user_collections.schemas import CollectionChunk

logger = logging.getLogger(__name__)

# Topicer's internal OpenAI semaphore is set to 10, so we match that to
# saturate it without overshooting.
PROVIDER_CONCURRENCY = 10

FALLBACK_SHARE = 0.25
"""Share of its reservation charged for a tag stream that ended without usable usage."""

SuggestionEvent = SuggestSpansChunkResult | SuggestSpansRunEnd
Unit = Literal["chunk", "tag", "selection"]
T = TypeVar("T")
R = TypeVar("R")


# ── Run state ──────────────────────────────────────────────────────────────


@dataclass
class _Tally:
    """Counts of one run, turned into the final ``SuggestSpansRunEnd``."""
    saved: int = 0
    rejected: int = 0
    save_failures: int = 0
    search_tag_failures: int = 0
    enrichment_failures: int = 0
    provider_failures: int = 0
    completed_calls: int = 0
    """Provider calls that succeeded and whose valid proposals were all saved."""
    error: str | None = None
    unit: Unit = "chunk"
    units_total: int = 0
    units_processed: int = 0
    quota_exhausted: QuotaExhausted | None = None
    """The refusal that stopped the run before all its units."""
    max_chunks_per_tag: int | None = None
    tag_limits: list[SuggestTagLimit] = field(default_factory=list)
    document_texts: dict[UUID, DocumentText] = field(default_factory=dict)
    """The run's document text for the derived data of its saved spans (#328): read by the first
    save and reused (saves that start before the first read finished read it too)."""

    def summary(self) -> SuggestSpansRunEnd:
        failures = (self.provider_failures + self.save_failures + self.search_tag_failures
                    + self.enrichment_failures + bool(self.error) + bool(self.quota_exhausted))
        if not failures:
            outcome = SuggestionRunOutcome.complete
        elif self.saved or self.completed_calls:
            outcome = SuggestionRunOutcome.partial
        else:
            outcome = SuggestionRunOutcome.failed
        return SuggestSpansRunEnd(
            outcome=outcome, saved=self.saved, rejected=self.rejected, save_failures=self.save_failures,
            search_tag_failures=self.search_tag_failures, enrichment_failures=self.enrichment_failures,
            provider_failures=self.provider_failures,
            error=self.error, unit=self.unit, units_total=self.units_total, units_processed=self.units_processed,
            stop_reason="quota_exhausted" if self.quota_exhausted else None,
            quota_exhausted=(QuotaExhaustedResponse.model_validate(self.quota_exhausted.body())
                             if self.quota_exhausted else None),
            max_chunks_per_tag=self.max_chunks_per_tag, tag_limits=list(self.tag_limits),
        )


@dataclass
class _ChunkEvent:
    """Saved spans and unsaved proposals of one event, so failures are reported."""
    tally: _Tally
    chunk_id: str
    error: str | None = None
    spans: list[TagSpan] = field(default_factory=list)
    unsaved: int = 0
    reasons: set[str] = field(default_factory=set)
    untagged: int = 0
    unenriched: int = 0
    save_failed: bool = False

    def reject(self, reason: str, count: int = 1) -> None:
        self.unsaved += count
        self.reasons.add(reason)
        self.tally.rejected += count

    def provider_failed(self, message: str) -> None:
        self.error = message
        self.tally.provider_failures += 1

    def result(self) -> SuggestSpansChunkResult:
        errors = [self.error] if self.error else []
        if self.unsaved:
            errors.append(f"{self.unsaved} proposal(s) not saved ({', '.join(sorted(self.reasons))})")
        if self.untagged:
            errors.append(f"{self.untagged} saved proposal(s) not yet findable by tag search")
        if self.unenriched:
            errors.append(f"{self.unenriched} saved proposal(s) without current search text or vector")
        return SuggestSpansChunkResult(
            chunk_id=self.chunk_id, spans=self.spans, error="; ".join(errors) or None, unsaved=self.unsaved,
        )


class SuggestionRun:
    """One prepared suggestion request; ``events()`` may be iterated once. While it runs,
    the collection's annotation tenant is recorded as in use (``hold``), so the idle
    deactivation leaves it active."""

    def __init__(self, produce: Callable[[_Tally], AsyncIterator[SuggestSpansChunkResult]], description: str,
                 tally: _Tally, hold: Callable[[], AsyncContextManager[None]] | None = None):
        self._produce = produce
        self._description = description
        self._tally = tally
        self._hold = hold or nullcontext
        self.summary: SuggestSpansRunEnd | None = None
        """The final summary once the run ended (also when cancelled; then not sent)."""

    async def events(self) -> AsyncGenerator[SuggestionEvent, None]:
        try:
            async with self._hold(), aclosing(self._produce(self._tally)) as results:
                async for result in results:
                    yield result
        except (asyncio.CancelledError, GeneratorExit):
            self.summary = self._tally.summary().model_copy(update={"outcome": SuggestionRunOutcome.cancelled})
            logger.info("AI suggestions cancelled (%s): %s", self._description, self.summary.model_dump_json())
            raise
        except Exception as e:
            logger.error("AI suggestions failed (%s): %s", self._description, type(e).__name__)
            self._tally.error = "AI suggestions stopped by an unexpected error; saved suggestions are kept."
        self.summary = self._tally.summary()
        yield self.summary


# ── Shared steps ───────────────────────────────────────────────────────────


async def _cancel_and_wait(tasks: Iterable[asyncio.Task]) -> None:
    """Cancel the tasks and wait until they ended, even if the caller is being cancelled."""
    tasks = list(tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        # Starlette cancels a disconnected stream through an anyio cancel scope, which
        # would interrupt this wait again; shield it so cleanup finishes.
        with anyio.CancelScope(shield=True):
            await asyncio.wait(tasks)


async def _uninterrupted(write: Awaitable[T]) -> T:
    """Finish a write even if the caller is cancelled meanwhile, then re-raise the cancellation."""
    task = asyncio.ensure_future(write)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        with anyio.CancelScope(shield=True):
            await asyncio.wait([task])
        if not task.cancelled() and task.exception() is not None:
            logger.warning("A span write finished during cancellation failed: %s", type(task.exception()).__name__)
        raise


_STOP = object()
"""Returned by an admission that was refused: start no further unit."""
_LATER = object()
"""Returned by an admission refused while other units run: retry when one has ended."""


async def _as_completed(items: Iterable[T], call: Callable[[T, Any], Awaitable[R]], limit: int,
                        admit: Callable[[bool], Awaitable[Any]]) -> AsyncGenerator[tuple[T, R], None]:
    """``(item, await call(item, admission))`` in completion order, with at most ``limit``
    calls running.

    Each item is admitted (``await admit(others_running)``) right before its call starts.
    Further items are started once finished calls have been taken out of the running set
    (their own settlement is part of the call), so an admission sees their settled usage.
    An admission that returns ``_LATER`` is retried after the next call ends (the
    reservations of running calls may be what left no room); one that returns ``_STOP``
    starts no further item, and running calls finish and are yielded. Closing the
    generator cancels the running calls and waits for them.
    """
    pending = iter(items)
    running: dict[asyncio.Task, T] = {}
    held = _STOP  # an item whose admission is to be retried
    stopped = False

    async def start_more() -> None:
        nonlocal held, stopped
        while not stopped and len(running) < limit:
            item, held = (next(pending, _STOP), _STOP) if held is _STOP else (held, _STOP)
            if item is _STOP:
                return
            admission = await admit(bool(running))
            if admission is _LATER:
                held = item
                return
            if admission is _STOP:
                stopped = True
                return
            running[asyncio.create_task(call(item, admission))] = item

    try:
        await start_more()
        while running:
            done, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
            finished = [(running.pop(task), task) for task in done]
            await start_more()
            for item, task in finished:
                yield item, task.result()
    finally:
        await _cancel_and_wait(running)


_USAGE_SOURCES = {"reported": "provider", "estimated": "estimated"}
_COST_SOURCES = {"reported": "provider", "estimated": "price"}


def _call_records(feature: str, usage: TopicerUsage | None) -> list[CallRecord]:
    """Topicer's reported usage as ledger calls; unknown usage is one call of unknown cost."""
    if usage is None:
        return [unfinished_call(feature)]
    calls = [CallRecord(feature=feature, tier="topicer", provider=c.provider[:32], model=c.model[:200],
                        outcome=c.outcome[:32], usage_source=_USAGE_SOURCES.get(c.usage_source, "unavailable"),
                        cost_source=_COST_SOURCES.get(c.cost_source, "unknown") if c.cost_usd is not None
                        else "unknown",
                        cost_usd=c.cost_usd, input_tokens=c.input_tokens, output_tokens=c.output_tokens)
             for c in usage.calls]
    return calls + [unfinished_call(feature)] * (usage.attempted_calls - len(usage.calls))


@dataclass
class _Allowance:
    """The run's units as operations of the caller's daily allowance (none without a budget)."""
    budget: AllowanceBudget | None
    feature: str
    reserve_usd: float
    """Reservation of one unit."""

    async def admit(self) -> str | None:
        """Raises ``QuotaExhausted`` when the allowance has no room for one more unit."""
        return None if self.budget is None else await self.budget.admit(self.feature, self.reserve_usd)

    def admitter(self, tally: _Tally, first: str | None) -> Callable[[bool], Awaitable[Any]]:
        """Admissions of the run's units, starting with ``first`` (admitted by ``prepare_*``):
        each counts a processed unit. A refusal returns ``_LATER`` while ``others_running``
        (their settlement may free room), otherwise it is recorded in ``tally`` and returns
        ``_STOP``."""
        admissions = iter([first])

        async def admit(others_running: bool = False) -> Any:
            admission = next(admissions, _STOP)
            if admission is _STOP:
                try:
                    admission = await self.admit()
                except QuotaExhausted as e:
                    if others_running:
                        return _LATER
                    tally.quota_exhausted = e
                    logger.info("AI suggestions stopped by the daily allowance after %d of %d %ss",
                                tally.units_processed, tally.units_total, tally.unit)
                    return _STOP
            tally.units_processed += 1
            return admission

        return admit

    async def settle(self, admission: str | None, usage: TopicerUsage | None, *, no_work: bool = False,
                     fallback: bool = False) -> None:
        """Charge the unit's usage; finishes even when the caller is cancelled meanwhile.

        ``fallback``: the unit ended without usage information; charge ``FALLBACK_SHARE``
        of its reservation, recorded as an estimate rather than consumption.
        """
        if self.budget is not None and admission is not None:
            calls = [] if no_work else [self._fallback_call()] if fallback else _call_records(self.feature, usage)
            await _uninterrupted(self._settle(admission, calls))

    def _fallback_call(self) -> CallRecord:
        # No provider, model or tokens: nothing was reported.
        return CallRecord(feature=self.feature, tier="topicer", provider="", model="", outcome="usage_missing",
                          usage_source="unavailable", cost_source="fallback",
                          cost_usd=self.reserve_usd * FALLBACK_SHARE)

    async def _settle(self, admission: str, calls: list[CallRecord]) -> None:
        try:
            await self.budget.settle_calls(admission, calls)
        except Exception as e:
            # Content-free; the unit's reservation stays charged.
            logger.error("Topicer usage settlement failed: %s", type(e).__name__)


def _uuid(value: Any) -> str | None:
    try:
        return str(UUID(str(value)))
    except ValueError:
        return None


def _offset(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


@dataclass(frozen=True)
class _Proposal:
    tag_id: str
    start: int
    """Code point offset into the text sent to the provider."""
    end: int
    reason: str | None
    confidence: float | None


def _validated(raw: Any, allowed_tag_ids: set[str], text_len: int,
               default_tag_id: str | None = None) -> _Proposal | str:
    """The proposal, or why it is invalid. ``text_len``: code points of the text sent."""
    if not isinstance(raw, dict):
        return "invalid proposal"
    tag = raw.get("tag")
    tag_id = tag.get("id") if isinstance(tag, dict) else None
    tag_id = _uuid(tag_id) if tag_id else default_tag_id
    if tag_id is None or tag_id not in allowed_tag_ids:
        return "tag outside the request"
    start, end = _offset(raw.get("span_start")), _offset(raw.get("span_end"))
    if start is None or end is None or not 0 <= start < end <= text_len:
        return "invalid offsets"
    reason = raw.get("reason")
    confidence = raw.get("confidence")
    return _Proposal(
        tag_id=tag_id, start=start, end=end,
        reason=reason if isinstance(reason, str) else None,
        confidence=float(confidence) if isinstance(confidence, int | float) and not isinstance(confidence, bool)
        else None,
    )


async def _save(store: AnnotationStore, collection_id: UUID, document_id: UUID, event: _ChunkEvent, chunk_id: str,
                proposal: _Proposal, start: int, end: int) -> None:
    """Store one validated proposal (``start``/``end`` in UTF-16 units of ``chunk_id``, a
    chunk of the document) in the collection's tenant."""
    span = PostSpan(chunkId=chunk_id, tagId=proposal.tag_id, start=start, end=end, type=SpanType.auto,
                    reason=proposal.reason, confidence=proposal.confidence)
    try:
        result = await _uninterrupted(service.save_span(store, collection_id, document_id, span,
                                                        event.tally.document_texts))
    except Exception as e:
        failure = step_failure("insert_span", chunk_id, e)
        event.unsaved += 1
        event.reasons.add("storage failure, may have been saved" if failure.uncertain else "storage failure")
        event.save_failed = True
        event.tally.save_failures += 1
        return
    event.spans.append(TagSpan(**result.model_dump(include=set(TagSpan.model_fields))))
    event.tally.saved += 1
    steps = {f.step for f in result.failed}
    if "update_chunk_tags" in steps:
        event.untagged += 1
        event.tally.search_tag_failures += 1
    if steps - {"update_chunk_tags"}:
        event.unenriched += 1
        event.tally.enrichment_failures += 1


async def _authorized_tags(store: AnnotationStore, user: Principal | None, collection_id: str,
                           document_id: str, tag_ids: list[str]) -> tuple[UUID, UUID, list[TopicerTag]]:
    """(collection, document, tags) after the access and scope checks, in this order."""
    if not tag_ids:
        raise InvalidRequestError("tag_ids must not be empty")
    grant = await access.require_annotation_edit(store.collections, user, collection_id)
    ids = await access.require_tags_in_collection(store.tags, tag_ids, grant.collection_id)
    document = await access.require_document_in_collection(store.collections, document_id, grant.collection_id)
    tags = []
    for tag_id in ids:
        tag = await store.tags.read(tag_id)
        if tag is None:
            raise NotFoundError("Tag not found")
        tags.append(TopicerTag(id=str(tag.id), name=tag.name, definition=tag.definition or "",
                               examples=list(tag.examples or [])))
    return grant.collection_id, document, tags


async def topicer_configs(provider: TopicerClient) -> list[str]:
    """The Topicer configurations (AI models) requests may name (#189);
    ``ServiceUnavailableError`` when Topicer cannot list them."""
    try:
        return await provider.list_configs()
    except TopicerError as e:
        raise ServiceUnavailableError("The list of AI models is unavailable") from e


async def provider_for(provider: TopicerClient, config_name: str | None) -> TopicerClient:
    """``provider`` with the Topicer configuration a request named (#189).

    ``None`` or the default is ``provider`` itself, without asking Topicer. Another name
    must be one Topicer lists as loaded (``InvalidRequestError`` otherwise), so an unknown
    name never reaches a proposal call; ``ServiceUnavailableError`` when the list cannot
    be read.
    """
    if config_name is None or config_name == provider.config_name:
        return provider
    if config_name not in await topicer_configs(provider):
        raise InvalidRequestError("Unknown AI model")
    return provider.with_config(config_name)


# ── Whole document (thorough / optimized) ──────────────────────────────────


async def prepare_document_run(store: AnnotationStore, provider: TopicerClient, user: Principal | None,
                               request: SuggestSpansRequest, mode: Literal["thorough", "optimized"],
                               budget: AllowanceBudget | None = None) -> SuggestionRun:
    """
    Suggestions for the document's chunks in the collection.

    ``thorough``: every such chunk is sent to Topicer with all requested tags, one call
    per chunk; one event per chunk, in completion order. ``optimized``: one Topicer
    database stream per tag (Topicer pre-filters chunks by vector similarity, at most
    ``provider.max_chunks_per_tag``), tags one after another; one event per chunk Topicer
    returns, and one event with an empty ``chunk_id`` when a tag's stream fails. Needs
    annotation-edit access; the tags and the document must belong to the collection.

    Each chunk (thorough) or tag (optimized) is admitted against ``budget`` before it is
    sent; the first admission happens here, after the access checks, so a refusal raises
    ``QuotaExhausted`` (HTTP 429) before anything is streamed.
    """
    collection_id, document_id, tags = await _authorized_tags(
        store, user, request.collection_id, request.document_id, request.tag_ids)
    provider = await provider_for(provider, request.config_name)
    chunks = await store.collections.read_all_chunks_by_document(document_id, collection_id)
    allowed = {t.id for t in tags}
    description = f"{mode}, collection {collection_id}, document {document_id}"
    chunk_reserve = budget.policy.topicer_reserve_usd_per_chunk if budget is not None else 0.0
    if mode == "thorough":
        allowance = _Allowance(budget, "topicer_thorough", chunk_reserve)
        tally = _Tally(unit="chunk", units_total=len(chunks))
    else:
        allowance = _Allowance(budget, "topicer_optimized", chunk_reserve * provider.max_chunks_per_tag)
        tally = _Tally(unit="tag", units_total=len(tags), max_chunks_per_tag=provider.max_chunks_per_tag)
    first = await allowance.admit() if tally.units_total else None
    admit = allowance.admitter(tally, first)

    async def thorough(tally: _Tally) -> AsyncGenerator[SuggestSpansChunkResult, None]:
        async def call(chunk: CollectionChunk, admission: str | None) -> list | TopicerError:
            usage, no_work = None, False
            try:
                answer = await provider.propose_for_text(chunk_id=str(chunk.id), text=chunk.text or "", tags=tags)
                usage = answer.usage
                return answer.proposals
            except TopicerError as e:
                no_work = e.no_work
                return e
            finally:
                await allowance.settle(admission, usage, no_work=no_work)

        async with aclosing(_as_completed(chunks, call, PROVIDER_CONCURRENCY, admit)) as completed:
            async for chunk, proposals in completed:
                text = chunk.text or ""
                event = _ChunkEvent(tally, str(chunk.id))
                if isinstance(proposals, TopicerError):
                    event.provider_failed(f"topicer: {proposals}")
                    proposals = []
                for raw in proposals:
                    proposal = _validated(raw, allowed, len(text))
                    if isinstance(proposal, str):
                        event.reject(proposal)
                        continue
                    await _save(store, collection_id, document_id, event, str(chunk.id), proposal,
                                utf16_offset(text, proposal.start), utf16_offset(text, proposal.end))
                if event.error is None and not event.save_failed:
                    tally.completed_calls += 1
                yield event.result()

    async def optimized(tally: _Tally) -> AsyncGenerator[SuggestSpansChunkResult, None]:
        # The only chunks proposals may be saved on (Topicer returns chunk ids itself),
        # and the text their offsets are checked against.
        text_by_id = {str(c.id): c.text or "" for c in chunks}
        for tag in tags:
            admission = await admit()
            if admission is _STOP:
                return
            save_failed = False
            summary: TopicerStreamSummary | None = None
            failure: TopicerError | None = None
            ended = False  # the stream ended normally (not failed, cancelled or closed)
            try:
                stream = provider.propose_for_db_stream(tag=tag, collection_id=str(collection_id),
                                                        document_id=str(document_id))
                async with aclosing(stream) as provider_events:
                    async for provider_event in provider_events:
                        if isinstance(provider_event, TopicerStreamSummary):
                            summary = provider_event
                            continue
                        chunk_id = _uuid(provider_event.get("id"))
                        proposals = provider_event.get("tag_span_proposals") or []
                        if not isinstance(proposals, list):
                            proposals = [proposals]
                        if chunk_id is None:
                            if proposals:
                                tally.rejected += len(proposals)
                                logger.warning("Topicer returned %d proposals without a valid chunk id",
                                               len(proposals))
                            continue
                        event = _ChunkEvent(tally, chunk_id)
                        if chunk_id not in text_by_id:
                            # Not a chunk of this document in this collection: save nothing.
                            event.reject("chunk outside the collection", len(proposals))
                            proposals = []
                        text = text_by_id.get(chunk_id, "")
                        for raw in proposals:
                            proposal = _validated(raw, allowed, len(text), default_tag_id=tag.id)
                            if isinstance(proposal, str):
                                event.reject(proposal)
                                continue
                            await _save(store, collection_id, document_id, event, chunk_id, proposal,
                                        utf16_offset(text, proposal.start), utf16_offset(text, proposal.end))
                        save_failed = save_failed or event.save_failed
                        yield event.result()
                ended = True
            except TopicerError as e:
                failure = e
            finally:
                await allowance.settle(admission, summary.usage if summary else None,
                                       no_work=failure is not None and failure.no_work and summary is None,
                                       fallback=ended and summary is None)
            if summary is not None and summary.limit_reached:
                tally.tag_limits.append(SuggestTagLimit(
                    tag_id=tag.id, tag_name=tag.name, max_chunks=summary.max_chunks or provider.max_chunks_per_tag,
                    processed_chunks=summary.processed_chunks, candidates_truncated=summary.candidates_truncated))
            problem = _stream_problem(failure, summary, provider.max_chunks_per_tag)
            if problem:
                event = _ChunkEvent(tally, "")
                event.provider_failed(f"topicer (tag={tag.name}): {problem}")
                yield event.result()
                continue
            if summary is None:
                logger.warning("Topicer stream of tag %s (document %s, config %s) ended without a usable usage "
                               "summary (missing or malformed); charged %d%% of its reservation as a fallback "
                               "estimate", tag.id, document_id, provider.config_name, FALLBACK_SHARE * 100)
            if not save_failed:
                tally.completed_calls += 1

    return SuggestionRun(thorough if mode == "thorough" else optimized, description, tally,
                         hold=lambda: store.activity.in_use(collection_id))


def _stream_problem(failure: TopicerError | None, summary: TopicerStreamSummary | None,
                    max_chunks: int) -> str | None:
    """Why a tag's database stream did not complete, or None."""
    if failure is not None and str(failure) == "HTTP 422":
        logger.warning("Topicer refused a database stream with max_chunks=%d; check TOPICER_MAX_CHUNKS_PER_TAG "
                       "against Topicer's max_chunks_ceiling", max_chunks)
        return f"HTTP 422 (Topicer refused the request; the per-tag limit of {max_chunks} chunks may exceed its own)"
    if failure is not None:
        return str(failure)
    if summary is not None and summary.status == "partial":
        return "some chunks failed"
    if summary is not None and summary.status == "failed":
        return "failed"
    return None


# ── Selection ──────────────────────────────────────────────────────────────


@dataclass
class _Selection:
    """The selected chunks, their texts concatenated, and the selected code point range."""
    chunks: list[AnnotationChunk]
    starts: list[int]
    """Code point offset of each chunk in the concatenation, plus the total length."""
    start: int
    end: int

    @property
    def text(self) -> str:
        return "".join(c.text for c in self.chunks)[self.start:self.end]

    def locate(self, offset: int, *, end: bool = False) -> tuple[int, int]:
        """(chunk index, code point offset in that chunk) of a concatenation offset.

        A start at a chunk boundary belongs to the following chunk, an end to the
        preceding one.
        """
        for i in range(len(self.chunks)):
            if self.starts[i] <= offset < self.starts[i + 1] or (end and offset == self.starts[i + 1]):
                return i, offset - self.starts[i]
        raise ValueError(offset)


async def prepare_selection_run(store: AnnotationStore, provider: TopicerClient, user: Principal | None,
                                request: SuggestSpansSelectionRequest,
                                budget: AllowanceBudget | None = None) -> SuggestionRun:
    """
    Suggestions for a passage the user selected, which may extend over several chunks
    of the collection (sent in document order; chunks between them that are not in the
    collection are not part of the selection text). One Topicer call with the selected
    text; one event per proposal. A saved span is anchored on the chunk where it starts,
    its end measured through the following chunks of the document as for user-created
    cross-chunk spans (``offsets.py``). Needs annotation-edit access; the tags, the
    document and the chunks must belong to the collection.

    The call is one operation of ``budget``, admitted here after the checks (reserving one
    chunk evaluation per selected chunk), so a refusal raises ``QuotaExhausted``.
    """
    if not request.tag_ids:
        raise InvalidRequestError("tag_ids must not be empty")
    if not request.chunk_ids:
        raise InvalidRequestError("chunk_ids must not be empty")
    if request.selection_end <= request.selection_start:
        raise InvalidRequestError("selection_end must be greater than selection_start")
    collection_id, document_id, tags = await _authorized_tags(
        store, user, request.collection_id, request.document_id, request.tag_ids)
    chunk_ids = await access.require_chunks_in_collection(store.collections, request.chunk_ids, collection_id,
                                                          document_id)
    chunks = []
    for chunk_id in chunk_ids:
        chunk = await store.documents.read_chunk_text(chunk_id)
        if chunk is None:
            raise NotFoundError("Chunk not found in this collection")
        chunks.append(chunk)
    if len(chunk_ids) != len(request.chunk_ids) or any(b.order <= a.order for a, b in zip(chunks, chunks[1:])):
        raise InvalidRequestError("chunk_ids must be distinct chunks in document order")
    provider = await provider_for(provider, request.config_name)

    concatenation = "".join(c.text for c in chunks)
    starts = [0]
    for c in chunks:
        starts.append(starts[-1] + len(c.text))
    # The browser measures the selection in UTF-16 units.
    selection = _Selection(chunks, starts, code_point_offset(concatenation, max(0, request.selection_start)),
                           code_point_offset(concatenation, request.selection_end))
    if selection.end <= selection.start:
        raise InvalidRequestError("The selection contains no text of the selected chunks")
    allowed = {t.id for t in tags}
    by_order: dict[int, AnnotationChunk] = {c.order: c for c in chunks}
    reserve = budget.policy.topicer_reserve_usd_per_chunk * len(chunks) if budget is not None else 0.0
    allowance = _Allowance(budget, "topicer_selection", reserve)
    tally = _Tally(unit="selection", units_total=1)
    admit = allowance.admitter(tally, await allowance.admit())

    async def length_between(anchor: AnnotationChunk, last: AnnotationChunk) -> int | None:
        """UTF-16 length of the document's chunks from ``anchor`` up to (not including) ``last``.

        None if their orders have a gap. Reads the chunks between that were not selected
        (not in the collection).
        """
        between = range(anchor.order + 1, last.order)
        if any(order not in by_order for order in between):
            more = await store.documents.read_following_chunk_texts(anchor.document_id, anchor.order, len(between))
            by_order.update({c.order: c for c in more if c.order not in by_order})
        if any(order not in by_order for order in between):
            return None
        return text_length(anchor.text) + sum(text_length(by_order[order].text) for order in between)

    async def produce(tally: _Tally) -> AsyncGenerator[SuggestSpansChunkResult, None]:
        anchor_id = str(chunks[0].id)
        admission = await admit()
        usage, no_work = None, False
        try:
            answer = await provider.propose_for_text(chunk_id=anchor_id, text=selection.text, tags=tags)
            usage = answer.usage
        except TopicerError as e:
            no_work = e.no_work
            event = _ChunkEvent(tally, anchor_id)
            event.provider_failed(f"topicer: {e}")
            yield event.result()
            return
        finally:
            await allowance.settle(admission, usage, no_work=no_work)
        proposals = answer.proposals
        save_failed = False
        for raw in proposals:
            proposal = _validated(raw, allowed, selection.end - selection.start)
            if isinstance(proposal, str):
                event = _ChunkEvent(tally, anchor_id)
                event.reject(proposal)
                yield event.result()
                continue
            first, local_start = selection.locate(selection.start + proposal.start)
            last, local_end = selection.locate(selection.start + proposal.end, end=True)
            anchor = chunks[first]
            event = _ChunkEvent(tally, str(anchor.id))
            end = utf16_offset(chunks[last].text, local_end)
            if last != first:
                before = await length_between(anchor, chunks[last])
                if before is None:
                    event.reject("crosses a gap between chunks")
                    yield event.result()
                    continue
                end += before
            await _save(store, collection_id, document_id, event, str(anchor.id), proposal, utf16_offset(anchor.text, local_start), end)
            save_failed = save_failed or event.save_failed
            # One event per proposal: the saved span, or an unsaved count with the reason.
            yield event.result()
        if not save_failed:
            tally.completed_calls += 1

    return SuggestionRun(produce, f"selection, collection {collection_id}, document {document_id}", tally,
                         hold=lambda: store.activity.in_use(collection_id))
