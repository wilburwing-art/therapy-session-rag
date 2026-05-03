"""Webhook delivery record.

One row per attempted delivery. Contains the full signed payload body so
admins can replay or inspect. Attempts are driven by a background worker
that updates ``status`` from pending → in_flight → delivered / failed;
retries create new rows so the audit trail is append-only per attempt.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.db.organization import Organization
    from src.models.db.webhook_endpoint import WebhookEndpoint


class WebhookDeliveryStatus(enum.StrEnum):
    """Lifecycle of a single delivery attempt."""

    PENDING = "pending"
    IN_FLIGHT = "in_flight"
    DELIVERED = "delivered"
    FAILED = "failed"


class WebhookDelivery(Base, TimestampMixin):
    """One attempt to deliver a webhook event to a customer endpoint."""

    __tablename__ = "webhook_deliveries"

    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="Stable ID for this logical event; same across retries",
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Exact JSON body POSTed to the customer endpoint",
    )
    status: Mapped[WebhookDeliveryStatus] = mapped_column(
        Enum(WebhookDeliveryStatus, name="webhook_delivery_status"),
        nullable=False,
        default=WebhookDeliveryStatus.PENDING,
        insert_default=WebhookDeliveryStatus.PENDING,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        insert_default=0,
    )
    response_status_code: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    response_body_snippet: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="First 1KB of the response body, for operator diagnostics",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    endpoint: Mapped[WebhookEndpoint] = relationship(
        back_populates="deliveries",
        lazy="selectin",
    )
    organization: Mapped[Organization] = relationship(
        foreign_keys=[organization_id],
        lazy="selectin",
    )
