"""Page assets (#541): the filesystem store, the page reads and their HTTP contract.

The store derives every path from UUIDs and never serves a file outside its root. The
reads are public, check that the document exists before touching any file, and give a
text-only document (no manifest) an explicit ``available: false``.
"""
import json
import os
from uuid import UUID, uuid4

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from semant_demo.adapters.filesystem.page_assets import (
    InvalidManifest, ManifestPage, PageAssetStore, PageManifest)
from semant_demo.adapters.weaviate.documents import chunk_properties
from semant_demo.core.errors import InvalidRequestError, NotFoundError
from semant_demo.features.documents import pages
from semant_demo.features.documents.schemas import DocumentChunk, LayoutStart
from semant_demo.main import create_app
from semant_demo.routes.dependencies import get_documents
from tests.app_support import make_test_config, offline_weaviate

DOC = UUID("5e3a0000-0000-4000-8000-00000000d541")
TEXT_ONLY = UUID("5e3a0000-0000-4000-8000-00000000d542")
PAGE_1, PAGE_2, PAGE_3 = (UUID(f"5e3a0000-0000-4000-8000-0000000d2f0{i}") for i in (1, 2, 3))
JPEG = b"\xff\xd8\xff\xe0 synthetic jpeg \xff\xd9"
LAYOUT = {"schema": "semant.page-layout", "version": 1, "pageId": str(PAGE_1), "regions": []}
ANCHOR = {"pageId": str(PAGE_2), "lineId": "r001-l002", "offset": 3, "match": "exact"}


def _manifest(document_id=DOC) -> PageManifest:
    return PageManifest(documentId=document_id, library="nlk",
                        params={"lineConfidence": 0.6, "minChunkChars": 768, "maxChunkChars": 1152},
                        pages=[ManifestPage(pageId=PAGE_1, order=0, label="[1]", pageType="FrontCover",
                                            width=1378, height=2000, image=True, layout=True, thumbnail=True),
                               ManifestPage(pageId=PAGE_2, order=1, label="2", pageType="NormalPage", layout=True),
                               ManifestPage(pageId=PAGE_3, order=2, label="3", pageType="Blank")])


@pytest.fixture
def store(tmp_path) -> PageAssetStore:
    store = PageAssetStore(tmp_path / "assets")
    store.write_manifest(_manifest())
    store.write_asset(DOC, PAGE_1, "image", JPEG)
    store.write_asset(DOC, PAGE_1, "thumbnail", JPEG[:8])
    store.write_asset(DOC, PAGE_1, "layout", json.dumps(LAYOUT).encode())
    store.write_asset(DOC, PAGE_2, "layout", json.dumps({**LAYOUT, "pageId": str(PAGE_2)}).encode())
    return store


# --- store -------------------------------------------------------------------------------

def test_paths_are_derived_from_ids_only(tmp_path):
    store = PageAssetStore(tmp_path)

    assert store.manifest_path(DOC) == tmp_path / "5e" / str(DOC) / "manifest.json"
    assert store.asset_path(DOC, PAGE_1, "image") == tmp_path / "5e" / str(DOC) / f"{PAGE_1}.jpg"
    assert store.asset_path(DOC, PAGE_1, "layout").name == f"{PAGE_1}.json"
    assert store.asset_path(DOC, PAGE_1, "thumbnail").name == f"{PAGE_1}.thumb.jpg"
    with pytest.raises(ValueError):
        store.asset_path(DOC, "../../etc/passwd", "image")  # type: ignore[arg-type]


def test_manifest_and_assets_round_trip(store):
    assert store.read_manifest(DOC) == _manifest()
    assert store.asset_file(DOC, PAGE_1, "image").read_bytes() == JPEG
    assert store.asset_file(DOC, PAGE_3, "image") is None
    assert store.read_manifest(TEXT_ONLY) is None
    # The manifest file uses the documented key "schema".
    assert json.loads(store.manifest_path(DOC).read_text())["schema"] == "semant.page-manifest"
    assert [p.name for p in store.document_dir(DOC).iterdir() if p.name.endswith(".tmp")] == []


