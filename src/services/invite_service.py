"""Therapist invite service.

Issue, list, revoke, and accept invites for new therapists joining a
practice. Tokens are stored hashed; the plaintext is returned once at
issue time so the caller can email it or copy it. Acceptance creates a
therapist user with a password hash and mints a therapist session JWT
the endpoint places in a cookie.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import create_access_token, hash_password
from src.core.config import Settings, get_settings
from src.core.exceptions import ConflictError, NotFoundError, UnauthorizedError
from src.models.db.therapist_invite import TherapistInvite, TherapistInviteRole
from src.models.db.user import User, UserRole
from src.repositories.therapist_invite_repo import TherapistInviteRepository
from src.services.auth_service import AuthService

logger = logging.getLogger(__name__)

_TOKEN_BYTES = 32
_INVITE_TTL = timedelta(days=7)


class InviteService:
    """Issue and consume therapist invites."""

    def __init__(
        self,
        db_session: AsyncSession,
        settings: Settings | None = None,
    ) -> None:
        self.db_session = db_session
        self.settings = settings or get_settings()
        self.repo = TherapistInviteRepository(db_session)
        self.auth_service = AuthService(db_session, settings=self.settings)

    async def issue_invite(
        self,
        organization_id: uuid.UUID,
        inviter_id: uuid.UUID,
        email: str,
        role: TherapistInviteRole = TherapistInviteRole.THERAPIST,
    ) -> tuple[TherapistInvite, str, datetime]:
        """Issue an invite. Rejects if the email is already a user anywhere
        or already has a pending invite in this organization.

        Returns (invite, raw_token, expires_at). Callers persist only the
        hashed token in the database; the raw token goes to the invitee.
        """
        normalized_email = email.lower().strip()
        existing_user = await self.auth_service.get_user_by_email(normalized_email)
        if existing_user is not None:
            raise ConflictError(detail="A user with this email already exists")

        pending = await self.repo.get_pending_for_org_and_email(
            organization_id=organization_id,
            email=normalized_email,
        )
        if pending is not None:
            raise ConflictError(detail="A pending invite already exists for this email")

        raw_token = secrets.token_urlsafe(_TOKEN_BYTES)
        token_hash = self._hash_token(raw_token)
        expires_at = datetime.now(UTC) + _INVITE_TTL

        invite = await self.repo.create(
            organization_id=organization_id,
            invited_by_user_id=inviter_id,
            email=normalized_email,
            role=role,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        logger.info(
            "Therapist invite issued: org=%s invitee=%s role=%s expires=%s",
            organization_id,
            normalized_email,
            role.value,
            expires_at.isoformat(),
        )
        return invite, raw_token, expires_at

    async def list_invites(self, organization_id: uuid.UUID) -> list[TherapistInvite]:
        """List every invite (pending and accepted) for an organization."""
        return await self.repo.list_for_org(organization_id)

    async def revoke_invite(
        self,
        organization_id: uuid.UUID,
        invite_id: uuid.UUID,
    ) -> None:
        """Delete a pending invite. Raises NotFoundError if the invite
        doesn't exist for this org, or ConflictError if it's already
        accepted (deletion would orphan the user record).
        """
        invite = await self.repo.get_by_id_for_org(invite_id, organization_id)
        if invite is None:
            raise NotFoundError(resource="Invite", resource_id=str(invite_id))
        if invite.accepted_at is not None:
            raise ConflictError(detail="Cannot revoke an invite that has already been accepted")
        await self.repo.revoke(invite_id)
        logger.info("Therapist invite %s revoked by org %s", invite_id, organization_id)

    async def accept_invite(
        self,
        raw_token: str,
        password: str,
        full_name: str,
    ) -> tuple[User, str, datetime]:
        """Redeem an invite and create a therapist user.

        Returns (user, jwt, jwt_expires_at). Raises UnauthorizedError
        for invalid/expired/already-accepted tokens. Raises ConflictError
        if the invite's email has been claimed by another user in the
        meantime (race condition — rare but possible).
        """
        if len(password) < 8:
            raise ConflictError(detail="Password must be at least 8 characters")

        token_hash = self._hash_token(raw_token)
        invite = await self.repo.get_by_token_hash(token_hash)
        generic = UnauthorizedError("Invalid or expired invite")
        if invite is None:
            raise generic
        if invite.accepted_at is not None:
            logger.info("Invite %s already accepted", invite.id)
            raise generic
        if invite.expires_at <= datetime.now(UTC):
            logger.info("Invite %s expired", invite.id)
            raise generic

        # Guard against the email having been claimed since the invite
        # was issued.
        existing_user = await self.auth_service.get_user_by_email(invite.email)
        if existing_user is not None:
            raise ConflictError(detail="A user with this email already exists")

        user = User(
            organization_id=invite.organization_id,
            email=invite.email,
            role=UserRole.THERAPIST,
            full_name=full_name,
            password_hash=hash_password(password),
        )
        self.db_session.add(user)
        await self.db_session.flush()
        await self.db_session.refresh(user)

        await self.repo.mark_accepted(invite.id)

        token, expires_at = create_access_token(
            user_id=user.id,
            organization_id=user.organization_id,
            audience="therapist",
            settings=self.settings,
        )
        logger.info(
            "Invite %s accepted: user=%s org=%s",
            invite.id,
            user.id,
            user.organization_id,
        )
        return user, token, expires_at

    @staticmethod
    def _hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
