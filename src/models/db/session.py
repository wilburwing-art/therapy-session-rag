"""Session database model."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.db.consent import Consent
    from src.models.db.session_chunk import SessionChunk
    from src.models.db.transcript import Transcript, TranscriptionJob
    from src.models.db.user import User


class SessionStatus(enum.StrEnum):
    """Status of a therapy session recording."""

    PENDING = "pending"
    UPLOADED = "uploaded"
    TRANSCRIBING = "transcribing"
    EMBEDDING = "embedding"
    READY = "ready"
    FAILED = "failed"


class SessionType(enum.StrEnum):
    """Type of session recording method."""

    UPLOAD = "upload"  # Traditional file upload
    VIDEO_CALL = "video_call"  # Live video call recorded client-side


class Session(Base, TimestampMixin):
    """Session model for tracking therapy session recordings.

    Represents a single therapy session recording with its processing state.
    """

    __tablename__ = "sessions"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    therapist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    consent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("consents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    session_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    recording_path: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    recording_duration_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status"),
        nullable=False,
        default=SessionStatus.PENDING,
    )
    session_type: Mapped[SessionType] = mapped_column(
        Enum(SessionType, name="session_type"),
        nullable=False,
        default=SessionType.UPLOAD,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    session_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
    )

    # Relationships
    patient: Mapped["User"] = relationship(
        foreign_keys=[patient_id],
        lazy="selectin",
    )
    therapist: Mapped["User"] = relationship(
        foreign_keys=[therapist_id],
        lazy="selectin",
    )
    consent: Mapped["Consent"] = relationship(
        foreign_keys=[consent_id],
        lazy="selectin",
    )
    transcription_jobs: Mapped[list["TranscriptionJob"]] = relationship(
        back_populates="session",
        lazy="selectin",
    )
    transcript: Mapped["Transcript | None"] = relationship(
        back_populates="session",
        lazy="selectin",
        uselist=False,
    )
    chunks: Mapped[list["SessionChunk"]] = relationship(
        back_populates="session",
        lazy="selectin",
    )

    __table_args__ = (
        # Composite indexes for common query patterns
        Index("ix_sessions_patient_status", "patient_id", "status"),
        Index("ix_sessions_therapist_status", "therapist_id", "status"),
        Index("ix_sessions_patient_date", "patient_id", "session_date"),
    )
