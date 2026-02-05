"""Pydantic schemas for chat functionality."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChatMessageCreate(BaseModel):
    """Schema for creating a chat message."""

    content: str = Field(..., min_length=1, max_length=4000)
    conversation_id: UUID | None = Field(
        None, description="ID of existing conversation, or None for new"
    )


class ChatSource(BaseModel):
    """A source citation from a therapy session."""

    session_id: UUID
    chunk_id: UUID
    content_preview: str = Field(..., max_length=200)
    relevance_score: float = Field(..., ge=0, le=1)
    start_time: float | None = None
    speaker: str | None = None


class ChatMessageResponse(BaseModel):
    """Response from the chat service."""

    model_config = ConfigDict(from_attributes=True)

    content: str
    conversation_id: UUID
    message_id: UUID
    sources: list[ChatSource] = Field(default_factory=list)
    created_at: datetime


class ConversationMessage(BaseModel):
    """A message in a conversation history."""

    role: str  # "user" or "assistant"
    content: str
    created_at: datetime
    sources: list[ChatSource] | None = None


class ConversationRead(BaseModel):
    """Schema for reading a full conversation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID
    messages: list[ConversationMessage]
    created_at: datetime
    updated_at: datetime


class ChatRequest(BaseModel):
    """Request schema for chat endpoint."""

    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: UUID | None = Field(None)
    top_k: int = Field(5, ge=1, le=10, description="Number of context chunks to retrieve")


class ChatResponse(BaseModel):
    """Response schema for chat endpoint."""

    response: str
    conversation_id: UUID
    sources: list[ChatSource]
