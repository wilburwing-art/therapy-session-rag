"""User Pydantic schemas."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRole(StrEnum):
    """User role enumeration."""

    THERAPIST = "therapist"
    PATIENT = "patient"
    ADMIN = "admin"


class UserBase(BaseModel):
    """Base schema for user data."""

    email: EmailStr = Field(..., description="User email address")
    role: UserRole = Field(..., description="User role")


class UserCreate(UserBase):
    """Schema for creating a new user."""

    organization_id: UUID = Field(..., description="Organization the user belongs to")


class UserRead(UserBase):
    """Schema for reading user data."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="User unique identifier")
    organization_id: UUID = Field(..., description="Organization the user belongs to")
    full_name: str | None = Field(None, description="User's full name")
    email_verified_at: datetime | None = Field(
        None, description="When the user's email was verified"
    )
    created_at: datetime = Field(..., description="When the user was created")
    updated_at: datetime = Field(..., description="When the user was last updated")


class PatientCreate(BaseModel):
    """Schema a therapist uses to onboard a new patient."""

    email: EmailStr = Field(..., description="Patient's email address")
    full_name: str = Field(..., min_length=1, max_length=255)
