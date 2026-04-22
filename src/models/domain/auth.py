"""Auth Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    user_id: UUID
    organization_id: UUID
    email: EmailStr
    full_name: str | None = None
    expires_at: datetime


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=255)
    practice_name: str = Field(..., min_length=1, max_length=255)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(..., min_length=8)
    new_password: str = Field(..., min_length=8, max_length=128)


class EmailVerificationConfirm(BaseModel):
    token: str = Field(..., min_length=8)


class RegisterResponse(BaseModel):
    user_id: UUID
    organization_id: UUID
    email: EmailStr
    full_name: str
    practice_name: str
    expires_at: datetime


class CurrentUser(BaseModel):
    """Therapist identity returned from /auth/me."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    email: EmailStr
    role: str
    full_name: str | None = None
    email_verified_at: datetime | None = None


class MagicLinkCreateRequest(BaseModel):
    patient_id: UUID


class MagicLinkCreateResponse(BaseModel):
    token: str = Field(
        ...,
        description="Raw magic-link token. Include as `?t={token}` in the URL sent to the patient.",
    )
    expires_at: datetime


class MagicLinkRedeemRequest(BaseModel):
    token: str = Field(..., min_length=8)


class MagicLinkRedeemResponse(BaseModel):
    patient_id: UUID
    organization_id: UUID
    expires_at: datetime


class CurrentPatient(BaseModel):
    """Patient identity returned from /auth/patient/me."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    email: EmailStr
    full_name: str | None = None
