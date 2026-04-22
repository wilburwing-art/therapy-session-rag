"""Patient themes database model.

Stores cross-session theme analysis for a patient: recurring topics,
emotional patterns, coping strategies mentioned, progress indicators,
and ongoing concerns. Synthesized from the patient's session recaps.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.db.user import User


class PatientThemes(Base, TimestampMixin):
    """Cross-session theme synthesis for a single patient.

    One row per patient; re-generated on demand when the therapist
    clicks "refresh" or when a configurable number of new sessions
    have accumulated since the last generation.
    """

    __tablename__ = "patient_themes"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    recurring_topics: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    emotional_patterns: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    coping_strategies: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    progress_indicators: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    ongoing_concerns: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    source_session_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    model_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    patient: Mapped["User"] = relationship(
        foreign_keys=[patient_id],
        lazy="selectin",
    )
