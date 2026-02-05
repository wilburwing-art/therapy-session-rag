"""Consent database model."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.db.base import Base

if TYPE_CHECKING:
    from src.models.db.user import User


class ConsentType(enum.StrEnum):
    """Types of consent that can be granted."""

    RECORDING = "recording"
    TRANSCRIPTION = "transcription"
    AI_ANALYSIS = "ai_analysis"


class ConsentStatus(enum.StrEnum):
    """Status of a consent record."""

    GRANTED = "granted"
    REVOKED = "revoked"


class Consent(Base):
    """Consent model for tracking patient consent.

    This model uses an append-only pattern:
    - Granting consent creates a new record with status='granted'
    - Revoking consent creates a NEW record with status='revoked'
    - Consent records are never updated after creation (immutable)

    This provides a complete audit trail of all consent changes.
    """

    __tablename__ = "consents"

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
    consent_type: Mapped[ConsentType] = mapped_column(
        Enum(ConsentType, name="consent_type"),
        nullable=False,
    )
    status: Mapped[ConsentStatus] = mapped_column(
        Enum(ConsentStatus, name="consent_status"),
        nullable=False,
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45),  # IPv6 max length
        nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    consent_metadata: Mapped[dict[str, Any] | None] = mapped_column(
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

    __table_args__ = (
        # Composite index for consent lookups (patient + therapist + type, ordered by granted_at)
        Index(
            "ix_consents_patient_therapist_type_granted",
            "patient_id",
            "therapist_id",
            "consent_type",
            "granted_at",
        ),
    )
