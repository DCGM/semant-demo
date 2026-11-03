"""PAGE XML -> page layout JSON and chunk-start anchors (#540), on synthetic PAGE XML."""
import json
import random
import zipfile
from uuid import UUID

import pytest

from semant_demo.features.documents.positions import text_length
from semant_demo.maintenance.page_layout.__main__ import main
from semant_demo.maintenance.page_layout.anchors import build_stream, match_chunks, replay
from semant_demo.maintenance.page_layout.convert import StoredChunk, convert_document, read_chunks, read_page_xml
from semant_demo.maintenance.page_layout.geometry import line_heights, word_starts
from semant_demo.maintenance.page_layout.parse import NAMESPACE, PageXmlError, parse_heights, parse_page_xml
from semant_demo.maintenance.page_layout.serialize import Params, serialize

DOC = UUID("5e3a0000-0000-4000-8000-00000000d540")
PAGES = [UUID(int=0x540_000 + i) for i in range(8)]
SMALL = Params(line_confidence=0.6, min_chunk_chars=40, max_chunk_chars=60)


def line(line_id, text, conf=0.9, *, baseline="10,100 410,100", heights="[18.6, 6.9]", polygon=None):
    attributes = f' custom="{{&quot;heights&quot;: {heights}}}"' if heights else ""
    coords = f'<Coords points="{polygon}"/>' if polygon else ""
    base = f'<Baseline points="{baseline}"/>' if baseline is not None else ""
    if text is None:
        equiv = ""
    else:
        escaped = text.replace("&", "&amp;").replace("<", "&lt;")
        conf_attr = f' conf="{conf}"' if conf is not None else ""
        equiv = f"<TextEquiv{conf_attr}><Unicode>{escaped}</Unicode></TextEquiv>"
    return f'<TextLine id="{line_id}"{attributes}>{coords}{base}{equiv}</TextLine>'


def page_xml(page_id, regions, *, reading_order=None, namespace=NAMESPACE, image_filename=None):
    """``regions``: list of (region id, [line(...) strings]) or raw XML strings."""
    body = "".join(r if isinstance(r, str) else f'<TextRegion id="{r[0]}">{"".join(r[1])}</TextRegion>'
                   for r in regions)
    order = ""
    if reading_order:
        refs = "".join(f'<RegionRefIndexed index="{i}" regionRef="{r}"/>' for i, r in enumerate(reading_order))
        order = f'<ReadingOrder><OrderedGroup id="ro">{refs}</OrderedGroup></ReadingOrder>'
    name = image_filename or str(page_id)
    return (f'<?xml version="1.0" encoding="utf-8"?><PcGts xmlns="{namespace}"><Metadata/>'
            f'<Page imageFilename="{name}" imageWidth="1378" imageHeight="2000">{order}{body}</Page></PcGts>'
            ).encode("utf-8")


def para(region_id, *texts, conf=0.9):
    return region_id, [line(f"{region_id}-l{i}", t, conf) for i, t in enumerate(texts)]


def convert(pages_regions, params=SMALL, stored=None, **kwargs):
    xml = {PAGES[i]: page_xml(PAGES[i], regions) for i, regions in enumerate(pages_regions)}
    return convert_document(DOC, PAGES[:len(pages_regions)], xml, params, stored, **kwargs)


def texts(result):
    return [c["text"] for c in result.chunks]


def assert_round_trip(result, stored=None):
    """Every anchored chunk's text replays from its anchor through the page files."""
    files = {str(k): v for k, v in result.pages.items()}
    order = list(files)
    chunk_texts = [c.text for c in stored] if stored is not None else texts(result)
    for anchor, text in zip(result.anchors, chunk_texts):
        if anchor["layoutStart"] and anchor["layoutStart"]["match"] == "exact":
            assert replay(files, order, anchor["layoutStart"], text_length(text)) == text


# --- legacy serialization ----------------------------------------------------------------

