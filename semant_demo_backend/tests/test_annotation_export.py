"""CSV export of a collection's annotations (#719), with the in-memory fakes of the concordance tests.

The three scopes export exactly the annotations the workspace query selects when the export starts
(their ids are resolved first, by queries without offsets, in batches of whole documents beyond the
per-query maximum), in no particular order; rows are then read by id. Positions are the stored
document-level UTF-16 offsets (empty when not current); optional groups add only their columns;
attribute values are only accepted ones, inapplicable ones apart; cells are quoted and protected
against formula evaluation; denied and unresolvable exports read nothing, and a deletion or failed
read during the export aborts it instead of sending a shorter file.
"""
import csv
import io
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from semant_demo.core.errors import InvalidRequestError
from semant_demo.features.annotations import attribute_codec as codec
from semant_demo.features.annotations import export, service
from semant_demo.features.annotations.export import ExportInterrupted
from semant_demo.features.annotations.schemas import (
    AnnotationExportRequest, AnnotationFilters, AnnotationOrigin, SpanType, Tag, TagSpan,
)
from semant_demo.features.annotations.service import AnnotationStore
from semant_demo.features.attributes.schemas import Attribute, AttributeValue, Cardinality
from semant_demo.features.documents.criteria import ChunkVocabulary, DocumentFilters
from semant_demo.features.user_collections.access import AuthenticationRequired, ResourceNotFound
from tests.test_annotation_concordance import (
    COLLECTION, DOC_A, DOC_B, DOC_GONE, DOC_NO_YEAR, OTHER, OTHER_TAG, OWNER, SHARED, TAG, FakeCollections,
    FakeDocuments, FakeSpans, all_pages, row,
)

VOCABULARY = ChunkVocabulary(languages=("ces",), classifications={"complexity": ("easy", "hard"),
                                                                   "communicative_mode": ("narration",)})
TOPIC, SPEAKER = uuid4(), uuid4()
POLITICS, ECONOMY, UNKNOWN = uuid4(), uuid4(), uuid4()
MAN, WOMAN = uuid4(), uuid4()
ATTRIBUTES = [
    Attribute(id=SPEAKER, name="speaker", cardinality=Cardinality.single, tag_ids=[OTHER_TAG],
              values=[AttributeValue(id=MAN, label="man"), AttributeValue(id=WOMAN, label="woman")]),
    Attribute(id=TOPIC, name="topic", cardinality=Cardinality.multi, all_tags=True,
              values=[AttributeValue(id=POLITICS, label="politics"), AttributeValue(id=ECONOMY, label="economy"),
                      AttributeValue(id=UNKNOWN, label="Unknown", kind="unknown")]),
]


class ExportSpans(FakeSpans):
    def __init__(self):
        super().__init__()
        self.ai: dict[UUID, tuple[float | None, str | None]] = {}
        self.fail_after: int | None = None
        """Fail every row read by id after this many."""
        self.row_reads: list[list[UUID]] = []
        self.id_queries: list[tuple[list[UUID] | None, int]] = []

    async def query_ids(self, cid, query, *, document_ids=None, limit):
        self.id_queries.append((document_ids, limit))
        return await super().query_ids(cid, query, document_ids=document_ids, limit=limit)

    async def read_rows_by_id(self, cid, ids):
        if self.fail_after is not None and len(self.row_reads) >= self.fail_after:
            raise ConnectionError("store unavailable")
        self.row_reads.append(list(ids))
        rows = {r.id: r for r in self.rows}
        return {i: rows[i] for i in ids if i in rows}

    async def read_many(self, cid, ids):
        rows = {r.id: r for r in self.rows}
        return {i: TagSpan(id=str(i), chunkId=str(rows[i].chunkId), tagId=str(rows[i].tagId), start=0, end=1,
                           confidence=self.ai.get(i, (None, None))[0], reason=self.ai.get(i, (None, None))[1])
                for i in ids if i in rows}


class ExportDocuments(FakeDocuments):
    def __init__(self):
        super().__init__()
        self.chunks: dict[UUID, dict] = {}
        self.chunk_reads: list[list[UUID]] = []

    async def read_chunk_metadata(self, ids, properties):
        self.chunk_reads.append(list(ids))
        return {i: {p: self.chunks[i].get(p) for p in properties} for i in ids if i in self.chunks}


