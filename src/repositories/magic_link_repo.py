"""Repository for magic link operations."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.magic_link import MagicLink


class MagicLinkRepository:
    """Data access for patient magic links."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        patient_id: uuid.UUID,
        created_by_user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> MagicLink:
        link = MagicLink(
            patient_id=patient_id,
            created_by_user_id=created_by_user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(link)
        await self.session.flush()
        await self.session.refresh(link)
        return link

    async def get_by_token_hash(self, token_hash: str) -> MagicLink | None:
        result = await self.session.execute(
            select(MagicLink).where(MagicLink.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def mark_used(self, link_id: uuid.UUID) -> None:
        await self.session.execute(
            update(MagicLink)
            .where(MagicLink.id == link_id)
            .values(used_at=datetime.now(UTC))
        )