def legacy_chunks(pages, line_confidence, min_chunk_chars, max_chunk_chars):
    """A literal port of the loop in db_benchmarks/semant/db_prepare_documents.py (texts only).
    ``pages``: list of pages, each a list of regions, each a list of (text, conf)."""
    chunks = []
    for regions in pages:
        for paragraph in regions:
            if not chunks:
                chunks.append({"text": ""})
            paragraph_lines = [t for t, conf in paragraph if t and conf > line_confidence]
            while paragraph_lines:
                paragraph_text = '\n'.join(paragraph_lines)
                if len(paragraph_text) <= 10:
                    break
                if len(chunks[-1]["text"]) + len(paragraph_text) > max_chunk_chars:
                    chunks[-1]["text"] = chunks[-1]["text"] + '\n'
                    while len(chunks[-1]["text"]) < min_chunk_chars:
                        chunks[-1]["text"] = chunks[-1]["text"] + f'\n{paragraph_lines[0]}'
                        paragraph_lines = paragraph_lines[1:]
                    chunks.append({"text": ""})
                elif len(chunks[-1]["text"]) + len(paragraph_text) > min_chunk_chars:
                    chunks[-1]["text"] = f'{chunks[-1]["text"]}\n\n{paragraph_text}'
                    chunks.append({"text": ""})
                    paragraph_lines = []
                else:
                    chunks[-1]["text"] = f'{chunks[-1]["text"]}\n\n{paragraph_text}'
                    paragraph_lines = []
    if not chunks[-1]["text"]:
        chunks.pop()
    return [chunk["text"].strip() for chunk in chunks]


WORDS = ["Ročník", "XIX.", "lékařů", "českých", "imo-", "bilisace", "—", "(1880)", "𝔄𝔅", "a", " ", "  x  ", ";"]


def random_document(rng):
    pages = []
    for _ in range(rng.randint(1, 4)):
        regions = []
        for _ in range(rng.randint(1, 5)):
            regions.append([(" ".join(rng.choice(WORDS) for _ in range(rng.randint(0, 6))),
                             rng.choice([0.95, 0.9, 0.7, 0.6, 0.3])) for _ in range(rng.randint(1, 6))])
        pages.append(regions)
    return pages


@pytest.mark.parametrize("seed", range(40))
def test_serializer_reproduces_the_legacy_loop_and_round_trips(seed):
    rng = random.Random(seed)
    pages = random_document(rng)
    params = Params(0.6, rng.randint(20, 60), rng.randint(60, 120))
    regions = [[(f"r{r}", [line(f"r{r}-l{i}", t, c) for i, (t, c) in enumerate(lines)])
                for r, lines in enumerate(regions)] for regions in pages]
    try:
        expected = legacy_chunks(pages, params.line_confidence, params.min_chunk_chars, params.max_chunk_chars)
    except IndexError:
        expected = None                                             # the legacy code failed
    result = convert(regions, params)
    if expected is None:
        assert result.status == "legacy_failure" and result.chunks == []
        return
    assert result.status == "converted"
    assert texts(result) == expected
    assert all(a["layoutStart"] is None or a["layoutStart"]["match"] == "exact" for a in result.anchors)
    assert all((a["layoutStart"] is None) == (t == "") for a, t in zip(result.anchors, expected))
    assert_round_trip(result)


def test_chunks_cross_lines_regions_and_pages():
    result = convert([[para("r1", "První řádek textu", "druhý řádek"), para("r2", "Další odstavec zde")],
                      [para("r1", "Text na druhé straně pokračuje")]], Params(0.6, 400, 800))
    assert texts(result) == ["První řádek textu\ndruhý řádek\n\nDalší odstavec zde\n\nText na druhé straně pokračuje"]
    [anchor] = result.anchors
    assert anchor["layoutStart"] == {"pageId": str(PAGES[0]), "lineId": "r1-l0", "offset": 0, "match": "exact"}
    assert_round_trip(result)


