"""Organization database model."""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.db.api_key import ApiKey
    from src.models.db.user import User


class Organization(Base, TimestampMixin):
    """Organization model representing a therapy practice or platform integrator."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    video_chat_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
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
