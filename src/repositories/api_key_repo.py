"""Repository for API key operations."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.api_key import ApiKey


class ApiKeyRepository:
    """Repository for API key database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all_active(self) -> list[ApiKey]:
        """Get all active API keys.

        Returns:
            List of active API keys
        """
        result = await self.session.execute(
            select(ApiKey).where(ApiKey.is_active == True)  # noqa: E712
        )
        return list(result.scalars().all())

    async def get_by_id(self, api_key_id: uuid.UUID) -> ApiKey | None:
        """Get an API key by ID.

        Args:
            api_key_id: The API key ID

        Returns:
            The API key if found, None otherwise
        """
        result = await self.session.execute(
            select(ApiKey).where(ApiKey.id == api_key_id)
        )
        return result.scalar_one_or_none()

    async def get_active_by_organization(
        self, organization_id: uuid.UUID
    ) -> list[ApiKey]:
        """Get all active API keys for an organization.

        Args:
            organization_id: The organization ID

        Returns:
            List of active API keys for the organization
        """
        result = await self.session.execute(
            select(ApiKey).where(
                ApiKey.organization_id == organization_id,
                ApiKey.is_active == True,  # noqa: E712
            )
        )
        return list(result.scalars().all())

    async def create(self, api_key: ApiKey) -> ApiKey:
        """Create a new API key.

        Args:
            api_key: The API key to create

        Returns:
            The created API key
        """
        self.session.add(api_key)
        await self.session.flush()
        await self.session.refresh(api_key)
        return api_key

    async def update_last_used(self, api_key_id: uuid.UUID) -> None:
        """Update the last_used_at timestamp for an API key.

        Args:
            api_key_id: The API key ID
        """
        await self.session.execute(
            update(ApiKey)
            .where(ApiKey.id == api_key_id)
            .values(last_used_at=datetime.now(UTC))
        )

    async def revoke(self, api_key_id: uuid.UUID) -> bool:
        """Revoke an API key.

        Args:
            api_key_id: The API key ID

        Returns:
            True if the key was revoked, False if not found
        """
        cursor_result = await self.session.execute(
            update(ApiKey)
            .where(ApiKey.id == api_key_id, ApiKey.is_active == True)  # noqa: E712
            .values(is_active=False, revoked_at=datetime.now(UTC))
        )
        # For UPDATE statements, rowcount indicates affected rows
        rowcount = getattr(cursor_result, "rowcount", 0)
        return bool(rowcount and rowcount > 0)