def test_overflow_splits_a_paragraph_and_drops_a_short_remainder():
    lines = ["a" * 15, "b" * 15, "c" * 15, "d" * 15, "e" * 5]
    result = convert([[para("r1", "x" * 30), para("r2", *lines)]])
    # 30 + 77 > 60: "\n", then lines until 40 code points; the rest (d, e: 21) fits a new chunk
    assert texts(result) == ["x" * 30 + "\n\n" + "a" * 15, "b" * 15 + "\n" + "c" * 15 + "\n" + "d" * 15 + "\n" + "e" * 5]
    result = convert([[para("r1", "x" * 30), para("r2", "a" * 15, "b" * 8)]], Params(0.6, 40, 50))
    # the remainder "b"*8 has at most 10 code points: dropped, and absent from the page file
    assert texts(result) == ["x" * 30 + "\n\n" + "a" * 15]
    region = result.pages[PAGES[0]]["regions"][1]
    assert [l["id"] for l in region["lines"]] == ["r2-l0"]


def test_filtered_lines_are_absent_from_the_page_file():
    result = convert([[("r1", [line("keep", "Dobrý řádek textu", 0.9), line("low", "špatný řádek", 0.6),
                               line("empty", "", 0.9), line("none", None)]),
                       para("short", "krátký")]], Params(0.6, 400, 800))
    assert texts(result) == ["Dobrý řádek textu"]
    regions = result.pages[PAGES[0]]["regions"]
    assert [(r["id"], [l["id"] for l in r["lines"]]) for r in regions] == [("r1", ["keep"])]


def test_pages_empty_missing_and_unparseable():
    xml = {PAGES[0]: page_xml(PAGES[0], [para("r1", "Text první strany zde")]),
           PAGES[1]: page_xml(PAGES[1], []),                                  # no regions
           PAGES[3]: page_xml(PAGES[3], [para("r1", "Text čtvrté strany")])}  # PAGES[2] missing
    result = convert_document(DOC, PAGES[:4], xml, Params(0.6, 400, 800))
    assert result.status == "converted"
    assert texts(result) == ["Text první strany zde\n\nText čtvrté strany"]
    assert list(result.pages) == PAGES[:4]                                    # every page has a file
    assert result.pages[PAGES[1]]["regions"] == [] and result.pages[PAGES[1]]["image"] == {"width": 1378,
                                                                                         "height": 2000}
    assert result.pages[PAGES[2]]["image"] is None
    assert {w["code"] for w in result.warnings} == {"missing_page_xml"}

    xml[PAGES[2]] = b"<PcGts><broken"
    failed = convert_document(DOC, PAGES[:4], xml, Params(0.6, 400, 800))
    assert failed.status == "legacy_failure" and failed.failure == "unparseable_page_xml"
    assert failed.chunks == [] and failed.anchors == []
    assert all(p["regions"] == [] for p in failed.pages.values()) and len(failed.pages) == 4


def test_documents_the_legacy_code_failed_on():
    assert convert([[]]).failure == "no_regions"
    assert convert([[("r1", [line("l", "text bez jistoty", None)])]]).failure == "missing_conf"
    # an overflow that runs out of lines before the minimum
    assert convert([[para("r1", "y" * 35), para("r2", "z" * 30)]], Params(0.6, 70, 60)).failure \
        == "overflow_out_of_lines"