class FakeTags:
    async def read_by_collection(self, cid):
        return [Tag(id=TAG, name="Osoba", shorthand="O", color="red", pictogram="", definition="", examples=[]),
                Tag(id=OTHER_TAG, name="=Místo", shorthand="M", color="blue", pictogram="", definition="",
                    examples=[])]


class FakeDefinitions:
    async def read_all(self, cid):
        return ATTRIBUTES if cid == COLLECTION else []


class FakeUsers:
    async def get_users(self, ids):
        names = {OWNER.id: "Owner Name", SHARED.id: None}
        return [SimpleNamespace(id=i, name=names[i], username=f"user-{i.hex[:4]}") for i in ids if i in names]


@pytest.fixture
def store():
    return AnnotationStore(collections=FakeCollections(), tags=FakeTags(), spans=ExportSpans(), documents=ExportDocuments())


async def run(store, user=OWNER, **fields):
    request = AnnotationExportRequest(**({"scope": "collection", "types": ["pos", "auto", "neg"]} | fields))
    result = await export.export_annotations(store, FakeDefinitions(), FakeUsers(), VOCABULARY, user, COLLECTION,
                                             request)
    content = b"".join([part async for part in result.content])
    return result, content


def parse(content: bytes, delimiter=",") -> list[dict[str, str]]:
    assert content.startswith(b"\xef\xbb\xbf")
    return list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""), delimiter=delimiter))


# ── Scopes ────────────────────────────────────────────────────────────────

def ids_of(content: bytes) -> list[UUID]:
    return [UUID(r["annotation_id"]) for r in parse(content)]


async def test_filter_matches_are_exported_across_pages_as_the_workspace_lists_them(store, monkeypatch):
    monkeypatch.setattr(export, "EXPORT_PAGE", 2)
    store.spans.rows = [row(DOC_A, 30), row(DOC_B, 0), row(DOC_A, 0), row(DOC_NO_YEAR, 4), row(DOC_A, 10),
                        row(DOC_B, 5, type=SpanType.neg), row(DOC_B, 9, tag=OTHER_TAG)]
    filters = AnnotationFilters(tag_ids=[TAG])
    listed, total = await all_pages(store, 3, filters)
    result, content = await run(store, scope="filters", filters=filters.model_dump(), types=None)
    exported = ids_of(content)
    assert sorted(exported, key=str) == sorted(listed, key=str) and len(set(exported)) == len(exported)
    assert result.count == total == 5 and result.missing == 0
    assert [len(read) for read in store.spans.row_reads] == [2, 2, 1]  # read by id in pages
    assert store.spans.id_queries == [(None, 5)]  # resolved by one query: no offset, limit = the count


async def test_more_matches_than_one_query_returns_are_resolved_in_batches_of_whole_documents(store, monkeypatch):
    monkeypatch.setattr(service, "_MAX_WINDOW", 3)
    store.spans.rows = [row(DOC_A, i) for i in range(3)] + [row(DOC_B, i) for i in range(2)] + [row(DOC_NO_YEAR, 0)]
    result, content = await run(store)
    assert sorted(ids_of(content), key=str) == sorted((r.id for r in store.spans.rows), key=str)
    assert result.count == 6
    batches = [(sorted(map(str, documents)), limit) for documents, limit in store.spans.id_queries]
    assert batches == [([str(DOC_A)], 3), (sorted([str(DOC_B), str(DOC_NO_YEAR)]), 3)]


async def test_annotations_without_a_document_are_exported_when_one_query_resolves_them(store):
    loose = row(None, 0)
    store.spans.rows = [row(DOC_A, 0), loose]
    rows = {UUID(r["annotation_id"]): r for r in parse((await run(store))[1])}
    assert set(rows) == {r.id for r in store.spans.rows}
    assert (rows[loose.id]["document_id"], rows[loose.id]["document_available"]) == ("", "false")


async def test_document_filters_apply_to_the_filter_scope(store):
    store.spans.rows = [row(DOC_A, 0), row(DOC_B, 0)]
    filters = AnnotationFilters(document_filters=DocumentFilters(year_min=1900))
    _, content = await run(store, scope="filters", filters=filters.model_dump(), types=None)
    assert [r["document_title"] for r in parse(content)] == ["Almanach"]


