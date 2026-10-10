"""Kramerius metadata synchronization: mapping, source-library policy, report and apply (#257)."""
import json
from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy import create_engine, insert

from semant_demo.adapters.sql.kramerius_metadata import META_RECORDS, read_meta_records
from semant_demo.config import Config
from semant_demo.maintenance import metadata_sync
from semant_demo.maintenance.kramerius_mapping import FIELDS, IssueDate, SourceRecord, map_record, parse_issue_date, values
from semant_demo.maintenance.metadata_sync import (
    apply_exit_code, apply_report, build_report, coerce, plan_document, read_library_map, target_properties,
    write_candidates)

DOC = UUID("5e3a0000-0000-4000-8000-00000000d001")
OTHER = UUID("5e3a0000-0000-4000-8000-00000000d002")
NAMES = Config(environ={}).collectionNames
UTC = timezone.utc

CURRENT_SCHEMA = {
    "title": "text", "titleMetadata": "text", "subtitle": "text", "partNumber": "text", "partName": "text",
    "dateIssued": "date", "yearIssued": "number", "dateIssuedMetadata": "date", "yearIssuedMetadata": "number",
    "author": "text[]", "publisher": "text", "language": "text", "documentType": "text",
    "placeOfPublication": "text", "seriesName": "text", "seriesNumber": "text", "edition": "text",
    "editors": "text[]", "illustrators": "text[]", "translators": "text[]", "redaktors": "text[]",
    "manufacturePublisher": "text", "manufacturePlaceTerm": "text", "public": "boolean", "url": "uuid",
    "library": "text",
}
LEGACY_SCHEMA = {
    "library": "text", "title": "text", "subTitle": "text", "partNumber": "int", "yearIssued": "int",
    "dateIssued": "date", "authors": "text[]", "placeTerm": "text", "seriesNumber": "int", "public": "boolean",
    "url": "text",
}


def record(library="mzk", **kwargs) -> SourceRecord:
    return SourceRecord(id=str(DOC), library=library, **kwargs)


def targets(schema=CURRENT_SCHEMA):
    return target_properties(schema)[0]


# --- value normalization -----------------------------------------------------------------

@pytest.mark.parametrize("data, expected", [
    ([["Own", "Parent"], ["Parent", "Grandparent"]], ["Own", "Parent", "Grandparent"]),
    (["B", "A", "B"], ["B", "A"]),
    ("  single ", ["single"]),
    ([[], ["", None], [" x "]], ["x"]),
    (None, []),
])
def test_values_flatten_in_order_without_repeats(data, expected):
    assert values(data) == expected


@pytest.mark.parametrize("text, expected", [
    ("22.5.1929", IssueDate(datetime(1929, 5, 22, tzinfo=UTC), 1929)),
    ("1929-05-22", IssueDate(datetime(1929, 5, 22, tzinfo=UTC), 1929)),
    ("5.1929", IssueDate(year=1929)),
    ("1929-05", IssueDate(year=1929)),
    ("1929", IssueDate(year=1929)),
    ("[1929?]", IssueDate(year=1929)),
    ("asi 1929", IssueDate(year=1929)),
    ("ca. 1929", IssueDate(year=1929)),
    ("1890-1895", IssueDate()),
    ("1890-", IssueDate()),
    ("189-", IssueDate()),
    ("31.2.1929", IssueDate()),
    ("13.1929", IssueDate()),
    ("unknown", IssueDate()),
    (None, IssueDate()),
])
def test_issue_dates_keep_only_stated_precision(text, expected):
    assert parse_issue_date(text) == expected


def test_parsed_range_within_one_year_gives_that_year():
    assert parse_issue_date("1890-1890", datetime(1890, 1, 1), datetime(1890, 12, 31)) == IssueDate(year=1890)
    assert parse_issue_date("1890-1895", datetime(1890, 1, 1), datetime(1895, 12, 31)) == IssueDate()
    # Seen in the mirror: an issue with date "not_found" and equal parsed start/end.
    assert parse_issue_date("not_found", datetime(1921, 3, 29), datetime(1921, 3, 29)) == IssueDate(
        datetime(1921, 3, 29, tzinfo=UTC), 1921)
    assert parse_issue_date(None, datetime(1921, 1, 1), datetime(1921, 1, 1)) == IssueDate(year=1921)
    # "1912/13" with a garbage parsed start (4000-04-04) and no end.
    assert parse_issue_date("1912/13", datetime(4000, 4, 4), None) == IssueDate()
    # A start date alone is either a point (e.g. a year stored as 1 January) or an open range.
    assert parse_issue_date(None, datetime(1890, 1, 1), None) == IssueDate()


