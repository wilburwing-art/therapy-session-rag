"""Session recap database model.

Stores LLM-generated summaries of therapy sessions for the therapist
dashboard: brief, key topics, emotional tone, homework, follow-ups,
and risk flags.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.db.session import Session


class SessionRecap(Base, TimestampMixin):
    """LLM-generated recap of a therapy session.

    One recap per session. Populated after the embedding pipeline
    completes, either automatically via the summarization worker or
    manually via the regenerate endpoint.
    """

    __tablename__ = "session_recaps"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    brief: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    key_topics: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    emotional_tone: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    homework_assigned: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    follow_ups: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    risk_flags: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    model_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    session: Mapped["Session"] = relationship(
        foreign_keys=[session_id],
        lazy="selectin",
    )
