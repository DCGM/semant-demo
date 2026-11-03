"""Page-order export from the Kramerius mirror (#571): library choice, ordering, warnings, CLI."""
import json
import zipfile
from uuid import UUID

import pytest
from sqlalchemy import create_engine, insert

from semant_demo.adapters.sql.kramerius_metadata import META_RECORDS, PageRow, read_document_pages
from semant_demo.maintenance import page_order
from semant_demo.maintenance.page_order import (
    choose_library, connect_read_only, export, export_document, page_xml_names, real_path, summary)

DOC = UUID("5e3a0000-0000-4000-8000-00000000d001")
OTHER = UUID("5e3a0000-0000-4000-8000-00000000d002")
NLK = [UUID(int=0x100 + i) for i in range(4)]   # nlk page ids
NKP = [UUID(int=0x200 + i) for i in range(4)]   # the same pages in nkp
IMAGE = "/mnt/x/nlk/doc.images/page.jpg"
ZIP = "/mnt/x/nlk/doc.page_xml.zip"


def row(page_id, library, order, image=None, xml=None, label=None, page_type="NormalPage"):
    return PageRow(page_id=page_id, library=library, order=order, label=label, page_type=page_type,
                   image_path=image, page_xml_path=xml)


def mirrored(nlk_image=IMAGE, nlk_xml=None, nkp_image=page_order.NOT_FOUND, nkp_xml=page_order.NOT_FOUND):
    """One document in nlk and nkp, with different page ids, as in the mirror."""
    return ([row(p, "nlk", i, nlk_image, nlk_xml) for i, p in enumerate(NLK)]
            + [row(p, "nkp", i, nkp_image, nkp_xml) for i, p in enumerate(NKP)])


@pytest.mark.parametrize("value, expected", [
    (None, None), ("", None), ("  ", None), ("not_found", None), (IMAGE, IMAGE)])
def test_real_path_ignores_empty_and_not_found(value, expected):
    assert real_path(value) == expected


# --- library choice ----------------------------------------------------------------------

def test_library_with_real_paths_wins_over_not_found_and_empty():
    rows = mirrored() + [row(UUID(int=0x300 + i), "cbvk", i) for i in range(4)]
    assert choose_library(rows, None) == ("nlk", "paths")


def test_real_page_xml_paths_break_a_tie_of_image_paths():
    rows = mirrored(nlk_image=IMAGE, nkp_image=IMAGE, nkp_xml=ZIP)
    assert choose_library(rows, None) == ("nkp", "paths")


def test_supplied_xml_names_break_a_tie():
    rows = mirrored(nlk_image=IMAGE, nkp_image=IMAGE)
    assert choose_library(rows, None) == (None, None)
    assert choose_library(rows, set(NKP[:2])) == ("nkp", "page_xml")


def test_xml_names_choose_when_no_library_has_paths():
    rows = mirrored(nlk_image=None, nkp_image=None, nkp_xml=None)
    assert choose_library(rows, set(NLK)) == ("nlk", "page_xml")
    assert choose_library(rows, None) == (None, None)


def test_only_library_without_paths_is_exported_with_a_warning():
    entry = export_document(DOC, [row(p, "cbvk", i) for i, p in enumerate(NLK)])
    assert (entry["status"], entry["library"], entry["libraryFrom"]) == ("exported", "cbvk", "only_library")
    assert "no_real_paths" in codes(entry)


def test_undecidable_library_is_ambiguous_without_pages():
    entry = export_document(DOC, mirrored(nlk_image=None, nkp_image=None, nkp_xml=None))
    assert entry["status"] == "ambiguous"
    assert entry["libraries"] == ["nkp", "nlk"] and entry["pages"] == []


def test_document_without_page_rows():
    entry = export_document(DOC, [])
    assert entry["status"] == "no_pages" and entry["pages"] == []


# --- cross-checks ------------------------------------------------------------------------

def codes(entry):
    return {warning["code"] for warning in entry["warnings"]}


def test_xml_names_of_another_library_are_a_conflict():
    entry = export_document(DOC, mirrored(), xml_pages={NLK[0], NKP[1]})
    assert entry["status"] == "page_xml_conflict" and entry["pages"] == []
    warning = next(w for w in entry["warnings"] if w["code"] == "page_xml_not_in_library")
    assert warning["count"] == 1 and warning["sample"] == [str(NKP[1])]


