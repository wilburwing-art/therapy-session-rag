"""Conversation database models."""

import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.db.user import User


class MessageRole(enum.StrEnum):
    """Role of the message sender."""

    USER = "user"
    ASSISTANT = "assistant"


class Conversation(Base, TimestampMixin):
    """Conversation model for tracking chat sessions.

    A conversation is a thread of messages between a patient and the AI assistant.
    """

    __tablename__ = "conversations"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    message_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Relationships
    patient: Mapped["User"] = relationship(
        foreign_keys=[patient_id],
        lazy="selectin",
    )
    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="conversation",
        lazy="selectin",
        order_by="ConversationMessage.sequence_number",
    )

    __table_args__ = (
        Index("ix_conversations_patient_updated", "patient_id", "updated_at"),
    )


class ConversationMessage(Base, TimestampMixin):
    """Individual message within a conversation."""

    __tablename__ = "conversation_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="message_role"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(
        back_populates="messages",
        lazy="selectin",
    )

    __table_args__ = (
        Index(
            "ix_conversation_messages_conv_seq",
            "conversation_id",
            "sequence_number",
        ),
    )
