"""Tenant isolation and row-level security helpers."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ForbiddenError, NotFoundError
from src.models.db.user import User


@dataclass
class TenantContext:
    """Context for tenant-scoped operations."""

    organization_id: uuid.UUID
    db_session: AsyncSession

    async def validate_user_in_org(self, user_id: uuid.UUID) -> User:
        """Validate that a user belongs to the tenant's organization.

        Args:
            user_id: The user ID to validate

        Returns:
            The User if valid

        Raises:
            NotFoundError: If user does not exist
            ForbiddenError: If user belongs to a different organization
        """
        result = await self.db_session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise NotFoundError(resource="User", resource_id=str(user_id))

        if user.organization_id != self.organization_id:
            raise ForbiddenError(
                detail="Access denied: user belongs to a different organization"
            )

        return user

    async def validate_users_in_org(self, *user_ids: uuid.UUID) -> list[User]:
        """Validate that multiple users belong to the tenant's organization.

        Args:
            *user_ids: User IDs to validate

        Returns:
            List of validated Users

        Raises:
            NotFoundError: If any user does not exist
            ForbiddenError: If any user belongs to a different organization
        """
        users = []
        for user_id in user_ids:
            user = await self.validate_user_in_org(user_id)
            users.append(user)
        return users

    async def validate_session_access(self, session_id: uuid.UUID) -> None:
        """Validate that a session belongs to the tenant's organization.

        Checks that both patient and therapist belong to the org.

        Args:
            session_id: The session ID to validate

        Raises:
            NotFoundError: If session does not exist
            ForbiddenError: If session's users belong to a different organization
        """
        from src.models.db.session import Session

        result = await self.db_session.execute(
            select(Session).where(Session.id == session_id)
        )
        session = result.scalar_one_or_none()

        if not session:
            raise NotFoundError(resource="Session", resource_id=str(session_id))

        # Validate both patient and therapist belong to org
        await self.validate_users_in_org(session.patient_id, session.therapist_id)
