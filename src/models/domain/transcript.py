"""Transcript Pydantic schemas."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TranscriptionJobStatus(StrEnum):
    """Status of a transcription job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TranscriptSegment(BaseModel):
    """Schema for a transcript segment.

    Represents a portion of the transcript with speaker
    information and timing.
    """

    text: str = Field(..., description="The transcribed text")
    start_time: float = Field(..., description="Start time in seconds")
    end_time: float = Field(..., description="End time in seconds")
    speaker: str | None = Field(None, description="Speaker identifier")
    confidence: float | None = Field(None, description="Confidence score (0-1)")
    words: list[dict[str, Any]] | None = Field(
        None, description="Word-level details"
    )


class TranscriptionJobCreate(BaseModel):
    """Schema for creating a transcription job."""

    session_id: UUID = Field(..., description="ID of the session to transcribe")


class TranscriptionJobRead(BaseModel):
    """Schema for reading transcription job data."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Job unique identifier")
    session_id: UUID = Field(..., description="ID of the session")
    status: TranscriptionJobStatus = Field(..., description="Current job status")
    started_at: datetime | None = Field(None, description="When processing started")
    completed_at: datetime | None = Field(None, description="When processing completed")
    error_message: str | None = Field(None, description="Error message if failed")
    retry_count: int = Field(..., description="Number of retry attempts")
    created_at: datetime = Field(..., description="When the job was created")


class TranscriptCreate(BaseModel):
    """Schema for creating a transcript."""

    session_id: UUID = Field(..., description="ID of the session")
    job_id: UUID | None = Field(None, description="ID of the transcription job")
    full_text: str = Field(..., description="Complete transcript text")
    segments: list[TranscriptSegment] = Field(
        default_factory=list, description="Transcript segments"
    )
    word_count: int | None = Field(None, description="Total word count")
    duration_seconds: float | None = Field(None, description="Audio duration")
    language: str | None = Field(None, description="Detected language code")
    confidence: float | None = Field(None, description="Overall confidence score")
    transcript_metadata: dict[str, Any] | None = Field(
        None, description="Additional metadata"
    )


class TranscriptRead(BaseModel):
    """Schema for reading transcript data."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Transcript unique identifier")
    session_id: UUID = Field(..., description="ID of the session")
    job_id: UUID | None = Field(None, description="ID of the transcription job")
    full_text: str = Field(..., description="Complete transcript text")
    segments: list[dict[str, Any]] = Field(..., description="Transcript segments")
    word_count: int | None = Field(None, description="Total word count")
    duration_seconds: float | None = Field(None, description="Audio duration")
    language: str | None = Field(None, description="Detected language code")
    confidence: float | None = Field(None, description="Overall confidence score")
    transcript_metadata: dict[str, Any] | None = Field(
        None, description="Additional metadata"
    )
    created_at: datetime = Field(..., description="When the transcript was created")
    updated_at: datetime = Field(..., description="When the transcript was updated")


class TranscriptSummary(BaseModel):
    """Schema for transcript list items."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Transcript unique identifier")
    session_id: UUID = Field(..., description="ID of the session")
    word_count: int | None = Field(None, description="Total word count")
    duration_seconds: float | None = Field(None, description="Audio duration")
    language: str | None = Field(None, description="Detected language code")
    created_at: datetime = Field(..., description="When the transcript was created")


class TranscriptionStatusResponse(BaseModel):
    """Response for checking transcription status."""

    session_id: UUID = Field(..., description="ID of the session")
    has_transcript: bool = Field(..., description="Whether transcript exists")
    job_status: TranscriptionJobStatus | None = Field(
        None, description="Status of most recent job"
    )
    error_message: str | None = Field(None, description="Error if failed")
