"""Pydantic schemas for session chunks."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SessionChunkBase(BaseModel):
    """Base schema for session chunks."""

    content: str = Field(..., description="The text content of the chunk")
    chunk_index: int = Field(..., ge=0, description="Index of the chunk within the transcript")
    start_time: float | None = Field(None, ge=0, description="Start time in seconds")
    end_time: float | None = Field(None, ge=0, description="End time in seconds")
    speaker: str | None = Field(None, max_length=50, description="Speaker identifier")
    token_count: int | None = Field(None, ge=0, description="Number of tokens in the chunk")
    chunk_metadata: dict[str, Any] | None = Field(None, description="Additional metadata")


class SessionChunkCreate(SessionChunkBase):
    """Schema for creating a session chunk."""

    session_id: UUID = Field(..., description="ID of the parent session")
    transcript_id: UUID = Field(..., description="ID of the source transcript")


class SessionChunkRead(SessionChunkBase):
    """Schema for reading a session chunk."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    transcript_id: UUID
    created_at: datetime
    updated_at: datetime


class SessionChunkWithEmbedding(SessionChunkRead):
    """Schema for a session chunk with its embedding vector."""

    embedding: list[float] | None = Field(
        None, description="Embedding vector (1536 dimensions)"
    )


class SessionChunkWithScore(SessionChunkRead):
    """Schema for a session chunk with similarity score from vector search."""

    score: float = Field(..., ge=0, le=1, description="Cosine similarity score")


class ChunkSearchRequest(BaseModel):
    """Request schema for chunk similarity search."""

    query: str = Field(..., min_length=1, description="Search query text")
    patient_id: UUID = Field(..., description="Patient ID (for security filtering)")
    top_k: int = Field(5, ge=1, le=20, description="Number of results to return")
    min_score: float | None = Field(
        None, ge=0, le=1, description="Minimum similarity score threshold"
    )


class ChunkSearchResult(BaseModel):
    """Response schema for chunk similarity search."""

    chunks: list[SessionChunkWithScore] = Field(..., description="Matching chunks")
    query: str = Field(..., description="Original query")
    total_found: int = Field(..., ge=0, description="Total number of matches")
