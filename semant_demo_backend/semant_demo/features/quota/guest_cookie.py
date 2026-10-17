"""The guest cookie of the daily LLM allowance (``principal.py``) on every kind of response.

A cookie issued while a request is handled is remembered in the request state and added
to the response's headers here, so it also reaches a streamed response, a route's own
``Response``, an error and a 429, not only a route's returned model. Without its own
imports of the application, so that ``main`` can install it.
"""
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

GUEST_COOKIE = "semant_guest"
_NEW_COOKIE_STATE = "quota_guest_set_cookie"


def remember_new_cookie(request: Request, set_cookie_header: str) -> None:
    setattr(request.state, _NEW_COOKIE_STATE, set_cookie_header)


class GuestCookieMiddleware:
    """Adds the guest cookie issued while handling a request to its response."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_cookie(message: Message) -> None:
            if message["type"] == "http.response.start":
                cookie = (scope.get("state") or {}).get(_NEW_COOKIE_STATE)
                if cookie is not None:
                    message["headers"] = [*message.get("headers", []), (b"set-cookie", cookie.encode("latin-1"))]
            await send(message)

        await self.app(scope, receive, send_with_cookie)