def test_edge_whitespace_hyphens_punctuation_and_non_bmp():
    result = convert([[("r1", [line("ws", "   začátek s mezerami  "), line("hy", "imo-"), line("p", "—;—"),
                               line("nb", "𝔄𝔅 text 𝔄"), line("end", "konec")])]], Params(0.6, 400, 800))
    [text] = texts(result)
    assert text == "začátek s mezerami  \nimo-\n—;—\n𝔄𝔅 text 𝔄\nkonec"              # verbatim, no dehyphenation
    assert result.anchors[0]["layoutStart"] == {"pageId": str(PAGES[0]), "lineId": "ws", "offset": 3,
                                                "match": "exact"}
    assert_round_trip(result)
    # a chunk starting after non-BMP characters: the offset counts UTF-16 units
    chunks = convert([[("r1", [line("nb", "𝔄𝔅 " + "x" * 40), line("t", "y" * 30)])]], Params(0.6, 30, 45))
    assert_round_trip(chunks)


def test_non_bmp_offset_in_utf16_units():
    xml = {PAGES[0]: page_xml(PAGES[0], [("r1", [line("nb", "𝔄𝔅  slovo dál")])])}
    result = convert_document(DOC, PAGES[:1], xml, Params(0.6, 400, 800),
                              stored=[StoredChunk("c", 0, "slovo dál")])
    # "slovo" starts at code point 4, UTF-16 unit 6; found away from the cursor, so "shifted"
    assert result.anchors[0]["layoutStart"] == {"pageId": str(PAGES[0]), "lineId": "nb", "offset": 6,
                                                "match": "exact"}
    assert result.anchors[0]["reason"] == "shifted"


def test_reading_order_is_ignored_like_pero_ocr():
    xml = page_xml(PAGES[0], [para("ra", "První podle XML"), para("rb", "Druhý podle XML")],
                   reading_order=["rb", "ra"])
    page = parse_page_xml(xml, PAGES[0])
    assert [r.id for r in page.regions] == ["ra", "rb"]


def test_parser_reports_and_drops():
    xml = page_xml(PAGES[0], [("r1", [line("dup", "jedna"), line("dup", "dva"),
                                      line("nobase", "bez baseline", baseline=None)]),
                              '<TextRegion id="outer"><TextRegion id="inner">'
                              + line("in", "vnořený") + "</TextRegion></TextRegion>"],
                   image_filename="something-else")
    page = parse_page_xml(xml, PAGES[0])
    codes = {code for code, _ in page.warnings}
    assert {"duplicate_line_id", "line_without_baseline", "nested_region", "image_filename_mismatch"} <= codes
    assert [l.id for l in page.regions[0].lines] == ["dup", "dup"]
    # like pero-ocr, the outer region also holds the nested region's lines
    assert [[l.id for l in r.lines] for r in page.regions[1:]] == [["in"], ["in"]]
    with pytest.raises(PageXmlError):
        parse_page_xml(b"<root/>", PAGES[0])
    with pytest.raises(PageXmlError):
        parse_page_xml(b"not xml", PAGES[0])


def test_chunk_starting_on_a_duplicated_line_id_has_no_anchor():
    result = convert([[("r1", [line("dup", "Text první řádky"), line("dup", "Text druhé řádky")])]],
                     Params(0.6, 400, 800))
    assert result.anchors[0]["layoutStart"] is None and result.anchors[0]["reason"] == "duplicate_line_id"


# --- geometry and page file ---------------------------------------------------------------

def test_page_file_is_versioned_with_integer_geometry_and_parameters():
    regions = [("r1", [line("a", "Ročník XIX. vyšel", baseline="100.4,158.6 124,158 255.5,157.2"),
                       line("b", "druhý řádek", heights=None, polygon="10,80 400,80 400,110 10,110")])]
    result = convert([regions], Params(0.6, 400, 800))
    data = result.pages[PAGES[0]]
    assert data["schema"] == "semant.page-layout" and data["version"] == 1
    assert data["params"] == {"lineConfidence": 0.6, "minChunkChars": 400, "maxChunkChars": 800}
    first, second = data["regions"][0]["lines"]
    assert first["baseline"] == [[100, 159], [124, 158], [256, 157]] and first["heights"] == [19, 7]
    assert second["heights"] == [20, 10]                               # estimated from the polygon
    numbers = [v for l in (first, second) for v in [*sum(l["baseline"], []), *l["heights"], *l["wordStarts"]]]
    assert all(isinstance(v, int) for v in numbers)
    json.dumps(data)