async def test_the_selection_is_exported_whatever_the_filters_with_every_status_and_missing_ids_counted(store):
    rejected, confirmed, other = row(DOC_B, 0, type=SpanType.neg), row(DOC_A, 0), row(DOC_A, 9)
    store.spans.rows = [rejected, confirmed, other]
    gone = uuid4()
    result, content = await run(store, scope="selection", annotation_ids=[rejected.id, confirmed.id, gone,
                                                                          confirmed.id], types=None)
    rows = parse(content)
    assert sorted((UUID(r["annotation_id"]), r["status"]) for r in rows) == \
        sorted([(confirmed.id, "confirmed"), (rejected.id, "rejected")])
    assert (result.count, result.missing) == (2, 1)


async def test_the_collection_scope_exports_exactly_the_chosen_statuses(store):
    store.spans.rows = [row(DOC_A, 0), row(DOC_A, 5, type=SpanType.auto), row(DOC_A, 9, type=SpanType.neg)]
    _, everything = await run(store)
    _, rejected = await run(store, types=["neg"])
    assert sorted(r["status"] for r in parse(everything)) == ["confirmed", "proposal", "rejected"]
    assert [r["status"] for r in parse(rejected)] == ["rejected"]


async def test_an_empty_scope_is_a_file_with_the_header_only(store):
    result, content = await run(store, scope="selection", annotation_ids=[], types=None)
    assert result.count == 0 and parse(content) == []
    assert content.decode("utf-8-sig").startswith("annotation_id,tag_id,tag_name,status")


@pytest.mark.parametrize("fields", [
    {"scope": "selection", "types": None},
    {"scope": "filters", "types": None},
    {"scope": "collection", "types": []},
    {"scope": "selection", "annotation_ids": [], "types": ["pos"]},
    {"scope": "collection", "filters": {}},
    {"scope": "filters", "filters": {"tag_ids": [], "ranking": {"mode": "semantic"}}, "types": None},
    {"delimiter": "tab"},
])
def test_requests_must_name_exactly_the_input_of_their_scope(fields):
    with pytest.raises(ValidationError):
        AnnotationExportRequest(**({"scope": "collection", "types": ["pos"]} | fields))


# ── Columns ───────────────────────────────────────────────────────────────

async def test_positions_and_text_are_the_stored_document_level_values_or_missing(store):
    emoji = "𝐀 Brno 👍"  # non-BMP characters count two UTF-16 units each
    current = row(DOC_A, 1_000_003, emoji)
    current = current.model_copy(update={"documentEndChar": 1_000_003 + len(emoji.encode("utf-16-le")) // 2,
                                         "leftContext": "line\nbreak, \"quoted\" ", "rightContext": ""})
    stale = row(DOC_A, 0, current=False)
    store.spans.rows = [current, stale]
    rows = {r["annotation_id"]: r for r in parse((await run(store))[1])}
    exported = rows[str(current.id)]
    assert (exported["text"], exported["left_context"], exported["right_context"]) == \
        (emoji, "line\nbreak, \"quoted\" ", "")
    assert (exported["document_start_char"], exported["document_end_char"]) == ("1000003", "1000013")
    assert exported["document_id"] == str(DOC_A) and exported["text_status"] == "ready"
    missing = rows[str(stale.id)]
    assert missing["text_status"] == "pending"
    assert [missing[c] for c in ("text", "left_context", "right_context", "document_start_char",
                                 "document_end_char")] == [""] * 5
    assert missing["document_id"] == str(DOC_A)


async def test_optional_groups_add_only_their_columns(store):
    store.spans.rows = [row(DOC_A, 0)]
    base, _ = await run(store, document_metadata=False)
    with_chunk, _ = await run(store, document_metadata=False, chunk_metadata=True)
    with_document, _ = await run(store)
    with_provenance, _ = await run(store, document_metadata=False, provenance=True)
    assert base.columns[:11] == ["annotation_id", "tag_id", "tag_name", "status", "text_status", "text",
                                 "left_context", "right_context", "document_id", "document_start_char",
                                 "document_end_char"]
    assert not any(c.startswith(("chunk_", "document_title", "created_")) for c in base.columns)
    for result, added in ((with_chunk, ["chunk_language", "chunk_complexity", "chunk_communicative_mode"]),
                          (with_document, ["document_available", "document_title", "document_language"]),
                          (with_provenance, ["origin", "created_by_name", "reviewed_at", "ai_reason"])):
        assert result.columns[:len(base.columns)] == base.columns
        assert set(added) <= set(result.columns[len(base.columns):])
        assert not set(result.columns[len(base.columns):]) & set(base.columns)


