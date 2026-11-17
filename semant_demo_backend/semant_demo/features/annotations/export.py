"""CSV export of a collection's annotations (#719).

One request exports one collection: the selected annotations (by id, whatever the current
filters), every match of the annotation query (``AnnotationFilters``, #663) or every annotation
of chosen types, never only a loaded page. The rows are in no particular order.

Two phases. First, before any byte is sent, the export is authorized (collection read access) and
the ids of the annotations to export are resolved with the concordance's own query (``_resolve``):
each id query reads with a limit and no offset, so concurrent edits cannot make it skip or repeat
annotations; more than ``_MAX_WINDOW`` matches (Weaviate's per-query maximum) are read in batches of
whole documents. What cannot be resolved completely is refused then (400), never truncated: more
than ``_MAX_DOCUMENTS`` annotated documents or ``_MAX_WINDOW`` matches in one document, or, beyond
``_MAX_WINDOW`` matches, annotations without a recorded document. The file holds exactly these
annotations (``X-Export-Count``): one created later is not in it.

Then the rows are read by id and written in pages of ``EXPORT_PAGE`` (tag names and attribute
definitions once; documents, anchor-chunk metadata and AI metadata once per page, never per row),
with their values at that moment. When a resolved annotation was deleted meanwhile, or a read
fails, the stream is aborted: the download fails instead of ending as a shorter, valid-looking
file. There is no snapshot of values (#335).

Columns (documented for users in docs/ARCHITECTURE.md, *Annotation CSV export*):

- Always: annotation id, tag id and name, ``status`` (``confirmed`` = ``pos``, ``proposal`` =
  ``auto``, ``rejected`` = ``neg``), ``text_status`` and, only when it is ``ready``, the annotated
  text, left and right context and the document id with ``document_start_char`` /
  ``document_end_char`` (half-open UTF-16 code-unit offsets in the whole document's text, #463);
  otherwise these cells are empty, never computed here. Then one column per attribute
  (``attribute: <name>``, the collection's order) with the labels of its accepted values, several
  joined by `` | `` in the attribute's value order; empty: no value. Only confirmed annotations
  hold accepted values (values kept on proposals or rejected annotations are not exported); values
  of an attribute that no longer applies to the annotation's tag (#500) are listed apart in
  ``inapplicable_attribute_values`` as ``<attribute>: <labels>``, separated by `` || ``.
- ``chunk_metadata``: the anchor chunk's (the chunk the annotation starts on) ``Chunks.language``
  and the configured classifications (``chunk_<name>``); for an annotation spanning several chunks
  only the anchor's values.
- ``document_metadata``: whether the document can be read and its bibliographic fields.
- ``provenance``: origin, creator, reviewer and last editor (id and name, when the person still
  has access to the collection) with their times, revision, edit version and AI run, confidence
  and reason.

Spreadsheet formula injection: a text cell starting with ``=``, ``+``, ``-``, ``@``, a tab or a
carriage return is prefixed with ``'`` (OWASP), also in headers; numbers are never changed. The
stored text is not modified, only its exported cell.
"""
import asyncio
import csv
import io
import logging
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID

from semant_demo.adapters.sql.attributes import AttributeRepository
from semant_demo.adapters.sql.users import UserLookup
from semant_demo.core.errors import InvalidRequestError
from semant_demo.features.annotations import attribute_codec as codec
from semant_demo.features.annotations import service
from semant_demo.features.annotations.enrichment import text_current
from semant_demo.features.annotations.schemas import (
    AnnotationExportRequest, AnnotationExportScope, AnnotationFilters, AnnotationRow, AnnotationSort,
    CsvDelimiter, SpanType, TagSpan,
)
from semant_demo.features.annotations.service import AnnotationStore, Id
from semant_demo.features.attributes import service as attributes_service
from semant_demo.features.attributes.schemas import Attribute
from semant_demo.features.documents.criteria import LANGUAGE_PROPERTY, ChunkVocabulary, document_conditions
from semant_demo.features.documents.schemas import Document
from semant_demo.features.user_collections import access
from semant_demo.features.user_collections import service as collections_service
from semant_demo.features.user_collections.access import Principal

logger = logging.getLogger(__name__)

