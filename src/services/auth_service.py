"""Therapist authentication service.

Handles email+password login, JWT issuance, and user lookup. Signup
(creating orgs and billing customers) lives in the signup flow; this
service is scoped to authenticating existing users.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import (
    AuthError,
    TokenClaims,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from src.core.config import Settings, get_settings
from src.core.exceptions import ConflictError, NotFoundError, UnauthorizedError
from src.models.db.auth_token import AuthTokenPurpose
from src.models.db.organization import Organization
from src.models.db.user import User, UserRole
from src.repositories.auth_token_repo import AuthTokenRepository

logger = logging.getLogger(__name__)


class AuthService:
    """Auth operations over the users table."""

    def __init__(
        self,
        db_session: AsyncSession,
        settings: Settings | None = None,
    ) -> None:
        self.db_session = db_session
        self.settings = settings or get_settings()

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self.db_session.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: uuid.UUID) -> User:
        result = await self.db_session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundError(resource="User", resource_id=str(user_id))
        return user

    async def authenticate_therapist(
        self, email: str, password: str
    ) -> tuple[User, str, datetime]:
        """Verify credentials and mint a therapist session token.

        Raises UnauthorizedError for any failure path (unknown user,
        wrong password, account not set up with a password, non-therapist
        role). All failure modes return the same error to avoid user
        enumeration.
        """
        user = await self.get_user_by_email(email)
        generic_error = UnauthorizedError("Invalid email or password")

        if user is None or user.password_hash is None:
            logger.info("Login failed: unknown email or no password set")
            raise generic_error

        if user.role != UserRole.THERAPIST:
            logger.info("Login denied: non-therapist role %s", user.role)
            raise generic_error

        if not verify_password(password, user.password_hash):
            logger.info("Login failed: password mismatch for %s", user.id)
            raise generic_error

        token, expires_at = create_access_token(
            user_id=user.id,
            organization_id=user.organization_id,
            audience="therapist",
            settings=self.settings,
        )
        logger.info("Therapist %s logged in", user.id)
        return user, token, expires_at

    async def resolve_therapist_from_token(self, token: str) -> User:
        """Decode a therapist JWT and load the user record."""
        try:
            claims: TokenClaims = decode_access_token(
                token,
                expected_audience="therapist",
                settings=self.settings,
            )
        except AuthError as exc:
            raise UnauthorizedError(str(exc)) from exc

        user = await self.get_user_by_id(claims.user_id)
        if user.role != UserRole.THERAPIST:
            raise UnauthorizedError("Token does not belong to a therapist account")
        if user.organization_id != claims.organization_id:
            raise UnauthorizedError("Token organization mismatch")
        return user

    async def set_password(self, user_id: uuid.UUID, new_password: str) -> None:
        """Set or replace a user's password hash."""
        user = await self.get_user_by_id(user_id)
        user.password_hash = hash_password(new_password)
        await self.db_session.flush()

    async def create_therapist(
        self,
        organization_id: uuid.UUID,
        email: str,
        password: str,
        full_name: str | None = None,
    ) -> User:
        """Create a therapist user. Raises ConflictError on duplicate email.

        Used by the signup flow; exposed here so tests can exercise the
        end-to-end auth path without the full signup orchestration.
        """
        normalized_email = email.lower()
        existing = await self.get_user_by_email(normalized_email)
        if existing:
            raise ConflictError(detail="A user with this email already exists")

        user = User(
            organization_id=organization_id,
            email=normalized_email,
            role=UserRole.THERAPIST,
            full_name=full_name,
            password_hash=hash_password(password),
        )
        self.db_session.add(user)
        await self.db_session.flush()
        await self.db_session.refresh(user)
        return user

    async def request_password_reset(self, email: str) -> str | None:
        """Create a password reset token.

        Returns the raw token if a user with that email exists, else None.
        Callers MUST NOT leak whether a user was found — the endpoint
        returns a uniform success response to avoid user enumeration.
        Token is persisted hashed; raw value is returned once for emailing.
        """
        user = await self.get_user_by_email(email.lower())
        if user is None:
            return None
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(minutes=30)
        repo = AuthTokenRepository(self.db_session)
        await repo.create(
            user_id=user.id,
            purpose=AuthTokenPurpose.PASSWORD_RESET,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        logger.info("Password reset token issued for user %s", user.id)
        return raw_token

    async def confirm_password_reset(self, raw_token: str, new_password: str) -> User:
        """Redeem a password reset token and set a new password."""
        if len(new_password) < 8:
            raise ConflictError(detail="Password must be at least 8 characters")
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        repo = AuthTokenRepository(self.db_session)
        token = await repo.get_by_hash(token_hash, AuthTokenPurpose.PASSWORD_RESET)
        if token is None or token.used_at is not None:
            raise UnauthorizedError("Invalid or already-used reset link")
        if token.expires_at <= datetime.now(UTC):
            raise UnauthorizedError("Reset link expired")

        user = await self.get_user_by_id(token.user_id)
        user.password_hash = hash_password(new_password)
        await repo.mark_used(token.id)
        await self.db_session.flush()
        logger.info("Password reset completed for user %s", user.id)
        return user

    async def request_email_verification(self, user_id: uuid.UUID) -> str:
        """Create an email verification token for a user. Returns raw token."""
        user = await self.get_user_by_id(user_id)
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(hours=24)
        repo = AuthTokenRepository(self.db_session)
        await repo.create(
            user_id=user.id,
            purpose=AuthTokenPurpose.EMAIL_VERIFICATION,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        return raw_token

    async def confirm_email_verification(self, raw_token: str) -> User:
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        repo = AuthTokenRepository(self.db_session)
        token = await repo.get_by_hash(
            token_hash, AuthTokenPurpose.EMAIL_VERIFICATION
        )
        if token is None or token.used_at is not None:
            raise UnauthorizedError("Invalid or already-used verification link")
        if token.expires_at <= datetime.now(UTC):
            raise UnauthorizedError("Verification link expired")
        user = await self.get_user_by_id(token.user_id)
        user.email_verified_at = datetime.now(UTC)
        await repo.mark_used(token.id)
        await self.db_session.flush()
        return user

    async def register_practice(
        self,
        email: str,
        password: str,
        practice_name: str,
        full_name: str | None = None,
    ) -> tuple[User, str, datetime]:
        """Create a new practice (org) + the founding therapist + session token.

        The operation is a single flush, so a duplicate email rolls back
        the org creation. The returned token is ready to place in the
        session cookie.
        """
        normalized_email = email.lower()
        existing = await self.get_user_by_email(normalized_email)
        if existing:
            raise ConflictError(detail="A user with this email already exists")

        organization = Organization(name=practice_name)
        self.db_session.add(organization)
        await self.db_session.flush()
        await self.db_session.refresh(organization)

        user = User(
            organization_id=organization.id,
            email=normalized_email,
            role=UserRole.THERAPIST,
            full_name=full_name,
            password_hash=hash_password(password),
        )
        self.db_session.add(user)
        await self.db_session.flush()
        await self.db_session.refresh(user)

        token, expires_at = create_access_token(
            user_id=user.id,
            organization_id=user.organization_id,
            audience="therapist",
            settings=self.settings,
        )
        logger.info(
            "Registered new practice '%s' with therapist %s",
            practice_name,
            user.id,
        )
        return user, token, expires_at
