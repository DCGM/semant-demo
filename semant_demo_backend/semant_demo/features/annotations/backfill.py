"""Status and backfill of annotation derived data (#328), for the operator command
``python -m semant_demo.maintenance.annotation_enrichment``.

The backfill writes only derived properties (text, context, positions, their state and
the contextual vector), never a span's offsets, chunk, tag, type or revision, and deletes
nothing. It is meant to run while no backend or other writer uses the store
(``docs/DATA_MAINTENANCE.md``): each write is checked against the revision it was
computed for (``service.write_if_revision``), but that check and the write are atomic only
within this process, not against edits of a running backend. It is bounded by ``limit``
spans per run; running it again continues with what is still incomplete.
Spans whose offsets do not describe the document text are recorded ``invalid`` once and
then left alone (a data inconsistency to review, not something to repair here).
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from uuid import UUID

from semant_demo.core.outcomes import StepFailure
from semant_demo.features.annotations.derivation import DerivedText
from semant_demo.features.annotations.enrichment import text_current, vector_current
from semant_demo.features.annotations.schemas import AnnotationRow, EnrichmentStatus, VectorStatus
from semant_demo.features.annotations.service import (
    AnnotationStore, Refresh, derive_refresh, refresh_vector, write_if_revision,
)
from semant_demo.features.annotations.source import ChunkSource
from semant_demo.adapters.weaviate.writes import step_failure


def text_state(row: AnnotationRow) -> str:
    """``current``, ``outdated`` (older derivation policy), ``failed``, ``invalid`` or
    ``missing`` (never derived, or derived for another revision)."""
    if text_current(row):
        return "current"
    if (row.enrichedRevision or 0) == (row.revision or 0):
        if row.enrichmentStatus == EnrichmentStatus.ready:
            return "outdated"
        if row.enrichmentStatus in (EnrichmentStatus.failed, EnrichmentStatus.invalid):
            return row.enrichmentStatus.value
    return "missing"


def vector_state(row: AnnotationRow, config_id: str | None) -> str:
    """``current``, ``failed`` (for the current revision), ``stale`` (another revision,
    configuration or derivation policy) or ``pending``; ``unconfigured`` without a vector
    configuration."""
    if config_id is None:
        return "unconfigured"
    if vector_current(row, config_id):
        return "current"
    if row.vectorStatus == VectorStatus.failed and (row.vectorRevision or 0) == (row.revision or 0) \
            and row.vectorConfig == config_id:
        return "failed"
    return "stale" if row.vectorStatus == VectorStatus.ready else "pending"


def _needs_text(row: AnnotationRow) -> bool:
    return text_state(row) in ("outdated", "failed", "missing")


def _needs_vector(row: AnnotationRow, config_id: str | None) -> bool:
    return config_id is not None and vector_state(row, config_id) != "current" and text_state(row) != "invalid"


def _incomplete(row: AnnotationRow, config_id: str | None) -> bool:
    return _needs_text(row) or _needs_vector(row, config_id)


@dataclass
class TenantReport:
    collection_id: str
    spans: int = 0
    text: Counter = field(default_factory=Counter)
    vector: Counter = field(default_factory=Counter)
    incomplete: int = 0
    """Spans whose text or vector the backfill would (re)write."""

    def as_dict(self) -> dict:
        return {"collection_id": self.collection_id, "spans": self.spans, "text": dict(self.text),
                "vector": dict(self.vector), "incomplete": self.incomplete}


async def _rows(store: AnnotationStore, collection_id: UUID) -> list[AnnotationRow]:
    return [r async for r in store.spans.iterate_rows(collection_id)]


async def status(store: AnnotationStore, collection_ids: list[UUID]) -> list[TenantReport]:
    """Counts of each tenant's spans by text and vector state (reads every span)."""
    vector = store.enrichment.vector
    reports = []
    for cid in collection_ids:
        report = TenantReport(str(cid))
        for row in await _rows(store, cid):
            report.spans += 1
            report.text[text_state(row)] += 1
            report.vector[vector_state(row, vector.id if vector else None)] += 1
            report.incomplete += _incomplete(row, vector.id if vector else None)
        reports.append(report)
    return reports


@dataclass
class BackfillResult:
    processed: int = 0
    text_written: int = 0
    vector_written: int = 0
    superseded: int = 0
    """Spans whose revision changed while being backfilled (an edit in this process): the
    derived data computed for the old revision was dropped."""
    not_processed: int = 0
    """Incomplete spans not attempted in this run (``limit`` reached)."""
    remaining_incomplete: int = 0
    """Spans still incomplete when the run ended, read again afterwards: the not processed
    ones, failed steps and, with ``vectors=False``, vectors still to embed. ``0`` means
    the tenants are complete for the configured vector."""
    failed: list[StepFailure] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"processed": self.processed, "text_written": self.text_written,
                "vector_written": self.vector_written, "superseded": self.superseded,
                "not_processed": self.not_processed, "remaining_incomplete": self.remaining_incomplete,
                "failed": [f.model_dump() for f in self.failed]}


def _stored(row: AnnotationRow) -> DerivedText:
    return DerivedText(text=row.text or "", left_context=row.leftContext or "", right_context=row.rightContext or "",
                       start_char=row.documentStartChar, end_char=row.documentEndChar,
                       start_word=row.documentStartWord, end_word=row.documentEndWord)


async def backfill(store: AnnotationStore, collection_ids: list[UUID], *, limit: int,
                   vectors: bool = True) -> BackfillResult:
    """Derive the missing, failed, stale or outdated text and (with ``vectors``) vectors
    of at most ``limit`` spans; each span reads its anchor and nearby chunks (``source.py``),
    chunks shared by spans of the run once. Afterwards every tenant is read again for
    ``remaining_incomplete``."""
    configured = store.enrichment.vector.id if store.enrichment.vector else None
    config_id = configured if vectors else None
    result = BackfillResult()
    source = ChunkSource(store.documents)
    for cid in collection_ids:
        todo = [r for r in await _rows(store, cid) if _incomplete(r, config_id)]
        take, rest = todo[:max(0, limit - result.processed)], todo[max(0, limit - result.processed):]
        result.not_processed += len(rest)
        by_document: dict[UUID | None, list[AnnotationRow]] = defaultdict(list)
        for row in take:
            by_document[row.documentId].append(row)
        for rows in by_document.values():
            await _backfill_document(store, cid, rows, config_id, result, source)
    for cid in collection_ids:
        result.remaining_incomplete += sum(_incomplete(r, configured) for r in await _rows(store, cid))
    return result


async def _backfill_document(store: AnnotationStore, cid: UUID, rows: list[AnnotationRow], config_id: str | None,
                             result: BackfillResult, source: ChunkSource) -> None:
    for row in rows:
        result.processed += 1
        revision = row.revision or 0
        if _needs_text(row):
            refresh = await derive_refresh(store, row.chunkId, row.start, row.end, revision, source)
            refresh.needs_vector = config_id is not None
            result.failed += refresh.failures
            try:
                written = await write_if_revision(
                    store, cid, row.id, revision,
                    refresh.properties(reset_vector=True, with_revision=False))
            except Exception as e:
                result.failed.append(step_failure("derive_annotation", row.id, e))
                continue
            if not written:
                result.superseded += 1
                continue
            result.text_written += refresh.derived is not None
        else:
            refresh = Refresh(revision, _stored(row), EnrichmentStatus.ready)
        if config_id is not None and refresh.derived is not None:
            result.failed += await refresh_vector(store, cid, row.id, refresh)
            result.vector_written += refresh.vector_stored
