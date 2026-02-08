"""Organization settings API endpoints."""

from fastapi import APIRouter
from sqlalchemy import select

from src.api.v1.dependencies import Auth
from src.core.database import DbSession
from src.models.db.organization import Organization
from src.models.domain.organization import (
    OrganizationSettingsRead,
    OrganizationSettingsUpdate,
)

router = APIRouter()


@router.get("/settings", response_model=OrganizationSettingsRead)
async def get_organization_settings(
    auth: Auth,
    session: DbSession,
) -> OrganizationSettingsRead:
    """Get organization settings for the authenticated org."""
    result = await session.execute(
        select(Organization).where(Organization.id == auth.organization_id)
    )
    org = result.scalar_one()
    return OrganizationSettingsRead(video_chat_enabled=org.video_chat_enabled)


@router.patch("/settings", response_model=OrganizationSettingsRead)
async def update_organization_settings(
    auth: Auth,
    session: DbSession,
    settings: OrganizationSettingsUpdate,
) -> OrganizationSettingsRead:
    """Update organization settings.

    Note: In production, this should be restricted to admin users only.
    """
    result = await session.execute(
        select(Organization).where(Organization.id == auth.organization_id)
    )
    org = result.scalar_one()

    if settings.video_chat_enabled is not None:
        org.video_chat_enabled = settings.video_chat_enabled

    await session.commit()
    await session.refresh(org)

    return OrganizationSettingsRead(video_chat_enabled=org.video_chat_enabled)
