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

from fastapi import Cookie, Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import AuthError, decode_access_token
from src.core.config import Settings, get_settings
from src.core.database import get_db_session
from src.core.exceptions import ForbiddenError, UnauthorizedError
from src.models.db.user import User, UserRole


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