def test_start_pages_of_another_library_are_a_conflict():
    entry = export_document(DOC, mirrored(), start_pages=[str(NLK[0]), str(NKP[2])])
    assert entry["status"] == "start_page_conflict" and entry["pages"] == []


def test_matching_start_pages_pass_and_invalid_values_are_reported():
    entry = export_document(DOC, mirrored(), start_pages=[str(NLK[0]), NLK[2], None, "page-7"],
                            start_pages_truncated=True)
    assert entry["status"] == "exported"
    assert {"invalid_start_page_ids", "start_pages_truncated"} <= codes(entry)


# --- pages -------------------------------------------------------------------------------

def test_pages_follow_mirror_order_with_labels_types_and_paths():
    rows = [row(NLK[2], "nlk", 7, IMAGE, ZIP, "3"), row(NLK[0], "nlk", 0, IMAGE, ZIP, "[1]", "TitlePage"),
            row(NLK[1], "nlk", 3, IMAGE, "not_found", "2")]
    entry = export_document(DOC, rows)
    assert [p["pageId"] for p in entry["pages"]] == [str(NLK[0]), str(NLK[1]), str(NLK[2])]
    assert entry["pages"][0] == {"pageId": str(NLK[0]), "order": 0, "label": "[1]", "pageType": "TitlePage",
                                 "imagePath": IMAGE, "pageXmlPath": ZIP, "hasImage": True, "hasPageXml": True}
    assert entry["pages"][1]["pageXmlPath"] is None and not entry["pages"][1]["hasPageXml"]
    assert codes(entry) == {"missing_page_xml"}


def test_supplied_files_decide_page_xml_availability():
    entry = export_document(DOC, mirrored(), xml_pages={NLK[0], NLK[1]})
    assert [p["hasPageXml"] for p in entry["pages"]] == [True, True, False, False]
    missing = next(w for w in entry["warnings"] if w["code"] == "missing_page_xml")
    assert missing["count"] == 2


def test_null_and_duplicate_orders_are_reported_not_fixed():
    rows = [row(NLK[0], "nlk", 1, IMAGE), row(NLK[1], "nlk", None, IMAGE), row(NLK[2], "nlk", 1, IMAGE),
            row(NLK[3], "nlk", 0, IMAGE)]
    entry = export_document(DOC, rows)
    assert [p["order"] for p in entry["pages"]] == [0, 1, 1, None]
    assert {"null_order", "duplicate_order"} <= codes(entry)
    duplicate = next(w for w in entry["warnings"] if w["code"] == "duplicate_order")
    assert duplicate["count"] == 2


def test_missing_images_are_reported():
    rows = [row(NLK[0], "nlk", 0, IMAGE, ZIP), row(NLK[1], "nlk", 1, None, ZIP)]
    entry = export_document(DOC, rows)
    assert [p["hasImage"] for p in entry["pages"]] == [True, False]
    assert codes(entry) == {"missing_image"}


# --- PAGE XML file names -----------------------------------------------------------------

def test_page_xml_names_from_a_zip_or_a_folder(tmp_path):
    with zipfile.ZipFile(tmp_path / f"{DOC}.page_xml.zip", "w") as zf:
        zf.writestr(f"{NLK[0]}.xml", "<x/>")
        zf.writestr(f"sub/{NLK[1]}.XML", "<x/>")
        zf.writestr("readme.txt", "")
        zf.writestr("not-a-uuid.xml", "")
    assert page_xml_names(tmp_path, DOC) == ({NLK[0], NLK[1]}, ["readme.txt", "not-a-uuid.xml"])

    (tmp_path / str(OTHER)).mkdir()
    (tmp_path / str(OTHER) / f"{NLK[2]}.xml").write_text("<x/>")
    assert page_xml_names(tmp_path, OTHER) == ({NLK[2]}, [])
    assert page_xml_names(tmp_path, UUID(int=9)) is None


# --- mirror reads ------------------------------------------------------------------------

@pytest.fixture
def source():
    engine = create_engine("sqlite://")
    META_RECORDS.metadata.create_all(engine)
    with connect_read_only(engine) as connection:
        yield connection
    engine.dispose()