def test_a_store_without_root_has_no_pages():
    store = PageAssetStore(None)

    assert not store.enabled
    assert store.read_manifest(DOC) is None
    assert store.asset_file(DOC, PAGE_1, "image") is None


def test_files_reached_through_a_link_out_of_the_root_are_absent(store, tmp_path):
    outside = tmp_path / "secret.jpg"
    outside.write_bytes(b"secret")
    store.asset_path(DOC, PAGE_3, "image").symlink_to(outside)
    os.mkdir(store.asset_path(DOC, PAGE_2, "image"))  # a directory, not a file

    assert store.asset_file(DOC, PAGE_3, "image") is None
    assert store.asset_file(DOC, PAGE_2, "image") is None


@pytest.mark.parametrize("content", [
    b"not json",
    json.dumps({"schema": "semant.page-manifest", "version": 2, "documentId": str(DOC), "pages": []}).encode(),
    json.dumps({"schema": "semant.page-manifest", "version": 1, "documentId": str(DOC),
                "pages": [{"pageId": str(PAGE_1), "order": 0}, {"pageId": str(PAGE_1), "order": 1}]}).encode(),
    json.dumps({"schema": "semant.page-manifest", "version": 1, "documentId": str(DOC),
                "pages": [{"pageId": str(PAGE_1), "order": 1}]}).encode(),
    json.dumps({"schema": "semant.page-manifest", "version": 1, "documentId": str(TEXT_ONLY), "pages": []}).encode(),
])
def test_invalid_manifests_are_refused(store, content):
    store.manifest_path(DOC).write_bytes(content)

    with pytest.raises(InvalidManifest):
        store.read_manifest(DOC)


# --- service -----------------------------------------------------------------------------

class FakeDocuments:
    def __init__(self, chunks=()):
        self.chunks = list(chunks)
        self.calls: list[tuple] = []

    async def exists(self, document_id):
        self.calls.append(("exists", document_id))
        return document_id in (DOC, TEXT_ONLY)

    async def read_chunks_covering_page(self, document_id, page, limit):
        self.calls.append(("page", document_id, page, limit))
        return [c for c in self.chunks if c.from_page <= page <= c.to_page][:limit]


class RecordingStore(PageAssetStore):
    def __init__(self, inner: PageAssetStore):
        super().__init__(inner.root)
        self.touched = False

    def read_manifest(self, document_id):
        self.touched = True
        return super().read_manifest(document_id)

    def asset_file(self, document_id, page_id, kind):
        self.touched = True
        return super().asset_file(document_id, page_id, kind)


def _chunk(order, from_page, to_page, anchor=None) -> DocumentChunk:
    return DocumentChunk(id=uuid4(), text=f"chunk {order}", start_page_id=PAGE_1, from_page=from_page,
                         to_page=to_page, document=DOC, order=order, layoutStart=anchor)


async def test_manifest_lists_every_page_with_urls_of_available_assets(store):
    result = await pages.read_pages(FakeDocuments(), store, str(DOC))

    assert result.available
    first, second, blank = result.pages
    assert (first.order, first.label, first.page_type, first.width, first.height) == (0, "[1]", "FrontCover", 1378, 2000)
    assert first.image_url == f"/api/documents/{DOC}/pages/{PAGE_1}/image"
    assert first.thumbnail_url == f"/api/documents/{DOC}/pages/{PAGE_1}/thumbnail"
    assert (second.image_url, second.layout_url) == (None, f"/api/documents/{DOC}/pages/{PAGE_2}/layout")
    assert (blank.page_id, blank.image_url, blank.layout_url, blank.thumbnail_url) == (PAGE_3, None, None, None)


