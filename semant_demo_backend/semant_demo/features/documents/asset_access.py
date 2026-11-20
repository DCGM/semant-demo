"""Signed page-asset URLs of documents read through a collection (#279).

Page images, thumbnails and layout files are loaded by the browser (``<img src>``), which
sends no bearer token. A public document's assets need none. For a restricted or unknown
document, readable only through a collection (``documents.service.readable_document``), the
authorized page manifest gives asset URLs with an ``access`` token: an HMAC over the
document, the collection, the user and an expiry, keyed by the application secret.

A signed URL is a bearer credential: anyone holding it can read that document's asset while
the token is valid (``TOKEN_LIFETIME_SECONDS``) and the original user can still read the
token's collection, which still holds the document. Every asset read checks those two again
(``pages.read_page_asset``), so revoking a share or removing the document denies the next read
at once. Signing out and account deactivation are *not* checked: the token stays valid until
it expires. The manifest says when its URLs expire (``DocumentPages.access_expires_at``); the
scan viewer reads it again before then, so a long reading session keeps working.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable
from uuid import UUID

TOKEN_LIFETIME_SECONDS = 30 * 60
"""How long a signed asset URL is accepted after its manifest was read (maintainer decision
on #789): short, since the URL is a bearer credential."""

_KEY_PURPOSE = b"semant-page-asset-v1"


@dataclass(frozen=True)
class AssetGrant:
    """Who read the manifest a signed asset URL came from, and through which collection."""
    document_id: UUID
    collection_id: UUID
    user_id: UUID


@dataclass(frozen=True)
class SignedAccess:
    """A token and the time it stops being accepted."""
    token: str
    expires_at: datetime


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

    def sign(self, grant: AssetGrant) -> "SignedAccess":
        expires = int(self._clock()) + self._lifetime
        payload = f"{grant.document_id.hex}.{grant.collection_id.hex}.{grant.user_id.hex}.{expires}"
        return SignedAccess(f"{payload}.{self._signature(payload)}", datetime.fromtimestamp(expires, UTC))

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
