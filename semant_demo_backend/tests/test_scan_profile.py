"""Import profile v1 of the stored page scans (#594): the size rule and the layout scaling."""
import io

import pytest
from PIL import Image

from semant_demo.maintenance.page_import import scan_profile as sp


def layout(heights, size=(1000, 2000)):
    return {"schema": "semant.page-layout", "version": 1, "pageId": "p", "params": {},
            "image": {"width": size[0], "height": size[1]} if size else None,
            "regions": [{"id": "r1", "lines": [{"id": f"l{i}", "text": "ab cd", "baseline": [[10, 100], [410, 100]],
                                                "heights": h, "wordStarts": [0, 240]}
                                               for i, h in enumerate(heights)]}]}


def test_line_heights_ignore_missing_and_invalid_heights():
    page = layout([[10, 5], None, [0, 0], [-1, 9], [3.5, 2], [True, 1], [4], [7, 0]])
    assert sp.line_heights(page) == [15, 7]
    assert sp.line_heights({"regions": []}) == []


def test_percentile_interpolates_between_ranks():
    assert sp.percentile([]) is None
    assert sp.percentile([30]) == 30
    assert sp.percentile(range(10, 101, 10)) == pytest.approx(19)  # numpy.percentile(..., 10)
    assert sp.percentile([50, 20, 40, 30, 10, 60, 70, 80, 90, 100, 110]) == pytest.approx(20)


@pytest.mark.parametrize("height, expected", [
    (None, 1.0), (12, 1.0), (19.9, 1.0),  # below 20 px: original size
    (20, 20 / 18), (24.2, 24.2 / 18), (36, 2.0), (54, 3.0),
    (90, 3.0),  # at most 3 times smaller
])
def test_reduction_threshold_target_and_cap(height, expected):
    assert sp.reduction(height) == pytest.approx(expected)


def test_output_size_rounds_keeps_ratio_and_never_enlarges():
    assert sp.output_size(1378, 2000, 1.0) == (1378, 2000)
    assert sp.output_size(1378, 2000, 26 / 18) == (954, 1385)
    assert sp.output_size(1000, 2000, 3.0) == (334, 667)  # ceil: not more than 3 times smaller
    assert sp.output_size(1, 1, 3.0) == (1, 1)
    assert sp.output_size(100, 100, 0.5) == (100, 100)


def test_line_height_is_converted_when_page_xml_names_another_size():
    page = layout([[30, 10]] * 3, size=(2000, 4000))
    assert sp.source_line_height(page, (1000, 2000)) == pytest.approx(20)
    assert sp.source_line_height(page, (2000, 4000)) == pytest.approx(40)
    assert sp.source_line_height(layout([None]), (1000, 2000)) is None


def test_scaled_layout_geometry_matches_the_output_size():
    page = layout([[19, 7], None])
    page["regions"][0]["lines"][0]["baseline"] = [[-4, 100], [410, 100], [1003, 1999]]

    scaled = sp.scale_layout(page, (500, 667))

    assert scaled["image"] == {"width": 500, "height": 667}
    first, second = scaled["regions"][0]["lines"]
    assert first["baseline"] == [[0, 33], [205, 33], [500, 667]]  # rounded, clamped to the image
    assert first["heights"] == [6, 2] and second["heights"] is None  # by the vertical scale
    # Word starts follow the change of the baseline's length (here about half).
    assert second["baseline"] == [[5, 33], [205, 33]] and second["wordStarts"] == [0, 120]
    # Ids, text and order are unchanged; the input is not modified.
    assert [(r["id"], [(l["id"], l["text"]) for l in r["lines"]]) for r in scaled["regions"]] \
        == [(r["id"], [(l["id"], l["text"]) for l in r["lines"]]) for r in page["regions"]]
    assert page["image"] == {"width": 1000, "height": 2000} and page["regions"][0]["lines"][0]["heights"] == [19, 7]


def test_layout_of_the_same_size_or_without_image_is_unchanged():
    page = layout([[19, 7]])
    assert sp.scale_layout(page, (1000, 2000)) is page
    empty = layout([], size=None)
    assert sp.scale_layout(empty, (10, 10)) is empty


@pytest.mark.parametrize("mode", ["RGB", "L", "CMYK"])
def test_derived_scan_is_a_quality_85_jpeg_of_the_requested_size(mode):
    out = io.BytesIO()
    Image.new(mode, (300, 200), 128 if mode == "L" else None).save(out, "JPEG", quality=98)

    derived = sp.derive_scan(out.getvalue(), (150, 100))

    with Image.open(io.BytesIO(derived.data)) as image:
        assert image.format == "JPEG" and image.size == (150, 100) == derived.size
        assert image.mode == ("L" if mode == "L" else "RGB")
    same = sp.derive_scan(out.getvalue(), (300, 200))
    assert same.size == (300, 200)
