"""Concordance (KWIC) queries of the Annotations service (#329), with in-memory fakes.

Rows are paged in a total order (document title, year, position, id; or annotated text,
id), so consecutive pages together are exactly the full result; filters by tag, type,
text, document and year; rejected annotations only on request; derived text only when
current; denied requests read nothing. The Weaviate queries themselves:
tests/integration/test_annotation_concordance.py.
"""
import re
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from semant_demo.adapters.weaviate.criteria import UnavailableFilter
from semant_demo.core.errors import InvalidRequestError, NotFoundError, ServiceUnavailableError
from semant_demo.features.annotations import service
from semant_demo.features.annotations.derivation import DERIVATION_VERSION
from semant_demo.features.annotations.schemas import (
    MAX_ATTRIBUTE_FILTER_VALUES, MAX_ATTRIBUTE_FILTERS, AnnotationFilters, AnnotationIdsRequest, AnnotationRow,
    AnnotationSort, EnrichmentStatus, SpanType, TextScope, TextStatus,
)
from semant_demo.features.documents.criteria import AnyOf, ContainsWords, DocumentFilters, NumberRange
from semant_demo.features.annotations.collation import sort_keys
from semant_demo.features.annotations.enrichment import Enrichment
from semant_demo.features.annotations.service import AnnotationStore
from semant_demo.features.annotations import attribute_codec as codec
from semant_demo.features.documents.schemas import Document
from semant_demo.features.user_collections.access import AuthenticationRequired, ResourceNotFound

OWNER, SHARED, OTHER = (SimpleNamespace(id=uuid4(), is_superuser=False) for _ in range(3))
COLLECTION = uuid4()
TAG, OTHER_TAG = uuid4(), uuid4()
# Titles out of id order, one document without year, one deleted from the corpus.
DOC_B = UUID("00000000-0000-4000-8000-000000000001")
DOC_A = UUID("00000000-0000-4000-8000-000000000002")
DOC_NO_YEAR = UUID("00000000-0000-4000-8000-000000000003")
DOC_GONE = UUID("00000000-0000-4000-8000-000000000004")
DOCUMENTS = {
    DOC_A: Document(id=DOC_A, title="Almanach", yearIssued=1912, library="mzk", language="ces"),
    DOC_B: Document(id=DOC_B, title="Bulletin", yearIssued=1850, library="nkp", language="deu"),
    DOC_NO_YEAR: Document(id=DOC_NO_YEAR, title="Čtení", library="mzk"),
}


class FakeCollections:
    async def read_access_record(self, cid):
        return (OWNER.id, {SHARED.id}) if cid == COLLECTION else None


def _holds(document: Document, condition) -> bool:
    """The shared document predicates (``criteria``), as the Weaviate rendering evaluates them."""
    value = getattr(document, condition.prop)
    if isinstance(condition, NumberRange):
        return value is not None and (condition.minimum is None or value >= condition.minimum) \
            and (condition.maximum is None or value <= condition.maximum)
    if isinstance(condition, ContainsWords):
        words = (value or "").casefold().split()
        return any(all(any(w.casefold() in t for t in words) for w in alternative)
                   for alternative in condition.alternatives)
    assert isinstance(condition, AnyOf)
    return value is not None and value.casefold() in {v.casefold() for v in condition.values}


class FakeDocuments:
    def __init__(self):
        self.reads: list[list[UUID]] = []
        self.eligible_reads: list[tuple[list[UUID], list]] = []
        self.unavailable: Exception | None = None

    async def read_many(self, ids):
        self.reads.append(list(ids))
        return {i: DOCUMENTS[i] for i in ids if i in DOCUMENTS}

    async def read_eligible(self, ids, collection_id=None, conditions=(), include_restricted=False):
        assert collection_id is None  # annotated documents of a collection need not be in it
        # The collection is authorized: its annotated documents are not limited to public ones (#279).
        assert include_restricted
        if self.unavailable is not None:
            raise self.unavailable
        self.eligible_reads.append((list(ids), list(conditions)))
        return {i: DOCUMENTS[i] for i in ids
                if i in DOCUMENTS and all(_holds(DOCUMENTS[i], c) for c in conditions)}


def years(year_min=None, year_max=None, **fields) -> AnnotationFilters:
    return AnnotationFilters(document_filters=DocumentFilters(year_min=year_min, year_max=year_max), **fields)


_SCOPE_FIELDS = {TextScope.annotation: ("text",), TextScope.context: ("leftContext", "rightContext"),
                 TextScope.both: ("text", "leftContext", "rightContext")}


def _word_in(row: AnnotationRow, word: str, scope: TextScope) -> bool:
    """``like *word*`` on a word-tokenized field: inside one of its words, ignoring case."""
    return any(word.lower() in token.lower() for name in _SCOPE_FIELDS[scope]
               for token in re.findall(r"[^\W_]+", getattr(row, name) or ""))


def _position_key(row: AnnotationRow):
    # Weaviate's ascending sort puts missing values first.
    return tuple((v is not None, v or 0) for v in (row.documentStartChar, row.documentEndChar)) + (str(row.id),)


