"""Concordance (KWIC) queries of the Annotations service (#329), with in-memory fakes.

Rows are paged in a total order (document title, year, position, id; or annotated text,
id), so consecutive pages together are exactly the full result; filters by tag, type,
text, document and year; rejected annotations only on request; derived text only when
current; denied requests read nothing. The Weaviate queries themselves:
tests/integration/test_annotation_concordance.py.
"""
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from semant_demo.core.errors import InvalidRequestError, ServiceUnavailableError
from semant_demo.features.annotations import service
from semant_demo.features.annotations.derivation import DERIVATION_VERSION
from semant_demo.features.annotations.schemas import (
    AnnotationIdsRequest, AnnotationRow, AnnotationSort, EnrichmentStatus, SpanType, TextStatus,
)
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
    DOC_A: Document(id=DOC_A, title="Almanach", yearIssued=1912),
    DOC_B: Document(id=DOC_B, title="Bulletin", yearIssued=1850),
    DOC_NO_YEAR: Document(id=DOC_NO_YEAR, title="Čtení"),
}


class FakeCollections:
    async def read_access_record(self, cid):
        return (OWNER.id, {SHARED.id}) if cid == COLLECTION else None


class FakeDocuments:
    def __init__(self):
        self.reads: list[list[UUID]] = []

    async def read_many(self, ids):
        self.reads.append(list(ids))
        return {i: DOCUMENTS[i] for i in ids if i in DOCUMENTS}


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

    def _match(self, query, document_ids):
        return [r for r in self.rows
                if r.type in query.types
                and (not query.tag_ids or r.tagId in query.tag_ids)
                and (not query.words or (r.enrichmentStatus == EnrichmentStatus.ready
                                         and r.derivationVersion == query.derivation_version))
                and all(r.text is not None and any(w.lower() in t.lower() for t in r.text.split())
                        for w in query.words)
                and (document_ids is None or r.documentId in document_ids)
                and (query.ids is None or r.id in query.ids)
                and (not query.attribute_values or r.type == SpanType.pos)
                and all(any(codec.encode(a, v) in (r.attributeValues or []) for v in vs)
                        for a, vs in query.attribute_values.items())
                and not any(c.startswith(f"{a}:") for a in query.attribute_unassigned
                            for c in (r.attributeValues or []) if r.type == SpanType.pos)]

    async def count_by_document(self, cid, query, limit, document_ids=None):
        counts: dict[UUID, int] = {}
        for row in self._match(query, document_ids):
            if row.documentId is not None:
                counts[row.documentId] = counts.get(row.documentId, 0) + 1
        return dict(list(counts.items())[:limit])

    async def count_rows(self, cid, query, document_ids=None):
        return len(self._match(query, document_ids))

    async def query_rows(self, cid, query, *, by_text, document_ids=None, limit, offset=0):
        self.queries += 1
        key = (lambda r: (r.text is not None, r.text or "", str(r.id))) if by_text else _position_key
        return sorted(self._match(query, document_ids), key=key)[offset:offset + limit]


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


@pytest.fixture
def store():
    return AnnotationStore(collections=FakeCollections(), tags=None, spans=FakeSpans(), chunk_tags=None,
                           documents=FakeDocuments())


def ids(page):
    return [r.id for r in page.rows]


async def all_pages(store, size, **kwargs):
    rows, offset = [], 0
    while True:
        page = await service.query_annotations(store, OWNER, COLLECTION, limit=size, offset=offset, **kwargs)
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
    rejected = await service.query_annotations(store, OWNER, COLLECTION, types=[SpanType.neg])
    assert [r.type for r in rejected.rows] == [SpanType.neg]


