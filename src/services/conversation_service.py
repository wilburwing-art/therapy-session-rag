"""Service for conversation management."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.models.db.conversation import Conversation, ConversationMessage, MessageRole
from src.models.domain.chat import (
    ChatSource,
    ConversationMessageRead,
    ConversationRead,
    ConversationSummary,
)
from src.repositories.conversation_repo import ConversationRepository
from src.services.claude_client import Message


class ConversationService:
    """Service for managing chat conversations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ConversationRepository(session)

    async def create_conversation(
        self,
        patient_id: uuid.UUID,
        organization_id: uuid.UUID,
        title: str | None = None,
    ) -> ConversationRead:
        """Create a new conversation.

        Args:
            patient_id: The patient's user ID
            organization_id: The organization ID
            title: Optional title for the conversation

        Returns:
            The created conversation
        """
        conversation = Conversation(
            patient_id=patient_id,
            organization_id=organization_id,
            title=title,
            message_count=0,
        )
        created = await self.repo.create(conversation)
        return self._to_conversation_read(created)

    async def get_conversation(
        self,
        conversation_id: uuid.UUID,
        patient_id: uuid.UUID,
    ) -> ConversationRead:
        """Get a conversation by ID.

        Args:
            conversation_id: The conversation ID
            patient_id: The patient's ID (for security)

        Returns:
            The conversation with messages

        Raises:
            NotFoundError: If conversation not found or not owned by patient
        """
        conversation = await self.repo.get_by_id_for_patient(
            conversation_id=conversation_id,
            patient_id=patient_id,
            include_messages=True,
        )
        if not conversation:
            raise NotFoundError(resource="Conversation")
        return self._to_conversation_read(conversation)

    async def get_or_create_conversation(
        self,
        conversation_id: uuid.UUID | None,
        patient_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> tuple[Conversation, bool]:
        """Get an existing conversation or create a new one.

        Args:
            conversation_id: Optional existing conversation ID
            patient_id: The patient's user ID
            organization_id: The organization ID

        Returns:
            Tuple of (conversation, is_new)

        Raises:
            NotFoundError: If conversation_id provided but not found
        """
        if conversation_id:
            conversation = await self.repo.get_by_id_for_patient(
                conversation_id=conversation_id,
                patient_id=patient_id,
                include_messages=True,
            )
            if not conversation:
                raise NotFoundError(resource="Conversation")
            return conversation, False

        conversation = Conversation(
            patient_id=patient_id,
            organization_id=organization_id,
            message_count=0,
        )
        await self.repo.create(conversation)
        return conversation, True

    async def add_user_message(
        self,
        conversation: Conversation,
        content: str,
    ) -> ConversationMessage:
        """Add a user message to a conversation.

        Args:
            conversation: The conversation
            content: The message content

        Returns:
            The created message
        """
        seq = await self.repo.get_next_sequence_number(conversation.id)
        message = ConversationMessage(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=content,
            sequence_number=seq,
            sources=None,
        )
        created = await self.repo.add_message(message)
        await self.repo.increment_message_count(conversation.id)
        return created

    async def add_assistant_message(
        self,
        conversation: Conversation,
        content: str,
        sources: list[ChatSource] | None = None,
    ) -> ConversationMessage:
        """Add an assistant message to a conversation.

        Args:
            conversation: The conversation
            content: The message content
            sources: Optional list of source citations

        Returns:
            The created message
        """
        seq = await self.repo.get_next_sequence_number(conversation.id)
        sources_json = (
            [s.model_dump(mode="json") for s in sources] if sources else None
        )
        message = ConversationMessage(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=content,
            sequence_number=seq,
            sources=sources_json,
        )
        created = await self.repo.add_message(message)
        await self.repo.increment_message_count(conversation.id)
        return created

    async def list_conversations(
        self,
        patient_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ConversationSummary]:
        """List conversations for a patient.

        Args:
            patient_id: The patient's user ID
            limit: Maximum number to return
            offset: Number to skip

        Returns:
            List of conversation summaries
        """
        conversations = await self.repo.list_for_patient(
            patient_id=patient_id,
            limit=limit,
            offset=offset,
        )
        return [self._to_conversation_summary(c) for c in conversations]

    def get_history_for_claude(
        self,
        conversation: Conversation,
    ) -> list[Message]:
        """Convert conversation messages to Claude message format.

        Args:
            conversation: The conversation with messages loaded

        Returns:
            List of Message objects for Claude API
        """
        messages: list[Message] = []
        for msg in conversation.messages:
            messages.append(Message(role=msg.role.value, content=msg.content))
        return messages

    async def generate_title(
        self,
        conversation_id: uuid.UUID,
        first_message: str,
    ) -> str:
        """Generate a title for a conversation based on the first message.

        Args:
            conversation_id: The conversation ID
            first_message: The first user message

        Returns:
            The generated title
        """
        # Simple title generation: take first 50 chars of first message
        title = first_message[:50].strip()
        if len(first_message) > 50:
            title += "..."
        await self.repo.update_title(conversation_id, title)
        return title

    def _to_conversation_read(self, conversation: Conversation) -> ConversationRead:
        """Convert a Conversation model to ConversationRead schema."""
        messages = []
        for msg in conversation.messages:
            sources = None
            if msg.sources:
                sources = [ChatSource(**s) for s in msg.sources]
            messages.append(
                ConversationMessageRead(
                    id=msg.id,
                    role=msg.role.value,
                    content=msg.content,
                    sequence_number=msg.sequence_number,
                    sources=sources,
                    created_at=msg.created_at,
                )
            )
        return ConversationRead(
            id=conversation.id,
            patient_id=conversation.patient_id,
            organization_id=conversation.organization_id,
            title=conversation.title,
            message_count=conversation.message_count,
            messages=messages,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )

    def _to_conversation_summary(
        self, conversation: Conversation
    ) -> ConversationSummary:
        """Convert a Conversation model to ConversationSummary schema."""
        return ConversationSummary(
            id=conversation.id,
            patient_id=conversation.patient_id,
            title=conversation.title,
            message_count=conversation.message_count,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )
