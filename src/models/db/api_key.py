"""API Key database model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.db.organization import Organization


class ApiKey(Base, TimestampMixin):
    """API Key model for authentication.

    API keys are hashed before storage - never store plaintext keys.
    The plaintext key is returned only once at creation time.
    """

    __tablename__ = "api_keys"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Hashed API key - never store plaintext",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-readable name for identification",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        insert_default=True,
        nullable=False,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        back_populates="api_keys",
        lazy="selectin",
    )

    def revoke(self) -> None:
        """Revoke this API key."""
        self.is_active = False
        self.revoked_at = func.now()

    def mark_used(self) -> None:
        """Update the last_used_at timestamp."""
        self.last_used_at = func.now()