class FakeSpans:
    """Rows of one tenant, queried with the semantics of ``SpanRepository``'s queries."""

    def __init__(self):
        self.rows: list[AnnotationRow] = []
        self.queries = 0
        self.provenance = False
        self.attributes = True
        self.keys: dict[UUID, dict] = {}
        """Stored sort key properties by row id (#666); rows read only ``sortKeyVersion``."""
        self.sorted_by: list[str | None] = []

    def _match(self, query, document_ids):
        return [r for r in self.rows
                if r.type in query.types
                and (not query.tag_ids or r.tagId in query.tag_ids)
                and (not query.words or (r.enrichmentStatus == EnrichmentStatus.ready
                                         and r.derivationVersion == query.derivation_version))
                and all(_word_in(r, w, query.text_scope) for w in query.words)
                and (document_ids is None or r.documentId in document_ids)
                and (query.ids is None or r.id in query.ids)
                and (not query.attribute_values or r.type == SpanType.pos)
                and all(any(codec.encode(a, v) in (r.attributeValues or []) for v in vs)
                        for a, vs in query.attribute_values.items())
                and not any(c.startswith(f"{a}:") for a in query.attribute_unassigned
                            for c in (r.attributeValues or []) if r.type == SpanType.pos)
                and (query.sort_key_version is None or r.sortKeyVersion == query.sort_key_version)
                and (query.holds_value is None
                     or (r.type == SpanType.pos and query.holds_value in (r.attributeValues or [])))
                and (r.type != SpanType.pos or not set(query.holds_none_of) & set(r.attributeValues or []))
                and (query.near_ids is None or r.id in query.near_ids)]

    async def count_by_document(self, cid, query, limit, document_ids=None):
        counts: dict[UUID, int] = {}
        for row in self._match(query, document_ids):
            if row.documentId is not None:
                counts[row.documentId] = counts.get(row.documentId, 0) + 1
        return dict(list(counts.items())[:limit])

    async def count_rows(self, cid, query, document_ids=None):
        return len(self._match(query, document_ids))

    async def query_rows(self, cid, query, *, sort_by=None, document_ids=None, limit, offset=0, descending=False):
        self.queries += 1
        self.sorted_by.append(sort_by)
        rows = self._match(query, document_ids)
        value = (lambda r: getattr(r, sort_by)) if sort_by in ("text", None) else (lambda r: self.keys.get(r.id, {}).get(sort_by))
        if sort_by is None:
            ordered = sorted(rows, key=_position_key)
        elif descending:  # as Weaviate: without a value last, then the id ascending
            by_id = sorted(rows, key=lambda r: str(r.id))
            ordered = (sorted([r for r in by_id if value(r) is not None], key=value, reverse=True)
                       + [r for r in by_id if value(r) is None])
        else:
            ordered = sorted(rows, key=lambda r: (value(r) is not None, value(r) or "", str(r.id)))
        return ordered[offset:offset + limit]


    async def query_positions(self, cid, query, *, document_ids=None, limit):
        self.queries += 1
        return sorted(self._match(query, document_ids), key=lambda r: str(r.id))[:limit]

    async def query_ids(self, cid, query, *, document_ids=None, limit):
        self.queries += 1
        return {r.id: (r.editVersion or 0, r.attributeVersion or 0)
                for r in sorted(self._match(query, document_ids), key=lambda r: str(r.id))[:limit]}


def row(document, start, text="slovo", *, tag=TAG, type=SpanType.pos, current=True, rid=None):
    derived = {"text": text, "leftContext": "vlevo ", "rightContext": " vpravo",
               "documentStartChar": start, "documentEndChar": start + len(text), "enrichmentStatus": "ready",
               "enrichedRevision": 1, "derivationVersion": DERIVATION_VERSION} if current else {}
    return AnnotationRow(id=rid or uuid4(), tagId=tag, type=type, chunkId=uuid4(), documentId=document, start=0,
                         end=len(text), revision=1, **derived)


def with_keys(store) -> None:
    """The store holds the sort keys of #666 and every row with current text has its keys."""
    store.enrichment = Enrichment(derived=True, sort_keys=True)
    for r in store.spans.rows:
        if r.text is not None:
            keys = sort_keys(r.text, r.leftContext or "", r.rightContext or "")
            store.spans.keys[r.id] = keys.properties(r.revision or 0)
            r.sortKeyVersion, r.sortKeyRevision = keys.version, r.revision


ATTRIBUTE = UUID("00000000-0000-4000-8000-0000000000a1")
RED, GREEN, BLUE, OLD = (UUID(f"00000000-0000-4000-8000-0000000000b{i}") for i in range(4))


class FakeAttributes:
    """The collection's attribute definitions: ``ATTRIBUTE`` with values red, green, blue and the
    retired old (defined between green and blue)."""

    def __init__(self):
        self.reads = 0

    async def read(self, collection_id, attribute_id):
        self.reads += 1
        if collection_id != COLLECTION or attribute_id != ATTRIBUTE:
            return None
        values = [SimpleNamespace(id=RED, retired=False), SimpleNamespace(id=GREEN, retired=False),
                  SimpleNamespace(id=OLD, retired=True), SimpleNamespace(id=BLUE, retired=False)]
        return SimpleNamespace(id=ATTRIBUTE, values=values)


@pytest.fixture
def store():
    return AnnotationStore(collections=FakeCollections(), tags=None, spans=FakeSpans(), documents=FakeDocuments())


def ids(page):
    return [r.id for r in page.rows]


async def all_pages(store, size, filters=None, **kwargs):
    rows, offset = [], 0
    while True:
        page = await service.query_annotations(store, OWNER, COLLECTION, filters, limit=size, offset=offset, **kwargs)
        rows += ids(page)
        offset += size
        if offset >= page.total:
            return rows, page.total


async def test_document_order_is_title_then_position_then_id_and_pages_partition_it(store):
    same = sorted([uuid4(), uuid4()], key=str)  # identical text and offsets, distinct ids
    store.spans.rows = [row(DOC_B, 5), row(DOC_A, 30), row(DOC_A, 10, rid=same[1]), row(DOC_A, 10, rid=same[0]),
                        row(DOC_NO_YEAR, 1), row(DOC_B, 1), row(DOC_GONE, 0)]
    expected = [r.id for r in sorted(store.spans.rows, key=lambda r: (
        [DOC_A, DOC_B, DOC_NO_YEAR, DOC_GONE].index(r.documentId), _position_key(r)))]
    assert expected[:2] == same

    for size in range(1, 9):
        rows, total = await all_pages(store, size)
        assert rows == expected, size
        assert total == 7


async def test_year_order_puts_documents_without_year_last(store):
    store.spans.rows = [row(DOC_NO_YEAR, 0), row(DOC_A, 0), row(DOC_B, 0)]
    page = await service.query_annotations(store, OWNER, COLLECTION, sort=AnnotationSort.year)
    assert [r.documentId for r in page.rows] == [DOC_B, DOC_A, DOC_NO_YEAR]


async def test_descending_document_order_reverses_titles_keeps_reading_order_and_missing_last(store):
    later, earlier = row(DOC_A, 30), row(DOC_A, 10)
    store.spans.rows = [later, earlier, row(DOC_NO_YEAR, 1), row(DOC_B, 1), row(DOC_GONE, 0)]
    ascending = await service.query_annotations(store, OWNER, COLLECTION)
    descending = await service.query_annotations(store, OWNER, COLLECTION, descending=True)
    documents = [r.documentId for r in ascending.rows]
    titled = [d for d in dict.fromkeys(documents) if d != DOC_GONE]
    assert list(dict.fromkeys(r.documentId for r in descending.rows)) == [*reversed(titled), DOC_GONE]
    assert [r.id for r in descending.rows if r.documentId == DOC_A] == [earlier.id, later.id]
    for size in range(1, 6):
        rows, _ = await all_pages(store, size, descending=True)
        assert rows == [r.id for r in descending.rows], size


