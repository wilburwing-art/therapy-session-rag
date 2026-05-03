"""Short-lived auth tokens for password reset and email verification.

Modeled like magic_links but with an explicit `purpose` discriminator
so the same table can back multiple flows. Tokens are hashed at rest;
redeeming one sets `used_at` atomically.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.db.user import User


class AuthTokenPurpose(enum.StrEnum):
    """What the token unlocks."""

    PASSWORD_RESET = "password_reset"
    EMAIL_VERIFICATION = "email_verification"


class AuthToken(Base, TimestampMixin):
    __tablename__ = "auth_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purpose: Mapped[AuthTokenPurpose] = mapped_column(
        Enum(AuthTokenPurpose, name="auth_token_purpose"),
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

    user: Mapped["User"] = relationship(foreign_keys=[user_id], lazy="selectin")

    __table_args__ = (Index("ix_auth_tokens_user_purpose", "user_id", "purpose", "expires_at"),)
