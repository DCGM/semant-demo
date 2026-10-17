"""Whose daily LLM allowance a request uses.

A signed-in request uses its account (the validated user id, never a caller-supplied
one). Any other request is a guest identified by a random first-party cookie that the
server issues when it is missing or malformed; the ledger stores only its SHA-256.
Clearing the cookie starts a new guest allowance, an accepted limitation. Logging in
switches to the account allowance; logging out leaves the guest usage as it was.

A newly issued cookie is added to whatever response the request gets, also a streamed
one, an error or a 429 (``guest_cookie.GuestCookieMiddleware``).
"""
import hashlib
import re
import secrets

from fastapi import Depends, Request, Response

from semant_demo.adapters.sql.quota import QuotaLedger
from semant_demo.features.quota.guest_cookie import GUEST_COOKIE, remember_new_cookie
from semant_demo.features.quota.service import AllowanceBudget, QuotaPolicy, QuotaPrincipal
from semant_demo.routes.dependencies import get_quota_ledger, get_quota_policy
from semant_demo.users.auth import current_active_optional_user
from semant_demo.users.models import User

_GUEST_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")


def guest_principal(token: str) -> QuotaPrincipal:
    return QuotaPrincipal(kind="guest", id=hashlib.sha256(token.encode()).hexdigest())


async def get_quota_principal(request: Request,
                              user: User | None = Depends(current_active_optional_user),
                              policy: QuotaPolicy = Depends(get_quota_policy)) -> QuotaPrincipal:
    """The account of a signed-in user, else the guest of the request's cookie; a new
    guest cookie is added to the response by ``GuestCookieMiddleware``."""
    if user is not None:
        return QuotaPrincipal(kind="account", id=str(user.id))
    token = request.cookies.get(GUEST_COOKIE)
    if token is None or not _GUEST_TOKEN.fullmatch(token):
        token = secrets.token_urlsafe(32)
        cookie = Response()
        cookie.set_cookie(GUEST_COOKIE, token, max_age=policy.guest_cookie_max_age_seconds, path="/api",
                          secure=policy.guest_cookie_secure, httponly=True, samesite="lax")
        remember_new_cookie(request, cookie.headers["set-cookie"])
    return guest_principal(token)


async def get_allowance_budget(principal: QuotaPrincipal = Depends(get_quota_principal),
                               ledger: QuotaLedger = Depends(get_quota_ledger),
                               policy: QuotaPolicy = Depends(get_quota_policy)) -> AllowanceBudget:
    """The caller's daily allowance, for ``LlmGateway.operation``."""
    return AllowanceBudget(ledger, policy, principal)