async def test_descending_year_order_keeps_documents_without_year_last(store):
    store.spans.rows = [row(DOC_NO_YEAR, 0), row(DOC_A, 0), row(DOC_B, 0)]
    page = await service.query_annotations(store, OWNER, COLLECTION, sort=AnnotationSort.year, descending=True)
    assert [r.documentId for r in page.rows] == [DOC_A, DOC_B, DOC_NO_YEAR]


async def test_descending_text_order_is_passed_to_the_store(store):
    store.spans.rows = [row(DOC_A, 0, "zebra"), row(DOC_B, 0, "Ahoj"), row(DOC_A, 9, "beta"), row(DOC_B, 5, current=False)]
    page = await service.query_annotations(store, OWNER, COLLECTION, sort=AnnotationSort.text, descending=True)
    assert [r.text for r in page.rows] == ["zebra", "beta", "Ahoj", None]


async def test_text_order_reads_no_document_counts_and_joins_only_the_page(store):
    store.spans.rows = [row(DOC_A, 0, "zebra"), row(DOC_B, 0, "Ahoj"), row(DOC_A, 9, "beta")]
    page = await service.query_annotations(store, OWNER, COLLECTION, sort=AnnotationSort.text, limit=2)
    assert [r.text for r in page.rows] == ["Ahoj", "beta"]
    assert page.total == 3
    assert [set(r) for r in store.documents.reads] == [{DOC_A, DOC_B}]


async def test_rejected_annotations_only_on_request(store):
    store.spans.rows = [row(DOC_A, 0, type=SpanType.pos), row(DOC_A, 1, type=SpanType.auto),
                        row(DOC_A, 2, type=SpanType.neg)]
    default = await service.query_annotations(store, OWNER, COLLECTION)
    assert {r.type for r in default.rows} == {SpanType.pos, SpanType.auto}
    rejected = await service.query_annotations(store, OWNER, COLLECTION, AnnotationFilters(types=[SpanType.neg]))
    assert [r.type for r in rejected.rows] == [SpanType.neg]


async def test_filters_by_tag_text_document_and_year(store):
    store.spans.rows = [row(DOC_A, 0, "Školní reforma"), row(DOC_A, 20, "reforma", tag=OTHER_TAG),
                        row(DOC_B, 0, "školní dvůr"), row(DOC_NO_YEAR, 0, "školní")]
    by_tag = await service.query_annotations(store, OWNER, COLLECTION, AnnotationFilters(tag_ids=[OTHER_TAG]))
    assert [r.text for r in by_tag.rows] == ["reforma"]
    by_words = await service.query_annotations(store, OWNER, COLLECTION, AnnotationFilters(q="ŠKOL, refor"))
    assert [r.text for r in by_words.rows] == ["Školní reforma"]
    by_document = await service.query_annotations(store, OWNER, COLLECTION, AnnotationFilters(document_ids=[DOC_B]))
    assert [r.text for r in by_document.rows] == ["školní dvůr"]
    by_year = await service.query_annotations(store, OWNER, COLLECTION, years(1900, 1950), sort=AnnotationSort.text)
    assert by_year.total == 2 and {r.documentId for r in by_year.rows} == {DOC_A}
    # A year range leaves out documents without a year.
    since = await service.query_annotations(store, OWNER, COLLECTION, years(1800))
    assert DOC_NO_YEAR not in {r.documentId for r in since.rows}


async def test_annotations_are_read_by_id_with_the_type_filter_they_ask_for(store):
    # The workspace reads the annotation it shows as it is now, also when it left the page's filters (#460).
    approved, other = row(DOC_A, 0, type=SpanType.pos), row(DOC_A, 5, type=SpanType.auto)
    store.spans.rows = [approved, other]
    page = await service.query_annotations(store, OWNER, COLLECTION, AnnotationFilters(types=list(SpanType)),
                                           annotation_ids=[str(approved.id)])
    assert (ids(page), page.total) == ([approved.id], 1)
    with pytest.raises(InvalidRequestError):
        await service.query_annotations(store, OWNER, COLLECTION, annotation_ids=["not-an-id"])


async def test_rows_report_text_status_and_unavailable_documents(store):
    pending = row(DOC_GONE, 0, current=False)
    failed = row(DOC_A, 1, current=False).model_copy(update={"enrichmentStatus": EnrichmentStatus.failed, "enrichedRevision": 1})
    stale = row(DOC_A, 2).model_copy(update={"revision": 2})  # derived for revision 1
    store.spans.rows = [pending, failed, stale]
    page = {r.id: r for r in (await service.query_annotations(store, OWNER, COLLECTION)).rows}
    assert page[pending.id].textStatus == TextStatus.pending
    assert page[pending.id].documentAvailable is False and page[pending.id].documentTitle is None
    assert page[failed.id].textStatus == TextStatus.failed
    assert page[stale.id].textStatus == TextStatus.pending
    assert page[stale.id].text is None and page[stale.id].leftContext is None
    assert page[failed.id].documentTitle == "Almanach" and page[failed.id].documentYear == 1912


async def test_unicode_text_is_returned_unchanged(store):
    text = "Zdeňka 😀 é"
    store.spans.rows = [row(DOC_A, 0, text)]
    [listed] = (await service.query_annotations(store, OWNER, COLLECTION)).rows
    assert listed.text == text and listed.leftContext == "vlevo " and listed.rightContext == " vpravo"


async def test_shared_users_read_and_others_are_denied_before_any_read(store):
    store.spans.rows = [row(DOC_A, 0)]
    assert (await service.query_annotations(store, SHARED, COLLECTION)).total == 1
    store.spans.queries, store.documents.reads = 0, []
    with pytest.raises(ResourceNotFound):
        await service.query_annotations(store, OTHER, COLLECTION)
    with pytest.raises(AuthenticationRequired):
        await service.list_annotated_documents(store, None, COLLECTION)
    assert store.spans.queries == 0 and store.documents.reads == []


@pytest.mark.parametrize("filters, kwargs", [
    (None, {"limit": 0}), (None, {"limit": 201}), (None, {"offset": -1}),
    (AnnotationFilters(q=" ".join(["w"] * 11)), {}),
    (None, {"sort": AnnotationSort.text, "offset": 9990, "limit": 20})])
async def test_invalid_queries_are_refused(store, filters, kwargs):
    with pytest.raises(InvalidRequestError):
        await service.query_annotations(store, OWNER, COLLECTION, filters, **kwargs)


