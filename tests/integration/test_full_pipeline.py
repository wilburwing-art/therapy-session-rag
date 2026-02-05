"""Full pipeline integration tests.

Tests the complete flow: upload → transcribe → embed → chat
Uses mocked external services (Deepgram, OpenAI, Claude) but real database.
"""

import os
import uuid
from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.consent import Consent
from src.models.db.session import Session, SessionStatus
from src.models.db.user import User
from src.repositories.chunk_repo import ChunkRepository
from src.repositories.session_repo import SessionRepository
from src.repositories.transcript_repo import TranscriptRepository
from src.services.embedding_service import EmbeddingService
from src.services.transcription_service import TranscriptionService

pytestmark = pytest.mark.asyncio


class TestFullPipeline:
    """Test the complete therapy session pipeline."""

    @pytest_asyncio.fixture
    async def test_session(
        self,
        db_session: AsyncSession,
        test_patient: User,
        test_therapist: User,
        test_consent: Consent,
    ) -> Session:
        """Create a test therapy session."""
        session = Session(
            id=uuid.uuid4(),
            patient_id=test_patient.id,
            therapist_id=test_therapist.id,
            consent_id=test_consent.id,
            session_date=date(2025, 1, 15),
            status=SessionStatus.PENDING,
        )
        db_session.add(session)
        await db_session.flush()
        await db_session.refresh(session)
        return session

    async def test_create_session_via_api(
        self,
        async_client: AsyncClient,
        test_patient: User,
        test_therapist: User,
        test_consent: Consent,
    ):
        """Test creating a session through the API."""
        response = await async_client.post(
            "/api/v1/sessions",
            json={
                "patient_id": str(test_patient.id),
                "therapist_id": str(test_therapist.id),
                "consent_id": str(test_consent.id),
                "session_date": "2025-01-15",
            },
        )

        assert response.status_code == 201, response.text
        data = response.json()
        assert data["patient_id"] == str(test_patient.id)
        assert data["status"] == "pending"

    async def test_upload_recording_with_real_file(
        self,
        async_client: AsyncClient,
        test_session: Session,
        test_audio_content: bytes | None,
        mock_storage_service,
    ):
        """Test uploading a real audio recording."""
        if test_audio_content is None:
            pytest.skip("Test audio file not found")

        response = await async_client.post(
            f"/api/v1/sessions/{test_session.id}/recording",
            files={
                "file": ("test_session.m4a", test_audio_content, "audio/mp4"),
            },
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "uploaded"
        assert "recording_path" in data

    async def test_transcription_service(
        self,
        db_session: AsyncSession,
        test_session: Session,
        mock_deepgram_client,
        mock_storage_service,
    ):
        """Test the transcription service directly."""
        # Update session to have a recording path
        test_session.recording_path = "recordings/test/test_session.m4a"
        test_session.status = SessionStatus.UPLOADED
        await db_session.flush()

        # Run transcription
        service = TranscriptionService(db_session)

        # Create transcription job
        job = await service.create_transcription_job(test_session.id)
        assert job.session_id == test_session.id

        # Process transcription (with mocked Deepgram)
        # Note: This would normally be done by the worker
        # For testing, we call it directly with mocks
        transcript = await service.process_transcription(job.id)

        assert transcript.session_id == test_session.id
        assert "feeling" in transcript.full_text.lower()
        assert len(transcript.segments) > 0

    async def test_embedding_service(
        self,
        db_session: AsyncSession,
        test_session: Session,
        mock_embedding_client,
    ):
        """Test the embedding service directly."""
        # First, create a transcript
        transcript_repo = TranscriptRepository(db_session)
        from src.models.db.transcript import Transcript

        transcript = Transcript(
            id=uuid.uuid4(),
            session_id=test_session.id,
            full_text="Hello, how are you feeling today? I've been feeling anxious lately.",
            segments=[
                {
                    "text": "Hello, how are you feeling today?",
                    "start_time": 0.0,
                    "end_time": 2.3,
                    "speaker": "Speaker 0",
                },
                {
                    "text": "I've been feeling anxious lately.",
                    "start_time": 3.0,
                    "end_time": 5.1,
                    "speaker": "Speaker 1",
                },
            ],
            word_count=11,
            duration_seconds=5.1,
            language="en",
            confidence=0.95,
        )
        await transcript_repo.create_transcript(transcript)

        # Update session status
        test_session.status = SessionStatus.EMBEDDING
        await db_session.flush()

        # Run embedding
        service = EmbeddingService(db_session)
        chunks = await service.process_embeddings(test_session.id)

        assert len(chunks) > 0
        # Verify chunks were created with content
        for chunk in chunks:
            assert chunk.content
            assert chunk.session_id == test_session.id

    async def test_vector_search(
        self,
        db_session: AsyncSession,
        test_session: Session,
        test_patient: User,
        mock_embedding,
    ):
        """Test vector similarity search."""
        from src.models.db.session_chunk import SessionChunk
        from src.repositories.vector_search_repo import VectorSearchRepository

        chunk_repo = ChunkRepository(db_session)

        # Create test chunks with embeddings
        chunk = SessionChunk(
            id=uuid.uuid4(),
            session_id=test_session.id,
            transcript_id=uuid.uuid4(),  # Fake transcript ID for test
            chunk_index=0,
            content="I've been feeling anxious lately about work.",
            embedding=mock_embedding,
        )
        await chunk_repo.create_chunk(chunk)
        await db_session.flush()

        # Search for similar chunks
        vector_repo = VectorSearchRepository(db_session)
        results = await vector_repo.search_similar(
            query_embedding=mock_embedding,
            patient_id=test_patient.id,
            top_k=5,
        )

        assert len(results) > 0
        assert results[0].chunk.content == "I've been feeling anxious lately about work."

    async def test_chat_endpoint(
        self,
        async_client: AsyncClient,
        test_patient: User,
        mock_claude_client,
        mock_embedding_client,
        mock_redis,
    ):
        """Test the chat endpoint."""
        response = await async_client.post(
            "/api/v1/chat",
            params={"patient_id": str(test_patient.id)},
            json={
                "message": "What did we discuss about anxiety?",
                "top_k": 5,
            },
        )

        # Note: This may return empty sources if no chunks exist
        # but should still return a valid response
        assert response.status_code == 200, response.text
        data = response.json()
        assert "response" in data
        assert "sources" in data

    async def test_full_pipeline_with_mocks(
        self,
        db_session: AsyncSession,
        test_session: Session,
        test_patient: User,
        mock_deepgram_client,
        mock_embedding_client,
        mock_storage_service,
    ):
        """Test the complete pipeline with mocked external services."""
        # 1. Simulate recording upload
        test_session.recording_path = "recordings/test/session.m4a"
        test_session.status = SessionStatus.UPLOADED
        await db_session.flush()

        # 2. Run transcription
        transcription_service = TranscriptionService(db_session)
        job = await transcription_service.create_transcription_job(test_session.id)

        # Note: In real usage, this would be done by the worker
        # We need to mock the embedding queue to prevent it from actually queueing
        from unittest.mock import patch
        with patch("src.services.transcription_service.queue_embedding"):
            transcript = await transcription_service.process_transcription(job.id)

        assert transcript is not None
        assert transcript.full_text

        # 3. Run embedding
        embedding_service = EmbeddingService(db_session)
        chunks = await embedding_service.process_embeddings(test_session.id)

        assert len(chunks) > 0

        # 4. Verify session is ready
        session_repo = SessionRepository(db_session)
        updated_session = await session_repo.get_by_id(test_session.id)
        assert updated_session is not None
        assert updated_session.status == SessionStatus.READY

        # 5. Verify chunks have embeddings
        chunk_repo = ChunkRepository(db_session)
        has_embeddings = await chunk_repo.has_embeddings(test_session.id)
        assert has_embeddings


class TestPipelineErrorHandling:
    """Test error handling in the pipeline."""

    @pytest_asyncio.fixture
    async def test_session(
        self,
        db_session: AsyncSession,
        test_patient: User,
        test_therapist: User,
        test_consent: Consent,
    ) -> Session:
        """Create a test therapy session."""
        session = Session(
            id=uuid.uuid4(),
            patient_id=test_patient.id,
            therapist_id=test_therapist.id,
            consent_id=test_consent.id,
            session_date=date(2025, 1, 15),
            status=SessionStatus.PENDING,
        )
        db_session.add(session)
        await db_session.flush()
        await db_session.refresh(session)
        return session

    async def test_transcription_without_recording_fails(
        self,
        db_session: AsyncSession,
        test_session: Session,
    ):
        """Test that transcription fails if no recording exists."""
        service = TranscriptionService(db_session)

        job = await service.create_transcription_job(test_session.id)

        from src.services.transcription_service import TranscriptionError

        with pytest.raises(TranscriptionError, match="no recording"):
            await service.process_transcription(job.id)

    async def test_embedding_without_transcript_fails(
        self,
        db_session: AsyncSession,
        test_session: Session,
    ):
        """Test that embedding fails if no transcript exists."""
        service = EmbeddingService(db_session)

        from src.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError, match="Transcript"):
            await service.process_embeddings(test_session.id)

    async def test_api_requires_auth(
        self,
        async_client: AsyncClient,
    ):
        """Test that API endpoints require authentication."""
        # Create a new client without the API key header
        from httpx import ASGITransport
        from httpx import AsyncClient as HttpxClient

        from src.main import app

        transport = ASGITransport(app=app)
        async with HttpxClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/sessions")
            assert response.status_code == 401