def test_map_record_takes_own_values_first_and_leaves_missing_fields_out():
    mapped = map_record(record(
        title=None, date="1889", record_type="periodicalitem", public=True,
        metadata_json={"Title": [["Brünner Zeitung"], ["Parent title"]], "DateIssued": [["12.12.1889"]],
                       "Author": [["B. Author", "A. Author"], ["A. Author"]], "Language": [["deu"]],
                       "SeriesNumber": [["IV"]], "PlaceTerm": [[]]}))

    assert mapped == {
        "title": "Brünner Zeitung", "titleMetadata": "Brünner Zeitung",
        "dateIssued": datetime(1889, 12, 12, tzinfo=UTC), "yearIssued": 1889,
        "dateIssuedMetadata": datetime(1889, 12, 12, tzinfo=UTC), "yearIssuedMetadata": 1889,
        "author": ["B. Author", "A. Author"], "language": "deu", "seriesNumber": "IV",
        "documentType": "periodicalitem", "public": True, "library": "mzk",
    }
    assert set(mapped) <= set(FIELDS)


def test_a_day_outside_the_chosen_year_is_dropped():
    mapped = map_record(record(date="1889", metadata_json={"DateIssued": ["12.12.1890"]}))
    assert mapped["yearIssued"] == 1889 and "dateIssued" not in mapped
    assert mapped["dateIssuedMetadata"] == datetime(1890, 12, 12, tzinfo=UTC)


@pytest.mark.parametrize("value, data_type, expected", [
    ("IV", "text", "IV"),
    ("12", "int", 12),
    (12, "text", "12"),
    (1889, "number", 1889),
    ("1889", "number", 1889),
    (["a"], "text[]", ["a"]),
    (True, "boolean", True),
    (datetime(1889, 1, 2), "date", datetime(1889, 1, 2, tzinfo=UTC)),
])
def test_coerce_converts_to_the_declared_type(value, data_type, expected):
    assert coerce(value, data_type) == expected


@pytest.mark.parametrize("value, data_type", [
    ("IV", "int"), ("IV", "number"), (True, "text"), (1, "boolean"), ("x", "uuid"), ("x", "text[]"), ("1889", "date"),
])
def test_coerce_rejects_values_that_do_not_fit(value, data_type):
    with pytest.raises(ValueError):
        coerce(value, data_type)

# --- source library policy ---------------------------------------------------------------

MZK = record("mzk", title="Own title", public=False, in_library=True, metadata_json={"Publisher": ["MZK publisher"]})
NKP = record("nkp", title="Fuller title", public=True, date="1.1.1900",
             metadata_json={"Publisher": ["NKP publisher"], "Author": ["Someone"], "Language": ["ces"]})


def plan(stored, records, schema=CURRENT_SCHEMA, **kwargs):
    return plan_document(DOC, stored, records, targets(schema), **kwargs)


@pytest.mark.parametrize("records", [[MZK, NKP], [NKP, MZK]])
def test_only_the_source_library_row_is_used(records):
    entry = plan({"library": "mzk", "public": False}, records)

    assert entry["library"] == "mzk" and entry["library_from"] == "stored" and entry["in_library"] is True
    assert entry["mirror_libraries"] == ["mzk", "nkp"]
    assert entry["changes"] == {"title": {"old": None, "new": "Own title"},
                                "publisher": {"old": None, "new": "MZK publisher"}}
    assert "held" not in entry  # NKP's public=True is never considered


def test_fields_missing_in_the_source_library_stay_missing():
    entry = plan({"library": "mzk"}, [NKP, MZK])
    assert {"author", "language", "yearIssued", "dateIssued"}.isdisjoint(entry["changes"])


def test_stored_values_the_source_lacks_are_reported_not_cleared():
    entry = plan({"library": "mzk", "author": ["Kept"], "public": False}, [MZK])
    assert entry["stale"] == ["author"] and "author" not in entry["changes"]


def test_access_change_is_held_unless_requested():
    stored = {"library": "nkp", "public": False}
    held = plan(stored, [NKP])
    applied = plan(stored, [NKP], update_access=True)

    assert held["held"]["public"] == {"old": False, "new": True, "reason": "access flag; needs --update-access"}
    assert "public" not in held["changes"]
    assert applied["changes"]["public"] == {"old": False, "new": True}