@pytest.mark.parametrize("fields", [{"tag_ids": ["not-a-uuid"]}, {"year_from": 1900},
                                    {"document_filters": {"year_min": 1950, "year_max": 1900}},
                                    {"document_filters": {"title_contains": ["*"]}}, {"text_scope": "title"}])
def test_malformed_annotation_queries_are_refused_by_the_model(fields):
    # The shared document filters' validation applies; the old year_from/year_to fields are refused, not ignored.
    with pytest.raises(ValueError):
        AnnotationFilters.model_validate(fields)


async def test_too_many_annotated_documents_are_refused_not_truncated(store, monkeypatch):
    monkeypatch.setattr(service, "_MAX_DOCUMENTS", 2)
    store.spans.rows = [row(DOC_A, 0), row(DOC_B, 0), row(DOC_NO_YEAR, 0)]
    with pytest.raises(InvalidRequestError):
        await service.query_annotations(store, OWNER, COLLECTION)


async def test_the_document_limit_counts_only_the_chosen_documents(store, monkeypatch):
    monkeypatch.setattr(service, "_MAX_DOCUMENTS", 2)
    store.spans.rows = [row(DOC_A, 0), row(DOC_B, 0), row(DOC_NO_YEAR, 0)]
    page = await service.query_annotations(store, OWNER, COLLECTION, AnnotationFilters(document_ids=[DOC_A]))
    assert (page.total, [r.documentId for r in page.rows]) == (1, [DOC_A])


async def test_text_search_skips_text_of_another_revision_or_policy(store):
    current = row(DOC_A, 0, "Novák")
    failed = row(DOC_A, 5, "Novák").model_copy(update={"enrichmentStatus": EnrichmentStatus.failed})
    old_policy = row(DOC_A, 9, "Novák").model_copy(update={"derivationVersion": DERIVATION_VERSION - 1})
    store.spans.rows = [current, failed, old_policy]
    page = await service.query_annotations(store, OWNER, COLLECTION, AnnotationFilters(q="novák"))
    assert (page.total, ids(page)) == (1, [current.id])


async def test_annotated_documents_list_counts_by_title(store):
    store.spans.rows = [row(DOC_B, 0), row(DOC_A, 0), row(DOC_A, 5), row(DOC_GONE, 0),
                        row(DOC_B, 9, type=SpanType.neg)]
    listed = await service.list_annotated_documents(store, OWNER, COLLECTION)
    assert [(d.id, d.count, d.available) for d in listed] == [(DOC_A, 2, True), (DOC_B, 1, True),
                                                               (DOC_GONE, 1, False)]
    assert (listed[0].title, listed[0].year, listed[0].library, listed[0].language) == ("Almanach", 1912, "mzk", "ces")


# ── Annotation query (#663) ───────────────────────────────────────────────

def ctx(document, start, text, left="", right="", **kwargs):
    return row(document, start, text, **kwargs).model_copy(update={"leftContext": left, "rightContext": right})


async def test_the_text_scope_chooses_the_fields_each_word_must_occur_in(store):
    in_text = ctx(DOC_A, 0, "Novák", left="pan ", right=" z Brna")
    in_left = ctx(DOC_A, 10, "starosta", left="Novákův syn, ", right=" obce")
    in_right = ctx(DOC_A, 20, "kronikář", left="", right=", Novák")
    store.spans.rows = [in_text, in_left, in_right]

    async def found(q, scope):
        page = await service.query_annotations(store, OWNER, COLLECTION, AnnotationFilters(q=q, text_scope=scope))
        return set(ids(page))

    assert await found("novák", TextScope.annotation) == {in_text.id}
    assert await found("novák", TextScope.context) == {in_left.id, in_right.id}
    assert await found("NOVÁK", TextScope.both) == {in_text.id, in_left.id, in_right.id}
    # Each word may occur in another field of the scope, but every word must occur.
    assert await found("novák brna", TextScope.both) == {in_text.id}
    assert await found("novák brna", TextScope.annotation) == set()
    assert await found("syn starosta", TextScope.both) == {in_left.id}


async def test_underscores_separate_query_words_as_in_the_stored_text(store):
    # Weaviate's word tokenization splits "Novák_Brna" into two words; so does the query.
    both = ctx(DOC_A, 0, "Novák", right=" z Brna")
    store.spans.rows = [both]

    async def found(q, scope):
        return ids(await service.query_annotations(store, OWNER, COLLECTION, AnnotationFilters(q=q, text_scope=scope)))

    assert await found("novák_brna", TextScope.both) == [both.id]
    assert await found("novák_brna", TextScope.annotation) == []
    assert service._concordance_query(None, None, "a_b__c_").words == ["a", "b", "c"]


async def test_a_decomposed_query_matches_composed_text(store):
    composed = ctx(DOC_A, 0, "Zdeňku")
    store.spans.rows = [composed]
    page = await service.query_annotations(store, OWNER, COLLECTION, AnnotationFilters(q="zden\u030cku"))
    assert ids(page) == [composed.id]


async def test_context_search_also_needs_current_derived_text(store):
    stale = ctx(DOC_A, 0, "Novák", left="Praha ").model_copy(update={"derivationVersion": DERIVATION_VERSION - 1})
    store.spans.rows = [stale]
    page = await service.query_annotations(store, OWNER, COLLECTION,
                                           AnnotationFilters(q="praha", text_scope=TextScope.context))
    assert page.total == 0


@pytest.mark.parametrize("sort", list(AnnotationSort))
async def test_document_filters_select_the_annotations_of_the_documents_they_select(store, sort):
    store.spans.rows = [row(DOC_A, 0), row(DOC_A, 5), row(DOC_B, 0), row(DOC_NO_YEAR, 0), row(DOC_GONE, 0)]
    with_keys(store)
    extra = {"sort_attribute": ATTRIBUTE, "attributes": FakeAttributes()} if sort == AnnotationSort.attribute else {}

    async def documents(**filters):
        page = await service.query_annotations(
            store, OWNER, COLLECTION, AnnotationFilters(document_filters=DocumentFilters(**filters)), sort=sort,
            **extra)
        assert page.total == len(page.rows)
        return [r.documentId for r in page.rows]

    assert sorted(await documents(year_min=1900), key=str) == [DOC_A, DOC_A]
    assert await documents(year_max=1900) == [DOC_B]  # no year: never in a range
    assert await documents(title_contains=["BULL"]) == [DOC_B]
    assert sorted(set(await documents(title_contains=["alma", "čten"])), key=str) == sorted([DOC_A, DOC_NO_YEAR], key=str)
    assert sorted(set(await documents(libraries=["mzk"])), key=str) == sorted([DOC_A, DOC_NO_YEAR], key=str)
    assert await documents(languages=["DEU"]) == [DOC_B]
    assert await documents(libraries=["mzk"], year_max=1900) == []
    # A document deleted from the corpus matches no document filter.
    assert DOC_GONE not in await documents(languages=["ces", "deu"])


