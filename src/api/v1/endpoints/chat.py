"""Chat API endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.v1.dependencies import Auth, Events
from src.core.database import DbSession
from src.core.exceptions import RateLimitError
from src.models.db.event import EventCategory
from src.models.domain.chat import ChatRequest, ChatResponse, ConversationRead, ConversationSummary
from src.services.chat_service import ChatService
from src.services.conversation_service import ConversationService
from src.services.rate_limiter import ChatRateLimiter, RateLimitExceeded

router = APIRouter()


def get_chat_service(session: DbSession) -> ChatService:
    """Get chat service instance."""
    return ChatService(session)


def get_conversation_service(session: DbSession) -> ConversationService:
    """Get conversation service instance."""
    return ConversationService(session)


def get_chat_rate_limiter() -> ChatRateLimiter:
    """Get chat rate limiter instance."""
    return ChatRateLimiter()


ChatSvc = Annotated[ChatService, Depends(get_chat_service)]
ConvSvc = Annotated[ConversationService, Depends(get_conversation_service)]
RateLimiterDep = Annotated[ChatRateLimiter, Depends(get_chat_rate_limiter)]


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    patient_id: uuid.UUID,
    auth: Auth,
    service: ChatSvc,
    conversation_service: ConvSvc,
    rate_limiter: RateLimiterDep,
    events: Events,
) -> ChatResponse:
    """Send a message to the RAG chatbot.

    The chatbot uses your therapy session history to provide
    personalized, context-aware responses.

    Args:
        request: Chat request containing message and optional conversation_id
        patient_id: The patient's ID (query parameter)
        auth: Authentication context
        service: Chat service instance
        conversation_service: Conversation service for history persistence
        rate_limiter: Rate limiter for enforcing request limits

    Returns:
        ChatResponse with AI response and source citations

    Note:
        - Messages are limited to 4000 characters
        - Top-k context chunks can be configured (1-10, default 5)
        - Conversation history is maintained via conversation_id
        - Rate limited to 20 messages per hour per patient
    """
    # Check and consume rate limit
    try:
        await rate_limiter.check_and_consume(patient_id)
    except RateLimitExceeded as e:
        raise RateLimitError(
            detail=str(e),
            retry_after=e.reset_time,
        ) from e

    # Get or create conversation
    conversation, is_new = await conversation_service.get_or_create_conversation(
        conversation_id=request.conversation_id,
        patient_id=patient_id,
        organization_id=auth.organization_id,
    )

    # Build conversation history from persisted messages
    conversation_history = conversation_service.get_history_for_claude(conversation)

    # Add user message to conversation
    await conversation_service.add_user_message(conversation, request.message)

    # Generate title for new conversations
    if is_new:
        await conversation_service.generate_title(conversation.id, request.message)

    response = await service.chat(
        patient_id=patient_id,
        message=request.message,
        conversation_history=conversation_history if conversation_history else None,
        top_k=request.top_k,
    )

    # Persist assistant response
    await conversation_service.add_assistant_message(
        conversation, response.response, response.sources
    )

    # Update response with the correct conversation_id
    response.conversation_id = conversation.id

    await events.publish(
        event_name="chat.message_sent",
        category=EventCategory.USER_ACTION,
        organization_id=auth.organization_id,
        actor_id=patient_id,
        properties={
            "top_k": request.top_k,
            "source_count": len(response.sources),
            "conversation_id": str(conversation.id),
            "is_new_conversation": is_new,
            "message_length": len(request.message),
        },
    )

    return response


@router.get("/sessions-count")
async def get_sessions_count(
    patient_id: uuid.UUID,
    auth: Auth,  # noqa: ARG001
    service: ChatSvc,
) -> dict[str, int]:
    """Get the number of indexed sessions for a patient.

    Returns the count of therapy sessions that have been processed
    and are available for RAG queries.

    Args:
        patient_id: The patient's ID
        auth: Authentication context
        service: Chat service instance

    Returns:
        Dictionary with session count
    """
    count = await service.get_patient_session_count(patient_id)
    return {"session_count": count}


@router.get("/chunks-count")
async def get_chunks_count(
    patient_id: uuid.UUID,
    auth: Auth,  # noqa: ARG001
    service: ChatSvc,
) -> dict[str, int]:
    """Get the total number of indexed chunks for a patient.

    Returns the count of text chunks that have been processed
    and embedded for RAG queries.

    Args:
        patient_id: The patient's ID
        auth: Authentication context
        service: Chat service instance

    Returns:
        Dictionary with chunk count
    """
    count = await service.get_chunk_count(patient_id)
    return {"chunk_count": count}


@router.get("/rate-limit")
async def get_rate_limit_status(
    patient_id: uuid.UUID,
    auth: Auth,  # noqa: ARG001
    rate_limiter: RateLimiterDep,
) -> dict[str, int]:
    """Get the current rate limit status for a patient.

    Returns how many chat requests remain and the window reset time.

    Args:
        patient_id: The patient's ID
        auth: Authentication context
        rate_limiter: Rate limiter instance

    Returns:
        Dictionary with remaining requests and max requests per hour
    """
    remaining = await rate_limiter.get_remaining(patient_id)
    return {
        "remaining": remaining,
        "max_per_hour": rate_limiter.max_requests,
    }


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(
    patient_id: uuid.UUID,
    auth: Auth,  # noqa: ARG001
    conversation_service: ConvSvc,
    limit: int = 20,
    offset: int = 0,
) -> list[ConversationSummary]:
    """List conversations for a patient.

    Returns conversation summaries ordered by most recent first.

    Args:
        patient_id: The patient's ID
        auth: Authentication context
        conversation_service: Conversation service instance
        limit: Maximum number of conversations to return
        offset: Number of conversations to skip

    Returns:
        List of conversation summaries
    """
    return await conversation_service.list_conversations(
        patient_id=patient_id,
        limit=limit,
        offset=offset,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationRead)
async def get_conversation(
    conversation_id: uuid.UUID,
    patient_id: uuid.UUID,
    auth: Auth,  # noqa: ARG001
    conversation_service: ConvSvc,
) -> ConversationRead:
    """Get a specific conversation with all messages.

    Args:
        conversation_id: The conversation ID
        patient_id: The patient's ID
        auth: Authentication context
        conversation_service: Conversation service instance

    Returns:
        The conversation with all messages
    """
    return await conversation_service.get_conversation(
        conversation_id=conversation_id,
        patient_id=patient_id,
    )
