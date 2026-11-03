"""The existing-corpus page import (#542) with synthetic PAGE XML, JPEGs and fake chunk stores.

``assets`` writes page files, scans, thumbnails, the manifest and an anchor plan, page by
page and repeatably; ``anchors`` writes only the anchors that differ from the stored ones and
never touches chunk text. Sources that are missing or corrupt are reported, not fatal.
"""
import asyncio
import io
import json
import zipfile
from collections import Counter
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from PIL import Image

from semant_demo.adapters.filesystem.page_assets import PageAssetStore
from semant_demo.adapters.weaviate.layout_anchors import AnchoredChunk
from semant_demo.features.documents.positions import text_length
from semant_demo.maintenance.page_import import run
from semant_demo.maintenance.page_import.__main__ import _main
from semant_demo.maintenance.page_import.assets import plan_path
from semant_demo.maintenance.page_layout.anchors import replay
from semant_demo.maintenance.page_layout.convert import convert_document
from tests.test_page_layout import SMALL, page_xml, para

DOC = UUID("5e3a0000-0000-4000-8000-00000000d542")
PAGES = [UUID(int=0x542_000 + i) for i in range(3)]
REGIONS = [
    [para("r1", "Kronika obce Lhota, díl první.", "Roku 1848 přijel hejtman."), para("r2", "Ubytoval se u jelena.")],
    [para("r1", "Druhá strana: 𝔄𝔅 písmo a další text."), para("r2", "Konec kapitoly první, strana dvě.")],
    [],
]


def jpeg(width=120, height=200, color=(200, 190, 170)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), color).save(out, "JPEG")
    return out.getvalue()


class Sources:
    """A document's sources on disk and its export line (``page_order``, #571)."""

    def __init__(self, root: Path, xml_pages=(0, 1), images=(0, 1)):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.zip = root / f"{DOC}.page_xml.zip"
        with zipfile.ZipFile(self.zip, "w") as zf:
            for i in xml_pages:
                zf.writestr(f"{PAGES[i]}.xml", page_xml(PAGES[i], REGIONS[i]))
        self.images = {}
        for i in range(3):
            path = root / "images" / f"{PAGES[i]}.jpg"
            self.images[i] = path
            if i in images:
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(jpeg(width=120 + i))
        self.export = {"documentId": str(DOC), "status": "exported", "library": "nlk", "pages": [
            {"pageId": str(PAGES[i]), "order": i, "label": f"[{i + 1}]", "pageType": "NormalPage",
             "imagePath": str(self.images[i]), "pageXmlPath": str(self.zip), "hasImage": True, "hasPageXml": True}
            for i in range(3)]}


def stored_chunks(edit=None) -> list[AnchoredChunk]:
    """The document's chunks as the legacy chunker made them, with stored ids."""
    xml = {PAGES[i]: page_xml(PAGES[i], REGIONS[i]) for i in range(2)}
    result = convert_document(DOC, PAGES, xml, SMALL)
    chunks = [AnchoredChunk(UUID(int=0x5420 + c["order"]), c["order"], c["text"], 0, 1, str(PAGES[0]), None)
              for c in result.chunks]
    return edit(chunks) if edit else chunks


async def assets(store, sources, chunks, tmp_path, name="assets.json"):
    async def read(document_id):
        assert document_id == DOC
        return chunks
    summary = await run.run_assets(store, [sources.export], read, SMALL, 0.05, tmp_path / name, progress=lambda m: None)
    [line] = [json.loads(l) for l in (tmp_path / f"{name}.documents.jsonl").read_text().splitlines()]
    return summary, line


def page_files(store) -> dict[str, dict]:
    return {str(p): json.loads(store.asset_path(DOC, p, "layout").read_bytes()) for p in PAGES}


def mtimes(store) -> dict[str, int]:
    return {p.name: p.stat().st_mtime_ns for p in store.document_dir(DOC).iterdir()}


