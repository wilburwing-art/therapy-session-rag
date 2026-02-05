"""Tests for TranscriptionService."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import NotFoundError
from src.models.db.session import Session, SessionStatus
from src.models.db.transcript import (
    Transcript,
    TranscriptionJob,
    TranscriptionJobStatus,
)
from src.services.deepgram_client import Segment, TranscriptionResult
from src.services.transcription_service import (
    TranscriptionError,
    TranscriptionService,
)


@pytest.fixture
def mock_db_session() -> MagicMock:
    """Create mock database session."""
    session = MagicMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings."""
    settings = MagicMock()
    settings.deepgram_api_key = "test-key"
    settings.minio_endpoint = "localhost:9000"
    settings.minio_access_key = "minioadmin"
    settings.minio_secret_key = "minioadmin"
    settings.minio_bucket = "test-bucket"
    settings.minio_secure = False
    return settings


@pytest.fixture
def session_id() -> uuid.UUID:
    """Create test session ID."""
    return uuid.uuid4()


@pytest.fixture
def job_id() -> uuid.UUID:
    """Create test job ID."""
    return uuid.uuid4()


def create_mock_session(
    session_id: uuid.UUID,
    status: SessionStatus = SessionStatus.UPLOADED,
    recording_path: str | None = "recordings/test.mp3",
) -> MagicMock:
    """Create a mock Session object."""
    session = MagicMock(spec=Session)
    session.id = session_id
    session.patient_id = uuid.uuid4()
    session.therapist_id = uuid.uuid4()
    session.status = status
    session.recording_path = recording_path
    return session


def create_mock_job(
    job_id: uuid.UUID,
    session_id: uuid.UUID,
    status: TranscriptionJobStatus = TranscriptionJobStatus.PENDING,
) -> MagicMock:
    """Create a mock TranscriptionJob object."""
    job = MagicMock(spec=TranscriptionJob)
    job.id = job_id
    job.session_id = session_id
    job.status = status
    job.started_at = None
    job.completed_at = None
    job.error_message = None
    job.retry_count = 0
    job.created_at = datetime.now(UTC)
    return job


def create_mock_transcript(
    session_id: uuid.UUID,
    job_id: uuid.UUID,
) -> MagicMock:
    """Create a mock Transcript object."""
    transcript = MagicMock(spec=Transcript)
    transcript.id = uuid.uuid4()
    transcript.session_id = session_id
    transcript.job_id = job_id
    transcript.full_text = "Hello, how are you?"
    transcript.segments = [{"text": "Hello", "start_time": 0.0, "end_time": 0.5}]
    transcript.word_count = 4
    transcript.duration_seconds = 2.0
    transcript.language = "en"
    transcript.confidence = 0.95
    transcript.transcript_metadata = None
    transcript.created_at = datetime.now(UTC)
    transcript.updated_at = datetime.now(UTC)
    return transcript


class TestCreateTranscriptionJob:
    """Tests for create_transcription_job method."""

    async def test_creates_job_for_valid_session(
        self,
        mock_db_session: MagicMock,
        mock_settings: MagicMock,
        session_id: uuid.UUID,
        job_id: uuid.UUID,
    ) -> None:
        """Test job creation for valid session."""
        mock_session = create_mock_session(session_id)
        mock_job = create_mock_job(job_id, session_id)

        with (
            patch(
                "src.services.transcription_service.SessionRepository"
            ) as mock_session_repo_class,
            patch(
                "src.services.transcription_service.TranscriptRepository"
            ) as mock_transcript_repo_class,
        ):
            mock_session_repo = MagicMock()
            mock_session_repo.get_by_id = AsyncMock(return_value=mock_session)
            mock_session_repo_class.return_value = mock_session_repo

            mock_transcript_repo = MagicMock()
            mock_transcript_repo.create_job = AsyncMock(return_value=mock_job)
            mock_transcript_repo_class.return_value = mock_transcript_repo

            service = TranscriptionService(mock_db_session, settings=mock_settings)
            result = await service.create_transcription_job(session_id)

            assert result.id == job_id
            assert result.session_id == session_id
            assert result.status.value == "pending"

    async def test_raises_not_found_for_invalid_session(
        self,
        mock_db_session: MagicMock,
        mock_settings: MagicMock,
        session_id: uuid.UUID,
    ) -> None:
        """Test NotFoundError for invalid session."""
        with (
            patch(
                "src.services.transcription_service.SessionRepository"
            ) as mock_session_repo_class,
            patch("src.services.transcription_service.TranscriptRepository"),
        ):
            mock_session_repo = MagicMock()
            mock_session_repo.get_by_id = AsyncMock(return_value=None)
            mock_session_repo_class.return_value = mock_session_repo

            service = TranscriptionService(mock_db_session, settings=mock_settings)

            with pytest.raises(NotFoundError):
                await service.create_transcription_job(session_id)