class TestWithRealAudioFile:
    """Tests that use the real therapy session audio file.

    These tests require:
    1. The audio file at /Users/wilburpyn/Downloads/Wilbur-therapy-1-15-26.m4a
    2. Running Docker services (postgres, redis, minio)
    3. Valid API keys for Deepgram, OpenAI, Claude (for non-mocked tests)
    """

    @pytest.fixture
    def real_audio_path(self) -> str:
        """Get the path to the real audio file."""
        return "/Users/wilburpyn/Downloads/Wilbur-therapy-1-15-26.m4a"

    async def test_real_audio_file_exists(self, real_audio_path: str):
        """Verify the test audio file exists."""
        assert os.path.exists(real_audio_path), f"Audio file not found at {real_audio_path}"

        # Check file size (should be ~48MB)
        size = os.path.getsize(real_audio_path)
        assert size > 1_000_000, f"Audio file seems too small: {size} bytes"

    async def test_audio_file_is_valid_m4a(self, real_audio_path: str):
        """Verify the audio file is a valid M4A."""
        if not os.path.exists(real_audio_path):
            pytest.skip("Audio file not found")

        with open(real_audio_path, "rb") as f:
            header = f.read(12)

        # M4A files typically have 'ftyp' at offset 4
        assert b"ftyp" in header, "File doesn't appear to be a valid M4A"