# --- assets ------------------------------------------------------------------------------

async def test_import_writes_pages_scans_thumbnails_manifest_and_plan(tmp_path):
    store, sources, chunks = PageAssetStore(tmp_path / "assets"), Sources(tmp_path / "src", images=(0,)), stored_chunks()

    summary, line = await assets(store, sources, chunks, tmp_path)

    assert run.assets_exit_code(summary) == 0 and line["status"] == "imported"
    assert line["assets"] == {"image_copied": 1, "image_missing": 2, "layout_written": 3, "thumbnail_made": 1}
    assert line["anchors"] == {"exact": len(chunks), "approximate": 0, "none": 0, "reasons": {}}
    assert {w["code"] for w in line["warnings"]} == {"missing_image", "start_page_id_differs"}
    assert store.asset_file(DOC, PAGES[0], "image").read_bytes() == sources.images[0].read_bytes()  # byte for byte
    with Image.open(store.asset_file(DOC, PAGES[0], "thumbnail")) as thumbnail:
        assert thumbnail.format == "JPEG" and thumbnail.width <= 256
    manifest = store.read_manifest(DOC)
    assert [(p.order, p.label, p.image, p.layout, p.thumbnail) for p in manifest.pages] == [
        (0, "[1]", True, True, True), (1, "[2]", False, True, False), (2, "[3]", False, True, False)]
    assert (manifest.pages[0].width, manifest.pages[0].height) == (120, 200)
    assert manifest.params == SMALL.as_json() and manifest.library == "nlk"
    assert page_files(store)[str(PAGES[2])]["regions"] == []  # every page gets a file


async def test_verified_anchors_replay_the_stored_text_across_pages_and_non_bmp(tmp_path):
    store, chunks = PageAssetStore(tmp_path / "assets"), stored_chunks()
    await assets(store, Sources(tmp_path / "src"), chunks, tmp_path)
    plan = [json.loads(l) for l in plan_path(store, DOC).read_text().splitlines()]
    files, order = page_files(store), [str(p) for p in PAGES]

    assert [p["chunkId"] for p in plan] == [str(c.id) for c in chunks]
    assert any("𝔄" in c.text for c in chunks) and {p["layoutStart"]["pageId"] for p in plan} >= {str(PAGES[1])}
    for line, chunk in zip(plan, chunks):
        assert replay(files, order, line["layoutStart"], text_length(chunk.text)) == chunk.text


async def test_a_repeated_run_rewrites_nothing(tmp_path):
    store, sources, chunks = PageAssetStore(tmp_path / "assets"), Sources(tmp_path / "src"), stored_chunks()
    await assets(store, sources, chunks, tmp_path)
    before = mtimes(store)

    _, line = await assets(store, sources, chunks, tmp_path)

    assert line["assets"] == {"image_kept": 2, "image_missing": 1, "layout_unchanged": 3, "thumbnail_kept": 2}
    assert mtimes(store) == before


async def test_an_interrupted_run_is_completed_by_running_again(tmp_path, monkeypatch):
    store, sources, chunks = PageAssetStore(tmp_path / "assets"), Sources(tmp_path / "src"), stored_chunks()
    real_write = PageAssetStore.write_asset

    def crash_on_second_scan(self, document_id, page_id, kind, data):
        if kind == "image" and page_id == PAGES[1]:
            raise KeyboardInterrupt
        return real_write(self, document_id, page_id, kind, data)
    monkeypatch.setattr(PageAssetStore, "write_asset", crash_on_second_scan)
    with pytest.raises(KeyboardInterrupt):
        await assets(store, sources, chunks, tmp_path)
    assert store.asset_file(DOC, PAGES[0], "image") is not None and store.read_manifest(DOC) is None
    assert not any(p.name.endswith(".tmp") for p in store.document_dir(DOC).iterdir())
    monkeypatch.setattr(PageAssetStore, "write_asset", real_write)
    # A stored scan of another size (an older or damaged copy) is copied again.
    store.asset_path(DOC, PAGES[0], "image").write_bytes(b"\xff\xd8 truncated")

    _, line = await assets(store, sources, chunks, tmp_path)

    assert line["assets"]["image_copied"] == 2 and line["status"] == "imported"
    assert store.asset_file(DOC, PAGES[0], "image").read_bytes() == sources.images[0].read_bytes()
    assert [p.image for p in store.read_manifest(DOC).pages] == [True, True, False]