def add_rows(connection, *rows):
    # every row has every key: an executemany insert takes its columns from the first row
    empty = {column.name: None for column in META_RECORDS.columns}
    connection.execute(insert(META_RECORDS), [{**empty, "in_library": False, "record_type": "page", **r}
                                              for r in rows])


def mirror_rows(source):
    add_rows(source,
             {"id": DOC, "library": "nlk", "record_type": "periodicalitem"},
             {"id": DOC, "library": "nkp", "record_type": "periodicalitem"},
             *({"id": p, "library": "nlk", "parent_id": DOC, "parent_library": "nlk", "order": 3 - i,
                "number": str(3 - i), "page_type": "NormalPage", "image_path": IMAGE} for i, p in enumerate(NLK)),
             *({"id": p, "library": "nkp", "parent_id": DOC, "parent_library": "nkp", "order": i,
                "image_path": "not_found", "page_xml_path": "not_found"} for i, p in enumerate(NKP)),
             {"id": UUID(int=0x999), "library": "nlk", "parent_id": DOC, "parent_library": "nlk",
              "record_type": "internalpart", "order": 9},
             {"id": UUID(int=0x998), "library": "nlk", "parent_id": OTHER, "parent_library": "nlk", "order": 0})


def test_read_document_pages_reads_only_page_rows_of_the_documents(source):
    mirror_rows(source)
    pages = read_document_pages(source, [DOC, DOC, UUID(int=1)])
    assert set(pages) == {DOC}
    assert {(r.page_id, r.library) for r in pages[DOC]} == {(p, "nlk") for p in NLK} | {(p, "nkp") for p in NKP}
    first = next(r for r in pages[DOC] if r.page_id == NLK[0])
    assert (first.order, first.label, first.page_type, first.image_path) == (3, "3", "NormalPage", IMAGE)


def test_export_keeps_the_given_document_order(source, tmp_path):
    mirror_rows(source)
    entries = export(source, [OTHER, DOC, OTHER], page_xml_dir=tmp_path)
    assert [e["documentId"] for e in entries] == [str(OTHER), str(DOC)]
    other, doc = entries
    assert other["status"] == "exported" and other["libraryFrom"] == "only_library"
    assert doc["library"] == "nlk" and [p["pageId"] for p in doc["pages"]] == [str(p) for p in reversed(NLK)]
    assert "no_page_xml_files" in codes(doc)
    assert summary(entries)["statuses"] == {"exported": 2}


def test_read_only_connection_option(source):
    assert source.get_execution_options()["postgresql_readonly"] is True


# --- command line ------------------------------------------------------------------------

@pytest.fixture
def no_weaviate(monkeypatch):
    async def refuse(config):
        raise AssertionError("must not connect")
    monkeypatch.setattr("semant_demo.adapters.weaviate.client.connect_weaviate", refuse)
    monkeypatch.delenv(page_order.DSN_VARIABLE, raising=False)


async def test_cli_refuses_without_ids_or_source(no_weaviate, tmp_path):
    assert await page_order._main([]) == 2
    assert await page_order._main([str(DOC)]) == 2                                  # no DSN
    assert await page_order._main([str(DOC), "--page-xml-dir", str(tmp_path / "missing")]) == 2
    bad = tmp_path / "ids.txt"
    bad.write_text("not-a-uuid\n")
    assert await page_order._main(["--document-ids", str(bad)]) == 2


async def test_cli_writes_json_lines(no_weaviate, monkeypatch, tmp_path):
    database = tmp_path / "mirror.sqlite"
    engine = create_engine(f"sqlite:///{database}")
    META_RECORDS.metadata.create_all(engine)
    with engine.begin() as connection:
        mirror_rows(connection)
    engine.dispose()
    monkeypatch.setenv(page_order.DSN_VARIABLE, f"sqlite:///{database}")
    ids = tmp_path / "ids.txt"
    ids.write_text(f"# documents\n{DOC}\n\n")
    output = tmp_path / "pages.jsonl"

    assert await page_order._main(["--document-ids", str(ids), "--output", str(output)]) == 0
    [entry] = [json.loads(line) for line in output.read_text().splitlines()]
    assert entry["library"] == "nlk" and len(entry["pages"]) == 4

    assert await page_order._main([str(UUID(int=1)), "--output", str(output)]) == 1   # no_pages
