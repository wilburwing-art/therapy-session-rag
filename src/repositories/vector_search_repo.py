"""Repository for vector similarity search over session chunks."""

import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, literal_column, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.session import Session
from src.models.db.session_chunk import SessionChunk


@dataclass
class ChunkSearchResult:
    """Result from a chunk similarity search."""

    chunk: SessionChunk
    score: float  # Cosine similarity score (0-1, higher is more similar)


class VectorSearchRepository:
    """Repository for semantic search over session chunks.

    Uses pgvector's cosine distance operator for similarity search.
    All queries are filtered by patient_id for security.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search_similar(
        self,
        query_embedding: list[float],
        patient_id: uuid.UUID,
        top_k: int = 5,
        min_score: float | None = None,
        session_ids: list[uuid.UUID] | None = None,
    ) -> list[ChunkSearchResult]:
        """Search for chunks similar to a query embedding.

        SECURITY: All results are filtered by patient_id to ensure
        patients can only access their own session data.

        Args:
            query_embedding: The embedding vector to search for
            patient_id: The patient ID to filter by (required for security)
            top_k: Maximum number of results to return (default: 5)
            min_score: Minimum similarity score threshold (0-1)
            session_ids: Optional list of session IDs to restrict search to

        Returns:
            List of ChunkSearchResult ordered by similarity (highest first)
        """
        # Convert embedding to pgvector format string and cast to vector type
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        # Build the query with cosine distance using literal_column for the similarity
        # pgvector uses <=> for cosine distance (1 - similarity)
        # We compute similarity as 1 - distance
        similarity_expr: ColumnElement[float] = literal_column(
            f"(1 - (session_chunks.embedding <=> '{embedding_str}'::vector))"
        ).label("similarity")
        query = (
            select(
                SessionChunk,
                similarity_expr,
            )
            .join(Session, SessionChunk.session_id == Session.id)
            .where(Session.patient_id == patient_id)
            .where(SessionChunk.embedding.isnot(None))
        )

        # Filter by specific sessions if provided
        if session_ids:
            query = query.where(SessionChunk.session_id.in_(session_ids))

        # Order by similarity (highest first) and limit
        query = query.order_by(text("similarity DESC")).limit(top_k)

        result = await self.session.execute(query)
        rows = result.all()

        # Filter by minimum score if specified
        results: list[ChunkSearchResult] = []
        for row in rows:
            chunk = row[0]
            score = float(row[1])

            if min_score is not None and score < min_score:
                continue

            results.append(ChunkSearchResult(chunk=chunk, score=score))

        return results

    async def search_by_session(
        self,
        query_embedding: list[float],
        session_id: uuid.UUID,
        patient_id: uuid.UUID,
        top_k: int = 5,
    ) -> list[ChunkSearchResult]:
        """Search for similar chunks within a specific session.

        Args:
            query_embedding: The embedding vector to search for
            session_id: The specific session to search in
            patient_id: The patient ID (required for security verification)
            top_k: Maximum number of results to return

        Returns:
            List of ChunkSearchResult ordered by similarity
        """
        return await self.search_similar(
            query_embedding=query_embedding,
            patient_id=patient_id,
            top_k=top_k,
            session_ids=[session_id],
        )

    async def get_chunk_count_by_patient(self, patient_id: uuid.UUID) -> int:
        """Get total chunk count for a patient.

        Args:
            patient_id: The patient ID

        Returns:
            Total number of chunks across all sessions
        """
        result = await self.session.execute(
            select(SessionChunk.id)
            .join(Session, SessionChunk.session_id == Session.id)
            .where(Session.patient_id == patient_id)
        )
        return len(result.scalars().all())

    async def get_sessions_with_embeddings(
        self, patient_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """Get session IDs that have embeddings for a patient.

        Args:
            patient_id: The patient ID

        Returns:
            List of session IDs with embeddings
        """
        result = await self.session.execute(
            select(SessionChunk.session_id)
            .distinct()
            .join(Session, SessionChunk.session_id == Session.id)
            .where(Session.patient_id == patient_id)
            .where(SessionChunk.embedding.isnot(None))
        )
        return list(result.scalars().all())