async def test_chunk_metadata_is_the_anchor_chunks_read_once_per_page(store, monkeypatch):
    monkeypatch.setattr(export, "EXPORT_PAGE", 2)
    first, second, third = row(DOC_A, 0), row(DOC_A, 5), row(DOC_A, 9)
    second = second.model_copy(update={"chunkId": first.chunkId})
    store.spans.rows = [first, second, third]
    store.documents.chunks = {first.chunkId: {"language": "ces", "complexity": ["easy", "hard"],
                                              "communicative_mode": None},
                              third.chunkId: {"language": "deu", "complexity": "hard"}}
    rows = {UUID(r["annotation_id"]): r for r in parse((await run(store, chunk_metadata=True))[1])}
    assert {i: (r["chunk_language"], r["chunk_complexity"], r["document_language"]) for i, r in rows.items()} == {
        first.id: ("ces", "easy | hard", "ces"), second.id: ("ces", "easy | hard", "ces"),
        third.id: ("deu", "hard", "ces")}
    # One read per page, of the page's distinct anchor chunks.
    pages = [{r.chunkId for r in store.spans.rows if r.id in read} for read in store.spans.row_reads]
    assert [set(read) for read in store.documents.chunk_reads] == pages


async def test_document_metadata_and_unavailable_documents(store):
    store.spans.rows = [row(DOC_GONE, 0), row(DOC_NO_YEAR, 0)]
    rows = parse((await run(store))[1])
    assert sorted((r["document_available"], r["document_title"], r["document_year"], r["document_library"])
                  for r in rows) == [("false", "", "", ""), ("true", "Čtení", "", "mzk")]


async def test_provenance_names_current_people_and_ai_metadata(store):
    created, run_id = row(DOC_A, 0, type=SpanType.auto), uuid4()
    created = created.model_copy(update={"origin": AnnotationOrigin.ai, "createdBy": OWNER.id, "aiRunId": run_id,
                                         "reviewedBy": OTHER.id, "editVersion": 3, "revision": 2})
    old = row(DOC_A, 5)
    store.spans.rows = [created, old]
    store.spans.ai = {created.id: (0.75, "=SUM(A1)")}
    rows = {UUID(r["annotation_id"]): r for r in parse((await run(store, provenance=True))[1])}
    fields = ("origin", "created_by_name", "reviewed_by", "reviewed_by_name", "revision", "edit_version",
              "ai_run_id", "ai_confidence", "ai_reason")
    assert [rows[created.id][f] for f in fields] == \
        ["ai", "Owner Name", str(OTHER.id), "", "2", "3", str(run_id), "0.75", "'=SUM(A1)"]
    assert [rows[old.id][f] for f in fields] == ["unknown", "", "", "", "1", "0", "", "", ""]


async def test_attribute_values_are_accepted_ones_with_labels_and_inapplicable_ones_apart(store):
    def values(*pairs):
        return [codec.encode(a, v) for a, v in pairs]
    multi = row(DOC_A, 0, tag=OTHER_TAG).model_copy(update={"attributeValues": values(
        (TOPIC, ECONOMY), (TOPIC, POLITICS), (SPEAKER, WOMAN))})
    retagged = row(DOC_A, 5).model_copy(update={"attributeValues": values((SPEAKER, MAN), (TOPIC, UNKNOWN))})
    rejected = row(DOC_A, 9, type=SpanType.neg, tag=OTHER_TAG).model_copy(
        update={"attributeValues": values((SPEAKER, MAN))})
    none = row(DOC_A, 12)
    store.spans.rows = [multi, retagged, rejected, none]
    result, content = await run(store)
    assert result.columns[11:14] == ["attribute: speaker", "attribute: topic", "inapplicable_attribute_values"]
    rows = {UUID(r["annotation_id"]): r for r in parse(content)}
    assert {i: (r["attribute: speaker"], r["attribute: topic"], r["inapplicable_attribute_values"])
            for i, r in rows.items()} == {
        multi.id: ("woman", "politics | economy", ""), retagged.id: ("", "Unknown", "speaker: man"),
        rejected.id: ("", "", ""), none.id: ("", "", "")}