def test_differing_values_are_replaced_only_with_overwrite():
    stored = {"library": "mzk", "title": "Corrected title", "public": False}
    assert plan(stored, [MZK])["held"]["title"]["new"] == "Own title"
    assert plan(stored, [MZK], overwrite=True)["changes"]["title"] == {"old": "Corrected title", "new": "Own title"}


@pytest.mark.parametrize("stored, mapped, records, kind", [
    ({}, None, [], "no_library"),
    ({}, None, [MZK], "no_library"),                       # one row, but inference not requested
    ({"library": ""}, None, [MZK], "no_library"),
    ({}, None, [MZK, NKP], "multiple_libraries"),
    ({"library": "mzk"}, "nkp", [MZK, NKP], "library_conflict"),
    ({"library": "knav"}, None, [MZK, NKP], "no_source_row"),
    ({}, "knav", [], "no_source_row"),
    ({"library": "mzk"}, None, [MZK, MZK], "ambiguous_source_row"),
])
def test_unknown_or_unmatched_source_is_unresolved(stored, mapped, records, kind):
    entry = plan(stored, records, mapped_library=mapped)
    assert entry["status"] == "unresolved" and entry["kind"] == kind
    assert "changes" not in entry


def test_unresolved_entries_name_the_mirror_libraries_without_using_them():
    entry = plan({"library": "knav"}, [NKP, MZK])
    assert entry["reason"] == "no mirror row for library 'knav' (rows exist for mzk, nkp; not used)"
    assert entry["mirror_libraries"] == ["mzk", "nkp"] and entry["stored_library"] == "knav"


def test_library_map_supplies_the_library_and_fills_a_declared_property():
    entry = plan({}, [MZK, NKP], mapped_library="mzk")
    assert entry["status"] == "update" and entry["library_from"] == "library_map"
    assert entry["changes"]["library"] == {"old": None, "new": "mzk"}


def test_unique_row_is_only_a_candidate_and_never_changes_access():
    entry = plan({"public": False}, [NKP], infer_unique=True, update_access=True)

    assert entry["status"] == "candidate" and entry["library_from"] == "inferred_unique"
    assert entry["changes"]["library"] == {"old": None, "new": "nkp"}
    assert entry["held"]["public"]["reason"] == "access flag; never changed for an inferred library"
    assert plan({}, [MZK, NKP], infer_unique=True)["kind"] == "multiple_libraries"


def test_distrusted_stored_library_is_resolved_again():
    stored = {"library": "mzk"}
    assert plan(stored, [NKP], distrusted=frozenset({"mzk"}))["kind"] == "no_library"
    inferred = plan(stored, [NKP], distrusted=frozenset({"mzk"}), infer_unique=True)
    mapped = plan(stored, [MZK, NKP], distrusted=frozenset({"mzk"}), mapped_library="nkp")

    assert inferred["status"] == "candidate" and inferred["changes"]["library"] == {"old": "mzk", "new": "nkp"}
    assert mapped["status"] == "update" and mapped["changes"]["library"] == {"old": "mzk", "new": "nkp"}
    assert mapped["changes"]["publisher"]["new"] == "NKP publisher"


def test_override_corrects_a_wrong_stored_library_without_overwrite():
    entry = plan({"library": "mzk", "publisher": "MZK publisher"}, [MZK, NKP], override_library="nkp")

    assert entry["library_from"] == "override"
    assert entry["changes"]["library"] == {"old": "mzk", "new": "nkp"}
    assert entry["held"]["publisher"]["new"] == "NKP publisher"  # other values still need --overwrite


# --- target schema -----------------------------------------------------------------------

def test_legacy_property_names_and_types():
    src = record("mzk", date="1889", metadata_json={
        "Author": ["A"], "Subtitle": ["Sub"], "PlaceTerm": ["Brno"], "SeriesNumber": ["IV"], "PartNumber": ["7"]})
    entry = plan({"library": "mzk"}, [src], LEGACY_SCHEMA)

    assert entry["changes"] == {
        "authors": {"old": None, "new": ["A"]}, "subTitle": {"old": None, "new": "Sub"},
        "placeTerm": {"old": None, "new": "Brno"}, "partNumber": {"old": None, "new": 7},
        "yearIssued": {"old": None, "new": 1889}}
    assert entry["skipped"] == {"seriesNumber": "'IV' does not fit int"}


