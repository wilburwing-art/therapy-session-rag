"""Patient magic-link authentication service.

A therapist calls `issue_link` for a patient; the service returns a
raw token that can be emailed as a URL fragment. The patient later
calls `consume_link`, which validates the token, marks it used, and
returns a patient-audience session JWT.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import create_access_token
from src.core.config import Settings, get_settings
from src.core.exceptions import NotFoundError, UnauthorizedError
from src.models.db.user import User, UserRole
from src.repositories.magic_link_repo import MagicLinkRepository
from src.services.auth_service import AuthService

logger = logging.getLogger(__name__)

_TOKEN_BYTES = 32


class MagicLinkService:
    """Issue and consume one-time patient magic links."""

    def __init__(
        self,
        db_session: AsyncSession,
        settings: Settings | None = None,
    ) -> None:
        self.db_session = db_session
        self.settings = settings or get_settings()
        self.repo = MagicLinkRepository(db_session)
        self.auth_service = AuthService(db_session, settings=self.settings)

    async def issue_link(
        self,
        patient_id: uuid.UUID,
        created_by_user_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> tuple[str, datetime]:
        """Issue a magic link for a patient.

        Verifies the patient exists in the therapist's org and has the
        patient role. Returns (raw_token, expires_at); persist the
        hash only.
        """
        patient = await self.auth_service.get_user_by_id(patient_id)
        if patient.role != UserRole.PATIENT:
            raise UnauthorizedError("Target user is not a patient")
        if patient.organization_id != organization_id:
            raise NotFoundError(resource="Patient", resource_id=str(patient_id))

        raw_token = secrets.token_urlsafe(_TOKEN_BYTES)
        token_hash = self._hash_token(raw_token)
        expires_at = datetime.now(UTC) + timedelta(
            seconds=self.settings.magic_link_ttl_seconds
        )

        await self.repo.create(
            patient_id=patient_id,
            created_by_user_id=created_by_user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        logger.info(
            "Magic link issued for patient %s by %s (expires %s)",
            patient_id,
            created_by_user_id,
            expires_at.isoformat(),
        )
        return raw_token, expires_at

    async def consume_link(self, raw_token: str) -> tuple[User, str, datetime]:
        """Redeem a magic link and mint a patient session token.

        Returns (patient_user, jwt, jwt_expires_at). Raises
        UnauthorizedError for any invalid, expired, or already-used
        token — callers must not leak which case it was.
        """
        token_hash = self._hash_token(raw_token)
        link = await self.repo.get_by_token_hash(token_hash)
        generic = UnauthorizedError("Invalid or expired link")
        if link is None:
            raise generic
        if link.used_at is not None:
            logger.info("Magic link %s already used", link.id)
            raise generic
        if link.expires_at <= datetime.now(UTC):
            logger.info("Magic link %s expired", link.id)
            raise generic

        patient = await self.auth_service.get_user_by_id(link.patient_id)
        if patient.role != UserRole.PATIENT:
            logger.warning(
                "Magic link %s pointed at non-patient user %s", link.id, patient.id
            )
            raise generic

        await self.repo.mark_used(link.id)

        token, expires_at = create_access_token(
            user_id=patient.id,
            organization_id=patient.organization_id,
            audience="patient",
            settings=self.settings,
        )
        logger.info("Patient %s authenticated via magic link %s", patient.id, link.id)
        return patient, token, expires_at

    @staticmethod
    def _hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