async def test_document_filters_are_evaluated_once_over_the_annotated_documents(store):
    store.spans.rows = [row(DOC_A, 0, "Praha"), row(DOC_B, 0, "Brno"), row(DOC_NO_YEAR, 0, "Praha")]
    filters = AnnotationFilters(q="praha", document_filters=DocumentFilters(libraries=["mzk"], year_min=1800))

    page = await service.query_annotations(store, OWNER, COLLECTION, filters)

    assert ids(page) == [store.spans.rows[0].id]
    [(read, conditions)] = store.documents.eligible_reads
    assert set(read) == {DOC_A, DOC_NO_YEAR}  # only documents with matching annotations
    assert {type(c) for c in conditions} == {NumberRange, AnyOf}


async def test_a_document_filter_the_store_cannot_evaluate_is_not_answered_empty(store):
    store.spans.rows = [row(DOC_A, 0)]
    store.documents.unavailable = LookupError("library is not recorded")
    filters = AnnotationFilters(document_filters=DocumentFilters(libraries=["mzk"]))
    with pytest.raises(LookupError):
        await service.query_annotations(store, OWNER, COLLECTION, filters)
    with pytest.raises(LookupError):
        await service.resolve_annotation_ids(store, OWNER, COLLECTION, AnnotationIdsRequest(**filters.model_dump()))


async def test_the_same_query_selects_the_same_annotations_in_pages_ids_and_documents(store):
    store.spans.rows = [ctx(DOC_A, 0, "Praha", right=" hlavní"), ctx(DOC_A, 5, "Brno", left="hlavní "),
                        ctx(DOC_B, 0, "Praha", right=" hlavní"), ctx(DOC_NO_YEAR, 0, "Praha", right=" hlavní"),
                        ctx(DOC_A, 9, "Praha", right=" hlavní", tag=OTHER_TAG)]
    fields = {"tag_ids": [TAG], "q": "hlavní", "text_scope": TextScope.context,
              "document_filters": DocumentFilters(libraries=["mzk"])}
    filters = AnnotationFilters(**fields)

    rows, total = await all_pages(store, 1, filters)
    resolved = await service.resolve_annotation_ids(store, OWNER, COLLECTION, AnnotationIdsRequest(**fields))
    documents = await service.list_annotated_documents(store, OWNER, COLLECTION, filters)

    assert total == 3 and sorted(rows, key=str) == sorted(resolved.ids, key=str)
    expected = {r.id for r in store.spans.rows[:2]} | {store.spans.rows[3].id}
    assert set(rows) == expected
    assert [(d.id, d.count) for d in documents] == [(DOC_A, 2), (DOC_NO_YEAR, 1)]


async def test_the_source_choices_ignore_the_document_choice_itself(store):
    store.spans.rows = [row(DOC_A, 0), row(DOC_B, 0, tag=OTHER_TAG)]
    documents = await service.list_annotated_documents(
        store, OWNER, COLLECTION, AnnotationFilters(tag_ids=[TAG], document_ids=[DOC_B]))
    assert [d.id for d in documents] == [DOC_A]


async def test_document_filters_of_a_denied_request_read_nothing(store):
    filters = AnnotationFilters(document_filters=DocumentFilters(libraries=["mzk"]))
    with pytest.raises(ResourceNotFound):
        await service.query_annotations(store, OTHER, COLLECTION, filters)
    with pytest.raises(ResourceNotFound):
        await service.list_annotated_documents(store, OTHER, COLLECTION, filters)
    assert store.documents.eligible_reads == [] and store.spans.queries == 0


# ── HTTP contract ─────────────────────────────────────────────────────────

async def test_routes_parse_repeated_filters_and_serialize_rows(tmp_path, store, monkeypatch):
    from asgi_lifespan import LifespanManager
    from httpx import ASGITransport, AsyncClient

    from semant_demo.main import create_app
    from semant_demo.routes.dependencies import get_annotation_store
    from tests.app_support import make_test_config, offline_weaviate
    from tests.auth_support import auth_headers, register

    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    app.dependency_overrides[get_annotation_store] = lambda: store
    store.spans.rows = [row(DOC_A, 0, "Novák", type=SpanType.neg), row(DOC_B, 0, "Brno", tag=OTHER_TAG),
                        row(DOC_A, 5, "Lhota")]
    path = f"/api/user_collections/{COLLECTION}/annotations"
    async with LifespanManager(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await register(client, email="kwic@example.com", password="StrongPassw0rd!")).status_code == 201
        headers = await auth_headers(client, "kwic@example.com", "StrongPassw0rd!")
        monkeypatch.setattr(OWNER, "id", UUID((await client.get("/api/users/me", headers=headers)).json()["id"]))

        anonymous = await client.get(path)
        page = await client.get(path, headers=headers, params=[("type", "pos"), ("type", "neg"),
                                                                ("tag_id", str(TAG)), ("limit", "1")])
        documents = await client.get(f"{path}/documents", headers=headers)
        by_id = await client.get(path, headers=headers, params=[("annotation_id", str(store.spans.rows[2].id))])
        bad = [await client.get(path, headers=headers, params=params)
               for params in ({"sort": "random"}, {"limit": 201}, {"type": "maybe"}, {"offset": -1},
                              {"text_scope": "title"}, {"year_min": 1950, "year_max": 1900},
                              {"title_contains": "*"}, {"tag_id": "not-a-uuid"})]
        filtered = await client.get(path, headers=headers, params=[
            ("type", "pos"), ("type", "neg"), ("q", "lho"), ("text_scope", "both"), ("year_min", "1900"),
            ("libraries", "mzk"), ("languages", "ces"), ("title_contains", "alma")])
        filtered_documents = await client.get(f"{path}/documents", headers=headers, params={"year_max": 1900})
        resolved = await client.post(f"{path}/ids", headers=headers,
                                     json={"document_filters": {"title_contains": ["bulletin"]}})
        old_fields = await client.post(f"{path}/ids", headers=headers, json={"year_from": 1900})
        store.documents.unavailable = UnavailableFilter("library", "missing")
        unavailable = await client.get(path, headers=headers, params={"libraries": "mzk"})

    assert anonymous.status_code == 401
    assert page.status_code == 200, page.text
    body = page.json()
    assert (body["total"], body["offset"], body["limit"]) == (2, 0, 1)
    [first] = body["rows"]
    assert (first["text"], first["type"], first["textStatus"], first["documentTitle"], first["documentYear"]) == \
        ("Novák", "neg", "ready", "Almanach", 1912)
    assert set(first) >= {"id", "tagId", "chunkId", "documentId", "start", "end", "revision", "leftContext",
                          "rightContext", "documentAvailable"}
    assert [(d["title"], d["count"]) for d in documents.json()] == [("Almanach", 1), ("Bulletin", 1)]
    assert [r["text"] for r in by_id.json()["rows"]] == ["Lhota"]
    assert [r.status_code for r in bad] == [422] * 8
    assert filtered.status_code == 200, filtered.text
    assert [r["text"] for r in filtered.json()["rows"]] == ["Lhota"]
    assert [d["title"] for d in filtered_documents.json()] == ["Bulletin"]
    assert resolved.status_code == 200 and resolved.json()["ids"] == [str(store.spans.rows[1].id)]
    assert old_fields.status_code == 422  # the former year fields are refused, never ignored
    assert unavailable.status_code == 422 and "library" in unavailable.json()["detail"]


