"""Analytics event database model."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.db.base import Base


class EventCategory(enum.StrEnum):
    """Category of analytics event."""

    USER_ACTION = "user_action"
    SYSTEM = "system"
    CLINICAL = "clinical"
    PERFORMANCE = "performance"


class AnalyticsEvent(Base):
    """Analytics event for tracking user actions and system events.

    Modeled after Snowplow's event schema with structured properties
    and extensible contexts.
    """

    __tablename__ = "analytics_events"

    event_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    event_category: Mapped[EventCategory] = mapped_column(
        Enum(EventCategory, name="event_category"),
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    properties: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    contexts: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_events_name_timestamp", "event_name", "event_timestamp"),
        Index("ix_events_org_timestamp", "organization_id", "event_timestamp"),
        Index(
            "ix_events_session",
            "session_id",
            postgresql_where="session_id IS NOT NULL",
        ),
        Index("ix_events_category_timestamp", "event_category", "event_timestamp"),
    )
