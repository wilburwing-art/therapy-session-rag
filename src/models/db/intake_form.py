"""Intake form database model.

A therapist-defined questionnaire sent to new patients before their first
session. The schema stores the list of questions as JSONB so therapists
can tailor forms per-practice without schema migrations.
"""

import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.db.organization import Organization
    from src.models.db.user import User


class IntakeFormStatus(enum.StrEnum):
    """Lifecycle of an intake form."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class IntakeForm(Base, TimestampMixin):
    """A reusable intake questionnaire scoped to an organization.

    ``questions`` is a JSONB array of ``{id, prompt, kind, required, choices?}``
    entries. Supported ``kind`` values: ``short_text``, ``long_text``,
    ``single_choice``, ``multi_choice``, ``scale``, ``date``.
    """

    __tablename__ = "intake_forms"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    status: Mapped[IntakeFormStatus] = mapped_column(
        Enum(IntakeFormStatus, name="intake_form_status"),
        nullable=False,
        default=IntakeFormStatus.DRAFT,
    )
    questions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )

    organization: Mapped["Organization"] = relationship(
        foreign_keys=[organization_id],
        lazy="selectin",
    )
    created_by: Mapped["User"] = relationship(
        foreign_keys=[created_by_user_id],
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_intake_forms_org_status", "organization_id", "status"),
    )
