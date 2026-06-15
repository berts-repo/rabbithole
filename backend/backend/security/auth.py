"""Session token, Origin validation, and /api/* auth middleware.

B1 establishes the bare-minimum loopback auth posture; B3 expands this module
with broader path/network primitives. The token is generated once per process,
held in memory only, and rotates whenever the server restarts. The browser
receives it as a `crawl_token` cookie (`HttpOnly` + `SameSite=Strict`) on first
SPA load.

Every `/api/*` request must present that exact cookie value. State-changing
methods (`POST`, `PUT`, `PATCH`, `DELETE`) must additionally present an
`Origin` of `http://127.0.0.1:7654` — Origin is the CSRF gate for mutations.
Safe methods (`GET`, `HEAD`, `OPTIONS`) skip the Origin check because
browsers omit `Origin` on same-origin GETs and `EventSource` handshakes, and
the cookie's `SameSite=Strict` already prevents cross-site requests from
attaching it.

Token comparison uses `hmac.compare_digest` to avoid timing oracles.
"""
from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

COOKIE_NAME = "crawl_token"
EXPECTED_ORIGIN = "http://127.0.0.1:7654"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass
class SessionState:
    token: str


def new_session() -> SessionState:
    return SessionState(token=secrets.token_urlsafe(32))


def verify_token(presented: str | None, expected: str) -> bool:
    if not presented:
        return False
    return hmac.compare_digest(presented, expected)


def verify_origin(presented: str | None) -> bool:
    return presented == EXPECTED_ORIGIN


class ApiAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        session: SessionState = request.app.state.session
        if request.method in UNSAFE_METHODS:
            if not verify_origin(request.headers.get("origin")):
                return JSONResponse({"error": "bad_origin"}, status_code=403)
        if not verify_token(request.cookies.get(COOKIE_NAME), session.token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)