# ── Resolving a selection (#459) ──────────────────────────────────────────

async def test_all_matches_resolve_to_the_ids_of_every_page(store):
    store.spans.rows = [row(DOC_A, i) for i in range(5)] + [row(DOC_B, 0, tag=OTHER_TAG),
                                                            row(DOC_A, 9, type=SpanType.neg)]
    resolved = await service.resolve_annotation_ids(store, SHARED, COLLECTION, AnnotationIdsRequest(tag_ids=[TAG]))

    rows, _ = await all_pages(store, 2, AnnotationFilters(tag_ids=[TAG]))
    assert sorted(resolved.ids, key=str) == sorted(rows, key=str)
    assert len(resolved.ids) == 5


async def test_resolving_applies_the_year_and_text_filters(store):
    store.spans.rows = [row(DOC_A, 0, "Praha"), row(DOC_B, 0, "Praha"), row(DOC_A, 9, "Brno")]
    resolved = await service.resolve_annotation_ids(store, OWNER, COLLECTION,
                                                    AnnotationIdsRequest(q="prah", document_filters=DocumentFilters(year_min=1900)))

    assert resolved.ids == [store.spans.rows[0].id]


async def test_resolved_ids_come_with_the_versions_a_review_expects(store):
    edited, untouched = row(DOC_A, 0), row(DOC_A, 5)
    store.spans.rows = [edited.model_copy(update={"editVersion": 3}), untouched]

    resolved = await service.resolve_annotation_ids(store, OWNER, COLLECTION, AnnotationIdsRequest())

    assert resolved.versions == {edited.id: 3, untouched.id: 0}


async def test_rows_report_their_version_and_provenance_or_an_unknown_origin(store):
    run, user = uuid4(), uuid4()
    store.spans.rows = [row(DOC_A, 0).model_copy(update={"editVersion": 2, "origin": "ai", "aiRunId": run,
                                                          "createdBy": user}), row(DOC_A, 5)]

    page = await service.query_annotations(store, OWNER, COLLECTION, limit=10)

    ai, migrated = page.rows
    assert (ai.editVersion, ai.provenance.origin, ai.provenance.aiRunId, ai.provenance.createdBy) == (2, "ai", run, user)
    assert (migrated.editVersion, migrated.provenance.origin, migrated.provenance.createdBy) == (0, "unknown", None)


async def test_within_tells_which_selected_annotations_the_filters_show(store):
    shown, hidden = row(DOC_A, 0), row(DOC_A, 5, tag=OTHER_TAG)
    store.spans.rows = [shown, hidden, row(DOC_A, 9)]
    deleted = uuid4()

    resolved = await service.resolve_annotation_ids(
        store, OWNER, COLLECTION, AnnotationIdsRequest(tag_ids=[TAG], within=[shown.id, hidden.id, deleted]))

    assert resolved.ids == [shown.id]
    empty = await service.resolve_annotation_ids(store, OWNER, COLLECTION, AnnotationIdsRequest(within=[]))
    assert empty.ids == []


async def test_more_matches_than_the_limit_are_refused_not_truncated(store, monkeypatch):
    monkeypatch.setattr(service, "MAX_RESOLVED_IDS", 2)
    store.spans.rows = [row(DOC_A, i) for i in range(3)]

    with pytest.raises(InvalidRequestError, match="3 annotations match"):
        await service.resolve_annotation_ids(store, OWNER, COLLECTION, AnnotationIdsRequest())
    assert store.spans.queries == 0


@pytest.mark.parametrize("user, error", [(OTHER, ResourceNotFound), (None, AuthenticationRequired)])
async def test_resolving_needs_read_access(user, error, store):
    store.spans.rows = [row(DOC_A, 0)]
    with pytest.raises(error):
        await service.resolve_annotation_ids(store, user, COLLECTION, AnnotationIdsRequest())


async def test_counts_per_type_and_tag_read_no_rows(store):
    store.spans.rows = [row(DOC_A, 0), row(DOC_A, 5), row(DOC_B, 0, type=SpanType.auto),
                        row(DOC_B, 5, type=SpanType.neg), row(DOC_A, 9, tag=OTHER_TAG),
                        row(DOC_B, 9, tag=OTHER_TAG, type=SpanType.auto, current=False)]

    counts = await service.count_annotations(store, SHARED, COLLECTION)
    assert (counts.approved, counts.suggestions, counts.rejected) == (3, 2, 1)
    counts = await service.count_annotations(store, OWNER, COLLECTION, tag_ids=[str(TAG)])
    assert (counts.approved, counts.suggestions, counts.rejected) == (2, 1, 1)
    assert store.spans.queries == 0 and store.documents.reads == []


async def test_counts_need_read_access_and_valid_tag_ids(store):
    with pytest.raises(ResourceNotFound):
        await service.count_annotations(store, OTHER, COLLECTION)
    with pytest.raises(InvalidRequestError):
        await service.count_annotations(store, OWNER, COLLECTION, tag_ids=["not-a-uuid"])


