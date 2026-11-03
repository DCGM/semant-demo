"""The synthetic page fixtures of the browser tests and the development backend (#543).

They must be what the page reads (#541) accept and cover the viewer's cases: covers, blank
pages, skipped numbers, a scan without layout, a page without assets and a long document.
"""
import json
from uuid import UUID

import pytest

from tests.corpus import load_corpus
from tests.page_fixtures import GAZETTE_PAGES, write_page_fixtures


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    return write_page_fixtures(tmp_path_factory.mktemp("page_assets"), load_corpus())


def _doc(key: str) -> UUID:
    return UUID(load_corpus().documents[key]["id"])


def test_manifests_list_every_case(store):
    chronicle = store.read_manifest(_doc("chronicle"))
    assert [p.label for p in chronicle.pages] == ["[1]", "1", "2", "3", "6", "7", "[8]"]
    assert [(p.image, p.layout, p.thumbnail) for p in chronicle.pages][4:6] == [(True, False, True),
                                                                               (False, False, False)]
    assert len(store.read_manifest(_doc("gazette")).pages) == GAZETTE_PAGES
    assert store.read_manifest(_doc("letters")) is None


def test_chunk_start_pages_are_in_the_manifests(store):
    for key in ("chronicle", "gazette"):
        pages = {str(p.pageId): p.order for p in store.read_manifest(_doc(key)).pages}
        for chunk in load_corpus().documents[key]["chunks"]:
            assert pages[chunk["start_page_id"]] == chunk["from_page"]


def test_every_listed_asset_exists_and_layout_lines_lie_on_the_scan(store):
    for key in ("chronicle", "gazette"):
        manifest = store.read_manifest(_doc(key))
        for page in manifest.pages:
            for kind in ("image", "layout", "thumbnail"):
                assert (store.asset_file(manifest.documentId, page.pageId, kind) is not None) == getattr(page, kind)
            if not page.layout:
                continue
            layout = json.loads(store.asset_file(manifest.documentId, page.pageId, "layout").read_bytes())
            assert (layout["schema"], layout["version"], layout["pageId"]) == ("semant.page-layout", 1, str(page.pageId))
            ids = [line["id"] for region in layout["regions"] for line in region["lines"]]
            assert len(ids) == len(set(ids))
            for region in layout["regions"]:
                for line in region["lines"]:
                    assert all(0 <= x < page.width and 0 <= y < page.height for x, y in line["baseline"])
                    assert line["wordStarts"] == sorted(line["wordStarts"])


def test_the_development_backend_writes_them_once_per_corpus_and_generator(tmp_path, monkeypatch):
    from tests import local_dev, page_fixtures

    calls = []
    monkeypatch.setattr(page_fixtures, "write_page_fixtures", lambda root, corpus: calls.append(root))
    root = tmp_path / "page_assets"
    assert local_dev.write_page_assets(root) == root
    local_dev.write_page_assets(root)
    assert calls == [root]
    (root / "fixtures.sha256").write_text("an older generator")
    local_dev.write_page_assets(root)
    assert len(calls) == 2


def test_fixture_anchors_replay_to_their_chunks_as_the_import_would_store_them(store):
    """The anchors of the browser tests (#544) are what the import's matcher accepts: an
    exact one replays to the chunk text, an approximate one within the 5 % edit distance."""
    from semant_demo.maintenance.page_layout.anchors import MAX_EDIT_RATIO, replay
    from semant_demo.maintenance.page_layout.edit_distance import levenshtein
    from tests.page_fixtures import fixture_anchors

    corpus = load_corpus()
    anchors = fixture_anchors(corpus)
    assert {corpus.chunks[k]["document"] for k in anchors} == {"chronicle", "gazette"}
    matches = {}
    for key, anchor in anchors.items():
        chunk = corpus.chunks[key]
        manifest = store.read_manifest(_doc(chunk["document"]))
        order = [str(p.pageId) for p in manifest.pages]
        pages = {str(p.pageId): json.loads(store.asset_file(manifest.documentId, p.pageId, "layout").read_bytes())
                 for p in manifest.pages if p.layout}
        assert order.index(anchor["pageId"]) == chunk["from_page"]
        replayed = replay(pages, order, anchor, len(chunk["text"].encode("utf-16-le")) // 2)
        if anchor["match"] == "exact":
            assert replayed == chunk["text"]
        else:
            assert replayed != chunk["text"]
            # The chunk against the text from the anchor, ending where it aligns best.
            longer = replay(pages, order, anchor, len(chunk["text"]) + 10) or ""
            distance = min(levenshtein(chunk["text"], longer[:n]) for n in range(len(chunk["text"]), len(longer) + 1))
            assert 0 < distance <= MAX_EDIT_RATIO * len(chunk["text"])
        matches[key] = anchor["match"]
    # One chunk continues onto the next page.
    assert corpus.chunks["chronicle_2"]["to_page"] == corpus.chunks["chronicle_2"]["from_page"] + 1
    assert sorted(matches.values()) == ["approximate"] * 3 + ["exact"] * 2
