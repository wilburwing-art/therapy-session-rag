"""Homework item database model.

One row per concrete between-session task the patient committed to in
a session. Materialized from ``session_recaps.homework_assigned`` when
a recap is generated so patients can track completion in the web app
and therapists can see what's pending.

Idempotency: a ``(session_id, task_hash)`` uniqueness constraint makes
re-running recap generation a no-op for the rows that already exist.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.db.organization import Organization
    from src.models.db.session import Session
    from src.models.db.user import User


class HomeworkItem(Base, TimestampMixin):
    """A between-session task assigned to a patient in a specific session."""

    __tablename__ = "homework_items"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    # Deterministic hash of the normalized task string, used to make
    # (session_id, task_hash) unique so recap re-generation is idempotent.
    task_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    completed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    session: Mapped["Session"] = relationship(
        foreign_keys=[session_id],
        lazy="selectin",
    )
    patient: Mapped["User"] = relationship(
        foreign_keys=[patient_id],
        lazy="selectin",
    )
    organization: Mapped["Organization"] = relationship(
        foreign_keys=[organization_id],
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "task_hash",
            name="uq_homework_items_session_task",
        ),
        Index(
            "ix_homework_items_patient_completed",
            "patient_id",
            "completed",
        ),
    )