async def test_no_attribute_columns_on_a_store_without_attributes(store):
    store.spans.attributes = False
    store.spans.rows = [row(DOC_A, 0)]
    result, _ = await run(store)
    assert not any(c.startswith(("attribute", "inapplicable")) for c in result.columns)


# ── CSV format ────────────────────────────────────────────────────────────

async def test_cells_are_quoted_unicode_and_protected_against_formulas(store):
    texts = ["=1+1", "+420 123", "-5", "@user", "\tTab", "Příliš žluťoučký kůň, \"úpěl\"\nďábelské ódy"]
    store.spans.rows = [row(DOC_A, i * 100, t) for i, t in enumerate(texts)]
    _, content = await run(store)
    rows = parse(content)
    assert sorted(r["text"] for r in rows) == sorted(["'=1+1", "'+420 123", "'-5", "'@user", "'\tTab", texts[-1]])
    assert [r["tag_name"] for r in rows] == ["Osoba"] * 6
    assert '"Příliš žluťoučký kůň, ""úpěl""\nďábelské ódy"' in content.decode("utf-8")  # quoted, quotes doubled
    assert content.count(b"\r\n") == len(rows) + 1  # records end with CRLF; the cell keeps its own \n


async def test_headers_are_protected_and_the_semicolon_delimiter_is_honoured(store):
    store.spans.rows = [row(DOC_A, 0, "a;b", tag=OTHER_TAG)]
    result, content = await run(store, delimiter="semicolon")
    [exported] = parse(content, delimiter=";")
    assert (exported["text"], exported["tag_name"]) == ("a;b", "'=Místo")
    assert ",annotation_id" not in content.decode("utf-8-sig")


@pytest.mark.parametrize("value, expected", [
    (None, ""), (True, "true"), (-3, "-3"), (0.5, "0.5"), (["a", None, "b"], "a | b"), ("-x", "'-x"),
    ("\rx", "'\rx"), ("x=1", "x=1"),
])
def test_cell_formatting(value, expected):
    assert export.cell(value) == expected


# ── Access, limits and interruptions ──────────────────────────────────────

@pytest.mark.parametrize("user, error", [(None, AuthenticationRequired), (OTHER, ResourceNotFound)])
async def test_export_needs_read_access_and_reads_nothing_otherwise(store, user, error):
    store.spans.rows = [row(DOC_A, 0)]
    with pytest.raises(error):
        await run(store, user=user)
    assert store.spans.queries == 0 and store.documents.reads == []


async def test_shared_users_export(store):
    store.spans.rows = [row(DOC_A, 0)]
    result, _ = await run(store, user=SHARED)
    assert result.count == 1


async def test_beyond_one_query_annotations_without_a_document_are_refused_not_dropped(store, monkeypatch):
    monkeypatch.setattr(service, "_MAX_WINDOW", 2)
    store.spans.rows = [row(DOC_A, 0), row(DOC_B, 0), row(None, 0)]
    with pytest.raises(InvalidRequestError, match="no recorded document"):
        await run(store)
    assert store.spans.id_queries == [] and store.spans.row_reads == []


async def test_too_many_annotations_in_one_document_are_refused_before_any_row(store, monkeypatch):
    monkeypatch.setattr(service, "_MAX_WINDOW", 2)
    store.spans.rows = [row(DOC_A, i) for i in range(3)]
    with pytest.raises(InvalidRequestError, match="per document"):
        await run(store)
    assert store.spans.id_queries == [] and store.spans.row_reads == []


async def test_too_many_documents_are_refused_not_truncated(store, monkeypatch):
    monkeypatch.setattr(service, "_MAX_DOCUMENTS", 1)
    monkeypatch.setattr(service, "_MAX_WINDOW", 1)  # more matches than one query returns: per document
    store.spans.rows = [row(DOC_A, 0), row(DOC_B, 0)]
    with pytest.raises(InvalidRequestError):
        await run(store)


async def test_a_failed_read_aborts_the_stream_instead_of_ending_the_file(store, monkeypatch):
    monkeypatch.setattr(export, "EXPORT_PAGE", 1)
    store.spans.rows = [row(DOC_A, 0), row(DOC_B, 0)]
    store.spans.fail_after = 1
    with pytest.raises(ExportInterrupted):
        await run(store)
    assert len(store.spans.row_reads) == 1


