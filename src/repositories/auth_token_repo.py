"""Repository for short-lived auth tokens."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.auth_token import AuthToken, AuthTokenPurpose


class AuthTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        user_id: uuid.UUID,
        purpose: AuthTokenPurpose,
        token_hash: str,
        expires_at: datetime,
    ) -> AuthToken:
        token = AuthToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(token)
        await self.session.flush()
        await self.session.refresh(token)
        return token

    async def get_by_hash(
        self, token_hash: str, purpose: AuthTokenPurpose
    ) -> AuthToken | None:
        result = await self.session.execute(
            select(AuthToken).where(
                AuthToken.token_hash == token_hash,
                AuthToken.purpose == purpose,
            )
        )
        return result.scalar_one_or_none()

    async def mark_used(self, token_id: uuid.UUID) -> None:
        await self.session.execute(
            update(AuthToken)
            .where(AuthToken.id == token_id)
            .values(used_at=datetime.now(UTC))
        )
