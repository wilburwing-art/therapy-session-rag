"""Webhook endpoint database model.

A customer-configured HTTP target that the platform will POST to when a
subscribed event fires. Each endpoint owns a rotating signing secret; we
store only the current secret (plaintext) because customers need it to
verify signatures on their side. Rotation regenerates the secret in place
and records the timestamp so operators can correlate a delivery to the
secret that signed it.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.db.organization import Organization
    from src.models.db.webhook_delivery import WebhookDelivery


class WebhookEventType(enum.StrEnum):
    """Events a customer may subscribe to.

    Kept small and explicit — the subscription list is append-only from
    the customer's perspective but we treat unknown types server-side as
    a validation error so typos surface at configure time.
    """

    SESSION_COMPLETED = "session.completed"
    RECAP_READY = "recap.ready"
    PATIENT_DELETED = "patient.deleted"
    PATIENT_CONSENT_GRANTED = "patient.consent_granted"


class WebhookEndpoint(Base, TimestampMixin):
    """A registered HTTP target for outbound webhooks."""

    __tablename__ = "webhook_endpoints"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        comment="Absolute https URL the platform will POST events to",
    )
    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    secret: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment=(
            "Signing secret used in the HMAC-SHA256 signature header. "
            "Stored plaintext so the customer can reset it only by "
            "rotating; we expose it only to the endpoint owner."
        ),
    )
    event_types: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)),
        nullable=False,
        comment="Array of event type strings this endpoint subscribes to",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        insert_default=True,
    )
    last_rotated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    disabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    organization: Mapped[Organization] = relationship(
        foreign_keys=[organization_id],
        lazy="selectin",
    )
    deliveries: Mapped[list[WebhookDelivery]] = relationship(
        back_populates="endpoint",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index(
            "ix_webhook_endpoints_org_active",
            "organization_id",
            "is_active",
        ),
    )