async def test_annotations_deleted_during_the_export_abort_it(store, monkeypatch):
    monkeypatch.setattr(export, "EXPORT_PAGE", 1)
    store.spans.rows = [row(DOC_A, 0), row(DOC_A, 5)]
    result = await export.export_annotations(
        store, FakeDefinitions(), FakeUsers(), VOCABULARY, OWNER, COLLECTION,
        AnnotationExportRequest(scope="collection", types=["pos"]))
    parts = [await anext(result.content)]  # the header
    store.spans.rows.pop()
    with pytest.raises(ExportInterrupted):
        async for part in result.content:
            parts.append(part)
    assert len(parts) <= 2


async def test_annotations_created_or_edited_during_the_export_neither_abort_it_nor_join_it(store, monkeypatch):
    monkeypatch.setattr(export, "EXPORT_PAGE", 1)
    first, second = row(DOC_A, 0), row(DOC_A, 5)
    store.spans.rows = [first, second]
    result = await export.export_annotations(
        store, FakeDefinitions(), FakeUsers(), VOCABULARY, OWNER, COLLECTION,
        AnnotationExportRequest(scope="collection", types=["pos"]))
    parts = [await anext(result.content)]
    created = row(DOC_A, 1)  # sorts before the others in a document: it would shift offset pages
    store.spans.rows = [created, first, second.model_copy(update={"type": SpanType.neg})]
    parts += [part async for part in result.content]
    rows = {UUID(r["annotation_id"]): r for r in parse(b"".join(parts))}
    assert result.count == 2 and set(rows) == {first.id, second.id}
    assert rows[second.id]["status"] == "rejected"  # its values when read; membership as resolved


# ── HTTP ──────────────────────────────────────────────────────────────────

async def test_route_streams_the_file_with_its_count_and_scope(tmp_path, store, monkeypatch):
    from asgi_lifespan import LifespanManager
    from httpx import ASGITransport, AsyncClient

    from semant_demo.main import create_app
    from semant_demo.routes.dependencies import get_annotation_store, get_attribute_definitions, get_user_lookup
    from tests.app_support import make_test_config, offline_weaviate
    from tests.auth_support import auth_headers, register

    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    app.dependency_overrides[get_annotation_store] = lambda: store
    app.dependency_overrides[get_attribute_definitions] = FakeDefinitions
    app.dependency_overrides[get_user_lookup] = FakeUsers
    kept = row(DOC_A, 0, "Lhota")
    store.spans.rows = [kept, row(DOC_B, 0, type=SpanType.neg)]
    path = f"/api/user_collections/{COLLECTION}/annotations/export"
    async with LifespanManager(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await register(client, email="csv@example.com", password="StrongPassw0rd!")).status_code == 201
        headers = await auth_headers(client, "csv@example.com", "StrongPassw0rd!")
        monkeypatch.setattr(OWNER, "id", UUID((await client.get("/api/users/me", headers=headers)).json()["id"]))
        anonymous = await client.post(path, json={"scope": "collection", "types": ["pos"]})
        filtered = await client.post(path, headers=headers, json={"scope": "filters", "filters": {"q": "lhota"}})
        selected = await client.post(path, headers=headers,
                                     json={"scope": "selection", "annotation_ids": [str(kept.id), str(uuid4())]})
        invalid = await client.post(path, headers=headers, json={"scope": "filters"})
        unknown = await client.post(path, headers=headers,
                                    json={"scope": "filters", "filters": {"year_from": 1900}})
        store.spans.fail_after = len(store.spans.row_reads)
        # The server aborts the response (the request logging middleware re-raises it): no complete file arrives.
        with pytest.raises(Exception, match="ExportInterrupted"):
            await client.post(path, headers=headers, json={"scope": "collection", "types": ["pos"]})

    assert anonymous.status_code == 401
    assert filtered.status_code == 200, filtered.text
    assert filtered.headers["content-type"] == "text/csv; charset=utf-8"
    assert filtered.headers["content-disposition"].startswith('attachment; filename="annotations-filters-')
    assert (filtered.headers["x-export-count"], filtered.headers["x-export-scope"]) == ("1", "filters")
    assert [r["text"] for r in parse(filtered.content)] == ["Lhota"]
    assert (selected.headers["x-export-count"], selected.headers["x-export-missing"]) == ("1", "1")
    assert invalid.status_code == 422 and unknown.status_code == 422
