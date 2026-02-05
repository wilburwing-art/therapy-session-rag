"""Transcript database models."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.db.session import Session
    from src.models.db.session_chunk import SessionChunk


class TranscriptionJobStatus(enum.StrEnum):
    """Status of a transcription job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TranscriptionJob(Base, TimestampMixin):
    """Tracks the status of transcription jobs.

    Created when a transcription request is submitted and updated
    throughout the processing lifecycle.
    """

    __tablename__ = "transcription_jobs"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[TranscriptionJobStatus] = mapped_column(
        Enum(TranscriptionJobStatus, name="transcription_job_status"),
        nullable=False,
        default=TranscriptionJobStatus.PENDING,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    external_job_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    job_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
    )

    # Relationships
    session: Mapped["Session"] = relationship(
        back_populates="transcription_jobs",
        lazy="selectin",
    )


class Transcript(Base, TimestampMixin):
    """Stores the full transcript and segments for a session.

    Contains both the full text and structured segments with
    speaker information and timestamps.
    """

    __tablename__ = "transcripts"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transcription_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    full_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    segments: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    word_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    duration_seconds: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    language: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )
    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    transcript_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
    )

    # Relationships
    session: Mapped["Session"] = relationship(
        back_populates="transcript",
        lazy="selectin",
    )
    job: Mapped["TranscriptionJob | None"] = relationship(
        lazy="selectin",
    )
    chunks: Mapped[list["SessionChunk"]] = relationship(
        back_populates="transcript",
        lazy="selectin",
    )
