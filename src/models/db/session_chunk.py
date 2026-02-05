"""Session chunk database model for storing transcript chunks with embeddings."""

import uuid
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.db.session import Session
    from src.models.db.transcript import Transcript

# OpenAI text-embedding-3-small produces 1536-dimensional vectors
EMBEDDING_DIMENSION = 1536


class SessionChunk(Base, TimestampMixin):
    """Stores transcript chunks with their embeddings for RAG retrieval.

    Each chunk represents a semantic unit of the transcript (typically ~500 tokens)
    with metadata preserved for context and speaker attribution.
    """

    __tablename__ = "session_chunks"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transcript_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transcripts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSION),  # type: ignore[no-untyped-call]
        nullable=True,
    )
    start_time: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    end_time: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    speaker: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    token_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    chunk_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
    )

    # Relationships
    session: Mapped["Session"] = relationship(
        back_populates="chunks",
        lazy="selectin",
    )
    transcript: Mapped["Transcript"] = relationship(
        back_populates="chunks",
        lazy="selectin",
    )

    __table_args__ = (
        # Index for vector similarity search using cosine distance
        Index(
            "ix_session_chunks_embedding_cosine",
            embedding,
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        # Composite index for filtering by session before vector search
        Index("ix_session_chunks_session_chunk", "session_id", "chunk_index"),
    )