async def test_a_text_only_document_has_no_pages(store):
    result = await pages.read_pages(FakeDocuments(), store, TEXT_ONLY)

    assert (result.available, result.pages) == (False, [])


async def test_an_unreadable_manifest_falls_back_to_text_only(store, caplog):
    store.manifest_path(DOC).write_text("{")

    result = await pages.read_pages(FakeDocuments(), store, DOC)

    assert (result.available, result.pages) == (False, [])
    assert "Unreadable page manifest" in caplog.text


@pytest.mark.parametrize("document_id", [str(uuid4()), "not-a-uuid", "../5e"])
async def test_unknown_documents_touch_no_files(store, document_id):
    recording = RecordingStore(store)

    for read in (pages.read_pages(FakeDocuments(), recording, document_id),
                 pages.read_page_asset(FakeDocuments(), recording, document_id, PAGE_1, "image")):
        with pytest.raises(NotFoundError):
            await read
    assert not recording.touched


@pytest.mark.parametrize("page_id, kind", [(PAGE_2, "image"), (PAGE_3, "layout"), ("not-a-uuid", "image"),
                                           (uuid4(), "thumbnail")])
async def test_absent_assets_are_not_found(store, page_id, kind):
    with pytest.raises(NotFoundError):
        await pages.read_page_asset(FakeDocuments(), store, DOC, page_id, kind)


async def test_page_chunks_are_the_chunks_covering_the_page_and_bounded():
    chunks = [_chunk(0, 0, 1), _chunk(1, 1, 1, LayoutStart(**ANCHOR)), _chunk(2, 1, 3), _chunk(3, 3, 3)]
    documents = FakeDocuments(chunks)

    result = await pages.read_page_chunks(documents, DOC, 1, 2)

    assert [c.order for c in result.chunks] == [0, 1]
    assert result.has_more and result.page == 1
    assert result.chunks[1].layoutStart == LayoutStart(**ANCHOR)
    assert documents.calls[-1] == ("page", DOC, 1, 3)
    assert (await pages.read_page_chunks(documents, DOC, 2, 5)).chunks == [chunks[2]]
    for page, limit in ((-1, 5), (0, 0), (0, pages.MAX_PAGE_CHUNKS + 1)):
        with pytest.raises(InvalidRequestError):
            await pages.read_page_chunks(documents, DOC, page, limit)


def test_stored_anchors_are_parsed_and_invalid_ones_left_out(caplog):
    assert chunk_properties({"order": 1})["order"] == 1
    assert chunk_properties({"layoutStart": {**ANCHOR, "offset": 3.0}})["layoutStart"] == LayoutStart(**ANCHOR)
    assert chunk_properties({"layoutStart": {**ANCHOR, "match": "fuzzy"}})["layoutStart"] is None
    assert chunk_properties({"layoutStart": {"pageId": None, "lineId": None, "offset": None, "match": None}}
                            )["layoutStart"] is None
    assert "invalid stored chunk layoutStart" in caplog.text


# --- HTTP --------------------------------------------------------------------------------

