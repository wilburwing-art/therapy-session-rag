"""Invite Pydantic schemas."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class InviteRole(StrEnum):
    """Role an invitee will be granted on acceptance."""

    THERAPIST = "therapist"
    ADMIN = "admin"


class InviteCreate(BaseModel):
    """Request body for issuing a new therapist invite."""

    email: EmailStr
    role: InviteRole = InviteRole.THERAPIST


class InviteCreateResponse(BaseModel):
    """Response returned when an invite is issued.

    The raw token is returned once so the inviter can copy/paste the
    accept URL if email delivery fails.
    """

    id: UUID
    email: EmailStr
    role: InviteRole
    token: str = Field(
        ...,
        description=(
            "Raw invite token. Include as `?t={token}` in the accept URL "
            "if you need to share the invite manually."
        ),
    )
    expires_at: datetime


class InviteRead(BaseModel):
    """Invite as surfaced on the team settings page."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    invited_by_user_id: UUID
    email: EmailStr
    role: InviteRole
    expires_at: datetime
    accepted_at: datetime | None = None
    created_at: datetime


class InviteAcceptRequest(BaseModel):
    """Public request body to redeem an invite and set a password."""

    token: str = Field(..., min_length=8)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=255)
