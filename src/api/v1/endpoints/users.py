"""Users API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from src.api.v1.dependencies import Auth
from src.core.database import DbSession
from src.models.db.user import User
from src.models.domain.user import UserRead, UserRole

router = APIRouter()


@router.get("", response_model=list[UserRead])
async def list_users(
    auth: Auth,
    session: DbSession,
    role: Annotated[UserRole | None, Query(description="Filter by user role")] = None,
) -> list[UserRead]:
    """List users in the authenticated organization.

    Optionally filter by role (therapist, patient, admin).
    Only returns users from the same organization as the API key.
    """
    query = select(User).where(User.organization_id == auth.organization_id)

    if role is not None:
        query = query.where(User.role == role)

    query = query.order_by(User.email)

    result = await session.execute(query)
    users = result.scalars().all()

    return [UserRead.model_validate(user) for user in users]
