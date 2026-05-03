"""Repository for therapist invite operations."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.therapist_invite import TherapistInvite, TherapistInviteRole


class TherapistInviteRepository:
    """Data access for therapist invites."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        organization_id: uuid.UUID,
        invited_by_user_id: uuid.UUID,
        email: str,
        role: TherapistInviteRole,
        token_hash: str,
        expires_at: datetime,
    ) -> TherapistInvite:
        invite = TherapistInvite(
            organization_id=organization_id,
            invited_by_user_id=invited_by_user_id,
            email=email,
            role=role,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(invite)
        await self.session.flush()
        await self.session.refresh(invite)
        return invite

    async def get_by_token_hash(self, token_hash: str) -> TherapistInvite | None:
        result = await self.session.execute(
            select(TherapistInvite).where(TherapistInvite.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_org(
        self,
        invite_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> TherapistInvite | None:
        result = await self.session.execute(
            select(TherapistInvite).where(
                TherapistInvite.id == invite_id,
                TherapistInvite.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_org(self, organization_id: uuid.UUID) -> list[TherapistInvite]:
        result = await self.session.execute(
            select(TherapistInvite)
            .where(TherapistInvite.organization_id == organization_id)
            .order_by(TherapistInvite.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_pending_for_org_and_email(
        self,
        organization_id: uuid.UUID,
        email: str,
    ) -> TherapistInvite | None:
        """Return an unaccepted, unexpired invite for (org, email), if any."""
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(TherapistInvite).where(
                TherapistInvite.organization_id == organization_id,
                TherapistInvite.email == email,
                TherapistInvite.accepted_at.is_(None),
                TherapistInvite.expires_at > now,
            )
        )
        return result.scalar_one_or_none()

    async def mark_accepted(self, invite_id: uuid.UUID) -> None:
        await self.session.execute(
            update(TherapistInvite)
            .where(TherapistInvite.id == invite_id)
            .values(accepted_at=datetime.now(UTC))
        )

    async def revoke(self, invite_id: uuid.UUID) -> None:
        """Delete a pending invite. Callers must verify it isn't accepted."""
        await self.session.execute(delete(TherapistInvite).where(TherapistInvite.id == invite_id))
