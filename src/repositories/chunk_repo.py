"""Repository for session chunk operations."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.session_chunk import SessionChunk


class ChunkRepository:
    """Repository for session chunk database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_chunk(self, chunk: SessionChunk) -> SessionChunk:
        """Create a new session chunk.

        Args:
            chunk: The chunk to create

        Returns:
            The created chunk
        """
        self.session.add(chunk)
        await self.session.flush()
        await self.session.refresh(chunk)
        return chunk

    async def create_chunks_batch(
        self, chunks: list[SessionChunk]
    ) -> list[SessionChunk]:
        """Create multiple chunks in a batch.

        Args:
            chunks: List of chunks to create

        Returns:
            List of created chunks
        """
        if not chunks:
            return []

        self.session.add_all(chunks)
        await self.session.flush()

        for chunk in chunks:
            await self.session.refresh(chunk)

        return chunks

    async def get_chunk_by_id(self, chunk_id: uuid.UUID) -> SessionChunk | None:
        """Get a chunk by ID.

        Args:
            chunk_id: The chunk ID

        Returns:
            The chunk if found, None otherwise
        """
        result = await self.session.execute(
            select(SessionChunk).where(SessionChunk.id == chunk_id)
        )
        return result.scalar_one_or_none()

    async def get_chunks_by_session(
        self,
        session_id: uuid.UUID,
    ) -> list[SessionChunk]:
        """Get all chunks for a session.

        Args:
            session_id: The session ID

        Returns:
            List of chunks ordered by chunk_index
        """
        query = (
            select(SessionChunk)
            .where(SessionChunk.session_id == session_id)
            .order_by(SessionChunk.chunk_index)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_chunks_by_transcript(
        self, transcript_id: uuid.UUID
    ) -> list[SessionChunk]:
        """Get all chunks for a transcript.

        Args:
            transcript_id: The transcript ID

        Returns:
            List of chunks ordered by chunk_index
        """
        result = await self.session.execute(
            select(SessionChunk)
            .where(SessionChunk.transcript_id == transcript_id)
            .order_by(SessionChunk.chunk_index)
        )
        return list(result.scalars().all())

    async def get_chunks_without_embeddings(
        self, session_id: uuid.UUID
    ) -> list[SessionChunk]:
        """Get chunks that don't have embeddings yet.

        Args:
            session_id: The session ID

        Returns:
            List of chunks without embeddings
        """
        result = await self.session.execute(
            select(SessionChunk)
            .where(SessionChunk.session_id == session_id)
            .where(SessionChunk.embedding.is_(None))
            .order_by(SessionChunk.chunk_index)
        )
        return list(result.scalars().all())

    async def update_chunk_embedding(
        self,
        chunk_id: uuid.UUID,
        embedding: list[float],
        token_count: int | None = None,
    ) -> bool:
        """Update the embedding for a chunk.

        Args:
            chunk_id: The chunk ID
            embedding: The embedding vector
            token_count: Optional token count

        Returns:
            True if updated, False if not found
        """
        chunk = await self.get_chunk_by_id(chunk_id)
        if chunk is None:
            return False

        chunk.embedding = embedding
        if token_count is not None:
            chunk.token_count = token_count

        await self.session.flush()
        return True

    async def delete_chunks_by_session(self, session_id: uuid.UUID) -> int:
        """Delete all chunks for a session.

        Args:
            session_id: The session ID

        Returns:
            Number of chunks deleted
        """
        cursor_result = await self.session.execute(
            delete(SessionChunk).where(SessionChunk.session_id == session_id)
        )
        rowcount = getattr(cursor_result, "rowcount", 0)
        return rowcount or 0

    async def delete_chunks_by_transcript(self, transcript_id: uuid.UUID) -> int:
        """Delete all chunks for a transcript.

        Args:
            transcript_id: The transcript ID

        Returns:
            Number of chunks deleted
        """
        cursor_result = await self.session.execute(
            delete(SessionChunk).where(SessionChunk.transcript_id == transcript_id)
        )
        rowcount = getattr(cursor_result, "rowcount", 0)
        return rowcount or 0

    async def count_chunks_by_session(self, session_id: uuid.UUID) -> int:
        """Count chunks for a session.

        Args:
            session_id: The session ID

        Returns:
            Number of chunks
        """
        result = await self.session.execute(
            select(SessionChunk.id).where(SessionChunk.session_id == session_id)
        )
        return len(result.scalars().all())

    async def has_embeddings(self, session_id: uuid.UUID) -> bool:
        """Check if all chunks for a session have embeddings.

        Args:
            session_id: The session ID

        Returns:
            True if all chunks have embeddings, False otherwise
        """
        chunks_without = await self.get_chunks_without_embeddings(session_id)
        total = await self.count_chunks_by_session(session_id)
        return total > 0 and len(chunks_without) == 0
