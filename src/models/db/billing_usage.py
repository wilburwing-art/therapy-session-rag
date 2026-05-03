"""Billing usage database model.

Tracks metered usage per organization per billing period for Stripe
metered billing. A row is created per (organization, period_start)
combination the first time a metered event fires inside that period,
and incremented as more events arrive. At period close, the row is
reported to Stripe via `MeterEvent` and remains as an immutable ledger
of what was billed.

Counters are monotonically non-decreasing within a period; the service
layer updates them atomically with `UPDATE ... SET col = col + 1`.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.db.organization import Organization


class BillingUsage(Base, TimestampMixin):
    """Per-org, per-period metered usage counters.

    One row per billing period. When a new period starts, a fresh row
    is created; old rows are retained for audit / invoice reconciliation.
    """

    __tablename__ = "billing_usage"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    sessions_transcribed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    recaps_generated: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    chat_messages: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    reported_to_stripe_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    stripe_meter_event_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    organization: Mapped["Organization"] = relationship(
        foreign_keys=[organization_id],
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "period_start",
            name="uq_billing_usage_org_period",
        ),
        Index(
            "ix_billing_usage_org_period",
            "organization_id",
            "period_start",
        ),
    )
