"""Consent Pydantic schemas."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConsentType(StrEnum):
    """Types of consent that can be granted."""

    RECORDING = "recording"
    TRANSCRIPTION = "transcription"
    AI_ANALYSIS = "ai_analysis"


class ConsentStatus(StrEnum):
    """Status of a consent record."""

    GRANTED = "granted"
    REVOKED = "revoked"


class ConsentGrant(BaseModel):
    """Schema for granting consent."""

    patient_id: UUID = Field(..., description="ID of the patient granting consent")
    therapist_id: UUID = Field(..., description="ID of the therapist")
    consent_type: ConsentType = Field(..., description="Type of consent being granted")
    consent_metadata: dict[str, Any] | None = Field(
        default=None, description="Optional metadata about the consent"
    )


class ConsentRevoke(BaseModel):
    """Schema for revoking consent."""

    patient_id: UUID = Field(..., description="ID of the patient")
    therapist_id: UUID = Field(..., description="ID of the therapist")
    consent_type: ConsentType = Field(..., description="Type of consent being revoked")
    consent_metadata: dict[str, Any] | None = Field(
        default=None, description="Optional metadata about the revocation"
    )


class ConsentRead(BaseModel):
    """Schema for reading consent data."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Consent record unique identifier")
    patient_id: UUID = Field(..., description="ID of the patient")
    therapist_id: UUID = Field(..., description="ID of the therapist")
    consent_type: ConsentType = Field(..., description="Type of consent")
    status: ConsentStatus = Field(..., description="Current status of the consent")
    granted_at: datetime = Field(..., description="When consent was granted")
    revoked_at: datetime | None = Field(None, description="When consent was revoked")
    ip_address: str | None = Field(None, description="IP address of the request")
    user_agent: str | None = Field(None, description="User agent of the request")
    consent_metadata: dict[str, Any] | None = Field(None, description="Additional metadata")


class ConsentCheck(BaseModel):
    """Schema for checking consent status."""

    patient_id: UUID = Field(..., description="ID of the patient")
    consent_type: ConsentType = Field(..., description="Type of consent to check")
    has_consent: bool = Field(..., description="Whether active consent exists")
    consent: ConsentRead | None = Field(
        None, description="The active consent record if it exists"
    )


class ConsentAuditEntry(BaseModel):
    """Schema for consent audit log entries."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Consent record unique identifier")
    consent_type: ConsentType = Field(..., description="Type of consent")
    status: ConsentStatus = Field(..., description="Status at this point in time")
    granted_at: datetime = Field(..., description="When consent was granted")
    revoked_at: datetime | None = Field(None, description="When consent was revoked")
    ip_address: str | None = Field(None, description="IP address of the request")
    user_agent: str | None = Field(None, description="User agent of the request")
