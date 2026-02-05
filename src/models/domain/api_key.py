"""API Key Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyBase(BaseModel):
    """Base schema for API key data."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable name for the API key",
    )


class ApiKeyCreate(ApiKeyBase):
    """Schema for creating a new API key."""

    organization_id: UUID = Field(..., description="Organization this key belongs to")


class ApiKeyCreateResponse(ApiKeyBase):
    """Schema returned when creating an API key.

    This is the ONLY time the plaintext key is returned.
    Store it securely - it cannot be retrieved again.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="API key unique identifier")
    organization_id: UUID = Field(..., description="Organization this key belongs to")
    key: str = Field(
        ...,
        description="The API key - store this securely, it will not be shown again",
    )
    created_at: datetime = Field(..., description="When the key was created")


class ApiKeyRead(ApiKeyBase):
    """Schema for reading API key data (without the actual key)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="API key unique identifier")
    organization_id: UUID = Field(..., description="Organization this key belongs to")
    is_active: bool = Field(..., description="Whether the key is active")
    last_used_at: datetime | None = Field(None, description="When the key was last used")
    revoked_at: datetime | None = Field(None, description="When the key was revoked")
    created_at: datetime = Field(..., description="When the key was created")
    updated_at: datetime = Field(..., description="When the key was last updated")


class ApiKeyRevoke(BaseModel):
    """Schema for revoking an API key."""

    id: UUID = Field(..., description="API key to revoke")