@pytest.fixture
async def client(tmp_path, store):
    app = create_app(make_test_config(tmp_path, PAGE_ASSETS_DIR=str(store.root)), weaviate_connector=offline_weaviate)
    app.dependency_overrides[get_documents] = lambda: FakeDocuments([_chunk(0, 0, 1, LayoutStart(**ANCHOR))])
    async with LifespanManager(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_assets_are_served_anonymously_with_type_and_caching(client):
    image = await client.get(f"/api/documents/{DOC}/pages/{PAGE_1}/image")
    layout = await client.get(f"/api/documents/{DOC}/pages/{PAGE_1}/layout")
    thumbnail = await client.get(f"/api/documents/{DOC}/pages/{PAGE_1}/thumbnail")

    assert (image.status_code, image.headers["content-type"], image.content) == (200, "image/jpeg", JPEG)
    assert image.headers["cache-control"] == "public, max-age=86400"
    assert (layout.status_code, layout.headers["content-type"], layout.json()) == (200, "application/json", LAYOUT)
    assert layout.headers["cache-control"] == "no-cache"
    assert (thumbnail.status_code, thumbnail.headers["content-type"]) == (200, "image/jpeg")


async def test_assets_answer_conditional_requests(client, store):
    path = f"/api/documents/{DOC}/pages/{PAGE_1}/layout"
    first = await client.get(path)

    again = await client.get(path, headers={"If-None-Match": first.headers["etag"]})
    store.write_asset(DOC, PAGE_1, "layout", b'{"replaced": true}')
    changed = await client.get(path, headers={"If-None-Match": first.headers["etag"]})

    assert (again.status_code, again.content, again.headers["etag"]) == (304, b"", first.headers["etag"])
    assert (changed.status_code, changed.json()) == (200, {"replaced": True})


@pytest.mark.parametrize("path", [
    f"/api/documents/{DOC}/pages/{PAGE_2}/image",              # page without a scan
    f"/api/documents/{uuid4()}/pages/{PAGE_1}/image",          # unknown document
    f"/api/documents/not-a-uuid/pages/{PAGE_1}/image",
    f"/api/documents/{DOC}/pages/..%2F..%2Fmanifest/image",
    f"/api/documents/{DOC}/pages/manifest/layout",
])
async def test_absent_or_malformed_assets_are_404(client, path):
    assert (await client.get(path)).status_code == 404


async def test_unknown_asset_kinds_are_rejected(client):
    assert (await client.get(f"/api/documents/{DOC}/pages/{PAGE_1}/manifest.json")).status_code == 422


async def test_page_manifest_and_page_chunks_over_http(client):
    manifest = await client.get(f"/api/documents/{DOC}/pages")
    text_only = await client.get(f"/api/documents/{TEXT_ONLY}/pages")
    unknown = await client.get(f"/api/documents/{uuid4()}/pages")
    chunks = await client.get(f"/api/documents/{DOC}/chunks/by_page", params={"page": 1})
    too_many = await client.get(f"/api/documents/{DOC}/chunks/by_page", params={"page": 1, "limit": 51})

    assert manifest.status_code == 200, manifest.text
    assert manifest.headers["cache-control"] == "no-cache"
    body = manifest.json()
    assert body["available"] and [p["order"] for p in body["pages"]] == [0, 1, 2]
    assert body["pages"][2] == {"page_id": str(PAGE_3), "order": 2, "label": "3", "page_type": "Blank"}
    assert text_only.json() == {"document_id": str(TEXT_ONLY), "available": False, "pages": []}
    assert unknown.status_code == 404
    assert chunks.status_code == 200, chunks.text
    assert chunks.json()["chunks"][0]["layoutStart"] == ANCHOR
    assert (chunks.json()["page"], chunks.json()["has_more"]) == (1, False)
    assert too_many.status_code == 422


async def test_without_an_asset_directory_every_document_is_text_only(tmp_path):
    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    app.dependency_overrides[get_documents] = FakeDocuments
    async with LifespanManager(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        manifest = await client.get(f"/api/documents/{DOC}/pages")
        image = await client.get(f"/api/documents/{DOC}/pages/{PAGE_1}/image")

    assert manifest.json() == {"document_id": str(DOC), "available": False, "pages": []}
    assert image.status_code == 404


def test_page_reads_are_public_operations(tmp_path):
    paths = create_app(make_test_config(tmp_path)).openapi()["paths"]

    for path in ("/api/documents/{document_id}/pages", "/api/documents/{document_id}/pages/{page_id}/{kind}",
                 "/api/documents/{document_id}/chunks/by_page"):
        assert "security" not in paths[path]["get"]
    kind = next(p for p in paths["/api/documents/{document_id}/pages/{page_id}/{kind}"]["get"]["parameters"]
                if p["name"] == "kind")
    assert kind["schema"]["enum"] == ["image", "layout", "thumbnail"]
