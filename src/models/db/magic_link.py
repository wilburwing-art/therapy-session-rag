"""Magic link database model.

One-time tokens issued by a therapist and redeemed by a patient to
obtain a short-lived patient session JWT.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.db.user import User


class MagicLink(Base, TimestampMixin):
    """One-time magic link for patient passwordless auth.

    Tokens are stored hashed; the plaintext is only returned at
    creation time. Consuming a link is idempotent: the `used_at`
    column is set on redemption and subsequent redemptions are
    rejected.
    """

    __tablename__ = "magic_links"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    patient: Mapped["User"] = relationship(
        foreign_keys=[patient_id],
        lazy="selectin",
    )
    created_by: Mapped["User"] = relationship(
        foreign_keys=[created_by_user_id],
        lazy="selectin",
    )

    __table_args__ = (Index("ix_magic_links_patient_expires", "patient_id", "expires_at"),)