def test_heights_and_word_starts():
    assert parse_heights('{"heights": [18.6, 6.9], "category": "text"}') == (18.6, 6.9)
    assert parse_heights("heights_v2:[12.5,4]") == (12.5, 4.0)
    assert parse_heights('{"category": "text"}') is None
    assert word_starts("ab cd", [(0, 0), (50, 0)]) == [0, 30]
    assert word_starts("", [(0, 0), (50, 0)]) is None
    assert word_starts("ab", [(5, 5)]) is None
    page = parse_page_xml(page_xml(PAGES[0], [("r", [line("l", "x", heights=None)])]), PAGES[0])
    assert line_heights(page.regions[0].lines[0]) is None


# --- matching stored chunks ---------------------------------------------------------------

LONG = [[para(f"r{i}", f"Odstavec {i}: " + "slovo " * 12 + f"konec {i}.") for i in range(12)]]


def test_stored_chunks_matching_exactly():
    clean = convert(LONG, Params(0.6, 150, 250))
    stored = [StoredChunk(f"id{i}", i, c["text"]) for i, c in enumerate(clean.chunks)]
    result = convert(LONG, Params(0.6, 150, 250), stored)
    assert result.counts() == {"exact": len(stored), "approximate": 0, "none": 0}
    assert [a["chunkId"] for a in result.anchors] == [s.id for s in stored]
    assert_round_trip(result, stored)


def edit(text, ratio):
    chars = list(text)
    for i in range(1, len(chars), max(1, round(1 / ratio))):
        chars[i] = "#"
    return "".join(chars)


def test_small_edits_are_approximate_and_large_ones_have_no_anchor():
    params = Params(0.6, 150, 250)
    clean = convert(LONG, params)
    stored = [StoredChunk(f"id{i}", i, c["text"]) for i, c in enumerate(clean.chunks)]
    stored[1] = StoredChunk("id1", 1, edit(stored[1].text, 0.03))
    stored[3] = StoredChunk("id3", 3, edit(stored[3].text, 0.2))
    result = convert(LONG, params, stored)
    matches = [a["layoutStart"]["match"] if a["layoutStart"] else None for a in result.anchors]
    assert matches[1] == "approximate" and result.anchors[1]["reason"] == "edited"
    assert result.anchors[1]["layoutStart"]["lineId"] == clean.anchors[1]["layoutStart"]["lineId"]
    assert matches[3] is None and result.anchors[3]["reason"] == "too_different"
    assert all(m == "exact" for i, m in enumerate(matches) if i not in (1, 3))
    assert {"approximate_anchor", "unanchored_too_different"} <= {w["code"] for w in result.warnings}

    stricter = convert(LONG, params, stored, max_edit_ratio=0.01)
    assert stricter.anchors[1]["layoutStart"] is None


def test_a_missing_stored_chunk_does_not_misplace_the_following_ones():
    params = Params(0.6, 150, 250)
    clean = convert(LONG, params)
    stored = [StoredChunk(f"id{i}", i, c["text"]) for i, c in enumerate(clean.chunks) if i != 2]
    stored[2] = StoredChunk(stored[2].id, stored[2].order, edit(stored[2].text, 0.5))   # heavy edit after it
    result = convert(LONG, params, stored)
    by_order = {a["order"]: a["layoutStart"] for a in result.anchors}
    for order, anchor in by_order.items():
        if anchor is not None:
            reference = clean.anchors[order]["layoutStart"]
            assert (anchor["lineId"], anchor["offset"]) == (reference["lineId"], reference["offset"])
    assert by_order[3] is None and by_order[4]["match"] == "exact"


