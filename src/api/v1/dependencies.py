"""FastAPI dependencies for API v1."""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Cookie, Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import AuthError, decode_access_token
from src.core.config import Settings, get_settings
from src.core.database import DbSession, get_db_session
from src.core.exceptions import UnauthorizedError
from src.core.security import is_valid_api_key_format, verify_api_key
from src.models.db.api_key import ApiKey
from src.models.db.user import User, UserRole
from src.repositories.api_key_repo import ApiKeyRepository
from src.services.auth_service import AuthService
from src.services.event_service import EventPublisher


@dataclass
class AuthContext:
    """Authentication context containing validated API key info."""

    api_key_id: uuid.UUID
    organization_id: uuid.UUID
    api_key_name: str


async def get_api_key_auth(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    session: AsyncSession = Depends(get_db_session),
    cookie_token: str | None = Cookie(default=None, alias="therapyrag_session"),
    settings: Settings = Depends(get_settings),
) -> AuthContext:
    """Validate API key and return authentication context.

    Args:
        x_api_key: The API key from X-API-Key header
        session: Database session

    Returns:
        AuthContext with validated API key information

    Raises:
        UnauthorizedError: If API key is missing, invalid, or inactive
    """
    # Prefer therapist JWT cookie when the web app is the caller; fall
    # back to API keys for server-to-server traffic.
    if cookie_token:
        try:
            claims = decode_access_token(
                cookie_token,
                expected_audience="therapist",
                settings=settings,
            )
        except AuthError as exc:
            raise UnauthorizedError(str(exc)) from exc

        user_result = await session.execute(
            select(User).where(User.id == claims.user_id)
        )
        user = user_result.scalar_one_or_none()
        if user is None or user.role != UserRole.THERAPIST:
            raise UnauthorizedError("Session does not belong to a therapist")
        if user.organization_id != claims.organization_id:
            raise UnauthorizedError("Session organization mismatch")
        return AuthContext(
            api_key_id=user.id,
            organization_id=user.organization_id,
            api_key_name=user.email,
        )

    if not x_api_key:
        raise UnauthorizedError(
            "Authentication required: provide a therapist session cookie or X-API-Key header."
        )

    if not is_valid_api_key_format(x_api_key):
        raise UnauthorizedError("Invalid API key format.")

    # Find all active API keys and check against each
    # This is necessary because we store hashed keys
    key_result = await session.execute(
        select(ApiKey).where(ApiKey.is_active == True)  # noqa: E712
    )
    active_keys = key_result.scalars().all()

    for api_key in active_keys:
        if verify_api_key(x_api_key, api_key.key_hash):
            # Update last_used_at
            repo = ApiKeyRepository(session)
            await repo.update_last_used(api_key.id)

            return AuthContext(
                api_key_id=api_key.id,
                organization_id=api_key.organization_id,
                api_key_name=api_key.name,
            )

    raise UnauthorizedError("Invalid API key.")


async def get_current_therapist(
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    cookie_token: str | None = Cookie(default=None, alias="therapyrag_session"),
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """Resolve the authenticated therapist from a JWT cookie or bearer header."""
    token: str | None = cookie_token
    if token is None and authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value:
            token = value
    if not token:
        raise UnauthorizedError("Therapist session required")

    auth_service = AuthService(session, settings=settings)
    return await auth_service.resolve_therapist_from_token(token)


async def get_therapist_auth_context(
    user: User = Depends(get_current_therapist),
) -> AuthContext:
    """Expose a therapist session as an AuthContext for endpoints that
    already depend on `Auth` / AuthContext (org-scoped tenancy)."""
    return AuthContext(
        api_key_id=user.id,
        organization_id=user.organization_id,
        api_key_name=user.email,
    )


async def get_current_patient(
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    cookie_token: str | None = Cookie(default=None, alias="therapyrag_patient"),
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """Resolve the authenticated patient from a JWT cookie or bearer header."""
    from src.core.auth import AuthError, decode_access_token
    from src.models.db.user import UserRole

    token: str | None = cookie_token
    if token is None and authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value:
            token = value
    if not token:
        raise UnauthorizedError("Patient session required")

    try:
        claims = decode_access_token(
            token, expected_audience="patient", settings=settings
        )
    except AuthError as exc:
        raise UnauthorizedError(str(exc)) from exc

    result = await session.execute(select(User).where(User.id == claims.user_id))
    user = result.scalar_one_or_none()
    if user is None or user.role != UserRole.PATIENT:
        raise UnauthorizedError("Token does not belong to a patient account")
    if user.organization_id != claims.organization_id:
        raise UnauthorizedError("Token organization mismatch")
    return user


# Type alias for dependency injection
Auth = Annotated[AuthContext, Depends(get_api_key_auth)]
CurrentTherapist = Annotated[User, Depends(get_current_therapist)]
TherapistAuth = Annotated[AuthContext, Depends(get_therapist_auth_context)]
CurrentPatient = Annotated[User, Depends(get_current_patient)]


def get_event_publisher(session: DbSession) -> EventPublisher:
    """Get event publisher instance."""
    return EventPublisher(session)


Events = Annotated[EventPublisher, Depends(get_event_publisher)]
