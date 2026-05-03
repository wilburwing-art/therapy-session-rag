"""Structured clinical assessments (PHQ-9, GAD-7).

Stores a patient's self-report responses and the computed total score.
Designed so new instruments can be added by defining a new scoring
helper; the schema itself is instrument-agnostic.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.db.user import User


class AssessmentInstrument(enum.StrEnum):
    PHQ9 = "phq9"
    GAD7 = "gad7"


class Assessment(Base, TimestampMixin):
    __tablename__ = "assessments"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    administered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    instrument: Mapped[AssessmentInstrument] = mapped_column(
        Enum(AssessmentInstrument, name="assessment_instrument"),
        nullable=False,
    )
    responses: Mapped[list[int]] = mapped_column(
        JSONB,
        nullable=False,
    )
    total_score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    severity: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )
    administered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    assessment_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    patient: Mapped["User"] = relationship(
        foreign_keys=[patient_id],
        lazy="selectin",
    )
    administered_by: Mapped["User | None"] = relationship(
        foreign_keys=[administered_by_user_id],
        lazy="selectin",
    )

    __table_args__ = (
        Index(
            "ix_assessments_patient_instrument_date",
            "patient_id",
            "instrument",
            "administered_at",
        ),
    )