EXPORT_PAGE = 500
"""Annotations read and written per page of an export."""
VALUE_SEPARATOR = " | "
"""Between several values in one cell (attribute values, authors, chunk classifications)."""
ATTRIBUTE_SEPARATOR = " || "
"""Between the attributes listed in ``inapplicable_attribute_values``."""
BOM = "﻿"
"""Lets spreadsheet applications recognize UTF-8."""
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
STATUS_LABELS = {SpanType.pos: "confirmed", SpanType.auto: "proposal", SpanType.neg: "rejected"}
ALL_TYPES = [SpanType.pos, SpanType.auto, SpanType.neg]

_DOCUMENT_FIELDS: list[tuple[str, Callable[[Document], Any]]] = [
    ("document_title", lambda d: d.title), ("document_subtitle", lambda d: d.subtitle),
    ("document_year", lambda d: d.yearIssued), ("document_date_issued", lambda d: d.dateIssued),
    ("document_authors", lambda d: d.author), ("document_editors", lambda d: d.editors),
    ("document_publisher", lambda d: d.publisher), ("document_place_of_publication", lambda d: d.placeOfPublication),
    ("document_library", lambda d: d.library), ("document_language", lambda d: d.language),
    ("document_type", lambda d: d.documentType), ("document_genre", lambda d: d.genre),
    ("document_part_number", lambda d: d.partNumber), ("document_part_name", lambda d: d.partName),
    ("document_series_name", lambda d: d.seriesName), ("document_series_number", lambda d: d.seriesNumber),
    ("document_edition", lambda d: d.edition),
]
"""The bibliographic columns of the ``document_metadata`` group (the document id is always present).
``document_language`` is the document's language, not the anchor chunk's (``chunk_language``)."""


class ExportInterrupted(RuntimeError):
    """The export could not be completed after its first rows were sent; the stream is aborted."""


def cell(value: Any) -> str:
    """The CSV cell of a value: empty for ``None``, lists joined by ``VALUE_SEPARATOR``, text that a
    spreadsheet would evaluate as a formula prefixed with ``'``."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return protect(VALUE_SEPARATOR.join(str(v) for v in value if v is not None))
    return protect(str(value))


def protect(text: str) -> str:
    """``text`` that spreadsheet applications show as text, not evaluate as a formula."""
    return f"'{text}" if text.startswith(_FORMULA_START) else text


@dataclass
class _Context:
    """What the rows of one export are written with: read once, before the first row."""
    request: AnnotationExportRequest
    tags: dict[UUID, str]
    attributes: list[Attribute]
    classifications: list[str]
    people: dict[UUID, str] = field(default_factory=dict)


def _columns(context: _Context) -> list[str]:
    request = context.request
    columns = ["annotation_id", "tag_id", "tag_name", "status", "text_status", "text", "left_context",
               "right_context", "document_id", "document_start_char", "document_end_char"]
    columns += [f"attribute: {a.name}" for a in context.attributes]
    if context.attributes:
        columns.append("inapplicable_attribute_values")
    if request.chunk_metadata:
        columns += ["chunk_language", *(f"chunk_{name}" for name in context.classifications)]
    if request.document_metadata:
        columns += ["document_available", *(name for name, _ in _DOCUMENT_FIELDS)]
    if request.provenance:
        columns += ["origin", "created_by", "created_by_name", "created_at", "reviewed_by", "reviewed_by_name",
                    "reviewed_at", "last_edited_by", "last_edited_by_name", "last_edited_at", "revision",
                    "edit_version", "ai_run_id", "ai_confidence", "ai_reason"]
    return columns


def _labels(attribute: Attribute, value_ids: list[UUID]) -> str:
    """The labels of the values, in the attribute's value order; an id no value has as itself."""
    order = {v.id: (i, v.label) for i, v in enumerate(attribute.values)}
    known = sorted((order[v] for v in value_ids if v in order))
    return VALUE_SEPARATOR.join([label for _, label in known] + [str(v) for v in value_ids if v not in order])


def _attribute_cells(row: AnnotationRow, attributes: list[Attribute]) -> list[str]:
    """One cell per attribute and the inapplicable values cell. Only a confirmed annotation's
    values are accepted classifications (#331); values of an attribute that does not apply to its
    current tag (#500) are listed apart, never in the attribute's column."""
    held = codec.group(row.attributeValues) if row.type == SpanType.pos else {}
    cells, inapplicable = [], []
    for attribute in attributes:
        values = held.get(attribute.id, [])
        if values and row.tagId is not None and attributes_service.applies(attribute, row.tagId):
            cells.append(_labels(attribute, values))
        else:
            cells.append("")
            if values:
                inapplicable.append(f"{attribute.name}: {_labels(attribute, values)}")
    return [*cells, ATTRIBUTE_SEPARATOR.join(inapplicable)] if attributes else []


