"""Organization Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OrganizationBase(BaseModel):
    """Base schema for organization data."""

    name: str = Field(..., min_length=1, max_length=255, description="Organization name")


class OrganizationCreate(OrganizationBase):
    """Schema for creating a new organization."""

    pass


class OrganizationRead(OrganizationBase):
    """Schema for reading organization data."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Organization unique identifier")
    video_chat_enabled: bool = Field(
        default=False, description="Whether video chat is enabled for this org"
    )
    created_at: datetime = Field(..., description="When the organization was created")
    updated_at: datetime = Field(..., description="When the organization was last updated")
    disabled_at: datetime | None = Field(
        default=None, description="When an admin suspended the organization, if any"
    )


class OrganizationAdminView(BaseModel):
    """Operator-panel summary row for an organization."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime
    subscription_status: str
    disabled_at: datetime | None = None
    user_count: int = 0
    session_count: int = 0


class OrganizationUserView(BaseModel):
    """User row inside the admin org-detail view."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role: str
    full_name: str | None = None
    created_at: datetime
    email_verified_at: datetime | None = None


class OrganizationSessionCountsByStatus(BaseModel):
    """Session count bucketed by pipeline status, for the admin detail view."""

    pending: int = 0
    uploaded: int = 0
    transcribing: int = 0
    embedding: int = 0
    ready: int = 0
    failed: int = 0


class OrganizationAdminDetail(BaseModel):
    """Full admin-panel detail payload for a single organization."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime
    subscription_status: str
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    trial_ends_at: datetime | None = None
    current_period_end: datetime | None = None
    disabled_at: datetime | None = None
    users: list[OrganizationUserView] = Field(default_factory=list)
    session_counts: OrganizationSessionCountsByStatus = Field(
        default_factory=lambda: OrganizationSessionCountsByStatus()
    )


class AdminAuditEventItem(BaseModel):
    """Single event row returned by the admin audit log endpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_name: str
    event_category: str
    organization_id: UUID
    actor_id: UUID | None = None
    session_id: UUID | None = None
    event_timestamp: datetime
    properties: dict[str, object] | None = None


class AdminAuditEventPage(BaseModel):
    """Cursor-paginated audit event page."""

    events: list[AdminAuditEventItem]
    next_cursor: str | None = None
    has_more: bool = False


class OrganizationSettingsRead(BaseModel):
    """Schema for reading organization settings."""

    model_config = ConfigDict(from_attributes=True)

    video_chat_enabled: bool = Field(
        ..., description="Whether video chat is enabled for this org"
    )


class OrganizationSettingsUpdate(BaseModel):
    """Schema for updating organization settings."""

    video_chat_enabled: bool | None = Field(
        None, description="Enable/disable video chat for this org"
    )
