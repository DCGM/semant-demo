"""The page layout conversion and chunk anchors on real PERO OCR pages and stored legacy
chunks (#546; fixtures in ``tests/real_pages.py``)."""
import json
import re
import zipfile
from collections import Counter
from uuid import UUID

import pytest

from semant_demo.adapters.filesystem.page_assets import PageAssetStore
from semant_demo.adapters.weaviate.layout_anchors import AnchoredChunk
from semant_demo.features.documents.positions import text_length
from semant_demo.maintenance.page_import.anchors import read_plan
from semant_demo.maintenance.page_import.assets import import_document
from semant_demo.maintenance.page_layout.anchors import replay
from semant_demo.maintenance.page_layout.serialize import Params
from tests.real_pages import FIXTURE, GENERATED, convert, documents, generate

CHRONICLE_1839 = UUID("000070c8-2b2a-46f9-8052-1ce4b7dac249")
NEWSPAPER_COLUMNS = UUID("0002097a-2223-46b0-8507-bde4b059daaa")
VOLUME_1906 = UUID("00094a56-54af-4bd4-9559-c5601d81b15d")
REPEATED_TEXT = UUID("000b03e0-53d7-11ee-9c28-0050568d319f")
OTHER_OCR = UUID("00246353-3566-4e72-80a6-4019d8f94d59")


@pytest.fixture(scope="module")
def results():
    return {document_id: convert(document) for document_id, document in documents().items()}


def anchors_of(results, document_id):
    return {a["chunkId"]: a for a in results[document_id].anchors}


def test_generated_files_are_the_converters_output():
    """The frontend tests read ``generated/``; it must be what the converter makes now."""
    expected = generate()
    actual = {p.relative_to(GENERATED): p.read_bytes() for p in GENERATED.rglob("*") if p.is_file()}
    assert sorted(actual) == sorted(expected), "run `python -m tests.real_pages --write`"
    changed = [str(p) for p in expected if actual[p] != expected[p]]
    assert not changed, f"stale generated files {changed}: run `python -m tests.real_pages --write`"


def test_anchor_levels_per_document(results):
    levels = {document_id: Counter((a["layoutStart"] or {}).get("match") or f"none:{a['reason']}"
                                   for a in result.anchors) for document_id, result in results.items()}
    assert levels == {
        CHRONICLE_1839: {"exact": 8},
        NEWSPAPER_COLUMNS: {"exact": 3, "approximate": 1},
        VOLUME_1906: {"exact": 12},
        REPEATED_TEXT: {"exact": 13, "none:not_found": 13, "none:too_different": 1},
        OTHER_OCR: {"none:not_found": 1, "none:too_different": 1},
    }


def test_every_anchor_is_where_the_whole_document_import_put_it(results):
    """An excerpt of a document is serialized without the pages before it, so the legacy
    rules can drop other short remainders and an exact chunk may become approximate (a
    known limitation, docs/PAGE_LAYOUT.md); the anchor must still be the same line and
    offset, and no chunk without an anchor in the whole document may get one."""
    compared = 0
    for document_id, document in documents().items():
        anchors = anchors_of(results, document_id)
        for chunk in document.chunks:
            full, here = chunk["fullRunLayoutStart"], anchors[chunk["id"]]["layoutStart"]
            assert (full is None) == (here is None), chunk["id"]
            if full:
                compared += 1
                assert (here["pageId"], here["lineId"], here["offset"]) == (full["pageId"], full["lineId"], full["offset"])
    assert compared == 37


def test_exact_anchors_replay_the_stored_text_in_utf16_units(results):
    replayed = 0
    for document_id, document in documents().items():
        result, order = results[document_id], [str(p) for p in document.page_ids]
        pages = {str(page_id): page for page_id, page in result.pages.items()}
        anchors = anchors_of(results, document_id)
        for chunk in document.chunks:
            anchor = anchors[chunk["id"]]["layoutStart"]
            if anchor and anchor["match"] == "exact":
                assert replay(pages, order, anchor, text_length(chunk["text"])) == chunk["text"]
                replayed += 1
            elif anchor:
                # Approximate: a few edits only, within the 5 % threshold.
                assert 0 < anchors[chunk["id"]]["differences"] <= 0.05 * len(chunk["text"])
    assert replayed == 36


def test_a_chunk_crossing_ten_page_breaks_and_blank_pages(results):
    document = documents()[VOLUME_1906]
    chunk = document.chunks[0]
    pages = results[VOLUME_1906].pages
    anchor = anchors_of(results, VOLUME_1906)[chunk["id"]]["layoutStart"]
    assert anchor["match"] == "exact" and anchor["pageId"] == str(document.page_ids[0])
    # The front matter, the first chunk's pages 0..10.
    front = document.entry["pages"][:11]
    blanks = [UUID(p["pageId"]) for p in front if p["pageType"] == "Blank"]
    lines = {page_id: [line["text"] for region in pages[page_id]["regions"] for line in region["lines"]]
             for page_id in document.page_ids[:11]}
    # Four blank pages have page files without lines (their scan's size is still there), and
    # the chunk goes on after them; a fifth "blank" holds a library stamp the OCR kept.
    assert [len(lines[page_id]) for page_id in blanks] == [0, 0, 0, 0, 1]
    assert all(pages[page_id]["image"] for page_id in blanks)
    assert lines[blanks[-1]][0] in chunk["text"]
    # The same caption on three plate pages, all in this one chunk.
    caption = "Aus dem naturhistorischen Vereinsmuseum."
    assert sum(1 for page_id in lines if caption in lines[page_id]) == 3
    assert chunk["text"].count(caption) == 3
    assert chunk["toPage"] - chunk["fromPage"] == 10