def _record(row: AnnotationRow, context: _Context, document: Document | None, chunk: dict[str, Any] | None,
            span: TagSpan | None) -> list[Any]:
    request = context.request
    ready = text_current(row)
    record: list[Any] = [
        row.id, row.tagId, context.tags.get(row.tagId) if row.tagId else None,
        STATUS_LABELS.get(row.type) if row.type else None, service._text_status(row).value,
        row.text if ready else None, row.leftContext if ready else None, row.rightContext if ready else None,
        row.documentId, row.documentStartChar if ready else None, row.documentEndChar if ready else None,
        *_attribute_cells(row, context.attributes),
    ]
    if request.chunk_metadata:
        chunk = chunk or {}
        record += [chunk.get(LANGUAGE_PROPERTY), *(chunk.get(name) for name in context.classifications)]
    if request.document_metadata:
        record += [document is not None, *(read(document) if document else None for _, read in _DOCUMENT_FIELDS)]
    if request.provenance:
        def person(user_id: UUID | None) -> list[Any]:
            return [user_id, context.people.get(user_id) if user_id else None]
        record += [row.origin.value if row.origin else "unknown", *person(row.createdBy), row.createdAt,
                   *person(row.reviewedBy), row.reviewedAt, *person(row.lastEditedBy), row.lastEditedAt,
                   row.revision or 0, row.editVersion or 0, row.aiRunId,
                   span.confidence if span else None, span.reason if span else None]
    return record


def _csv(records: Sequence[Sequence[Any]], delimiter: CsvDelimiter) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";" if delimiter == CsvDelimiter.semicolon else ",",
                        quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerows([[cell(v) for v in record] for record in records])
    return buffer.getvalue().encode("utf-8")


@dataclass
class AnnotationExport:
    """A counted, authorized export whose rows are read while ``content`` is iterated."""
    scope: AnnotationExportScope
    count: int
    """Annotations the file holds (one row each)."""
    missing: int
    """Scope ``selection``: requested ids that are no annotation of the collection (any more)."""
    columns: list[str]
    content: AsyncIterator[bytes]


def _query(request: AnnotationExportRequest):
    """The annotation query of the export's scope and the requested annotation ids."""
    if request.scope == AnnotationExportScope.selection:
        ids = list(dict.fromkeys(request.annotation_ids or []))
        return service._filters_query(AnnotationFilters(types=ALL_TYPES), ids), AnnotationFilters(), ids
    if request.scope == AnnotationExportScope.filters:
        assert request.filters is not None
        return service._filters_query(request.filters), request.filters, None
    return service._filters_query(AnnotationFilters(types=request.types)), AnnotationFilters(), None


def _batches(counts: dict[UUID, int], limit: int) -> list[list[UUID]]:
    """The documents in batches of whole documents whose matches add up to at most ``limit``."""
    batches: list[list[UUID]] = []
    size = limit
    for document, count in counts.items():
        if count > limit:
            raise InvalidRequestError(
                f"A document has {count} matching annotations; at most {limit} per document can be exported "
                "at once. Narrow the filters.")
        if size + count > limit:
            batches.append([])
            size = 0
        batches[-1].append(document)
        size += count
    return batches


async def _resolve(store: AnnotationStore, cid: UUID, query, filters: AnnotationFilters,
                   ids: list[UUID] | None) -> list[UUID]:
    """The ids of the annotations to export, as they match now, in no particular order. Each id
    query reads with ``limit`` and no offset, so concurrent changes cannot shift it: up to
    ``_MAX_WINDOW`` matches in one query, more by batches of whole documents (Weaviate returns
    at most ``_MAX_WINDOW`` objects per query). Raises before any row for what cannot be resolved
    completely."""
    window = service._MAX_WINDOW
    if ids is not None:  # the selection (at most MAX_RESOLVED_IDS): the members that exist
        found = await store.spans.query_ids(cid, query, limit=max(len(ids), 1))
        return [i for i in ids if i in found]
    document_ids = filters.document_ids or None
    conditions = document_conditions(filters.document_filters)
    query, _ = await service._apply_near(store, cid, filters, query, conditions)
    if conditions:  # only annotations of the documents the document filters select
        documents = await service._annotated_documents(store, cid, query, AnnotationSort.document, document_ids,
                                                       conditions)
        counts, total = documents.counts, sum(documents.counts.values())
    else:
        counts, total = None, await store.spans.count_rows(cid, query, document_ids)
    if total <= window:
        return list(await store.spans.query_ids(cid, query, document_ids=list(counts) if counts is not None
                                                else document_ids, limit=max(total, 1)))
    if counts is None:
        counts = await store.spans.count_by_document(cid, query, service._MAX_DOCUMENTS + 1, document_ids)
        if len(counts) > service._MAX_DOCUMENTS:
            raise InvalidRequestError(f"The annotations are in more than {service._MAX_DOCUMENTS} documents; "
                                      "filter by tag or text first.")
        if total > sum(counts.values()):
            raise InvalidRequestError(
                f"{total - sum(counts.values())} of the annotations have no recorded document, so more than "
                f"{window} cannot be exported at once; narrow the filters.")
    resolved: list[UUID] = []
    for batch in _batches(counts, window):
        resolved += await store.spans.query_ids(cid, query, document_ids=batch,
                                                limit=sum(counts[d] for d in batch))
    return resolved


