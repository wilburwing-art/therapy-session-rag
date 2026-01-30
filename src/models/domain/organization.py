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
    created_at: datetime = Field(..., description="When the organization was created")
    updated_at: datetime = Field(..., description="When the organization was last updated")