async def test_filters_by_tag_text_document_and_year(store):
    store.spans.rows = [row(DOC_A, 0, "Školní reforma"), row(DOC_A, 20, "reforma", tag=OTHER_TAG),
                        row(DOC_B, 0, "školní dvůr"), row(DOC_NO_YEAR, 0, "školní")]
    by_tag = await service.query_annotations(store, OWNER, COLLECTION, tag_ids=[str(OTHER_TAG)])
    assert [r.text for r in by_tag.rows] == ["reforma"]
    by_words = await service.query_annotations(store, OWNER, COLLECTION, text="ŠKOL, refor")
    assert [r.text for r in by_words.rows] == ["Školní reforma"]
    by_document = await service.query_annotations(store, OWNER, COLLECTION, document_ids=[str(DOC_B)])
    assert [r.text for r in by_document.rows] == ["školní dvůr"]
    by_year = await service.query_annotations(store, OWNER, COLLECTION, year_from=1900, year_to=1950,
                                              sort=AnnotationSort.text)
    assert by_year.total == 2 and {r.documentId for r in by_year.rows} == {DOC_A}
    # A year range leaves out documents without a year.
    since = await service.query_annotations(store, OWNER, COLLECTION, year_from=1800)
    assert DOC_NO_YEAR not in {r.documentId for r in since.rows}


async def test_annotations_are_read_by_id_with_the_type_filter_they_ask_for(store):
    # The workspace reads the annotation it shows as it is now, also when it left the page's filters (#460).
    approved, other = row(DOC_A, 0, type=SpanType.pos), row(DOC_A, 5, type=SpanType.auto)
    store.spans.rows = [approved, other]
    page = await service.query_annotations(store, OWNER, COLLECTION, annotation_ids=[str(approved.id)],
                                           types=list(SpanType))
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


@pytest.mark.parametrize("kwargs", [{"limit": 0}, {"limit": 201}, {"offset": -1}, {"tag_ids": ["not-a-uuid"]},
                                    {"text": " ".join(["w"] * 11)},
                                    {"sort": AnnotationSort.text, "offset": 9990, "limit": 20}])
async def test_invalid_queries_are_refused(store, kwargs):
    with pytest.raises(InvalidRequestError):
        await service.query_annotations(store, OWNER, COLLECTION, **kwargs)


async def test_too_many_annotated_documents_are_refused_not_truncated(store, monkeypatch):
    monkeypatch.setattr(service, "_MAX_DOCUMENTS", 2)
    store.spans.rows = [row(DOC_A, 0), row(DOC_B, 0), row(DOC_NO_YEAR, 0)]
    with pytest.raises(InvalidRequestError):
        await service.query_annotations(store, OWNER, COLLECTION)


async def test_the_document_limit_counts_only_the_chosen_documents(store, monkeypatch):
    monkeypatch.setattr(service, "_MAX_DOCUMENTS", 2)
    store.spans.rows = [row(DOC_A, 0), row(DOC_B, 0), row(DOC_NO_YEAR, 0)]
    page = await service.query_annotations(store, OWNER, COLLECTION, document_ids=[str(DOC_A)])
    assert (page.total, [r.documentId for r in page.rows]) == (1, [DOC_A])


async def test_text_search_skips_text_of_another_revision_or_policy(store):
    current = row(DOC_A, 0, "Novák")
    failed = row(DOC_A, 5, "Novák").model_copy(update={"enrichmentStatus": EnrichmentStatus.failed})
    old_policy = row(DOC_A, 9, "Novák").model_copy(update={"derivationVersion": DERIVATION_VERSION - 1})
    store.spans.rows = [current, failed, old_policy]
    page = await service.query_annotations(store, OWNER, COLLECTION, text="novák")
    assert (page.total, ids(page)) == (1, [current.id])


async def test_annotated_documents_list_counts_by_title(store):
    store.spans.rows = [row(DOC_B, 0), row(DOC_A, 0), row(DOC_A, 5), row(DOC_GONE, 0),
                        row(DOC_B, 9, type=SpanType.neg)]
    listed = await service.list_annotated_documents(store, OWNER, COLLECTION)
    assert [(d.id, d.count, d.available) for d in listed] == [(DOC_A, 2, True), (DOC_B, 1, True),
                                                               (DOC_GONE, 1, False)]
    assert listed[0].title == "Almanach" and listed[0].year == 1912


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
               for params in ({"sort": "random"}, {"limit": 201}, {"type": "maybe"}, {"offset": -1})]

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
    assert [r.status_code for r in bad] == [422, 422, 422, 422]


# ── Resolving a selection (#459) ──────────────────────────────────────────

