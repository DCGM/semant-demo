"""CSV export of a collection's annotations (#719).

One request exports one collection: the selected annotations (by id, whatever the current
filters), every match of the annotation query (``AnnotationFilters``, #663) or every annotation
of chosen types. The scope is resolved with the concordance's own query and document order
(``service._annotated_documents``, ``service._rows_in_document_order``), so the export holds the
same annotations the workspace lists for the same filters, never only a loaded page.

Before any byte is sent the export is authorized (collection read access), validated and counted;
limits are refused then (400), never applied by truncation: more than ``_MAX_DOCUMENTS`` annotated
documents, more than ``_MAX_WINDOW`` annotations in one document, matching annotations without a
recorded document. The rows are then read and written in pages of ``EXPORT_PAGE`` (the documents,
tag names and attribute definitions once; the anchor chunks' metadata and the AI metadata once per
page, never per row). When a page reads fewer or more annotations than counted (they changed
during the export) or a read fails, the stream is aborted: the download fails instead of ending
as a shorter, valid-looking file. There is no snapshot (#335): annotations changed while the export
runs may be exported before or after the change.

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
    documents: dict[UUID, Document]
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


def _record(row: AnnotationRow, context: _Context, chunk: dict[str, Any] | None,
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
        document = context.documents.get(row.documentId) if row.documentId else None
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


async def export_annotations(store: AnnotationStore, definitions: AttributeRepository, users: UserLookup,
                             vocabulary: ChunkVocabulary, user: Principal | None, collection_id: Id,
                             request: AnnotationExportRequest) -> AnnotationExport:
    """
    The CSV export of the collection's annotations in ``request.scope`` (#719), authorized,
    validated and counted; its ``content`` reads and writes the rows page by page. Raises before any
    row for a scope that cannot be exported completely; ``content`` raises ``ExportInterrupted``
    when the annotations change or a read fails meanwhile.
    """
    grant = await access.require_collection_read(store.collections, user, collection_id)
    query, filters, ids = _query(request)
    service._require_attribute_properties(store, query)
    document_ids = filters.document_ids or None
    conditions = document_conditions(filters.document_filters)
    cid = await service.use_tenant(store, grant)
    if ids == []:
        found = service._Documents(order=[], counts={}, documents={})
    else:
        found = await service._annotated_documents(store, cid, query, AnnotationSort.document, document_ids,
                                                   conditions)
    total = sum(found.counts.values())
    if not conditions and ids != []:
        matching = await store.spans.count_rows(cid, query, document_ids)
        if matching > total:
            raise InvalidRequestError(
                f"{matching - total} of the annotations have no recorded document and cannot be exported; "
                "ask an administrator to run the annotation backfill.")
    largest = max(found.counts.values(), default=0)
    if largest > service._MAX_WINDOW:
        raise InvalidRequestError(
            f"A document has {largest} matching annotations; at most {service._MAX_WINDOW} per document can be "
            "exported at once. Narrow the filters.")

    attributes_store = attributes_service.AttributeStore(definitions=definitions, annotations=store)
    tags, attributes, people = await asyncio.gather(
        store.tags.read_by_collection(grant.collection_id),
        attributes_service.list_attributes(attributes_store, user, grant.collection_id)
        if store.spans.attributes else _nothing(),
        collections_service.list_people(store.collections, users, user, grant.collection_id)
        if request.provenance else _nothing())
    context = _Context(request=request, tags={t.id: t.name for t in tags}, attributes=list(attributes),
                       documents=found.documents, classifications=list(vocabulary.classifications),
                       people={p.id: p.name or p.username or "" for p in people})
    columns = _columns(context)
    return AnnotationExport(scope=request.scope, count=total, missing=len(ids) - total if ids is not None else 0,
                            columns=columns, content=_content(store, cid, query, found, total, context, columns))


async def _nothing() -> list:
    return []


async def _content(store: AnnotationStore, cid: UUID, query, found, total: int, context: _Context,
                   columns: list[str]) -> AsyncIterator[bytes]:
    request = context.request
    yield BOM.encode("utf-8") + _csv([columns], request.delimiter)
    written = 0
    try:
        for offset in range(0, total, EXPORT_PAGE):
            rows = await service._rows_in_document_order(store, cid, query, found, EXPORT_PAGE, offset)
            if len(rows) != min(EXPORT_PAGE, total - offset):
                raise ExportInterrupted("The annotations changed during the export")
            chunks, spans = await asyncio.gather(
                store.documents.read_chunk_metadata(
                    list({r.chunkId for r in rows if r.chunkId is not None}),
                    [LANGUAGE_PROPERTY, *context.classifications]) if request.chunk_metadata else _empty(),
                store.spans.read_many(cid, [r.id for r in rows]) if request.provenance else _empty())
            records = [_record(r, context, chunks.get(r.chunkId) if r.chunkId else None, spans.get(r.id))
                       for r in rows]
            written += len(records)
            yield _csv(records, request.delimiter)
    except ExportInterrupted:
        logger.warning("Annotation export aborted after %d of %d rows: the annotations changed", written, total)
        raise
    except Exception as exc:
        logger.warning("Annotation export aborted after %d of %d rows: %s", written, total, type(exc).__name__)
        raise ExportInterrupted("Reading the annotations failed during the export") from exc


async def _empty() -> dict:
    return {}
