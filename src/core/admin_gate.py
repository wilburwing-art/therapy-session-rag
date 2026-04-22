"""Admin role gate.

Admins sign in through the same therapist endpoint (same JWT audience,
same cookie), but their user record is tagged with ``UserRole.ADMIN``.
``get_current_therapist`` hard-rejects anything other than the therapist
role, so this module resolves the admin directly from the JWT and then
enforces the admin role on top.

Operator endpoints mount this dependency directly; the billing gate is
intentionally NOT applied to admin routes so an unpaid / suspended
practice can still be managed.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import AuthError, decode_access_token
from src.core.config import Settings, get_settings
from src.core.database import get_db_session
from src.core.exceptions import ForbiddenError, RateLimitError, UnauthorizedError
from src.models.db.user import User, UserRole
from src.services.rate_limiter import AuthRateLimiter, RateLimitExceeded


async def require_admin(
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    cookie_token: str | None = Cookie(default=None, alias="therapyrag_session"),
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """Resolve the caller and require ``UserRole.ADMIN``.

    Accepts either the therapist session cookie or a Bearer Authorization
    header carrying the same therapist-audience JWT. Raises 401 if no
    valid token is present and 403 if the user is authenticated but not
    an admin.
    """
    token: str | None = cookie_token
    if token is None and authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value:
            token = value
    if not token:
        raise UnauthorizedError("Admin session required")

    try:
        claims = decode_access_token(
            token, expected_audience="therapist", settings=settings
        )
    except AuthError as exc:
        raise UnauthorizedError(str(exc)) from exc

    result = await session.execute(select(User).where(User.id == claims.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise UnauthorizedError("Session user not found")
    if user.organization_id != claims.organization_id:
        raise UnauthorizedError("Session organization mismatch")
    if user.role != UserRole.ADMIN:
        raise ForbiddenError("Admin privileges required")
    return user


# 60 requests per minute per IP across the entire admin panel. Enough
# for the heaviest dashboard refresh (org list + detail + audit page in
# one tick), tight enough to catch someone scripting the admin API.
ADMIN_RATE_LIMIT_MAX_REQUESTS = 60
ADMIN_RATE_LIMIT_WINDOW_SECONDS = 60


def _admin_rate_limit_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _get_admin_rate_limiter() -> AuthRateLimiter:
    """Factory dep so FastAPI doesn't introspect ``AuthRateLimiter.__init__``.

    Using ``Depends(AuthRateLimiter)`` forces FastAPI to build a Pydantic
    field for the ``redis_client: Redis | None`` init param, which it
    can't serialize. A plain factory sidesteps that.
    """
    return AuthRateLimiter()


async def require_admin_rate_limit(
    request: Request,
    rate_limiter: AuthRateLimiter = Depends(_get_admin_rate_limiter),
) -> None:
    """Coarse per-IP rate limit applied to every /admin/* route.

    Uses the shared ``AuthRateLimiter``'s generic scope API so the counter
    lives in Redis alongside the other auth buckets. The dep is attached
    at the admin include-router level in ``src.api.v1.router``.
    """
    try:
        await rate_limiter.check(
            ip=_admin_rate_limit_ip(request),
            scope="admin_panel_ip",
            limit=ADMIN_RATE_LIMIT_MAX_REQUESTS,
            window=ADMIN_RATE_LIMIT_WINDOW_SECONDS,
        )
    except RateLimitExceeded as exc:
        raise RateLimitError(detail=str(exc), retry_after=exc.reset_time) from exc
