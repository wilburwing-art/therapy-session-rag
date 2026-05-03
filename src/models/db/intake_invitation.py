"""Intake invitation database model.

A one-time token issued by a therapist and sent to a prospective patient
via email. Redeeming the token loads the referenced intake form; the
patient submits answers through the public ``/api/v1/intake/invitations``
endpoints. Tokens are stored hashed; the plaintext is returned only at
creation time so the caller can email it or copy the link manually.
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
    from src.models.db.intake_form import IntakeForm
    from src.models.db.organization import Organization
    from src.models.db.user import User


class IntakeInvitationStatus(enum.StrEnum):
    """Lifecycle of an intake invitation."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    EXPIRED = "expired"
    REVOKED = "revoked"


class IntakeInvitation(Base, TimestampMixin):
    """A one-time invitation for a patient to complete an intake form."""

    __tablename__ = "intake_invitations"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    form_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intake_forms.id", ondelete="RESTRICT"),
        nullable=False,
    )
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    patient_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    patient_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        index=True,
    )
    status: Mapped[IntakeInvitationStatus] = mapped_column(
        Enum(IntakeInvitationStatus, name="intake_invitation_status"),
        nullable=False,
        default=IntakeInvitationStatus.PENDING,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    organization: Mapped["Organization"] = relationship(
        foreign_keys=[organization_id],
        lazy="selectin",
    )
    form: Mapped["IntakeForm"] = relationship(
        foreign_keys=[form_id],
        lazy="selectin",
    )
    invited_by: Mapped["User"] = relationship(
        foreign_keys=[invited_by_user_id],
        lazy="selectin",
    )

    __table_args__ = (
        Index(
            "ix_intake_invitations_org_status",
            "organization_id",
            "status",
        ),
        Index(
            "ix_intake_invitations_org_email",
            "organization_id",
            "patient_email",
        ),
    )
