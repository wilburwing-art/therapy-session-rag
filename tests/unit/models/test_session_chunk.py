"""Tests for SessionChunk model and schemas."""

import uuid
from datetime import datetime

import pytest

# Import all models to ensure relationships resolve properly
from src.models.db.api_key import ApiKey  # noqa: F401
from src.models.db.consent import Consent  # noqa: F401
from src.models.db.organization import Organization  # noqa: F401
from src.models.db.session import Session  # noqa: F401
from src.models.db.session_chunk import EMBEDDING_DIMENSION, SessionChunk
from src.models.db.transcript import Transcript  # noqa: F401
from src.models.db.user import User  # noqa: F401
from src.models.domain.session_chunk import (
    ChunkSearchRequest,
    ChunkSearchResult,
    SessionChunkCreate,
    SessionChunkRead,
    SessionChunkWithEmbedding,
    SessionChunkWithScore,
)


class TestSessionChunkModel:
    """Tests for SessionChunk database model."""

    def test_creates_session_chunk(self) -> None:
        """Test creating a session chunk."""
        session_id = uuid.uuid4()
        transcript_id = uuid.uuid4()

        chunk = SessionChunk(
            session_id=session_id,
            transcript_id=transcript_id,
            chunk_index=0,
            content="This is a test chunk of transcript text.",
            start_time=0.0,
            end_time=5.5,
            speaker="speaker_0",
            token_count=10,
        )

        assert chunk.session_id == session_id
        assert chunk.transcript_id == transcript_id
        assert chunk.chunk_index == 0
        assert chunk.content == "This is a test chunk of transcript text."
        assert chunk.start_time == 0.0
        assert chunk.end_time == 5.5
        assert chunk.speaker == "speaker_0"
        assert chunk.token_count == 10
        assert chunk.embedding is None

    def test_creates_chunk_with_embedding(self) -> None:
        """Test creating a chunk with embedding vector."""
        session_id = uuid.uuid4()
        transcript_id = uuid.uuid4()
        embedding = [0.1] * EMBEDDING_DIMENSION

        chunk = SessionChunk(
            session_id=session_id,
            transcript_id=transcript_id,
            chunk_index=0,
            content="Test content",
            embedding=embedding,
        )

        assert chunk.embedding == embedding
        assert len(chunk.embedding) == EMBEDDING_DIMENSION

    def test_creates_chunk_with_metadata(self) -> None:
        """Test creating a chunk with metadata."""
        session_id = uuid.uuid4()
        transcript_id = uuid.uuid4()

        chunk = SessionChunk(
            session_id=session_id,
            transcript_id=transcript_id,
            chunk_index=0,
            content="Test content",
            chunk_metadata={"source": "deepgram", "confidence": 0.95},
        )

        assert chunk.chunk_metadata == {"source": "deepgram", "confidence": 0.95}

    def test_embedding_dimension_constant(self) -> None:
        """Test that embedding dimension is correctly set."""
        assert EMBEDDING_DIMENSION == 1536

    def test_tablename(self) -> None:
        """Test table name is correct."""
        assert SessionChunk.__tablename__ == "session_chunks"


