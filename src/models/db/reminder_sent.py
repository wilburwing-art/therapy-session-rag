"""Reminder-sent audit log.

One row per reminder the platform attempts to deliver. The table is
append-only: we record every send attempt so operators can reason
about deliverability, dedupe on kind+target, and rate-limit noisy
reminder classes per-patient.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.db.user import User


class ReminderKind(enum.StrEnum):
    """Supported reminder classes."""

    HOMEWORK_DUE = "homework_due"
    SESSION_UPCOMING = "session_upcoming"
    INTAKE_PENDING = "intake_pending"
    ASSESSMENT_DUE = "assessment_due"


class ReminderChannel(enum.StrEnum):
    """Delivery channels for reminders."""

    SMS = "sms"
    EMAIL = "email"
    IN_APP = "in_app"


class ReminderStatus(enum.StrEnum):
    """Outcome of a reminder send attempt."""

    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class ReminderSent(Base, TimestampMixin):
    """Audit row for a single reminder send attempt."""

    __tablename__ = "reminders_sent"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[ReminderKind] = mapped_column(
        Enum(ReminderKind, name="reminder_kind"),
        nullable=False,
    )
    channel: Mapped[ReminderChannel] = mapped_column(
        Enum(ReminderChannel, name="reminder_channel"),
        nullable=False,
    )
    status: Mapped[ReminderStatus] = mapped_column(
        Enum(ReminderStatus, name="reminder_status"),
        nullable=False,
    )
    target: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Destination identifier: phone number, email, or patient UUID.",
    )
    dedupe_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment=(
            "Stable key scoped to patient+kind+period, used to prevent the "
            "scheduler from re-enqueuing the same reminder twice."
        ),
    )
    provider_message_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="External provider id (e.g. Twilio Message SID).",
    )
    error: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
    )
    reminder_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    patient: Mapped[User] = relationship(
        foreign_keys=[patient_id],
        lazy="selectin",
    )

    __table_args__ = (
        Index(
            "ix_reminders_sent_dedupe",
            "patient_id",
            "kind",
            "dedupe_key",
            unique=True,
        ),
        Index(
            "ix_reminders_sent_patient_kind_created",
            "patient_id",
            "kind",
            "created_at",
        ),
    )