class TestProcessTranscription:
    """Tests for process_transcription method."""

    async def test_successful_transcription(
        self,
        mock_db_session: MagicMock,
        mock_settings: MagicMock,
        session_id: uuid.UUID,
        job_id: uuid.UUID,
    ) -> None:
        """Test successful transcription processing."""
        mock_session = create_mock_session(session_id)
        mock_job = create_mock_job(job_id, session_id)
        mock_transcript = create_mock_transcript(session_id, job_id)

        transcription_result = TranscriptionResult(
            full_text="Hello, how are you?",
            segments=[
                Segment(
                    text="Hello",
                    start_time=0.0,
                    end_time=0.5,
                    speaker="Speaker 0",
                )
            ],
            duration_seconds=2.0,
            language="en",
            confidence=0.95,
            word_count=4,
        )

        with (
            patch(
                "src.services.transcription_service.SessionRepository"
            ) as mock_session_repo_class,
            patch(
                "src.services.transcription_service.TranscriptRepository"
            ) as mock_transcript_repo_class,
            patch(
                "src.services.transcription_service.StorageService"
            ) as mock_storage_class,
            patch(
                "src.services.transcription_service.DeepgramClient"
            ) as mock_deepgram_class,
            patch("httpx.AsyncClient") as mock_httpx,
            patch("src.workers.embedding_worker.queue_embedding"),
        ):
            mock_session_repo = MagicMock()
            mock_session_repo.get_by_id = AsyncMock(return_value=mock_session)
            mock_session_repo.update_status = AsyncMock(return_value=True)
            mock_session_repo_class.return_value = mock_session_repo

            mock_transcript_repo = MagicMock()
            mock_transcript_repo.get_job_by_id = AsyncMock(return_value=mock_job)
            mock_transcript_repo.update_job_status = AsyncMock(return_value=True)
            mock_transcript_repo.create_transcript = AsyncMock(
                return_value=mock_transcript
            )
            mock_transcript_repo_class.return_value = mock_transcript_repo

            mock_storage = MagicMock()
            mock_storage.get_presigned_url = AsyncMock(
                return_value="http://test-url.com/audio.mp3"
            )
            mock_storage_class.return_value = mock_storage

            mock_deepgram = MagicMock()
            mock_deepgram.transcribe_file = AsyncMock(return_value=transcription_result)
            mock_deepgram_class.return_value = mock_deepgram

            # Mock httpx client for downloading
            mock_response = MagicMock()
            mock_response.content = b"fake audio data"
            mock_response.raise_for_status = MagicMock()
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_httpx.return_value = mock_client

            service = TranscriptionService(mock_db_session, settings=mock_settings)
            result = await service.process_transcription(job_id)

            assert result.full_text == "Hello, how are you?"
            mock_session_repo.update_status.assert_called()

    async def test_fails_when_no_recording_path(
        self,
        mock_db_session: MagicMock,
        mock_settings: MagicMock,
        session_id: uuid.UUID,
        job_id: uuid.UUID,
    ) -> None:
        """Test failure when session has no recording path."""
        mock_session = create_mock_session(session_id, recording_path=None)
        mock_job = create_mock_job(job_id, session_id)

        with (
            patch(
                "src.services.transcription_service.SessionRepository"
            ) as mock_session_repo_class,
            patch(
                "src.services.transcription_service.TranscriptRepository"
            ) as mock_transcript_repo_class,
        ):
            mock_session_repo = MagicMock()
            mock_session_repo.get_by_id = AsyncMock(return_value=mock_session)
            mock_session_repo.update_status = AsyncMock(return_value=True)
            mock_session_repo_class.return_value = mock_session_repo

            mock_transcript_repo = MagicMock()
            mock_transcript_repo.get_job_by_id = AsyncMock(return_value=mock_job)
            mock_transcript_repo.update_job_status = AsyncMock(return_value=True)
            mock_transcript_repo_class.return_value = mock_transcript_repo

            service = TranscriptionService(mock_db_session, settings=mock_settings)

            with pytest.raises(TranscriptionError) as exc_info:
                await service.process_transcription(job_id)

            assert "no recording path" in str(exc_info.value).lower()

    async def test_raises_not_found_for_invalid_job(
        self,
        mock_db_session: MagicMock,
        mock_settings: MagicMock,
        job_id: uuid.UUID,
    ) -> None:
        """Test NotFoundError for invalid job."""
        with (
            patch("src.services.transcription_service.SessionRepository"),
            patch(
                "src.services.transcription_service.TranscriptRepository"
            ) as mock_transcript_repo_class,
        ):
            mock_transcript_repo = MagicMock()
            mock_transcript_repo.get_job_by_id = AsyncMock(return_value=None)
            mock_transcript_repo_class.return_value = mock_transcript_repo

            service = TranscriptionService(mock_db_session, settings=mock_settings)

            with pytest.raises(NotFoundError):
                await service.process_transcription(job_id)


