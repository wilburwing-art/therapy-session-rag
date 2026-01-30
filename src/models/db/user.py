"""User database model."""

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.db.organization import Organization


class UserRole(str, enum.Enum):
    """User role enumeration."""

    THERAPIST = "therapist"
    PATIENT = "patient"
    ADMIN = "admin"


class User(Base, TimestampMixin):
    """User model representing therapists, patients, and admins."""

    __tablename__ = "users"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"),
        nullable=False,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        back_populates="users",
        lazy="selectin",
    )
