"""Page images, page layout files and page manifests on the filesystem (#541).

The asset store is one configured directory (``PAGE_ASSETS_DIR``). Every path is derived
from document and page UUIDs only, never from client text::

    <root>/<first two hex digits of the document id>/<document id>/manifest.json
    <root>/<..>/<document id>/<page id>.jpg          the page scan (original JPEG)
    <root>/<..>/<document id>/<page id>.json         the page layout file (docs/PAGE_LAYOUT.md)
    <root>/<..>/<document id>/<page id>.thumb.jpg    the thumbnail

The manifest (``semant.page-manifest``, version 1) lists every page of the document's page
list in order, with the assets available for it. The assets are regenerable: there is no
backup, revision or transaction across files. Writes (used by the corpus import, #542) go to
a temporary file in the same directory that is then renamed, so a reader sees either the
old or the new complete file. Reading never follows a path outside the root: a file reached
through a symbolic link that leaves the root counts as absent.
"""
import os
import tempfile
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

AssetKind = Literal["image", "layout", "thumbnail"]
ASSET_KINDS: tuple[AssetKind, ...] = ("image", "layout", "thumbnail")
SUFFIXES: dict[AssetKind, str] = {"image": ".jpg", "layout": ".json", "thumbnail": ".thumb.jpg"}
MEDIA_TYPES: dict[AssetKind, str] = {"image": "image/jpeg", "layout": "application/json",
                                     "thumbnail": "image/jpeg"}
MANIFEST_NAME = "manifest.json"
MANIFEST_SCHEMA = "semant.page-manifest"
MANIFEST_VERSION = 1


class ManifestPage(BaseModel):
    """One page of the page list (#571) and the assets stored for it."""
    model_config = ConfigDict(extra="forbid")

    pageId: UUID
    order: int = Field(ge=0)
    """The page's index in the page list (0, 1, ...): the page number of the chunks'
    ``from_page``/``to_page``."""
    label: str | None = None
    """The printed page label (the mirror's ``number``), e.g. ``[627]``."""
    pageType: str | None = None
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    """The scan's size in pixels, when known."""
    image: bool = False
    layout: bool = False
    thumbnail: bool = False


class PageManifest(BaseModel):
    """A document's stored page manifest."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_name: Literal["semant.page-manifest"] = Field(default=MANIFEST_SCHEMA, alias="schema")
    version: Literal[1] = MANIFEST_VERSION
    documentId: UUID
    library: str | None = None
    params: dict[str, int | float] | None = None
    """The chunking parameters the layout files were made with (#540)."""
    pages: list[ManifestPage]

    @model_validator(mode="after")
    def _unique_pages(self) -> "PageManifest":
        if len({p.pageId for p in self.pages}) != len(self.pages):
            raise ValueError("duplicate pageId")
        if any(page.order != i for i, page in enumerate(self.pages)):
            raise ValueError("page order must be the index in the page list")
        return self


class InvalidManifest(Exception):
    """A stored manifest that cannot be parsed, or describes another document."""


class PageAssetStore:
    """The page assets under one root directory; ``root`` None means no assets at all."""

    def __init__(self, root: str | Path | None):
        self.root = Path(root) if root else None

    @property
    def enabled(self) -> bool:
        return self.root is not None

    def document_dir(self, document_id: UUID) -> Path:
        if self.root is None:
            raise RuntimeError("No page asset directory is configured")
        name = str(UUID(str(document_id)))
        return self.root / name[:2] / name

    def manifest_path(self, document_id: UUID) -> Path:
        return self.document_dir(document_id) / MANIFEST_NAME

    def asset_path(self, document_id: UUID, page_id: UUID, kind: AssetKind) -> Path:
        return self.document_dir(document_id) / (str(UUID(str(page_id))) + SUFFIXES[kind])

    def _existing(self, path: Path) -> Path | None:
        """``path`` if it is a regular file whose real location is inside the root."""
        try:
            real = path.resolve(strict=True)
            if not real.is_relative_to(self.root.resolve(strict=True)) or not real.is_file():
                return None
        except (OSError, RuntimeError):
            return None
        return real

    def read_manifest(self, document_id: UUID) -> PageManifest | None:
        """The document's manifest, None when there is none (or no store). Raises
        ``InvalidManifest`` for an unreadable one or one of another document."""
        if self.root is None:
            return None
        path = self._existing(self.manifest_path(document_id))
        if path is None:
            return None
        try:
            manifest = PageManifest.model_validate_json(path.read_bytes())
        except (OSError, ValidationError) as e:
            raise InvalidManifest(type(e).__name__) from e
        if manifest.documentId != document_id:
            raise InvalidManifest("documentId does not match")
        return manifest

    def asset_file(self, document_id: UUID, page_id: UUID, kind: AssetKind) -> Path | None:
        """The stored asset's file, None when it is absent (or there is no store)."""
        if self.root is None:
            return None
        return self._existing(self.asset_path(document_id, page_id, kind))

    def write_manifest(self, manifest: PageManifest) -> None:
        """Replace the document's manifest atomically."""
        data = manifest.model_dump_json(by_alias=True, indent=1).encode("utf-8")
        _write_atomically(self.manifest_path(manifest.documentId), data)

    def write_asset(self, document_id: UUID, page_id: UUID, kind: AssetKind, data: bytes) -> Path:
        """Replace one asset atomically; returns its path."""
        path = self.asset_path(document_id, page_id, kind)
        _write_atomically(path, data)
        return path


def _write_atomically(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