class TestGetTranscriptionStatus:
    """Tests for get_transcription_status method."""

    async def test_returns_status_with_transcript(
        self,
        mock_db_session: MagicMock,
        mock_settings: MagicMock,
        session_id: uuid.UUID,
        job_id: uuid.UUID,
    ) -> None:
        """Test status when transcript exists."""
        mock_transcript = create_mock_transcript(session_id, job_id)
        mock_job = create_mock_job(
            job_id, session_id, status=TranscriptionJobStatus.COMPLETED
        )

        with (
            patch("src.services.transcription_service.SessionRepository"),
            patch(
                "src.services.transcription_service.TranscriptRepository"
            ) as mock_transcript_repo_class,
        ):
            mock_transcript_repo = MagicMock()
            mock_transcript_repo.get_transcript_by_session_id = AsyncMock(
                return_value=mock_transcript
            )
            mock_transcript_repo.get_latest_job_for_session = AsyncMock(
                return_value=mock_job
            )
            mock_transcript_repo_class.return_value = mock_transcript_repo

            service = TranscriptionService(mock_db_session, settings=mock_settings)
            result = await service.get_transcription_status(session_id)

            assert result.has_transcript is True
            assert result.job_status is not None
            assert result.job_status.value == "completed"

    async def test_returns_status_while_processing(
        self,
        mock_db_session: MagicMock,
        mock_settings: MagicMock,
        session_id: uuid.UUID,
        job_id: uuid.UUID,
    ) -> None:
        """Test status when still processing."""
        mock_job = create_mock_job(
            job_id, session_id, status=TranscriptionJobStatus.PROCESSING
        )

        with (
            patch("src.services.transcription_service.SessionRepository"),
            patch(
                "src.services.transcription_service.TranscriptRepository"
            ) as mock_transcript_repo_class,
        ):
            mock_transcript_repo = MagicMock()
            mock_transcript_repo.get_transcript_by_session_id = AsyncMock(
                return_value=None
            )
            mock_transcript_repo.get_latest_job_for_session = AsyncMock(
                return_value=mock_job
            )
            mock_transcript_repo_class.return_value = mock_transcript_repo

            service = TranscriptionService(mock_db_session, settings=mock_settings)
            result = await service.get_transcription_status(session_id)

            assert result.has_transcript is False
            assert result.job_status is not None
            assert result.job_status.value == "processing"