async def test_all_matches_resolve_to_the_ids_of_every_page(store):
    store.spans.rows = [row(DOC_A, i) for i in range(5)] + [row(DOC_B, 0, tag=OTHER_TAG),
                                                            row(DOC_A, 9, type=SpanType.neg)]
    resolved = await service.resolve_annotation_ids(store, SHARED, COLLECTION, AnnotationIdsRequest(tag_ids=[TAG]))

    rows, _ = await all_pages(store, 2, tag_ids=[TAG])
    assert sorted(resolved.ids, key=str) == sorted(rows, key=str)
    assert len(resolved.ids) == 5


async def test_resolving_applies_the_year_and_text_filters(store):
    store.spans.rows = [row(DOC_A, 0, "Praha"), row(DOC_B, 0, "Praha"), row(DOC_A, 9, "Brno")]
    resolved = await service.resolve_annotation_ids(store, OWNER, COLLECTION,
                                                    AnnotationIdsRequest(q="prah", year_from=1900))

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
        return {r.id for r in (await service.query_annotations(store, OWNER, COLLECTION, **kwargs)).rows}

    assert await found(attribute_values=[f"{ATTRIBUTE}:{VALUE}"]) == {with_value.id, with_both.id}
    assert await found(attribute_values=[f"{ATTRIBUTE}:{VALUE}", f"{ATTRIBUTE}:{OTHER_VALUE}"]) \
        == {with_value.id, with_both.id, with_other_value.id}
    assert await found(attribute_values=[f"{ATTRIBUTE}:{VALUE}", f"{OTHER_ATTRIBUTE}:{OTHER_VALUE}"]) == {with_both.id}
    assert await found(attribute_unassigned=[str(OTHER_ATTRIBUTE)]) == {with_value.id, with_other_value.id, none.id}
    assert await found(attribute_unassigned=[str(ATTRIBUTE)]) == {none.id}
    assert await found(attribute_values=[f"{OTHER_ATTRIBUTE}:{OTHER_VALUE}"], attribute_unassigned=[str(ATTRIBUTE)]) == set()

    # Rows carry the accepted values and the version assignments expect; the resolved selection too.
    with_both.attributeVersion = 3
    page = await service.query_annotations(store, OWNER, COLLECTION, attribute_values=[f"{ATTRIBUTE}:{VALUE}"])
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

    page = await service.query_annotations(store, OWNER, COLLECTION, types=every_type,
                                           attribute_values=[f"{ATTRIBUTE}:{VALUE}"])
    assert [r.id for r in page.rows] == [approved.id]
    page = await service.query_annotations(store, OWNER, COLLECTION, types=every_type)
    by_id = {r.id: r for r in page.rows}
    assert by_id[approved.id].attributes == {ATTRIBUTE: [VALUE]} and by_id[rejected.id].attributes == {}
    page = await service.query_annotations(store, OWNER, COLLECTION, types=every_type,
                                           attribute_unassigned=[str(ATTRIBUTE)])
    assert [r.id for r in page.rows] == [rejected.id]


async def test_attribute_filters_are_refused_on_a_store_without_the_attribute_properties(store):
    store.spans.attributes = False
    with pytest.raises(ServiceUnavailableError):
        await service.query_annotations(store, OWNER, COLLECTION, attribute_values=[f"{ATTRIBUTE}:{VALUE}"])
    with pytest.raises(ServiceUnavailableError):
        await service.resolve_annotation_ids(
            store, OWNER, COLLECTION, AnnotationIdsRequest(attribute_unassigned=[str(ATTRIBUTE)]))
    await service.query_annotations(store, OWNER, COLLECTION)  # without attribute filters nothing changes


@pytest.mark.parametrize("values, unassigned", [(["x"], None), ([f"{ATTRIBUTE}:{VALUE} "], None),
                                                (None, ["x"]), (["a:b"], None)])
async def test_malformed_attribute_filters_are_refused(store, values, unassigned):
    with pytest.raises(InvalidRequestError):
        await service.query_annotations(store, OWNER, COLLECTION, attribute_values=values,
                                        attribute_unassigned=unassigned)


async def test_too_many_attribute_filters_are_refused(store):
    with pytest.raises(InvalidRequestError, match="at most"):
        await service.query_annotations(store, OWNER, COLLECTION,
                                        attribute_unassigned=[str(uuid4()) for _ in range(21)])