ATTRIBUTE, OTHER_ATTRIBUTE = uuid4(), uuid4()
VALUE, OTHER_VALUE = uuid4(), uuid4()


async def test_attribute_filters_match_any_value_of_an_attribute_all_attributes_and_unassigned(store):
    with_value, with_both, with_other_value, none = (row(DOC_A, i) for i in range(4))
    with_value.attributeValues = [codec.encode(ATTRIBUTE, VALUE)]
    with_both.attributeValues = [codec.encode(ATTRIBUTE, VALUE), codec.encode(OTHER_ATTRIBUTE, OTHER_VALUE)]
    with_other_value.attributeValues = [codec.encode(ATTRIBUTE, OTHER_VALUE)]
    store.spans.rows = [with_value, with_both, with_other_value, none]

    async def found(**kwargs):
        return {r.id for r in (await service.query_annotations(store, OWNER, COLLECTION,
                                                               AnnotationFilters(**kwargs))).rows}

    assert await found(attribute_values=[f"{ATTRIBUTE}:{VALUE}"]) == {with_value.id, with_both.id}
    assert await found(attribute_values=[f"{ATTRIBUTE}:{VALUE}", f"{ATTRIBUTE}:{OTHER_VALUE}"]) \
        == {with_value.id, with_both.id, with_other_value.id}
    assert await found(attribute_values=[f"{ATTRIBUTE}:{VALUE}", f"{OTHER_ATTRIBUTE}:{OTHER_VALUE}"]) == {with_both.id}
    assert await found(attribute_unassigned=[str(OTHER_ATTRIBUTE)]) == {with_value.id, with_other_value.id, none.id}
    assert await found(attribute_unassigned=[str(ATTRIBUTE)]) == {none.id}
    assert await found(attribute_values=[f"{OTHER_ATTRIBUTE}:{OTHER_VALUE}"], attribute_unassigned=[str(ATTRIBUTE)]) == set()

    # Rows carry the accepted values and the version assignments expect; the resolved selection too.
    with_both.attributeVersion = 3
    page = await service.query_annotations(store, OWNER, COLLECTION,
                                           AnnotationFilters(attribute_values=[f"{ATTRIBUTE}:{VALUE}"]))
    by_id = {r.id: r for r in page.rows}
    assert by_id[with_both.id].attributes == {ATTRIBUTE: [VALUE], OTHER_ATTRIBUTE: [OTHER_VALUE]}
    assert (by_id[with_both.id].attributeVersion, by_id[with_value.id].attributeVersion) == (3, 0)
    resolved = await service.resolve_annotation_ids(
        store, OWNER, COLLECTION, AnnotationIdsRequest(attribute_values=[f"{ATTRIBUTE}:{VALUE}"]))
    assert set(resolved.ids) == {with_value.id, with_both.id} and resolved.attribute_versions[with_both.id] == 3


async def test_values_kept_on_rejected_annotations_are_not_accepted_classifications(store):
    approved, rejected = row(DOC_A, 0), row(DOC_A, 1, type=SpanType.neg)
    for r in (approved, rejected):
        r.attributeValues = [codec.encode(ATTRIBUTE, VALUE)]
    store.spans.rows = [approved, rejected]
    every_type = [SpanType.pos, SpanType.auto, SpanType.neg]

    page = await service.query_annotations(store, OWNER, COLLECTION, AnnotationFilters(
        types=every_type, attribute_values=[f"{ATTRIBUTE}:{VALUE}"]))
    assert [r.id for r in page.rows] == [approved.id]
    page = await service.query_annotations(store, OWNER, COLLECTION, AnnotationFilters(types=every_type))
    by_id = {r.id: r for r in page.rows}
    assert by_id[approved.id].attributes == {ATTRIBUTE: [VALUE]} and by_id[rejected.id].attributes == {}
    page = await service.query_annotations(store, OWNER, COLLECTION, AnnotationFilters(
        types=every_type, attribute_unassigned=[ATTRIBUTE]))
    assert [r.id for r in page.rows] == [rejected.id]


async def test_attribute_filters_are_refused_on_a_store_without_the_attribute_properties(store):
    store.spans.attributes = False
    with pytest.raises(ServiceUnavailableError):
        await service.query_annotations(store, OWNER, COLLECTION,
                                        AnnotationFilters(attribute_values=[f"{ATTRIBUTE}:{VALUE}"]))
    with pytest.raises(ServiceUnavailableError):
        await service.resolve_annotation_ids(
            store, OWNER, COLLECTION, AnnotationIdsRequest(attribute_unassigned=[str(ATTRIBUTE)]))
    await service.query_annotations(store, OWNER, COLLECTION)  # without attribute filters nothing changes


@pytest.mark.parametrize("values", [["x"], [f"{ATTRIBUTE}:{VALUE} "], ["a:b"]])
async def test_malformed_attribute_filters_are_refused(store, values):
    with pytest.raises(InvalidRequestError):
        await service.query_annotations(store, OWNER, COLLECTION, AnnotationFilters(attribute_values=values))
    with pytest.raises(ValueError):
        AnnotationFilters(attribute_unassigned=["x"])


async def test_too_many_attribute_filters_are_refused(store):
    # Attributes and one attribute's many values are bounded by the query model (GET and id resolution alike).
    many = [codec.encode(ATTRIBUTE, uuid4()) for _ in range(MAX_ATTRIBUTE_FILTER_VALUES + 1)]
    with pytest.raises(ValueError):
        AnnotationFilters(attribute_values=many)
    with pytest.raises(ValueError):
        AnnotationIdsRequest(attribute_values=many)
    with pytest.raises(ValueError):
        AnnotationIdsRequest(attribute_unassigned=[uuid4() for _ in range(MAX_ATTRIBUTE_FILTERS + 1)])


# ── Czech text and context sorts, attribute sort (#666) ─────────────────────

def in_context(document, start, text, left, right, **kwargs):
    r = row(document, start, text, **kwargs)
    return r.model_copy(update={"leftContext": left, "rightContext": right})


@pytest.mark.parametrize("sort, prop", [(AnnotationSort.text, "textSortKey"), (AnnotationSort.left, "leftSortKey"),
                                        (AnnotationSort.right, "rightSortKey")])