async def test_corrupt_and_missing_scans_are_reported(tmp_path):
    sources = Sources(tmp_path / "src")
    sources.images[1].write_bytes(b"GIF89a not a jpeg")
    store = PageAssetStore(tmp_path / "assets")

    _, line = await assets(store, sources, stored_chunks(), tmp_path)

    assert line["status"] == "imported"
    assert {"corrupt_image", "missing_image"} <= {w["code"] for w in line["warnings"]}
    assert [p.image for p in store.read_manifest(DOC).pages] == [True, False, False]
    assert store.asset_file(DOC, PAGES[1], "image") is None


async def test_pages_without_a_page_xml_path_get_empty_layouts(tmp_path):
    sources = Sources(tmp_path / "src")
    for page in sources.export["pages"]:
        page["pageXmlPath"] = None
    store = PageAssetStore(tmp_path / "assets")

    _, line = await assets(store, sources, stored_chunks(), tmp_path)

    assert line["status"] == "no_regions" and line["anchors"]["exact"] == 0 and line["anchors"]["reasons"]
    assert all(f["regions"] == [] for f in page_files(store).values())


@pytest.mark.parametrize("outage", ["hidden", "corrupt"])
async def test_an_unreadable_page_xml_archive_keeps_the_earlier_import(tmp_path, outage):
    """A mount outage or a damaged archive must not replace valid layouts and anchor plans
    with empty ones (which a later ``anchors --write`` would turn into cleared anchors)."""
    store, sources, chunks = PageAssetStore(tmp_path / "assets"), Sources(tmp_path / "src"), stored_chunks()
    await assets(store, sources, chunks, tmp_path)
    plan, files, manifest = plan_path(store, DOC).read_bytes(), page_files(store), store.read_manifest(DOC)
    before = mtimes(store)
    original = sources.zip.read_bytes()
    if outage == "hidden":
        sources.zip.rename(sources.zip.with_suffix(".away"))
    else:
        sources.zip.write_bytes(original[: len(original) // 2])

    summary, line = await assets(store, sources, chunks, tmp_path, "outage.json")

    assert line["status"] == "page_xml_unavailable" and run.assets_exit_code(summary) == 1
    code = "missing_page_xml_zip" if outage == "hidden" else "unreadable_page_xml_zip"
    assert code in {w["code"] for w in line["warnings"]}
    assert mtimes(store) == before
    assert plan_path(store, DOC).read_bytes() == plan and page_files(store) == files
    assert store.read_manifest(DOC) == manifest

    if outage == "hidden":
        sources.zip.with_suffix(".away").rename(sources.zip)
    else:
        sources.zip.write_bytes(original)
    summary, line = await assets(store, sources, chunks, tmp_path, "restored.json")

    assert line["status"] == "imported" and run.assets_exit_code(summary) == 0
    assert line["anchors"]["exact"] == len(chunks) and plan_path(store, DOC).read_bytes() == plan


async def test_edited_and_unusable_stored_chunks(tmp_path):
    store, sources = PageAssetStore(tmp_path / "assets"), Sources(tmp_path / "src")

    def edited(chunks):
        first = chunks[0]
        return [AnchoredChunk(first.id, 0, first.text.replace("Lhota", "Lhotа"), 0, 1, first.start_page_id, None),
                *chunks[1:]]
    _, line = await assets(store, sources, stored_chunks(edited), tmp_path)
    assert line["anchors"]["approximate"] == 1 and line["status"] == "imported"

    def duplicated(chunks):
        return [*chunks, AnchoredChunk(uuid4(), chunks[-1].order, "copy", 1, 1, None, None)]
    _, line = await assets(store, sources, stored_chunks(duplicated), tmp_path, "dup.json")
    assert line["status"] == "no_anchors" and {w["code"] for w in line["warnings"]} >= {"duplicate_chunk_order"}
    assert plan_path(store, DOC).read_text() == ""


async def test_page_metadata_differences_are_reported_not_changed(tmp_path):
    store, sources = PageAssetStore(tmp_path / "assets"), Sources(tmp_path / "src")
    chunks = stored_chunks()  # every chunk says start page 0, pages 0..1

    _, line = await assets(store, sources, chunks, tmp_path)

    plan = [json.loads(l) for l in plan_path(store, DOC).read_text().splitlines()]
    on_second = [p for p in plan if p["layoutStart"]["pageId"] == str(PAGES[1])]
    assert on_second and line["pageMetadata"]["start_page_id_differs"] == len(on_second)
    assert line["pageMetadata"]["from_page_differs"] == len(on_second)
    assert line["pageMetadata"]["checked"] == len(chunks)
    assert "outside_page_range" not in line["pageMetadata"]


async def test_documents_not_exported_are_reported(tmp_path):
    store = PageAssetStore(tmp_path / "assets")
    exports = [{"documentId": str(DOC), "status": "ambiguous", "pages": []}]

    summary = await run.run_assets(store, exports, None, SMALL, 0.05, tmp_path / "r.json", progress=lambda m: None)

    assert summary["statuses"] == {"not_exported": 1} and run.assets_exit_code(summary) == 1
    assert store.documents() == []


# --- anchors -----------------------------------------------------------------------------

class FakeAnchors:
    def __init__(self, chunks: list[AnchoredChunk], fail=()):
        self.chunks = {c.id: c for c in chunks}
        self.writes: list[tuple[UUID, dict | None]] = []
        self.fail = set(fail)

    async def read_chunks(self, document_id):
        return list(self.chunks.values())

    async def write(self, chunk_id, value):
        if chunk_id in self.fail:
            raise TimeoutError
        self.writes.append((chunk_id, value))
        c = self.chunks[chunk_id]
        self.chunks[chunk_id] = AnchoredChunk(c.id, c.order, c.text, c.from_page, c.to_page, c.start_page_id, value)

    async def read_back(self, ids):
        return {i: self.chunks[i].layout_start for i in ids if i in self.chunks}


async def anchors_run(store, fake, tmp_path, write, name="anchors.json"):
    summary = await run.run_anchors(store, store.documents(), fake, write, 4, tmp_path / name, "test",
                                    progress=lambda m: None)
    [line] = [json.loads(l) for l in (tmp_path / f"{name}.documents.jsonl").read_text().splitlines()]
    return summary, line


@pytest.fixture
async def imported(tmp_path):
    store, chunks = PageAssetStore(tmp_path / "assets"), stored_chunks()
    await assets(store, Sources(tmp_path / "src"), chunks, tmp_path)
    return store, chunks


async def test_check_then_write_then_nothing_left(imported, tmp_path):
    store, chunks = imported
    fake = FakeAnchors(chunks)

    check, line = await anchors_run(store, fake, tmp_path, write=False, name="check.json")
    assert line["counts"] == {"set": len(chunks)} and fake.writes == [] and run.anchors_exit_code(check) == 1

    written, line = await anchors_run(store, fake, tmp_path, write=True, name="write.json")
    assert line["counts"] == {"set": len(chunks), "write_failed": 0, "written": len(chunks)}
    assert run.anchors_exit_code(written) == 0
    assert [c.text for c in fake.chunks.values()] == [c.text for c in chunks]  # text untouched

    again, line = await anchors_run(store, fake, tmp_path, write=True, name="again.json")
    assert line["counts"] == {"unchanged": len(chunks)} and len(fake.writes) == len(chunks)
    assert run.anchors_exit_code(again) == 0


async def test_changed_text_unverified_and_unplanned_chunks(imported, tmp_path):
    store, chunks = imported
    stale = {"pageId": str(PAGES[0]), "lineId": "r9-l9", "offset": 0, "match": "exact"}
    first, second, *rest = chunks
    extra = AnchoredChunk(uuid4(), 99, "added later", 1, 1, None, stale)
    fake = FakeAnchors([AnchoredChunk(first.id, 0, first.text + " (edited)", 0, 1, None, None), second, *rest, extra])
    plan = [json.loads(l) for l in plan_path(store, DOC).read_text().splitlines()]
    plan[1]["layoutStart"] = None  # this chunk is not verified any more ...
    fake.chunks[second.id] = AnchoredChunk(second.id, 1, second.text, 0, 1, None, stale)  # ... but has an anchor
    plan_path(store, DOC).write_text("".join(json.dumps(p) + "\n" for p in plan))

    summary, line = await anchors_run(store, fake, tmp_path, write=True)

    assert line["counts"]["text_changed"] == 1 and line["counts"]["clear"] == 1
    assert line["counts"]["unplanned_anchor"] == 1 and line["counts"]["set"] == len(chunks) - 2
    assert fake.chunks[second.id].layout_start is None and fake.chunks[extra.id].layout_start == stale
    assert first.id not in {w[0] for w in fake.writes}
    assert run.anchors_exit_code(summary) == 1  # the edited chunk needs a new assets run


async def test_a_plan_with_other_parameters_is_refused(imported, tmp_path):
    store, chunks = imported
    plan = [json.loads(l) for l in plan_path(store, DOC).read_text().splitlines()]
    plan_path(store, DOC).write_text("".join(json.dumps({**p, "params": {**p["params"], "minChunkChars": 1}}) + "\n"
                                             for p in plan))
    fake = FakeAnchors(chunks)

    summary, line = await anchors_run(store, fake, tmp_path, write=True)

    assert line["status"] == "params_mismatch" and fake.writes == [] and run.anchors_exit_code(summary) == 1


async def test_failed_writes_are_reported_and_retried_by_running_again(imported, tmp_path):
    store, chunks = imported
    fake = FakeAnchors(chunks, fail={chunks[0].id})

    summary, line = await anchors_run(store, fake, tmp_path, write=True)
    assert line["counts"]["write_failed"] == 1 and run.anchors_exit_code(summary) == 1

    fake.fail.clear()
    summary, line = await anchors_run(store, fake, tmp_path, write=True, name="retry.json")
    assert line["counts"] == {"set": 1, "unchanged": len(chunks) - 1, "write_failed": 0, "written": 1}
    assert run.anchors_exit_code(summary) == 0


def test_writing_needs_the_confirmed_endpoint(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WEAVIATE_HOST", "weaviate.invalid")
    monkeypatch.setenv("WEAVIATE_REST_PORT", "8080")

    code = asyncio.run(_main(["anchors", "--write", str(tmp_path / "w.json"), "--assets-dir", str(tmp_path),
                              "--confirm-endpoint", "localhost:8080"]))

    assert code == 2 and "Refusing to write" in capsys.readouterr().err
    assert not (tmp_path / "w.json").exists()


def test_report_totals_count_every_document(tmp_path):
    report = run.Report(tmp_path / "r.json", {"step": "x"})
    report.add({"status": "imported"}, {"pages": 2})
    report.add({"status": "imported"}, {"pages": 3})

    summary = json.loads((tmp_path / "r.json").read_text())
    assert (summary["complete"], summary["totals"], summary["statuses"]) == (False, {"pages": 5}, {"imported": 2})
    assert Counter(json.loads(l)["status"] for l in (tmp_path / "r.json.documents.jsonl").read_text().splitlines()) \
        == {"imported": 2}