def test_undeclared_fields_are_never_written():
    mapped_targets, undeclared = target_properties({"title": "text"})
    assert set(mapped_targets) == {"title"}
    assert "manufacturePublisher" in undeclared and "library" in undeclared


def test_stored_values_compare_after_normalization():
    src = record("mzk", date="12.12.1889")
    stored = {"library": "mzk", "yearIssued": 1889.0, "dateIssued": datetime(1889, 12, 12, tzinfo=UTC)}
    assert plan(stored, [src])["status"] == "unchanged"


# --- mirror reads ------------------------------------------------------------------------

@pytest.fixture
def source():
    engine = create_engine("sqlite://")
    META_RECORDS.metadata.create_all(engine)
    with engine.connect() as connection:
        yield connection
    engine.dispose()


def add_rows(connection, *rows):
    connection.execute(insert(META_RECORDS), [
        {"public": False, "in_library": False, "record_type": None, "title": None, "date": None,
         "start_date": None, "end_date": None, "metadata_json": None, **row} for row in rows])


def test_read_meta_records_groups_all_libraries_by_id(source):
    add_rows(source, {"id": DOC, "library": "mzk", "metadata_json": {"Author": [["A"]]}},
             {"id": DOC, "library": "nkp"}, {"id": OTHER, "library": "mzk"})

    found = read_meta_records(source, [DOC, UUID(int=1)])

    assert set(found) == {DOC}
    assert sorted(r.library for r in found[DOC]) == ["mzk", "nkp"]
    assert next(r for r in found[DOC] if r.library == "mzk").metadata_json == {"Author": [["A"]]}


# --- report and apply against a fake documents collection -------------------------------

class FakeDocuments:
    def __init__(self, documents: dict[UUID, dict], schema=CURRENT_SCHEMA):
        self.documents = documents
        self.schema = schema
        self.updates: list[tuple[UUID, dict]] = []
        self.fail: set[UUID] = set()
        self.lose_writes = False

    def install(self, monkeypatch):
        async def property_types(client, names):
            return self.schema

        async def page(client, names, after, limit):
            ids = sorted(i for i in self.documents if after is None or i > after)[:limit]
            return [(i, dict(self.documents[i])) for i in ids]

        async def read(client, names, ids):
            return {i: dict(self.documents[i]) for i in ids if i in self.documents}

        async def update(client, names, document_id, properties):
            if document_id in self.fail:
                raise TimeoutError("timed out")
            self.updates.append((document_id, properties))
            if not self.lose_writes:
                self.documents[document_id].update(properties)

        for name, fake in (("document_property_types", property_types), ("read_document_page", page),
                           ("read_documents", read), ("update_document", update)):
            monkeypatch.setattr(metadata_sync, name, fake)
        return self


async def report_of(source, **kwargs):
    return await build_report(None, NAMES, source, endpoint="localhost:8080", source_name="test", **kwargs)


async def test_report_continues_past_documents_without_source_rows(source, monkeypatch):
    FakeDocuments({DOC: {"library": "mzk"}, OTHER: {"library": "mzk"}}).install(monkeypatch)
    add_rows(source, {"id": OTHER, "library": "mzk", "title": "Found"})

    report = await report_of(source)

    counts = report["counts"]
    assert (counts["in_scope"], counts["eligible"], counts["candidate"]) == (2, 1, 0)
    assert counts["unresolved"] == {"no_source_row": 1}
    assert counts["mirror_libraries"] == {"none": 1, "one": 1, "several": 0}
    assert counts["library_from"] == {"stored": 1}
    assert report["next_after"] is None
    assert [e["status"] for e in report["documents"]] == ["unresolved", "update"]


async def test_report_pages_with_limit_and_after(source, monkeypatch):
    FakeDocuments({DOC: {}, OTHER: {}}).install(monkeypatch)

    first = await report_of(source, limit=1)
    rest = await report_of(source, after=UUID(first["next_after"]), limit=1)

    assert first["next_after"] == str(DOC)
    assert [e["id"] for e in first["documents"] + rest["documents"]] == [str(DOC), str(OTHER)]


