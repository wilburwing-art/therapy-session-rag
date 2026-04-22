"""Therapist authentication service.

Handles email+password login, JWT issuance, and user lookup. Signup
(creating orgs and billing customers) lives in the signup flow; this
service is scoped to authenticating existing users.
"""

from __future__ import annotations

import hashlib
import logging
import math
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
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


TOTP_CHALLENGE_AUDIENCE = "totp_challenge"


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
    ) -> tuple[User, str, datetime, bool]:
        """Verify credentials and either mint a session or start a 2FA challenge.

        Return shape: (user, token, expires_at, requires_2fa).

        - If the account has no 2FA, `token` is a real therapist session
          JWT and `requires_2fa=False`. The endpoint should set the
          session cookie.
        - If 2FA is enabled, `token` is a short-lived challenge JWT and
          `requires_2fa=True`. The endpoint should return it to the
          client without setting a session cookie; the client then calls
          `/auth/2fa/challenge` with a code.

        Password-verification failures increment `failed_login_count`;
        the threshold+lockout window are controlled by
        `settings.lockout_threshold` / `lockout_duration_minutes`.

        Raises UnauthorizedError for any failure path. Messaging is
        generic except for the lockout case, which tells the user how
        long to wait (worth the minor enumeration hint — otherwise users
        think their password just silently stopped working).
        """
        user = await self.get_user_by_email(email)
        generic_error = UnauthorizedError("Invalid email or password")

        if user is None or user.password_hash is None:
            logger.info("Login failed: unknown email or no password set")
            raise generic_error

        if user.role != UserRole.THERAPIST:
            logger.info("Login denied: non-therapist role %s", user.role)
            raise generic_error

        now = datetime.now(UTC)
        if user.locked_until is not None and user.locked_until > now:
            remaining = user.locked_until - now
            minutes = max(1, math.ceil(remaining.total_seconds() / 60))
            logger.info("Login denied: account %s locked for %d more min", user.id, minutes)
            raise UnauthorizedError(
                f"Account temporarily locked. Try again in {minutes} minutes."
            )

        if not verify_password(password, user.password_hash):
            user.failed_login_count = (user.failed_login_count or 0) + 1
            threshold = self.settings.lockout_threshold
            if user.failed_login_count >= threshold:
                user.locked_until = now + timedelta(
                    minutes=self.settings.lockout_duration_minutes
                )
                user.failed_login_count = 0
                logger.info(
                    "Account %s locked after %d failed attempts", user.id, threshold
                )
            await self.db_session.flush()
            logger.info("Login failed: password mismatch for %s", user.id)
            raise generic_error

        # Correct password — reset the counters before deciding on 2FA.
        user.failed_login_count = 0
        user.locked_until = None
        await self.db_session.flush()

        if user.totp_enabled_at is not None and user.totp_secret is not None:
            challenge_token, expires_at = self._mint_totp_challenge(user.id)
            logger.info("Therapist %s password verified, 2FA challenge issued", user.id)
            return user, challenge_token, expires_at, True

        token, expires_at = create_access_token(
            user_id=user.id,
            organization_id=user.organization_id,
            audience="therapist",
            settings=self.settings,
        )
        logger.info("Therapist %s logged in", user.id)
        return user, token, expires_at, False

    def _mint_totp_challenge(self, user_id: uuid.UUID) -> tuple[str, datetime]:
        """Create a short-lived JWT that proves password verification.

        Uses a dedicated audience so a challenge token can't be swapped
        in for a real session cookie elsewhere. Kept separate from
        `create_access_token` because the challenge carries no
        organization_id (we haven't committed to a session yet).
        """
        now = datetime.now(UTC)
        ttl = self.settings.totp_challenge_ttl_seconds
        expires_at = now + timedelta(seconds=ttl)
        claims: dict[str, Any] = {
            "sub": str(user_id),
            "aud": TOTP_CHALLENGE_AUDIENCE,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "jti": secrets.token_urlsafe(8),
        }
        token = jwt.encode(
            claims, self.settings.jwt_secret, algorithm=self.settings.jwt_algorithm
        )
        return token, expires_at

    def _decode_totp_challenge(self, challenge_token: str) -> uuid.UUID:
        try:
            raw = jwt.decode(
                challenge_token,
                self.settings.jwt_secret,
                algorithms=[self.settings.jwt_algorithm],
                audience=TOTP_CHALLENGE_AUDIENCE,
            )
        except JWTError as exc:
            raise UnauthorizedError("Invalid or expired 2FA challenge") from exc
        try:
            return uuid.UUID(raw["sub"])
        except (KeyError, ValueError, TypeError) as exc:
            raise UnauthorizedError("Malformed 2FA challenge") from exc

    async def complete_totp_challenge(
        self, challenge_token: str, code: str
    ) -> tuple[User, str, datetime]:
        """Verify a challenge token + TOTP code, mint a real session token."""
        # Local import to avoid circular dependency with src.services.totp_service.
        from src.services.totp_service import TotpService

        user_id = self._decode_totp_challenge(challenge_token)
        user = await self.get_user_by_id(user_id)
        if user.role != UserRole.THERAPIST:
            raise UnauthorizedError("Challenge does not belong to a therapist account")
        if user.totp_enabled_at is None or user.totp_secret is None:
            raise UnauthorizedError("2FA is not enabled for this account")

        totp = TotpService(self.db_session, settings=self.settings)
        if not totp.verify_code(user.totp_secret, code):
            raise UnauthorizedError("Invalid 2FA code")

        token, expires_at = create_access_token(
            user_id=user.id,
            organization_id=user.organization_id,
            audience="therapist",
            settings=self.settings,
        )
        logger.info("Therapist %s completed 2FA challenge", user.id)
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