class TestGetTranscript:
    """Tests for get_transcript method."""

    async def test_returns_transcript(
        self,
        mock_db_session: MagicMock,
        mock_settings: MagicMock,
        session_id: uuid.UUID,
        job_id: uuid.UUID,
    ) -> None:
        """Test transcript retrieval."""
        mock_transcript = create_mock_transcript(session_id, job_id)

        with (
            patch("src.services.transcription_service.SessionRepository"),
            patch(
                "src.services.transcription_service.TranscriptRepository"
            ) as mock_transcript_repo_class,
        ):
            mock_transcript_repo = MagicMock()
            mock_transcript_repo.get_transcript_by_session_id = AsyncMock(
                return_value=mock_transcript
            )
            mock_transcript_repo_class.return_value = mock_transcript_repo

            service = TranscriptionService(mock_db_session, settings=mock_settings)
            result = await service.get_transcript(session_id)

            assert result.full_text == "Hello, how are you?"

    async def test_raises_not_found(
        self,
        mock_db_session: MagicMock,
        mock_settings: MagicMock,
        session_id: uuid.UUID,
    ) -> None:
        """Test NotFoundError when transcript doesn't exist."""
        with (
            patch("src.services.transcription_service.SessionRepository"),
            patch(
                "src.services.transcription_service.TranscriptRepository"
            ) as mock_transcript_repo_class,
        ):
            mock_transcript_repo = MagicMock()
            mock_transcript_repo.get_transcript_by_session_id = AsyncMock(
                return_value=None
            )
            mock_transcript_repo_class.return_value = mock_transcript_repo

            service = TranscriptionService(mock_db_session, settings=mock_settings)

            with pytest.raises(NotFoundError):
                await service.get_transcript(session_id)


class TestRetryTranscription:
    """Tests for retry_transcription method."""

    async def test_retries_failed_job(
        self,
        mock_db_session: MagicMock,
        mock_settings: MagicMock,
        session_id: uuid.UUID,
        job_id: uuid.UUID,
    ) -> None:
        """Test retrying a failed job."""
        mock_job = create_mock_job(
            job_id, session_id, status=TranscriptionJobStatus.FAILED
        )
        mock_job.error_message = "Previous error"

        # After reset
        mock_job_reset = create_mock_job(
            job_id, session_id, status=TranscriptionJobStatus.PENDING
        )
        mock_job_reset.retry_count = 1

        with (
            patch("src.services.transcription_service.SessionRepository"),
            patch(
                "src.services.transcription_service.TranscriptRepository"
            ) as mock_transcript_repo_class,
        ):
            mock_transcript_repo = MagicMock()
            mock_transcript_repo.get_job_by_id = AsyncMock(
                side_effect=[mock_job, mock_job_reset]
            )
            mock_transcript_repo.update_job_status = AsyncMock(return_value=True)
            mock_transcript_repo.increment_retry_count = AsyncMock(return_value=True)
            mock_transcript_repo_class.return_value = mock_transcript_repo

            service = TranscriptionService(mock_db_session, settings=mock_settings)
            result = await service.retry_transcription(job_id)

            assert result.status.value == "pending"
            assert result.retry_count == 1

    async def test_raises_error_for_non_failed_job(
        self,
        mock_db_session: MagicMock,
        mock_settings: MagicMock,
        session_id: uuid.UUID,
        job_id: uuid.UUID,
    ) -> None:
        """Test error when trying to retry non-failed job."""
        mock_job = create_mock_job(
            job_id, session_id, status=TranscriptionJobStatus.COMPLETED
        )

        with (
            patch("src.services.transcription_service.SessionRepository"),
            patch(
                "src.services.transcription_service.TranscriptRepository"
            ) as mock_transcript_repo_class,
        ):
            mock_transcript_repo = MagicMock()
            mock_transcript_repo.get_job_by_id = AsyncMock(return_value=mock_job)
            mock_transcript_repo_class.return_value = mock_transcript_repo

            service = TranscriptionService(mock_db_session, settings=mock_settings)

            with pytest.raises(TranscriptionError) as exc_info:
                await service.retry_transcription(job_id)

            assert "only retry failed jobs" in str(exc_info.value).lower()


class TestGetContentType:
    """Tests for _get_content_type method."""

    def test_mp3_content_type(
        self,
        mock_db_session: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Test MP3 content type detection."""
        service = TranscriptionService(mock_db_session, settings=mock_settings)
        assert service._get_content_type("test.mp3") == "audio/mpeg"

    def test_wav_content_type(
        self,
        mock_db_session: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Test WAV content type detection."""
        service = TranscriptionService(mock_db_session, settings=mock_settings)
        assert service._get_content_type("test.wav") == "audio/wav"

    def test_unknown_defaults_to_mpeg(
        self,
        mock_db_session: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Test unknown extension defaults to audio/mpeg."""
        service = TranscriptionService(mock_db_session, settings=mock_settings)
        assert service._get_content_type("test.unknown") == "audio/mpeg"
