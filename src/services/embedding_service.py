"""Service for chunking transcripts and generating embeddings."""

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.exceptions import NotFoundError
from src.models.db.session import SessionStatus
from src.models.db.session_chunk import SessionChunk
from src.models.domain.session_chunk import SessionChunkRead
from src.repositories.chunk_repo import ChunkRepository
from src.repositories.session_repo import SessionRepository
from src.repositories.transcript_repo import TranscriptRepository
from src.services.embedding_client import EmbeddingClient, EmbeddingError

logger = logging.getLogger(__name__)


class EmbeddingServiceError(Exception):
    """Error during embedding processing."""

    pass


@dataclass
class ChunkData:
    """Data for a transcript chunk."""

    content: str
    chunk_index: int
    start_time: float | None
    end_time: float | None
    speaker: str | None
    segment_indices: list[int]


class EmbeddingService:
    """Service for chunking transcripts and generating embeddings.

    Handles the workflow of:
    1. Splitting transcripts into semantic chunks
    2. Generating embeddings for each chunk
    3. Storing chunks with embeddings in the database
    4. Updating session status
    """

    # Target chunk size in tokens (approximate)
    TARGET_CHUNK_SIZE = 500
    MAX_CHUNK_SIZE = 750
    MIN_CHUNK_SIZE = 100

    def __init__(
        self,
        db_session: AsyncSession,
        settings: Settings | None = None,
    ) -> None:
        self.db_session = db_session
        self.settings = settings or get_settings()
        self.session_repo = SessionRepository(db_session)
        self.transcript_repo = TranscriptRepository(db_session)
        self.chunk_repo = ChunkRepository(db_session)
        self._embedding_client: EmbeddingClient | None = None

    @property
    def embedding_client(self) -> EmbeddingClient:
        """Get or create embedding client (lazy initialization)."""
        if self._embedding_client is None:
            self._embedding_client = EmbeddingClient(settings=self.settings)
        return self._embedding_client

    async def process_embeddings(
        self,
        session_id: uuid.UUID,
    ) -> list[SessionChunkRead]:
        """Process embeddings for a session's transcript.

        This is the main workflow method that:
        1. Gets the transcript for the session
        2. Chunks the transcript text
        3. Generates embeddings for each chunk
        4. Stores chunks in the database
        5. Updates session status

        Args:
            session_id: The session ID

        Returns:
            List of created SessionChunkRead objects

        Raises:
            NotFoundError: If session or transcript not found
            EmbeddingServiceError: If processing fails
        """
        # Get session
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise NotFoundError(resource="Session", resource_id=str(session_id))

        # Get transcript
        transcript = await self.transcript_repo.get_transcript_by_session_id(session_id)
        if not transcript:
            raise NotFoundError(
                resource="Transcript",
                detail=f"No transcript found for session {session_id}",
            )

        try:
            # Delete any existing chunks (for re-embedding)
            deleted_count = await self.chunk_repo.delete_chunks_by_transcript(
                transcript.id
            )
            if deleted_count > 0:
                logger.info(
                    f"Deleted {deleted_count} existing chunks for transcript {transcript.id}"
                )

            # Chunk the transcript
            chunks_data = self.chunk_transcript(
                full_text=transcript.full_text,
                segments=transcript.segments,
            )

            if not chunks_data:
                logger.warning(f"No chunks generated for transcript {transcript.id}")
                # Still mark as ready if there's no content to embed
                await self.session_repo.update_status(
                    session_id=session_id,
                    status=SessionStatus.READY,
                )
                return []

            # Create chunk records
            chunk_models: list[SessionChunk] = []
            for chunk_data in chunks_data:
                chunk = SessionChunk(
                    session_id=session_id,
                    transcript_id=transcript.id,
                    chunk_index=chunk_data.chunk_index,
                    content=chunk_data.content,
                    start_time=chunk_data.start_time,
                    end_time=chunk_data.end_time,
                    speaker=chunk_data.speaker,
                    chunk_metadata={
                        "segment_indices": chunk_data.segment_indices,
                    },
                )
                chunk_models.append(chunk)

            # Save chunks
            created_chunks = await self.chunk_repo.create_chunks_batch(chunk_models)
            logger.info(f"Created {len(created_chunks)} chunks for session {session_id}")

            # Generate embeddings in batches
            texts = [chunk.content for chunk in created_chunks]
            embeddings = await self.embedding_client.embed_batch(texts)

            # Update chunks with embeddings
            for chunk, embedding_result in zip(created_chunks, embeddings, strict=True):
                await self.chunk_repo.update_chunk_embedding(
                    chunk_id=chunk.id,
                    embedding=embedding_result.embedding,
                    token_count=embedding_result.token_count,
                )

            logger.info(f"Generated embeddings for {len(embeddings)} chunks")

            # Update session status to ready
            await self.session_repo.update_status(
                session_id=session_id,
                status=SessionStatus.READY,
            )

            return [self._to_chunk_read(chunk) for chunk in created_chunks]

        except EmbeddingError as e:
            logger.error(f"Embedding error for session {session_id}: {e}")
            await self._fail_session(session_id, str(e))
            raise EmbeddingServiceError(f"Failed to generate embeddings: {e}") from e

        except Exception as e:
            logger.exception(f"Unexpected error processing embeddings for {session_id}")
            await self._fail_session(session_id, str(e))
            raise EmbeddingServiceError(f"Embedding processing failed: {e}") from e

    def chunk_transcript(
        self,
        full_text: str,
        segments: list[dict[str, Any]],
    ) -> list[ChunkData]:
        """Split a transcript into semantic chunks.

        Uses segments with speaker information to create chunks
        that preserve semantic boundaries while staying within
        target token limits.

        Args:
            full_text: The full transcript text
            segments: List of segment dicts with text, start_time, end_time, speaker

        Returns:
            List of ChunkData objects
        """
        if not segments:
            # No segments, chunk by character count
            return self._chunk_plain_text(full_text)

        chunks: list[ChunkData] = []
        current_texts: list[str] = []
        current_speaker: str | None = None
        current_start: float | None = None
        current_end: float | None = None
        current_segment_indices: list[int] = []
        current_token_estimate = 0

        for i, segment in enumerate(segments):
            segment_text = segment.get("text", "").strip()
            if not segment_text:
                continue

            segment_speaker = segment.get("speaker")
            segment_start = segment.get("start_time", segment.get("start"))
            segment_end = segment.get("end_time", segment.get("end"))
            segment_tokens = self._estimate_tokens(segment_text)

            # Check if we should start a new chunk
            should_split = False

            # Split if speaker changes
            if current_speaker is not None and segment_speaker != current_speaker:
                should_split = True

            # Split if we'd exceed max chunk size
            if current_token_estimate + segment_tokens > self.MAX_CHUNK_SIZE:
                should_split = True

            # Don't split if current chunk is too small
            if current_token_estimate < self.MIN_CHUNK_SIZE:
                should_split = False

            if should_split and current_texts:
                # Save current chunk
                chunks.append(
                    ChunkData(
                        content=" ".join(current_texts),
                        chunk_index=len(chunks),
                        start_time=current_start,
                        end_time=current_end,
                        speaker=current_speaker,
                        segment_indices=current_segment_indices,
                    )
                )
                current_texts = []
                current_segment_indices = []
                current_token_estimate = 0
                current_start = None

            # Add segment to current chunk
            current_texts.append(segment_text)
            current_segment_indices.append(i)
            current_token_estimate += segment_tokens
            current_speaker = segment_speaker

            if current_start is None:
                current_start = segment_start
            current_end = segment_end

            # Force split at target size
            if current_token_estimate >= self.TARGET_CHUNK_SIZE:
                chunks.append(
                    ChunkData(
                        content=" ".join(current_texts),
                        chunk_index=len(chunks),
                        start_time=current_start,
                        end_time=current_end,
                        speaker=current_speaker,
                        segment_indices=current_segment_indices,
                    )
                )
                current_texts = []
                current_segment_indices = []
                current_token_estimate = 0
                current_start = None
                current_speaker = None

        # Save final chunk
        if current_texts:
            chunks.append(
                ChunkData(
                    content=" ".join(current_texts),
                    chunk_index=len(chunks),
                    start_time=current_start,
                    end_time=current_end,
                    speaker=current_speaker,
                    segment_indices=current_segment_indices,
                )
            )

        return chunks

    def _chunk_plain_text(self, text: str) -> list[ChunkData]:
        """Chunk plain text without segment information.

        Args:
            text: The text to chunk

        Returns:
            List of ChunkData objects
        """
        if not text.strip():
            return []

        chunks: list[ChunkData] = []
        words = text.split()
        current_words: list[str] = []
        current_tokens = 0

        for word in words:
            word_tokens = self._estimate_tokens(word)

            if current_tokens + word_tokens > self.TARGET_CHUNK_SIZE and current_words:
                chunks.append(
                    ChunkData(
                        content=" ".join(current_words),
                        chunk_index=len(chunks),
                        start_time=None,
                        end_time=None,
                        speaker=None,
                        segment_indices=[],
                    )
                )
                current_words = []
                current_tokens = 0

            current_words.append(word)
            current_tokens += word_tokens

        if current_words:
            chunks.append(
                ChunkData(
                    content=" ".join(current_words),
                    chunk_index=len(chunks),
                    start_time=None,
                    end_time=None,
                    speaker=None,
                    segment_indices=[],
                )
            )

        return chunks

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Uses simple heuristic of ~4 characters per token.

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        return len(text) // 4 + 1

    async def get_chunks_for_session(
        self, session_id: uuid.UUID
    ) -> list[SessionChunkRead]:
        """Get all chunks for a session.

        Args:
            session_id: The session ID

        Returns:
            List of SessionChunkRead objects
        """
        chunks = await self.chunk_repo.get_chunks_by_session(session_id)
        return [self._to_chunk_read(chunk) for chunk in chunks]

    async def has_embeddings(self, session_id: uuid.UUID) -> bool:
        """Check if a session has embeddings generated.

        Args:
            session_id: The session ID

        Returns:
            True if session has embeddings
        """
        return await self.chunk_repo.has_embeddings(session_id)

    async def _fail_session(
        self, session_id: uuid.UUID, error_message: str
    ) -> None:
        """Mark a session as failed.

        Args:
            session_id: The session ID
            error_message: Error description
        """
        await self.session_repo.update_status(
            session_id=session_id,
            status=SessionStatus.FAILED,
            error_message=error_message,
        )

    def _to_chunk_read(self, chunk: SessionChunk) -> SessionChunkRead:
        """Convert SessionChunk DB model to SessionChunkRead schema."""
        return SessionChunkRead(
            id=chunk.id,
            session_id=chunk.session_id,
            transcript_id=chunk.transcript_id,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            start_time=chunk.start_time,
            end_time=chunk.end_time,
            speaker=chunk.speaker,
            token_count=chunk.token_count,
            chunk_metadata=chunk.chunk_metadata,
            created_at=chunk.created_at,
            updated_at=chunk.updated_at,
        )
