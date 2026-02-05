"""Tests for embedding service."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

# Import all models to ensure relationships resolve properly
from src.models.db.api_key import ApiKey  # noqa: F401
from src.models.db.consent import Consent  # noqa: F401
from src.models.db.organization import Organization  # noqa: F401
from src.models.db.session import Session, SessionStatus
from src.models.db.session_chunk import SessionChunk
from src.models.db.transcript import Transcript
from src.models.db.user import User  # noqa: F401
from src.services.embedding_client import EmbeddingError, EmbeddingResult
from src.services.embedding_service import ChunkData, EmbeddingService, EmbeddingServiceError


@pytest.fixture
def mock_db_session() -> MagicMock:
    """Create mock database session."""
    return MagicMock()


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings."""
    settings = MagicMock()
    settings.openai_api_key = "test-key"
    return settings


@pytest.fixture
def embedding_service(
    mock_db_session: MagicMock,
    mock_settings: MagicMock,
) -> EmbeddingService:
    """Create embedding service with mocks."""
    return EmbeddingService(
        db_session=mock_db_session,
        settings=mock_settings,
    )


@pytest.fixture
def sample_session() -> Session:
    """Create sample session."""
    session = MagicMock(spec=Session)
    session.id = uuid.uuid4()
    session.status = SessionStatus.TRANSCRIBING
    return session


@pytest.fixture
def sample_transcript() -> Transcript:
    """Create sample transcript."""
    transcript = MagicMock(spec=Transcript)
    transcript.id = uuid.uuid4()
    transcript.full_text = "Hello, how are you doing today? I'm doing well, thank you."
    transcript.segments = [
        {
            "text": "Hello, how are you doing today?",
            "start_time": 0.0,
            "end_time": 2.5,
            "speaker": "Speaker 0",
        },
        {
            "text": "I'm doing well, thank you.",
            "start_time": 2.5,
            "end_time": 4.5,
            "speaker": "Speaker 1",
        },
    ]
    return transcript


class TestChunkTranscript:
    """Tests for chunk_transcript method."""

    def test_chunks_by_segments(self, embedding_service: EmbeddingService) -> None:
        """Test chunking with segment data."""
        full_text = "Hello there. How are you?"
        segments = [
            {"text": "Hello there.", "start_time": 0.0, "end_time": 1.0, "speaker": "A"},
            {"text": "How are you?", "start_time": 1.0, "end_time": 2.0, "speaker": "B"},
        ]

        chunks = embedding_service.chunk_transcript(full_text, segments)

        # Small segments should be combined
        assert len(chunks) >= 1
        assert chunks[0].content
        assert chunks[0].chunk_index == 0

    def test_preserves_speaker_info(self, embedding_service: EmbeddingService) -> None:
        """Test that speaker info is preserved."""
        # Create segments with clear speaker changes
        segments = [
            {"text": "First speaker talking here.", "start_time": 0.0, "end_time": 1.0, "speaker": "A"},
            {"text": "Second speaker now.", "start_time": 1.0, "end_time": 2.0, "speaker": "B"},
        ]

        chunks = embedding_service.chunk_transcript("", segments)

        # Should have speaker info
        for chunk in chunks:
            if chunk.speaker:
                assert chunk.speaker in ["A", "B"]

    def test_preserves_timing(self, embedding_service: EmbeddingService) -> None:
        """Test that timing info is preserved."""
        segments = [
            {"text": "Start segment.", "start_time": 5.0, "end_time": 7.0, "speaker": "A"},
            {"text": "End segment.", "start_time": 7.0, "end_time": 10.0, "speaker": "A"},
        ]

        chunks = embedding_service.chunk_transcript("", segments)

        assert len(chunks) >= 1
        assert chunks[0].start_time == 5.0
        assert chunks[-1].end_time == 10.0

    def test_handles_empty_segments(self, embedding_service: EmbeddingService) -> None:
        """Test handling empty segments list."""
        chunks = embedding_service.chunk_transcript("Plain text without segments.", [])

        # Should fall back to plain text chunking
        assert len(chunks) >= 1
        assert "Plain text" in chunks[0].content

    def test_handles_empty_text(self, embedding_service: EmbeddingService) -> None:
        """Test handling empty text."""
        chunks = embedding_service.chunk_transcript("", [])
        assert len(chunks) == 0

    def test_respects_max_chunk_size(self, embedding_service: EmbeddingService) -> None:
        """Test that chunks don't exceed max size."""
        # Create multiple segments that together exceed max chunk size
        segment_text = "word " * 200  # ~1000 chars = ~250 tokens each
        segments = [
            {"text": segment_text, "start_time": 0.0, "end_time": 10.0, "speaker": "A"},
            {"text": segment_text, "start_time": 10.0, "end_time": 20.0, "speaker": "A"},
            {"text": segment_text, "start_time": 20.0, "end_time": 30.0, "speaker": "A"},
            {"text": segment_text, "start_time": 30.0, "end_time": 40.0, "speaker": "A"},
        ]

        chunks = embedding_service.chunk_transcript("", segments)

        # Should split into multiple chunks (4 segments at ~250 tokens each > 500 target)
        assert len(chunks) >= 2

    def test_stores_segment_indices(self, embedding_service: EmbeddingService) -> None:
        """Test that segment indices are stored."""
        segments = [
            {"text": "First.", "start_time": 0.0, "end_time": 1.0, "speaker": "A"},
            {"text": "Second.", "start_time": 1.0, "end_time": 2.0, "speaker": "A"},
            {"text": "Third.", "start_time": 2.0, "end_time": 3.0, "speaker": "A"},
        ]

        chunks = embedding_service.chunk_transcript("", segments)

        # Should have segment indices
        all_indices = []
        for chunk in chunks:
            all_indices.extend(chunk.segment_indices)

        # All segments should be referenced
        assert 0 in all_indices
        assert 1 in all_indices
        assert 2 in all_indices


