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
