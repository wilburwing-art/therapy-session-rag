"""Session Pydantic schemas."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SessionStatus(StrEnum):
    """Status of a therapy session recording."""

    PENDING = "pending"
    UPLOADED = "uploaded"
    TRANSCRIBING = "transcribing"
    EMBEDDING = "embedding"
    READY = "ready"
    FAILED = "failed"


class SessionCreate(BaseModel):
    """Schema for creating a new session."""

    patient_id: UUID = Field(..., description="ID of the patient")
    therapist_id: UUID = Field(..., description="ID of the therapist")
    consent_id: UUID = Field(..., description="ID of the active consent record")
    session_date: datetime = Field(..., description="Date and time of the session")
    session_metadata: dict[str, Any] | None = Field(
        default=None, description="Optional metadata about the session"
    )


class SessionUpdate(BaseModel):
    """Schema for updating a session."""

    status: SessionStatus | None = Field(None, description="New status")
    recording_path: str | None = Field(None, description="S3 key of the recording")
    recording_duration_seconds: int | None = Field(
        None, description="Duration in seconds"
    )
    error_message: str | None = Field(None, description="Error message if failed")
    session_metadata: dict[str, Any] | None = Field(None, description="Updated metadata")


class SessionRead(BaseModel):
    """Schema for reading session data."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Session unique identifier")
    patient_id: UUID = Field(..., description="ID of the patient")
    therapist_id: UUID = Field(..., description="ID of the therapist")
    consent_id: UUID = Field(..., description="ID of the consent record")
    session_date: datetime = Field(..., description="Date and time of the session")
    recording_path: str | None = Field(None, description="S3 key of the recording")
    recording_duration_seconds: int | None = Field(None, description="Duration in seconds")
    status: SessionStatus = Field(..., description="Current processing status")
    error_message: str | None = Field(None, description="Error message if failed")
    session_metadata: dict[str, Any] | None = Field(None, description="Session metadata")
    created_at: datetime = Field(..., description="When the session was created")
    updated_at: datetime = Field(..., description="When the session was last updated")


class SessionSummary(BaseModel):
    """Schema for session list items (less detail than full read)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Session unique identifier")
    patient_id: UUID = Field(..., description="ID of the patient")
    therapist_id: UUID = Field(..., description="ID of the therapist")
    session_date: datetime = Field(..., description="Date and time of the session")
    status: SessionStatus = Field(..., description="Current processing status")
    recording_duration_seconds: int | None = Field(None, description="Duration in seconds")
    created_at: datetime = Field(..., description="When the session was created")


class SessionUploadResponse(BaseModel):
    """Response after uploading a recording."""

    session_id: UUID = Field(..., description="ID of the session")
    recording_path: str = Field(..., description="S3 key where recording is stored")
    file_size: int = Field(..., description="Size of the uploaded file in bytes")
    status: SessionStatus = Field(..., description="New session status")


class SessionFilter(BaseModel):
    """Schema for filtering sessions."""

    patient_id: UUID | None = Field(None, description="Filter by patient")
    therapist_id: UUID | None = Field(None, description="Filter by therapist")
    status: SessionStatus | None = Field(None, description="Filter by status")
    date_from: datetime | None = Field(None, description="Filter sessions after this date")
    date_to: datetime | None = Field(None, description="Filter sessions before this date")
