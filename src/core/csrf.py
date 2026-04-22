"""Double-submit CSRF protection for cookie-authenticated routes.

Only cookie-based auth is vulnerable to CSRF — API-key callers send a
bearer-style header a cross-site attacker can't forge. So this middleware
enforces the CSRF contract *only* when a session cookie is present.

Contract:
- On login / register / magic-link redeem, a non-HttpOnly `therapyrag_csrf`
  cookie is set alongside the session cookie, holding a 32-byte random.
- For any state-changing request (POST/PUT/PATCH/DELETE) that has a
  session cookie, the client must echo that random in the
  `X-CSRF-Token` header. The middleware compares them in constant time.
- GET/HEAD/OPTIONS and safelisted paths are skipped.
"""

from __future__ import annotations

import hmac
import secrets

from fastapi import Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.core.config import Settings

CSRF_COOKIE_NAME = "therapyrag_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
_SESSION_COOKIES = ("therapyrag_session", "therapyrag_patient")
_EXEMPT_METHODS = {"GET", "HEAD", "OPTIONS"}

# Paths that must stay reachable without a CSRF token because either
# (a) the caller isn't logged in yet, or (b) integrity is proven some
# other way (signed webhook body, one-time token).
_EXEMPT_PREFIXES = (
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/logout",
    "/api/v1/auth/password-reset-request",
    "/api/v1/auth/password-reset-confirm",
    "/api/v1/auth/verify-email-confirm",
    "/api/v1/auth/patient/session",
    "/api/v1/auth/patient/logout",
    "/api/v1/billing/webhook",
    "/api/v1/invites/accept",
)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_csrf_cookie(
    response: Response,
    token: str,
    settings: Settings,
    max_age: int | None = None,
) -> None:
    """Set the CSRF cookie as non-HttpOnly so the client can read it.

    The session cookie carries the actual auth — losing the CSRF token
    just means the user has to re-login; it's not sensitive itself.
    """
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        max_age=max_age if max_age is not None else settings.jwt_access_token_ttl_seconds,
        httponly=False,
        secure=settings.jwt_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_csrf_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        httponly=False,
        secure=settings.jwt_cookie_secure,
        samesite="lax",
        path="/",
    )


class CsrfMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.settings = settings

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method in _EXEMPT_METHODS:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)

        # Only enforce when the caller is presenting a session cookie.
        # API-key and unauthenticated traffic (login attempt, etc.) pass
        # through — those paths either aren't CSRF-exploitable or are
        # exempted above.
        has_session_cookie = any(
            request.cookies.get(name) for name in _SESSION_COOKIES
        )
        if not has_session_cookie:
            return await call_next(request)

        header_token = request.headers.get(CSRF_HEADER_NAME)
        cookie_token = request.cookies.get(CSRF_COOKIE_NAME)

        if (
            not header_token
            or not cookie_token
            or not hmac.compare_digest(header_token, cookie_token)
        ):
            return JSONResponse(
                status_code=403,
                content={
                    "type": "about:blank#forbidden",
                    "title": "Forbidden",
                    "status": 403,
                    "detail": "Missing or invalid CSRF token.",
                },
                media_type="application/problem+json",
            )

        return await call_next(request)
