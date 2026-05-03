"""Therapist invite database model.

A pending invitation issued by an existing therapist to onboard a new
teammate into the same organization. Tokens are stored hashed; the
plaintext is returned only at creation time so the caller can email it
or copy it if email delivery fails. Redeeming the invite creates a new
therapist user with a password and clears the token by setting
`accepted_at`.
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
    from src.models.db.organization import Organization
    from src.models.db.user import User


class TherapistInviteRole(enum.StrEnum):
    """Role the invitee will be granted on acceptance."""

    THERAPIST = "therapist"
    ADMIN = "admin"


class TherapistInvite(Base, TimestampMixin):
    """One-time invite for a new therapist joining a practice."""

    __tablename__ = "therapist_invites"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    role: Mapped[TherapistInviteRole] = mapped_column(
        Enum(TherapistInviteRole, name="therapist_invite_role"),
        nullable=False,
        default=TherapistInviteRole.THERAPIST,
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
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    organization: Mapped["Organization"] = relationship(
        foreign_keys=[organization_id],
        lazy="selectin",
    )
    invited_by: Mapped["User"] = relationship(
        foreign_keys=[invited_by_user_id],
        lazy="selectin",
    )

    __table_args__ = (
        Index(
            "ix_therapist_invites_org_accepted",
            "organization_id",
            "accepted_at",
        ),
    )