def test_ocr_lines_below_the_confidence_threshold_are_left_out(results):
    """The blank pages of the front matter carry OCR of bleed-through: hundreds of lines,
    all below the threshold, none in the page files."""
    xml_lines, file_lines = 0, 0
    front = {p["pageId"] for p in documents()[VOLUME_1906].entry["pages"][:11]}
    with zipfile.ZipFile(FIXTURE / "page_xml" / f"{VOLUME_1906}.page_xml.zip") as zf:
        for name in zf.namelist():
            if name.removesuffix(".xml") in front:
                xml_lines += len(re.findall(r"<TextLine\b", zf.read(name).decode()))
    for page_id, page in results[VOLUME_1906].pages.items():
        if str(page_id) not in front:
            continue
        file_lines += sum(len(region["lines"]) for region in page["regions"])
    assert xml_lines > 1000 and file_lines < xml_lines / 10


def test_hyphenated_line_ends_are_kept_verbatim(results):
    """No dehyphenation: a word split over two lines stays split, with its hyphen and the
    line separator, in the chunk text and in the page files."""
    found = 0
    for document_id, document in documents().items():
        anchors = anchors_of(results, document_id)
        lines = [line["text"] for page in results[document_id].pages.values()
                 for region in page["regions"] for line in region["lines"]]
        for chunk in document.chunks:
            if (anchors[chunk["id"]]["layoutStart"] or {}).get("match") != "exact":
                continue
            for m in re.finditer(r"(\w+)-\n(\w+)", chunk["text"]):
                found += 1
                assert any(text.endswith(m.group(1) + "-") for text in lines)
    assert found > 50


def test_repeated_copies_of_a_page_get_no_anchor(results):
    """The legacy chunks of this page hold it twice; the second copies of exactly matched
    chunks are never placed on the same lines again."""
    document = documents()[REPEATED_TEXT]
    anchors = anchors_of(results, REPEATED_TEXT)
    first: dict[str, dict] = {}
    copies = 0
    for chunk in document.chunks:
        anchor = anchors[chunk["id"]]["layoutStart"]
        if chunk["text"] in first:
            copies += 1
            assert anchor is None and anchors[chunk["id"]]["reason"] == "not_found"
            assert first[chunk["text"]]["layoutStart"]["match"] == "exact"
        else:
            first[chunk["text"]] = anchors[chunk["id"]]
    assert copies == 9


def test_chunks_from_another_ocr_get_no_anchor(results):
    assert all(a["layoutStart"] is None for a in results[OTHER_OCR].anchors)
    # The stored text is the older Fraktur OCR (long s); the PAGE XML is not.
    assert all("ſ" in c["text"] for c in documents()[OTHER_OCR].chunks)
    assert not any("ſ" in line["text"] for page in results[OTHER_OCR].pages.values()
                   for region in page["regions"] for line in region["lines"])


def test_page_import_of_real_pages_with_missing_scans(tmp_path):
    """The import (#542) on the excerpt of the 1906 volume: one page has a scan, the others
    none; the manifest says so and the plan holds the converter's anchors."""
    document = documents()[VOLUME_1906]
    pages = []
    for order, page in enumerate(document.entry["pages"]):
        scan = document.scan(UUID(page["pageId"]))
        pages.append({"pageId": page["pageId"], "order": order, "label": page["label"], "pageType": page["pageType"],
                      "imagePath": str(scan) if scan else None, "hasImage": bool(scan),
                      "pageXmlPath": str(FIXTURE / "page_xml" / f"{document.id}.page_xml.zip"), "hasPageXml": True})
    entry = {"documentId": str(document.id), "status": "exported", "library": document.entry["library"], "pages": pages}
    chunks = [AnchoredChunk(id=UUID(c["id"]), order=c["order"], text=c["text"], start_page_id=None,
                            from_page=c["fromPage"] - document.entry["sourcePageOrders"][0],
                            to_page=c["toPage"] - document.entry["sourcePageOrders"][0], layout_start=None)
              for c in document.chunks]
    store = PageAssetStore(tmp_path)
    line = import_document(store, entry, chunks, Params(), 0.05)
    assert line["status"] == "imported"
    assert line["anchors"] == {"exact": 12, "approximate": 0, "none": 0, "reasons": {}}
    manifest = store.read_manifest(document.id)
    scanned = [i for i, p in enumerate(manifest.pages) if p.image]
    assert scanned == [14] and manifest.pages[14].thumbnail
    assert all(p.layout for p in manifest.pages) and not any(p.thumbnail for i, p in enumerate(manifest.pages) if i != 14)
    # The scan is kept byte for byte; its size is the downscaled copy's.
    assert manifest.pages[14].width == 900
    plan = {line["chunkId"]: line["layoutStart"] for line in read_plan(store, document.id)}
    generated = {a["chunkId"]: a["layoutStart"] for a in map(json.loads, (GENERATED / "anchors.jsonl").read_text().splitlines())
                 if a["documentId"] == str(document.id)}
    assert plan == generated