def test_repeated_text_never_gives_a_wrong_exact_anchor():
    repeated = [[para(f"r{i}", "Stejný text opakovaný na stránce znovu.") for i in range(6)]]
    params = Params(0.6, 30, 45)
    clean = convert(repeated, params)
    assert len(clean.chunks) == 6 and clean.counts()["exact"] == 6
    assert [a["layoutStart"]["lineId"] for a in clean.anchors] == [f"r{i}-l0" for i in range(6)]
    # with chunk 2 missing, the identical text of the others cannot be placed with certainty
    stored = [StoredChunk(f"id{i}", i, c["text"]) for i, c in enumerate(clean.chunks) if i != 2]
    result = convert(repeated, params, stored)
    for anchor in result.anchors:
        if anchor["layoutStart"] and anchor["layoutStart"]["match"] == "exact":
            assert anchor["layoutStart"]["lineId"] == f"r{anchor['order']}-l0"


def test_reordered_pages_give_no_wrong_anchors():
    regions = [[para("r1", f"Strana {p}: " + "text " * 20)] for p in range(4)]
    params = Params(0.6, 60, 200)
    clean = convert(regions, params)
    stored = [StoredChunk(f"id{i}", i, c["text"]) for i, c in enumerate(clean.chunks)]
    xml = {PAGES[i]: page_xml(PAGES[i], r) for i, r in enumerate(regions)}
    swapped = convert_document(DOC, [PAGES[0], PAGES[2], PAGES[1], PAGES[3]], xml, params, stored)
    for anchor, reference in zip(swapped.anchors, clean.anchors):
        if anchor["layoutStart"]:
            assert anchor["layoutStart"]["pageId"] == reference["layoutStart"]["pageId"]
    # the near-identical text of the other pages is never taken for the out-of-order one
    assert any(a["layoutStart"] is None for a in swapped.anchors)


def test_a_chunk_whose_first_paragraph_is_elsewhere_is_not_placed_mid_line():
    """Real case from the example data with file-name page order: the chunk's short first
    paragraph is on a page out of order, the rest matches; the start must not be derived
    from the rest (it would point into the middle of another line)."""
    intro = "Úvodní strana s jiným textem, " * 5
    long_text = "Hlavní odstavec s dlouhým a jedinečným textem, " + "který pokračuje dál " * 20
    regions = [[para("r0", intro)], [para("r1", "Do druhého roku.")], [para("r2", long_text)]]
    params = Params(0.6, 100, 2000)
    clean = convert(regions, params)
    assert len(clean.chunks) == 2 and clean.chunks[1]["text"].startswith("Do druhého roku.\n\n")
    stored = [StoredChunk(f"c{i}", i, c["text"]) for i, c in enumerate(clean.chunks)]
    xml = {PAGES[i]: page_xml(PAGES[i], r) for i, r in enumerate(regions)}
    swapped = convert_document(DOC, [PAGES[0], PAGES[2], PAGES[1]], xml, params, stored)
    anchor = swapped.anchors[1]["layoutStart"]
    assert anchor is None or (anchor["pageId"], anchor["lineId"], anchor["offset"]) == (str(PAGES[1]), "r1-l0", 0)


def test_empty_stored_chunk_and_matcher_warnings():
    stream = build_stream(serialize([parse_page_xml(page_xml(PAGES[0], [para("r", "Jediný odstavec textu")]),
                                                    PAGES[0])], SMALL))
    matches, warnings = match_chunks(stream, [(0, ""), (1, "nic"), (2, "nic"), (3, "nic")])
    assert matches[0].reason == "empty_chunk" and all(m.anchor is None for m in matches)
    assert warnings == ["consecutive_misses"]


# --- inputs and command line ---------------------------------------------------------------

