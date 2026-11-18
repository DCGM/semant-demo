"""Signed page-asset URLs of documents read through a collection (#279).

Page images, thumbnails and layout files are loaded by the browser (``<img src>``), which
sends no bearer token. A public document's assets need none. For a restricted or unknown
document, readable only through a collection (``documents.service.readable_document``), the
authorized page manifest gives asset URLs with an ``access`` token: an HMAC over the
document, the collection, the user and an expiry, keyed by the application secret.

The token is not a permission by itself: every asset read with it checks again that the
token's user can read the token's collection and that the document is still linked to it
(``pages.read_page_asset``), so revoking a share or removing the document denies the next
read at once. The expiry only bounds how long a leaked URL stays usable by the original
user's rights; the manifest is read again whenever the viewer opens a document.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Callable
from uuid import UUID

TOKEN_LIFETIME_SECONDS = 12 * 3600
"""How long a signed asset URL is accepted after its manifest was read."""

_KEY_PURPOSE = b"semant-page-asset-v1"


@dataclass(frozen=True)
class AssetGrant:
    """Who read the manifest a signed asset URL came from, and through which collection."""
    document_id: UUID
    collection_id: UUID
    user_id: UUID


class AssetSigner:
    """Signs and verifies asset access tokens with a key derived from ``secret``."""

    def __init__(self, secret: str, lifetime_seconds: int = TOKEN_LIFETIME_SECONDS,
                 clock: Callable[[], float] = time.time):
        self._key = hmac.new(secret.encode(), _KEY_PURPOSE, hashlib.sha256).digest()
        self._lifetime = lifetime_seconds
        self._clock = clock

    def _signature(self, payload: str) -> str:
        digest = hmac.new(self._key, payload.encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    def sign(self, grant: AssetGrant) -> str:
        expires = int(self._clock()) + self._lifetime
        payload = f"{grant.document_id.hex}.{grant.collection_id.hex}.{grant.user_id.hex}.{expires}"
        return f"{payload}.{self._signature(payload)}"

    def verify(self, token: str | None, document_id: UUID) -> AssetGrant | None:
        """The grant of a valid, unexpired token for ``document_id``; None otherwise."""
        if not token:
            return None
        parts = token.split(".")
        if len(parts) != 5:
            return None
        payload, signature = ".".join(parts[:4]), parts[4]
        if not hmac.compare_digest(self._signature(payload), signature):
            return None
        try:
            grant = AssetGrant(UUID(hex=parts[0]), UUID(hex=parts[1]), UUID(hex=parts[2]))
            expires = int(parts[3])
        except ValueError:
            return None
        if grant.document_id != document_id or expires < self._clock():
            return None
        return grant