class TestChunkPlainText:
    """Tests for plain text chunking."""

    def test_chunks_plain_text(self, embedding_service: EmbeddingService) -> None:
        """Test chunking plain text."""
        text = " ".join(["word"] * 200)

        chunks = embedding_service._chunk_plain_text(text)

        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk.content
            assert chunk.start_time is None
            assert chunk.speaker is None

    def test_empty_text_returns_empty(self, embedding_service: EmbeddingService) -> None:
        """Test empty text returns empty list."""
        chunks = embedding_service._chunk_plain_text("")
        assert len(chunks) == 0

        chunks = embedding_service._chunk_plain_text("   ")
        assert len(chunks) == 0


class TestProcessEmbeddings:
    """Tests for process_embeddings method."""

    @pytest.mark.asyncio
    async def test_processes_embeddings_successfully(
        self,
        embedding_service: EmbeddingService,
        sample_session: Session,
        sample_transcript: Transcript,
    ) -> None:
        """Test successful embedding processing."""
        # Setup mocks
        embedding_service.session_repo.get_by_id = AsyncMock(return_value=sample_session)
        embedding_service.transcript_repo.get_transcript_by_session_id = AsyncMock(
            return_value=sample_transcript
        )
        embedding_service.chunk_repo.delete_chunks_by_transcript = AsyncMock(
            return_value=0
        )

        # Mock chunk creation
        created_chunks = [
            MagicMock(
                id=uuid.uuid4(),
                session_id=sample_session.id,
                transcript_id=sample_transcript.id,
                chunk_index=0,
                content="Test content",
                start_time=0.0,
                end_time=1.0,
                speaker="Speaker 0",
                token_count=10,
                chunk_metadata={},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        ]
        embedding_service.chunk_repo.create_chunks_batch = AsyncMock(
            return_value=created_chunks
        )
        embedding_service.chunk_repo.update_chunk_embedding = AsyncMock(
            return_value=True
        )
        embedding_service.session_repo.update_status = AsyncMock()

        # Mock embedding client
        mock_embedding_result = EmbeddingResult(
            text="Test content",
            embedding=[0.1] * 1536,
            model="text-embedding-3-small",
            token_count=10,
        )
        embedding_service._embedding_client = MagicMock()
        embedding_service._embedding_client.embed_batch = AsyncMock(
            return_value=[mock_embedding_result]
        )

        # Execute
        results = await embedding_service.process_embeddings(sample_session.id)

        # Verify
        assert len(results) == 1
        embedding_service.session_repo.update_status.assert_called_with(
            session_id=sample_session.id,
            status=SessionStatus.READY,
        )

    @pytest.mark.asyncio
    async def test_raises_not_found_for_missing_session(
        self, embedding_service: EmbeddingService
    ) -> None:
        """Test NotFoundError for missing session."""
        embedding_service.session_repo.get_by_id = AsyncMock(return_value=None)

        from src.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            await embedding_service.process_embeddings(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_raises_not_found_for_missing_transcript(
        self,
        embedding_service: EmbeddingService,
        sample_session: Session,
    ) -> None:
        """Test NotFoundError for missing transcript."""
        embedding_service.session_repo.get_by_id = AsyncMock(return_value=sample_session)
        embedding_service.transcript_repo.get_transcript_by_session_id = AsyncMock(
            return_value=None
        )

        from src.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            await embedding_service.process_embeddings(sample_session.id)

    @pytest.mark.asyncio
    async def test_handles_embedding_error(
        self,
        embedding_service: EmbeddingService,
        sample_session: Session,
        sample_transcript: Transcript,
    ) -> None:
        """Test handling of embedding API errors."""
        # Setup mocks
        embedding_service.session_repo.get_by_id = AsyncMock(return_value=sample_session)
        embedding_service.transcript_repo.get_transcript_by_session_id = AsyncMock(
            return_value=sample_transcript
        )
        embedding_service.chunk_repo.delete_chunks_by_transcript = AsyncMock(
            return_value=0
        )
        embedding_service.chunk_repo.create_chunks_batch = AsyncMock(
            return_value=[MagicMock()]
        )
        embedding_service.session_repo.update_status = AsyncMock()

        # Mock embedding client to fail
        embedding_service._embedding_client = MagicMock()
        embedding_service._embedding_client.embed_batch = AsyncMock(
            side_effect=EmbeddingError("API error")
        )

        # Execute and verify
        with pytest.raises(EmbeddingServiceError):
            await embedding_service.process_embeddings(sample_session.id)

        # Should mark session as failed
        embedding_service.session_repo.update_status.assert_called_with(
            session_id=sample_session.id,
            status=SessionStatus.FAILED,
            error_message="API error",
        )

    @pytest.mark.asyncio
    async def test_deletes_existing_chunks_on_reprocess(
        self,
        embedding_service: EmbeddingService,
        sample_session: Session,
        sample_transcript: Transcript,
    ) -> None:
        """Test that existing chunks are deleted on reprocess."""
        # Setup mocks
        embedding_service.session_repo.get_by_id = AsyncMock(return_value=sample_session)
        embedding_service.transcript_repo.get_transcript_by_session_id = AsyncMock(
            return_value=sample_transcript
        )
        embedding_service.chunk_repo.delete_chunks_by_transcript = AsyncMock(
            return_value=5  # 5 chunks deleted
        )
        embedding_service.chunk_repo.create_chunks_batch = AsyncMock(
            return_value=[]
        )
        embedding_service.session_repo.update_status = AsyncMock()

        # Mock empty transcript to simplify
        sample_transcript.segments = []
        sample_transcript.full_text = ""

        await embedding_service.process_embeddings(sample_session.id)

        # Should have called delete
        embedding_service.chunk_repo.delete_chunks_by_transcript.assert_called_once_with(
            sample_transcript.id
        )


class TestTokenEstimate:
    """Tests for token estimation."""

    def test_estimates_tokens(self, embedding_service: EmbeddingService) -> None:
        """Test token estimation."""
        short_text = "hi"
        long_text = "a" * 100

        short_estimate = embedding_service._estimate_tokens(short_text)
        long_estimate = embedding_service._estimate_tokens(long_text)

        assert short_estimate >= 1
        assert long_estimate > short_estimate


class TestGetChunksForSession:
    """Tests for get_chunks_for_session method."""

    @pytest.mark.asyncio
    async def test_returns_chunks(self, embedding_service: EmbeddingService) -> None:
        """Test getting chunks for a session."""
        session_id = uuid.uuid4()

        mock_chunk = MagicMock(spec=SessionChunk)
        mock_chunk.id = uuid.uuid4()
        mock_chunk.session_id = session_id
        mock_chunk.transcript_id = uuid.uuid4()
        mock_chunk.chunk_index = 0
        mock_chunk.content = "Test content"
        mock_chunk.start_time = 0.0
        mock_chunk.end_time = 1.0
        mock_chunk.speaker = "Speaker 0"
        mock_chunk.token_count = 10
        mock_chunk.chunk_metadata = {}
        mock_chunk.created_at = datetime.now(UTC)
        mock_chunk.updated_at = datetime.now(UTC)

        embedding_service.chunk_repo.get_chunks_by_session = AsyncMock(
            return_value=[mock_chunk]
        )

        results = await embedding_service.get_chunks_for_session(session_id)

        assert len(results) == 1
        assert results[0].content == "Test content"


class TestHasEmbeddings:
    """Tests for has_embeddings method."""

    @pytest.mark.asyncio
    async def test_returns_true_when_has_embeddings(
        self, embedding_service: EmbeddingService
    ) -> None:
        """Test returns True when session has embeddings."""
        session_id = uuid.uuid4()
        embedding_service.chunk_repo.has_embeddings = AsyncMock(return_value=True)

        result = await embedding_service.has_embeddings(session_id)

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_embeddings(
        self, embedding_service: EmbeddingService
    ) -> None:
        """Test returns False when no embeddings."""
        session_id = uuid.uuid4()
        embedding_service.chunk_repo.has_embeddings = AsyncMock(return_value=False)

        result = await embedding_service.has_embeddings(session_id)

        assert result is False


class TestChunkData:
    """Tests for ChunkData dataclass."""

    def test_creates_chunk_data(self) -> None:
        """Test ChunkData creation."""
        chunk = ChunkData(
            content="Test content",
            chunk_index=0,
            start_time=0.0,
            end_time=1.0,
            speaker="Speaker A",
            segment_indices=[0, 1, 2],
        )

        assert chunk.content == "Test content"
        assert chunk.chunk_index == 0
        assert chunk.start_time == 0.0
        assert chunk.end_time == 1.0
        assert chunk.speaker == "Speaker A"
        assert chunk.segment_indices == [0, 1, 2]