async def test_text_and_context_sorts_page_by_their_sort_keys_in_both_directions(store, sort, prop):
    words = ["chata", "cesta", "Hrad", "hrad", "čas", "dub"]
    store.spans.rows = [in_context(DOC_A if i % 2 else DOC_B, i, w, f"x {w}", f" {w} y") for i, w in enumerate(words)]
    store.spans.rows.append(row(DOC_A, 99, current=False))  # not derived: no keys
    with_keys(store)

    for descending in (False, True):
        expected = [r.id for r in await store.spans.query_rows(COLLECTION, service._filters_query(AnnotationFilters()),
                                                               sort_by=prop, limit=100, descending=descending)]
        for size in range(1, 8):
            rows, total = await all_pages(store, size, sort=sort, descending=descending)
            assert rows == expected and total == 7, (descending, size)
    by_word = [r.text for r in (await service.query_annotations(store, OWNER, COLLECTION, sort=sort)).rows]
    assert by_word == [None, "cesta", "čas", "dub", "hrad", "Hrad", "chata"]
    assert set(store.spans.sorted_by) == {prop}


async def test_sorted_pages_report_the_rows_without_current_sort_keys(store):
    store.spans.rows = [row(DOC_A, 0, "a"), row(DOC_A, 1, "b"), row(DOC_B, 0, current=False)]
    with_keys(store)
    store.spans.rows[1].sortKeyVersion = "0:icu-1.0:00000000"  # another collator: not yet backfilled

    page = await service.query_annotations(store, OWNER, COLLECTION, sort=AnnotationSort.left)
    assert (page.total, page.unsortable) == (3, 2)
    assert (await service.query_annotations(store, OWNER, COLLECTION)).unsortable is None


async def test_without_sort_keys_text_sorts_by_code_point_and_context_sorts_are_unavailable(store):
    store.spans.rows = [row(DOC_A, 0, "čas"), row(DOC_A, 1, "dub")]

    page = await service.query_annotations(store, OWNER, COLLECTION, sort=AnnotationSort.text)
    assert store.spans.sorted_by == ["text"] and page.unsortable is None
    for sort in (AnnotationSort.left, AnnotationSort.right):
        with pytest.raises(ServiceUnavailableError, match="add-schema"):
            await service.query_annotations(store, OWNER, COLLECTION, sort=sort)
    assert store.spans.queries == 1


def held(document, start, *values, **kwargs):
    r = row(document, start, **kwargs)
    return r.model_copy(update={"attributeValues": [codec.encode(ATTRIBUTE, v) for v in values]})


async def attribute_pages(store, size, descending=False, **kwargs):
    return await all_pages(store, size, sort=AnnotationSort.attribute, sort_attribute=ATTRIBUTE,
                           attributes=FakeAttributes(), descending=descending, **kwargs)


async def test_attribute_sort_orders_by_value_then_document_order_with_missing_last(store):
    multi, red_b, red_a, green, blue, old, none, auto = (
        held(DOC_A, 50, BLUE, GREEN), held(DOC_B, 0, RED), held(DOC_A, 9, RED), held(DOC_A, 1, GREEN),
        held(DOC_A, 2, BLUE), held(DOC_B, 3, OLD), held(DOC_A, 0), held(DOC_A, 4, RED, type=SpanType.auto))
    other = row(DOC_B, 7).model_copy(update={"attributeValues": [codec.encode(uuid4(), uuid4())]})
    store.spans.rows = [multi, red_b, red_a, green, blue, old, none, auto, other]
    # red (document order: Almanach before Bulletin), green (with the multi-valued one once, under
    # green: its first value), blue, the retired value, then no value: unassigned, of another
    # attribute, or not approved (its values are not shown), in document order.
    expected = [red_a.id, red_b.id, green.id, multi.id, blue.id, old.id, none.id, auto.id, other.id]
    for size in range(1, 10):
        rows, total = await attribute_pages(store, size)
        assert rows == expected and total == 9, size


async def test_descending_attribute_sort_reverses_the_values_only(store):
    red, green, blue, old, none = held(DOC_A, 0, RED), held(DOC_A, 1, GREEN), held(DOC_A, 2, BLUE), \
        held(DOC_A, 3, OLD), held(DOC_A, 4)
    both = held(DOC_A, 5, RED, BLUE)
    store.spans.rows = [red, green, blue, old, none, both]
    for size in (1, 2, 6):
        rows, _ = await attribute_pages(store, size, descending=True)
        assert rows == [blue.id, both.id, green.id, red.id, old.id, none.id], size


async def test_attribute_sort_applies_the_filters_and_document_filters(store):
    store.spans.rows = [held(DOC_A, 0, GREEN), held(DOC_B, 0, RED), held(DOC_A, 1, RED, tag=OTHER_TAG)]
    rows, total = await attribute_pages(store, 10, filters=AnnotationFilters(tag_ids=[TAG]))
    assert rows == [store.spans.rows[1].id, store.spans.rows[0].id] and total == 2
    rows, total = await attribute_pages(store, 10, filters=years(year_min=1900))
    assert rows == [store.spans.rows[2].id, store.spans.rows[0].id] and total == 2


async def test_attribute_sort_needs_a_known_attribute_of_the_collection(store):
    store.spans.rows = [held(DOC_A, 0, RED)]
    attributes = FakeAttributes()
    with pytest.raises(InvalidRequestError, match="sort_attribute"):
        await service.query_annotations(store, OWNER, COLLECTION, sort=AnnotationSort.attribute, attributes=attributes)
    with pytest.raises(NotFoundError):
        await service.query_annotations(store, OWNER, COLLECTION, sort=AnnotationSort.attribute,
                                        sort_attribute=uuid4(), attributes=attributes)
    with pytest.raises(InvalidRequestError, match="only used with"):
        await service.query_annotations(store, OWNER, COLLECTION, sort=AnnotationSort.text, sort_attribute=ATTRIBUTE)
    store.spans.attributes = False
    with pytest.raises(ServiceUnavailableError):
        await service.query_annotations(store, OWNER, COLLECTION, sort=AnnotationSort.attribute,
                                        sort_attribute=ATTRIBUTE, attributes=attributes)
    assert store.spans.queries == 0


@pytest.mark.parametrize("user, error", [(None, AuthenticationRequired), (OTHER, ResourceNotFound)])
async def test_a_denied_attribute_sort_reads_no_definition(store, user, error):
    attributes = FakeAttributes()
    with pytest.raises(error):
        await service.query_annotations(store, user, COLLECTION, sort=AnnotationSort.attribute,
                                        sort_attribute=ATTRIBUTE, attributes=attributes)
    assert attributes.reads == 0 and store.spans.queries == 0
