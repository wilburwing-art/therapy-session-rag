"""Organization database model."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.db.api_key import ApiKey
    from src.models.db.user import User


class SubscriptionStatus(enum.StrEnum):
    """Subscription lifecycle states mirrored from Stripe."""

    NONE = "none"
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    INCOMPLETE = "incomplete"
    UNPAID = "unpaid"
    CANCELED = "canceled"


class Organization(Base, TimestampMixin):
    """Organization model representing a therapy practice or platform integrator."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    video_chat_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        unique=True,
        index=True,
    )
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        unique=True,
    )
    subscription_status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status"),
        nullable=False,
        default=SubscriptionStatus.NONE,
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    disabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    users: Mapped[list["User"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    api_keys: Mapped[list["ApiKey"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    def is_entitled(self) -> bool:
        """Return True if the practice's subscription is in good standing.

        An admin-disabled organization is never entitled, regardless of
        subscription status.
        """
        if self.disabled_at is not None:
            return False
        return self.subscription_status in {
            SubscriptionStatus.TRIALING,
            SubscriptionStatus.ACTIVE,
        }