class TestSessionChunkSchemas:
    """Tests for SessionChunk Pydantic schemas."""

    def test_session_chunk_create(self) -> None:
        """Test SessionChunkCreate schema."""
        session_id = uuid.uuid4()
        transcript_id = uuid.uuid4()

        chunk = SessionChunkCreate(
            session_id=session_id,
            transcript_id=transcript_id,
            chunk_index=0,
            content="Test chunk content",
            start_time=0.0,
            end_time=10.0,
            speaker="speaker_1",
            token_count=50,
        )

        assert chunk.session_id == session_id
        assert chunk.transcript_id == transcript_id
        assert chunk.chunk_index == 0
        assert chunk.content == "Test chunk content"

    def test_session_chunk_create_minimal(self) -> None:
        """Test SessionChunkCreate with minimal fields."""
        session_id = uuid.uuid4()
        transcript_id = uuid.uuid4()

        chunk = SessionChunkCreate(
            session_id=session_id,
            transcript_id=transcript_id,
            chunk_index=0,
            content="Minimal content",
        )

        assert chunk.session_id == session_id
        assert chunk.start_time is None
        assert chunk.speaker is None
        assert chunk.token_count is None

    def test_session_chunk_create_rejects_negative_index(self) -> None:
        """Test that negative chunk index is rejected."""
        with pytest.raises(ValueError):
            SessionChunkCreate(
                session_id=uuid.uuid4(),
                transcript_id=uuid.uuid4(),
                chunk_index=-1,
                content="Test",
            )

    def test_session_chunk_read(self) -> None:
        """Test SessionChunkRead schema."""
        chunk_id = uuid.uuid4()
        session_id = uuid.uuid4()
        transcript_id = uuid.uuid4()
        now = datetime.utcnow()

        chunk = SessionChunkRead(
            id=chunk_id,
            session_id=session_id,
            transcript_id=transcript_id,
            chunk_index=5,
            content="Read chunk content",
            start_time=30.0,
            end_time=45.5,
            speaker="speaker_0",
            token_count=100,
            chunk_metadata={"key": "value"},
            created_at=now,
            updated_at=now,
        )

        assert chunk.id == chunk_id
        assert chunk.session_id == session_id
        assert chunk.transcript_id == transcript_id
        assert chunk.created_at == now

    def test_session_chunk_with_embedding(self) -> None:
        """Test SessionChunkWithEmbedding schema."""
        chunk_id = uuid.uuid4()
        session_id = uuid.uuid4()
        transcript_id = uuid.uuid4()
        now = datetime.utcnow()
        embedding = [0.5] * EMBEDDING_DIMENSION

        chunk = SessionChunkWithEmbedding(
            id=chunk_id,
            session_id=session_id,
            transcript_id=transcript_id,
            chunk_index=0,
            content="Content with embedding",
            embedding=embedding,
            created_at=now,
            updated_at=now,
        )

        assert chunk.embedding == embedding
        assert len(chunk.embedding) == EMBEDDING_DIMENSION

    def test_session_chunk_with_score(self) -> None:
        """Test SessionChunkWithScore schema."""
        chunk_id = uuid.uuid4()
        session_id = uuid.uuid4()
        transcript_id = uuid.uuid4()
        now = datetime.utcnow()

        chunk = SessionChunkWithScore(
            id=chunk_id,
            session_id=session_id,
            transcript_id=transcript_id,
            chunk_index=0,
            content="Scored content",
            score=0.85,
            created_at=now,
            updated_at=now,
        )

        assert chunk.score == 0.85

    def test_session_chunk_with_score_validates_range(self) -> None:
        """Test that score must be between 0 and 1."""
        with pytest.raises(ValueError):
            SessionChunkWithScore(
                id=uuid.uuid4(),
                session_id=uuid.uuid4(),
                transcript_id=uuid.uuid4(),
                chunk_index=0,
                content="Test",
                score=1.5,  # Invalid: > 1
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )


class TestChunkSearchSchemas:
    """Tests for chunk search request/response schemas."""

    def test_chunk_search_request(self) -> None:
        """Test ChunkSearchRequest schema."""
        patient_id = uuid.uuid4()

        request = ChunkSearchRequest(
            query="What did we discuss about anxiety?",
            patient_id=patient_id,
            top_k=10,
            min_score=0.7,
        )

        assert request.query == "What did we discuss about anxiety?"
        assert request.patient_id == patient_id
        assert request.top_k == 10
        assert request.min_score == 0.7

    def test_chunk_search_request_defaults(self) -> None:
        """Test ChunkSearchRequest default values."""
        patient_id = uuid.uuid4()

        request = ChunkSearchRequest(
            query="Test query",
            patient_id=patient_id,
        )

        assert request.top_k == 5
        assert request.min_score is None

    def test_chunk_search_request_validates_top_k(self) -> None:
        """Test that top_k must be between 1 and 20."""
        with pytest.raises(ValueError):
            ChunkSearchRequest(
                query="Test",
                patient_id=uuid.uuid4(),
                top_k=0,  # Invalid: < 1
            )

        with pytest.raises(ValueError):
            ChunkSearchRequest(
                query="Test",
                patient_id=uuid.uuid4(),
                top_k=50,  # Invalid: > 20
            )

    def test_chunk_search_request_rejects_empty_query(self) -> None:
        """Test that empty query is rejected."""
        with pytest.raises(ValueError):
            ChunkSearchRequest(
                query="",
                patient_id=uuid.uuid4(),
            )

    def test_chunk_search_result(self) -> None:
        """Test ChunkSearchResult schema."""
        chunk_id = uuid.uuid4()
        session_id = uuid.uuid4()
        transcript_id = uuid.uuid4()
        now = datetime.utcnow()

        chunk = SessionChunkWithScore(
            id=chunk_id,
            session_id=session_id,
            transcript_id=transcript_id,
            chunk_index=0,
            content="Found content",
            score=0.92,
            created_at=now,
            updated_at=now,
        )

        result = ChunkSearchResult(
            chunks=[chunk],
            query="search query",
            total_found=1,
        )

        assert len(result.chunks) == 1
        assert result.query == "search query"
        assert result.total_found == 1
        assert result.chunks[0].score == 0.92

    def test_chunk_search_result_empty(self) -> None:
        """Test ChunkSearchResult with no results."""
        result = ChunkSearchResult(
            chunks=[],
            query="no match query",
            total_found=0,
        )

        assert len(result.chunks) == 0
        assert result.total_found == 0