async def test_report_lists_requested_ids_missing_from_the_target(source, monkeypatch):
    FakeDocuments({DOC: {}}).install(monkeypatch)
    report = await report_of(source, document_ids=[OTHER], library_map={OTHER: "mzk"})
    assert report["documents"] == [{"id": str(OTHER), "status": "unresolved", "kind": "not_in_target",
                                    "reason": "no such document in the target collection"}]


async def test_candidates_are_written_for_review(source, monkeypatch, tmp_path):
    FakeDocuments({DOC: {}, OTHER: {}}).install(monkeypatch)
    add_rows(source, {"id": DOC, "library": "nkp"}, {"id": OTHER, "library": "mzk"}, {"id": OTHER, "library": "nkp"})
    report = await report_of(source, infer_unique=True)
    path = tmp_path / "candidates.csv"

    assert write_candidates(path, report) == 1
    assert read_library_map(path) == {DOC: "nkp"}
    assert report["counts"]["candidate"] == 1 and report["counts"]["unresolved"] == {"multiple_libraries": 1}


async def test_candidates_without_changes_are_listed(source, monkeypatch, tmp_path):
    schema = {k: v for k, v in CURRENT_SCHEMA.items() if k != "library"}
    FakeDocuments({DOC: {}}, schema=schema).install(monkeypatch)
    add_rows(source, {"id": DOC, "library": "nkp"})
    report = await report_of(source, infer_unique=True)

    assert [e["status"] for e in report["documents"]] == ["candidate"]
    assert write_candidates(tmp_path / "c.csv", report) == 1


async def test_report_is_json_and_apply_writes_and_verifies_reviewed_changes(source, monkeypatch):
    store = FakeDocuments({DOC: {}, OTHER: {"library": "mzk"}}).install(monkeypatch)
    add_rows(source, {"id": DOC, "library": "mzk", "date": "22.5.1929", "title": "T"},
             {"id": OTHER, "library": "mzk", "title": "U"})
    report = json.loads(json.dumps(await report_of(source, library_map={DOC: "mzk"})))

    result = await apply_report(None, NAMES, report)

    assert {k: result[k] for k in ("in_scope", "unresolved", "candidate", "eligible", "applied", "verified",
                                   "already_applied", "not_applied", "failed")} == {
        "in_scope": 2, "unresolved": 0, "candidate": 0, "eligible": 2, "applied": 2, "verified": 2,
        "already_applied": 0, "not_applied": [], "failed": []}
    assert apply_exit_code(result) == 0
    assert store.documents[DOC] == {"library": "mzk", "title": "T", "yearIssued": 1929,
                                    "dateIssued": datetime(1929, 5, 22, tzinfo=UTC)}
    again = await apply_report(None, NAMES, report)  # rerunning is safe
    assert again["already_applied"] == 2 and apply_exit_code(again) == 0


async def test_apply_checks_the_library_even_when_it_is_not_changed(source, monkeypatch):
    store = FakeDocuments({DOC: {"library": "mzk"}}).install(monkeypatch)
    add_rows(source, {"id": DOC, "library": "mzk", "title": "MZK title"})
    report = await report_of(source)
    assert "library" not in report["documents"][0]["changes"]
    store.documents[DOC]["library"] = "nkp"

    result = await apply_report(None, NAMES, report)

    assert result["not_applied"] == [{"id": str(DOC), "reason": "library changed since the report"}]
    assert store.updates == [] and apply_exit_code(result) == 1


async def test_apply_skips_documents_changed_since_the_report_and_reports_failures(source, monkeypatch):
    third = UUID(int=3)
    store = FakeDocuments({DOC: {"library": "mzk"}, OTHER: {"library": "mzk"}, third: {"library": "mzk"}})
    store.install(monkeypatch)
    add_rows(source, *({"id": i, "library": "mzk", "title": "New"} for i in (DOC, OTHER, third)))
    report = await report_of(source)
    store.documents[DOC]["title"] = "Edited meanwhile"
    del store.documents[third]
    store.fail.add(OTHER)

    result = await apply_report(None, NAMES, report)

    assert result["applied"] == 0
    assert result["not_applied"] == [{"id": str(third), "reason": "the document no longer exists"},
                                     {"id": str(DOC), "reason": "title changed since the report"}]
    assert result["failed"] == [{"id": str(OTHER), "error": "TimeoutError: timed out"}]
    assert store.documents[DOC]["title"] == "Edited meanwhile"
    assert apply_exit_code(result) == 1