async def export_annotations(store: AnnotationStore, definitions: AttributeRepository, users: UserLookup,
                             vocabulary: ChunkVocabulary, user: Principal | None, collection_id: Id,
                             request: AnnotationExportRequest) -> AnnotationExport:
    """
    The CSV export of the collection's annotations in ``request.scope`` (#719): authorized, then the
    ids of the annotations to export resolved; its ``content`` reads and writes their rows by id,
    page by page. Raises before any row for a scope that cannot be resolved completely; ``content``
    raises ``ExportInterrupted`` when a resolved annotation was deleted or a read fails meanwhile.
    """
    grant = await access.require_collection_read(store.collections, user, collection_id)
    query, filters, ids = _query(request)
    service._require_attribute_properties(store, query)
    cid = await service.use_tenant(store, grant)
    resolved = await _resolve(store, cid, query, filters, ids) if ids != [] else []

    attributes_store = attributes_service.AttributeStore(definitions=definitions, annotations=store)
    tags, attributes, people = await asyncio.gather(
        store.tags.read_by_collection(grant.collection_id),
        attributes_service.list_attributes(attributes_store, user, grant.collection_id)
        if store.spans.attributes else _nothing(),
        collections_service.list_people(store.collections, users, user, grant.collection_id)
        if request.provenance else _nothing())
    context = _Context(request=request, tags={t.id: t.name for t in tags}, attributes=list(attributes),
                       classifications=list(vocabulary.classifications),
                       people={p.id: p.name or p.username or "" for p in people})
    columns = _columns(context)
    return AnnotationExport(scope=request.scope, count=len(resolved),
                            missing=len(ids) - len(resolved) if ids is not None else 0,
                            columns=columns, content=_content(store, cid, resolved, context, columns))


async def _nothing() -> list:
    return []


async def _content(store: AnnotationStore, cid: UUID, resolved: list[UUID], context: _Context,
                   columns: list[str]) -> AsyncIterator[bytes]:
    request = context.request
    yield BOM.encode("utf-8") + _csv([columns], request.delimiter)
    written = 0
    try:
        for offset in range(0, len(resolved), EXPORT_PAGE):
            page = resolved[offset:offset + EXPORT_PAGE]
            found = await store.spans.read_rows_by_id(cid, page)
            if len(found) != len(page):
                raise ExportInterrupted("An annotation was deleted during the export")
            rows = [found[i] for i in page]
            documents, chunks, spans = await asyncio.gather(
                store.documents.read_many(list({r.documentId for r in rows if r.documentId is not None}))
                if request.document_metadata else _empty(),
                store.documents.read_chunk_metadata(
                    list({r.chunkId for r in rows if r.chunkId is not None}),
                    [LANGUAGE_PROPERTY, *context.classifications]) if request.chunk_metadata else _empty(),
                store.spans.read_many(cid, page) if request.provenance else _empty())
            records = [_record(r, context, documents.get(r.documentId) if r.documentId else None,
                               chunks.get(r.chunkId) if r.chunkId else None, spans.get(r.id)) for r in rows]
            written += len(records)
            yield _csv(records, request.delimiter)
    except ExportInterrupted:
        logger.warning("Annotation export aborted after %d of %d rows: an annotation was deleted",
                       written, len(resolved))
        raise
    except Exception as exc:
        logger.warning("Annotation export aborted after %d of %d rows: %s", written, len(resolved),
                       type(exc).__name__)
        raise ExportInterrupted("Reading the annotations failed during the export") from exc


async def _empty() -> dict:
    return {}