def test_read_page_xml_from_zip_and_folder(tmp_path):
    with zipfile.ZipFile(tmp_path / f"{DOC}.page_xml.zip", "w") as zf:
        zf.writestr(f"{PAGES[0]}.xml", b"<x/>")
        zf.writestr("notes.txt", b"")
    assert read_page_xml(tmp_path, DOC) == ({PAGES[0]: b"<x/>"}, ["notes.txt"])
    other = UUID(int=7)
    (tmp_path / str(other)).mkdir()
    (tmp_path / str(other) / f"{PAGES[1]}.xml").write_bytes(b"<y/>")
    assert read_page_xml(tmp_path, other) == ({PAGES[1]: b"<y/>"}, [])
    assert read_page_xml(tmp_path, UUID(int=8)) is None


def test_read_chunks_validates(tmp_path):
    path = tmp_path / "chunks.jsonl"
    path.write_text(json.dumps({"id": "b", "document": str(DOC), "order": 1, "text": "y"}) + "\n"
                    + json.dumps({"id": "a", "documentId": str(DOC), "order": 0, "text": "x"}) + "\n")
    assert [c.id for c in read_chunks(path)[DOC]] == ["a", "b"]
    path.write_text(json.dumps({"id": "a", "document": str(DOC), "order": "0", "text": "x"}) + "\n")
    with pytest.raises(ValueError):
        read_chunks(path)


def write_document(directory, pages_regions):
    with zipfile.ZipFile(directory / f"{DOC}.page_xml.zip", "w") as zf:
        for i, regions in enumerate(pages_regions):
            zf.writestr(f"{PAGES[i]}.xml", page_xml(PAGES[i], regions))


def test_cli_writes_pages_chunks_anchors_and_report(tmp_path):
    source = tmp_path / "xml"
    source.mkdir()
    write_document(source, [[para("r1", "Text druhé strany v pořadí")], [para("r1", "Text první strany")]])
    order = tmp_path / "pages.jsonl"
    order.write_text(json.dumps({"documentId": str(DOC), "status": "exported",
                                 "pages": [{"pageId": str(PAGES[1])}, {"pageId": str(PAGES[0])}]}) + "\n")
    out = tmp_path / "out"
    assert main(["--page-xml-dir", str(source), "--page-order", str(order), "--output", str(out),
                 "--min-chunk-chars", "400", "--max-chunk-chars", "800"]) == 0
    assert sorted(p.name for p in (out / "pages" / str(DOC)).iterdir()) == sorted(f"{p}.json" for p in PAGES[:2])
    [chunk] = [json.loads(l) for l in (out / "chunks.jsonl").read_text().splitlines()]
    assert chunk["text"] == "Text první strany\n\nText druhé strany v pořadí"          # the exported order
    [anchor] = [json.loads(l) for l in (out / "anchors.jsonl").read_text().splitlines()]
    assert anchor["layoutStart"]["pageId"] == str(PAGES[1])
    report = json.loads((out / "report.json").read_text())
    assert report["params"]["minChunkChars"] == 400 and report["documents"][0]["pageOrderFrom"] == "page_order"

    assert main(["--page-xml-dir", str(source), "--output", str(out)]) == 2            # not empty
    # the command's own chunks as input; file-name order (a warning) changes the text: exit 1
    again = tmp_path / "again"
    assert main(["--page-xml-dir", str(source), "--output", str(again), "--chunks", str(out / "chunks.jsonl"),
                 "--min-chunk-chars", "400", "--max-chunk-chars", "800"]) == 1
    report = json.loads((again / "report.json").read_text())
    assert "file_name_order" in {w["code"] for w in report["documents"][0]["warnings"]}


def test_cli_refuses_invalid_arguments(tmp_path):
    assert main(["--page-xml-dir", str(tmp_path / "missing"), "--output", str(tmp_path / "o")]) == 2
    assert main(["--page-xml-dir", str(tmp_path), "--output", str(tmp_path / "o"),
                 "--min-chunk-chars", "90", "--max-chunk-chars", "50"]) == 2
