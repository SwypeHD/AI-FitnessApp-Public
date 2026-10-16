"""Shared-secret authentication for the API.

Off unless ``FITNESS_AUTH_TOKEN`` is set, so local development and the test suite run
exactly as before.

Only the API is protected. Static assets stay open because the page has to load in
order to prompt for the token, and it contains no user data — the logs behind the API
are what matter.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

HEADER_NAME = "X-Auth-Token"
COOKIE_NAME = "fittrack_token"

# Reachable without a token: the app shell, the icons, and a liveness check.
_OPEN_PREFIXES = ("/static/", "/health")


def _is_open(path: str) -> bool:
    return path == "/" or any(path.startswith(p) for p in _OPEN_PREFIXES)


def _presented_token(request: Request) -> str:
    """Read the token from a header, query string, or cookie.

    The header is what the app sends. The query string exists so a link can carry
    the token on first load, and the cookie so a plain browser navigation works
    once it's been set.
    """
    return (
        request.headers.get(HEADER_NAME)
        or request.query_params.get("token")
        or request.cookies.get(COOKIE_NAME)
        or ""
    )


class SharedSecretAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str) -> None:
        super().__init__(app)
        self._token = token or ""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not self._token or _is_open(request.url.path):
            return await call_next(request)

        presented = _presented_token(request)
        # compare_digest keeps the comparison constant-time; a plain == leaks the
        # token's prefix through timing.
        if not presented or not secrets.compare_digest(presented, self._token):
            return JSONResponse(
                {"detail": "Missing or invalid auth token."},
                status_code=401,
            )
        return await call_next(request)
