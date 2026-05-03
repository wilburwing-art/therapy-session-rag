"""Intake response database model.

Captures a patient's answers to an intake form. Answers are keyed by the
question ``id`` defined in the referring form's ``questions`` JSONB, so
the shape of the payload stays stable even if the form is edited later.
One response per invitation.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.db.intake_form import IntakeForm
    from src.models.db.intake_invitation import IntakeInvitation
    from src.models.db.organization import Organization


class IntakeResponse(Base, TimestampMixin):
    """A patient's submitted answers for an intake invitation."""

    __tablename__ = "intake_responses"

    invitation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intake_invitations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    form_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intake_forms.id", ondelete="RESTRICT"),
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    answers: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    submitted_ip: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    submitted_user_agent: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    invitation: Mapped["IntakeInvitation"] = relationship(
        foreign_keys=[invitation_id],
        lazy="selectin",
    )
    form: Mapped["IntakeForm"] = relationship(
        foreign_keys=[form_id],
        lazy="selectin",
    )
    organization: Mapped["Organization"] = relationship(
        foreign_keys=[organization_id],
        lazy="selectin",
    )

    __table_args__ = (
        Index(
            "ix_intake_responses_org_submitted",
            "organization_id",
            "submitted_at",
        ),
    )