async def test_apply_reports_writes_that_do_not_read_back(source, monkeypatch):
    store = FakeDocuments({DOC: {"library": "mzk"}}).install(monkeypatch)
    add_rows(source, {"id": DOC, "library": "mzk", "title": "New"})
    report = await report_of(source)
    store.lose_writes = True

    result = await apply_report(None, NAMES, report)

    assert (result["applied"], result["verified"]) == (1, 0)
    assert result["failed"] == [{"id": str(DOC), "error": "read back differs: title"}]
    assert apply_exit_code(result) == 1


async def test_apply_with_nothing_eligible_is_not_a_success(source, monkeypatch):
    FakeDocuments({DOC: {"library": "mzk"}}).install(monkeypatch)
    add_rows(source, {"id": DOC, "library": "mzk"})
    result = await apply_report(None, NAMES, await report_of(source))
    assert result["eligible"] == 0 and apply_exit_code(result) == 1


async def test_apply_refuses_incomplete_reports_unless_accepted(source, monkeypatch):
    store = FakeDocuments({DOC: {"library": "mzk"}, OTHER: {}}).install(monkeypatch)
    add_rows(source, {"id": DOC, "library": "mzk", "title": "New"}, {"id": OTHER, "library": "nkp"})
    report = await report_of(source, infer_unique=True)
    assert report["counts"]["candidate"] == 1

    with pytest.raises(LookupError, match="1 documents in the report are unresolved or candidates"):
        await apply_report(None, NAMES, report)
    result = await apply_report(None, NAMES, report, accept_incomplete=True)

    assert (result["eligible"], result["verified"], result["candidate"]) == (1, 1, 1)
    assert store.documents[OTHER] == {}  # the candidate is never written


@pytest.mark.parametrize("report_schema, store_schema", [
    (CURRENT_SCHEMA, {**CURRENT_SCHEMA, "seriesNumber": "int"}),                   # changed type
    ({k: v for k, v in CURRENT_SCHEMA.items() if k != "library"},) * 2,           # library not storable
])
async def test_apply_refuses_an_unsuitable_schema(source, monkeypatch, report_schema, store_schema):
    FakeDocuments({DOC: {"library": "mzk"}}, schema=report_schema).install(monkeypatch)
    add_rows(source, {"id": DOC, "library": "mzk", "title": "New"})
    report = await report_of(source)
    FakeDocuments({DOC: {"library": "mzk"}}, schema=store_schema).install(monkeypatch)

    with pytest.raises(LookupError):
        await apply_report(None, NAMES, report)


# --- command line ------------------------------------------------------------------------

@pytest.fixture
def no_connection(monkeypatch):
    async def refuse(config):
        raise AssertionError("must not connect")
    monkeypatch.setattr("semant_demo.adapters.weaviate.client.connect_weaviate", refuse)
    for name in ("WEAVIATE_HOST", "WEAVIATE_REST_PORT", metadata_sync.DSN_VARIABLE):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("report, args", [
    ({"endpoint": "localhost:8080", "collection": "Documents"}, []),
    ({"endpoint": "localhost:8080", "collection": "Documents"}, ["--confirm-endpoint", "server:8080"]),
    ({"endpoint": "server:8080", "collection": "Documents"}, ["--confirm-endpoint", "localhost:8080"]),
    ({"endpoint": "localhost:8080", "collection": "Other"}, ["--confirm-endpoint", "localhost:8080"]),
])
async def test_apply_refuses_before_connecting(no_connection, tmp_path, report, args):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({**report, "documents": []}), encoding="utf-8")
    assert await metadata_sync._main(["--apply", str(path), *args]) == 2


@pytest.mark.parametrize("args", [[], ["--confirm-endpoint", "server:8080"]])
async def test_schema_change_refuses_before_connecting(no_connection, args):
    assert await metadata_sync._main(["--add-library-property", *args]) == 2


async def test_report_needs_a_source_before_connecting(no_connection):
    assert await metadata_sync._main([]) == 2


def test_library_map_rejects_an_id_with_two_libraries(tmp_path):
    path = tmp_path / "map.csv"
    path.write_text(f"# document_id,library\n{DOC},mzk\n\n{OTHER},nkp\n", encoding="utf-8")
    assert read_library_map(path) == {DOC: "mzk", OTHER: "nkp"}

    path.write_text(f"{DOC},mzk\n{DOC},nkp\n", encoding="utf-8")
    with pytest.raises(ValueError, match="two libraries"):
        read_library_map(path)
