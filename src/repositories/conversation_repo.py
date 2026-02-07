"""Repository for conversation operations."""

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.db.conversation import Conversation, ConversationMessage


class ConversationRepository:
    """Repository for conversation database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, conversation: Conversation) -> Conversation:
        """Create a new conversation.

        Args:
            conversation: The conversation to create

        Returns:
            The created conversation
        """
        self.session.add(conversation)
        await self.session.flush()
        await self.session.refresh(conversation)
        return conversation

    async def get_by_id(
        self,
        conversation_id: uuid.UUID,
        include_messages: bool = True,
    ) -> Conversation | None:
        """Get a conversation by ID.

        Args:
            conversation_id: The conversation ID
            include_messages: Whether to eagerly load messages

        Returns:
            The conversation or None if not found
        """
        query = select(Conversation).where(Conversation.id == conversation_id)
        if include_messages:
            query = query.options(selectinload(Conversation.messages))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_id_for_patient(
        self,
        conversation_id: uuid.UUID,
        patient_id: uuid.UUID,
        include_messages: bool = True,
    ) -> Conversation | None:
        """Get a conversation by ID, ensuring it belongs to the patient.

        Args:
            conversation_id: The conversation ID
            patient_id: The patient's user ID (for security)
            include_messages: Whether to eagerly load messages

        Returns:
            The conversation or None if not found or not owned by patient
        """
        query = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.patient_id == patient_id,
        )
        if include_messages:
            query = query.options(selectinload(Conversation.messages))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_for_patient(
        self,
        patient_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Conversation]:
        """List conversations for a patient, most recent first.

        Args:
            patient_id: The patient's user ID
            limit: Maximum number of conversations to return
            offset: Number of conversations to skip

        Returns:
            List of conversations (without messages loaded)
        """
        result = await self.session.execute(
            select(Conversation)
            .where(Conversation.patient_id == patient_id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def add_message(self, message: ConversationMessage) -> ConversationMessage:
        """Add a message to a conversation.

        Args:
            message: The message to add

        Returns:
            The created message
        """
        self.session.add(message)
        await self.session.flush()
        await self.session.refresh(message)
        return message

    async def increment_message_count(self, conversation_id: uuid.UUID) -> None:
        """Increment the message count for a conversation.

        Args:
            conversation_id: The conversation ID
        """
        await self.session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(message_count=Conversation.message_count + 1)
        )

    async def get_next_sequence_number(self, conversation_id: uuid.UUID) -> int:
        """Get the next sequence number for a message in a conversation.

        Args:
            conversation_id: The conversation ID

        Returns:
            The next sequence number (1-indexed)
        """
        result = await self.session.execute(
            select(func.coalesce(func.max(ConversationMessage.sequence_number), 0))
            .where(ConversationMessage.conversation_id == conversation_id)
        )
        current_max = result.scalar_one()
        return current_max + 1

    async def update_title(
        self,
        conversation_id: uuid.UUID,
        title: str,
    ) -> None:
        """Update the title of a conversation.

        Args:
            conversation_id: The conversation ID
            title: The new title
        """
        await self.session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(title=title)
        )
