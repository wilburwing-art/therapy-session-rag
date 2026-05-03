"""TOTP (RFC 6238) second-factor service for therapist accounts.

Flow:
  1. `enroll(user_id)` generates a random Base32 secret, stores it
     encrypted in `users.totp_pending_secret`, and returns the
     otpauth:// provisioning URI plus the raw secret (so a user can
     manually type it if scanning a QR fails).
  2. User scans the URI (or types the secret) into their authenticator
     and submits a 6-digit code to `activate(user_id, code)`. We verify
     the code against the pending secret; on success we promote
     `totp_pending_secret` to `totp_secret`, stamp `totp_enabled_at`,
     and clear the pending slot.
  3. Login checks `user.totp_enabled_at`; if set, issue a challenge
     instead of a session token. The client calls `verify_code` on the
     challenge endpoint.
  4. `disable(user_id, code)` verifies a code one last time before
     clearing the stored secret.

Secrets are encrypted at rest via `src.core.crypto.encrypt_secret`. The
encryption key is shared across all secrets, so rotating it invalidates
every enrollment — ops should plan disables + re-enrolls around a rotation.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

import pyotp
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.crypto import decrypt_secret, encrypt_secret
from src.core.exceptions import ConflictError, UnauthorizedError
from src.services.auth_service import AuthService

logger = logging.getLogger(__name__)


class TotpService:
    """Enrollment and verification for TOTP 2FA."""

    def __init__(
        self,
        db_session: AsyncSession,
        settings: Settings | None = None,
    ) -> None:
        self.db_session = db_session
        self.settings = settings or get_settings()
        self._auth_service = AuthService(db_session, settings=self.settings)

    async def enroll(self, user_id: uuid.UUID) -> tuple[str, str]:
        """Start enrollment for a user.

        Returns (provisioning_uri, raw_secret). The raw secret is
        returned so the user can transcribe it manually if scanning
        the QR fails. `totp_pending_secret` is stored encrypted.

        Overwrites any existing pending secret — enrollment is not
        durable until `activate()` runs.
        """
        user = await self._auth_service.get_user_by_id(user_id)
        if user.totp_enabled_at is not None:
            raise ConflictError(detail="2FA is already enabled for this account")

        raw_secret = pyotp.random_base32()
        totp = pyotp.TOTP(raw_secret)
        provisioning_uri = totp.provisioning_uri(
            name=user.email,
            issuer_name=self.settings.totp_issuer,
        )

        user.totp_pending_secret = encrypt_secret(raw_secret, settings=self.settings)
        await self.db_session.flush()
        logger.info("TOTP enrollment started for user %s", user.id)
        return provisioning_uri, raw_secret

    async def activate(self, user_id: uuid.UUID, code: str) -> None:
        """Verify the enrollment code and promote pending → active."""
        user = await self._auth_service.get_user_by_id(user_id)
        if user.totp_enabled_at is not None:
            raise ConflictError(detail="2FA is already enabled for this account")
        if user.totp_pending_secret is None:
            raise ConflictError(detail="No pending 2FA enrollment to activate")

        secret = decrypt_secret(user.totp_pending_secret, settings=self.settings)
        totp = pyotp.TOTP(secret)
        if not totp.verify(code, valid_window=1):
            raise UnauthorizedError("Invalid 2FA code")

        # Keep the encrypted form on the record; we already know it's valid.
        user.totp_secret = user.totp_pending_secret
        user.totp_pending_secret = None
        user.totp_enabled_at = datetime.now(UTC)
        await self.db_session.flush()
        logger.info("TOTP activated for user %s", user.id)

    def verify_code(self, user_totp_secret: str | None, code: str) -> bool:
        """Verify a 6-digit TOTP code against a user's stored secret.

        Takes the encrypted secret directly so challenge-completion can
        run without a fresh DB lookup when the caller already has the
        User object.
        """
        if not user_totp_secret:
            return False
        try:
            secret = decrypt_secret(user_totp_secret, settings=self.settings)
        except Exception as exc:  # broad: Fernet raises InvalidToken + binascii errors
            logger.warning("Failed to decrypt TOTP secret: %s", exc)
            return False
        totp = pyotp.TOTP(secret)
        return bool(totp.verify(code, valid_window=1))

    async def disable(self, user_id: uuid.UUID, code: str) -> None:
        """Disable 2FA after verifying a current code.

        Requires the caller to prove current possession of the authenticator —
        without that, a stolen session cookie could permanently remove 2FA.
        """
        user = await self._auth_service.get_user_by_id(user_id)
        if user.totp_enabled_at is None or user.totp_secret is None:
            raise ConflictError(detail="2FA is not enabled for this account")

        if not self.verify_code(user.totp_secret, code):
            raise UnauthorizedError("Invalid 2FA code")

        user.totp_secret = None
        user.totp_enabled_at = None
        user.totp_pending_secret = None
        await self.db_session.flush()
        logger.info("TOTP disabled for user %s", user.id)
