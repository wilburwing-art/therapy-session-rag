"""Tests for Transcript models."""

import uuid
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.models.db.transcript import (
    Transcript,
    TranscriptionJob,
    TranscriptionJobStatus,
)
from src.models.domain.transcript import (
    TranscriptCreate,
    TranscriptionJobCreate,
    TranscriptionJobRead,
    TranscriptionStatusResponse,
    TranscriptRead,
    TranscriptSegment,
    TranscriptSummary,
)
from src.models.domain.transcript import (
    TranscriptionJobStatus as DomainTranscriptionJobStatus,
)


class TestTranscriptionJobStatusEnum:
    """Tests for TranscriptionJobStatus enum."""

    def test_pending_value(self) -> None:
        """Test PENDING status value."""
        assert TranscriptionJobStatus.PENDING.value == "pending"

    def test_processing_value(self) -> None:
        """Test PROCESSING status value."""
        assert TranscriptionJobStatus.PROCESSING.value == "processing"

    def test_completed_value(self) -> None:
        """Test COMPLETED status value."""
        assert TranscriptionJobStatus.COMPLETED.value == "completed"

    def test_failed_value(self) -> None:
        """Test FAILED status value."""
        assert TranscriptionJobStatus.FAILED.value == "failed"


class TestTranscriptionJobModel:
    """Tests for TranscriptionJob DB model."""

    def test_tablename(self) -> None:
        """Test table name."""
        assert TranscriptionJob.__tablename__ == "transcription_jobs"

    def test_has_session_id(self) -> None:
        """Test session_id column exists."""
        assert hasattr(TranscriptionJob, "session_id")

    def test_has_status(self) -> None:
        """Test status column exists."""
        assert hasattr(TranscriptionJob, "status")

    def test_has_retry_count(self) -> None:
        """Test retry_count column exists."""
        assert hasattr(TranscriptionJob, "retry_count")

    def test_has_external_job_id(self) -> None:
        """Test external_job_id column exists."""
        assert hasattr(TranscriptionJob, "external_job_id")

    def test_has_timestamps(self) -> None:
        """Test timestamp fields exist."""
        assert hasattr(TranscriptionJob, "started_at")
        assert hasattr(TranscriptionJob, "completed_at")
        assert hasattr(TranscriptionJob, "created_at")
        assert hasattr(TranscriptionJob, "updated_at")


class TestTranscriptModel:
    """Tests for Transcript DB model."""

    def test_tablename(self) -> None:
        """Test table name."""
        assert Transcript.__tablename__ == "transcripts"

    def test_has_session_id(self) -> None:
        """Test session_id column exists."""
        assert hasattr(Transcript, "session_id")

    def test_has_full_text(self) -> None:
        """Test full_text column exists."""
        assert hasattr(Transcript, "full_text")

    def test_has_segments(self) -> None:
        """Test segments column exists."""
        assert hasattr(Transcript, "segments")

    def test_has_word_count(self) -> None:
        """Test word_count column exists."""
        assert hasattr(Transcript, "word_count")

    def test_has_duration_seconds(self) -> None:
        """Test duration_seconds column exists."""
        assert hasattr(Transcript, "duration_seconds")

    def test_has_language(self) -> None:
        """Test language column exists."""
        assert hasattr(Transcript, "language")

    def test_has_confidence(self) -> None:
        """Test confidence column exists."""
        assert hasattr(Transcript, "confidence")


class TestTranscriptSegment:
    """Tests for TranscriptSegment schema."""

    def test_create_segment(self) -> None:
        """Test creating a transcript segment."""
        segment = TranscriptSegment(
            text="Hello, how are you?",
            start_time=0.0,
            end_time=2.5,
            speaker="Speaker 1",
            confidence=0.95,
        )

        assert segment.text == "Hello, how are you?"
        assert segment.start_time == 0.0
        assert segment.end_time == 2.5
        assert segment.speaker == "Speaker 1"
        assert segment.confidence == 0.95

    def test_segment_without_optional_fields(self) -> None:
        """Test segment without optional fields."""
        segment = TranscriptSegment(
            text="Test",
            start_time=0.0,
            end_time=1.0,
        )

        assert segment.speaker is None
        assert segment.confidence is None
        assert segment.words is None


class TestTranscriptionJobCreate:
    """Tests for TranscriptionJobCreate schema."""

    def test_create_job(self) -> None:
        """Test creating a job request."""
        session_id = uuid.uuid4()
        job = TranscriptionJobCreate(session_id=session_id)

        assert job.session_id == session_id

    def test_requires_session_id(self) -> None:
        """Test session_id is required."""
        with pytest.raises(ValueError):
            TranscriptionJobCreate()  # type: ignore[call-arg]


class TestTranscriptionJobRead:
    """Tests for TranscriptionJobRead schema."""

    def test_from_dict(self) -> None:
        """Test creating from dict."""
        now = datetime.utcnow()
        data = {
            "id": uuid.uuid4(),
            "session_id": uuid.uuid4(),
            "status": DomainTranscriptionJobStatus.PROCESSING,
            "started_at": now,
            "completed_at": None,
            "error_message": None,
            "retry_count": 0,
            "created_at": now,
        }

        schema = TranscriptionJobRead.model_validate(data)

        assert schema.status == DomainTranscriptionJobStatus.PROCESSING
        assert schema.retry_count == 0

    def test_from_orm(self) -> None:
        """Test creating from ORM model."""
        now = datetime.utcnow()
        job = MagicMock()
        job.id = uuid.uuid4()
        job.session_id = uuid.uuid4()
        job.status = TranscriptionJobStatus.COMPLETED
        job.started_at = now
        job.completed_at = now
        job.error_message = None
        job.retry_count = 1
        job.created_at = now

        schema = TranscriptionJobRead.model_validate(job)

        assert schema.status == DomainTranscriptionJobStatus.COMPLETED
        assert schema.retry_count == 1


class TestTranscriptCreate:
    """Tests for TranscriptCreate schema."""

    def test_create_transcript(self) -> None:
        """Test creating a transcript."""
        session_id = uuid.uuid4()
        transcript = TranscriptCreate(
            session_id=session_id,
            full_text="Hello, how are you today?",
            segments=[
                TranscriptSegment(
                    text="Hello,",
                    start_time=0.0,
                    end_time=0.5,
                ),
                TranscriptSegment(
                    text="how are you today?",
                    start_time=0.6,
                    end_time=2.0,
                ),
            ],
            word_count=5,
            duration_seconds=2.0,
            language="en",
            confidence=0.95,
        )

        assert transcript.session_id == session_id
        assert len(transcript.segments) == 2
        assert transcript.word_count == 5

    def test_create_minimal(self) -> None:
        """Test creating with minimal data."""
        transcript = TranscriptCreate(
            session_id=uuid.uuid4(),
            full_text="Test transcript",
        )

        assert len(transcript.segments) == 0
        assert transcript.word_count is None


class TestTranscriptRead:
    """Tests for TranscriptRead schema."""

    def test_from_dict(self) -> None:
        """Test creating from dict."""
        now = datetime.utcnow()
        data = {
            "id": uuid.uuid4(),
            "session_id": uuid.uuid4(),
            "job_id": uuid.uuid4(),
            "full_text": "Test transcript",
            "segments": [{"text": "Test", "start_time": 0.0, "end_time": 1.0}],
            "word_count": 2,
            "duration_seconds": 1.0,
            "language": "en",
            "confidence": 0.9,
            "transcript_metadata": None,
            "created_at": now,
            "updated_at": now,
        }

        schema = TranscriptRead.model_validate(data)

        assert schema.full_text == "Test transcript"
        assert len(schema.segments) == 1


class TestTranscriptSummary:
    """Tests for TranscriptSummary schema."""

    def test_from_dict(self) -> None:
        """Test creating from dict."""
        now = datetime.utcnow()
        data = {
            "id": uuid.uuid4(),
            "session_id": uuid.uuid4(),
            "word_count": 100,
            "duration_seconds": 60.0,
            "language": "en",
            "created_at": now,
        }

        schema = TranscriptSummary.model_validate(data)

        assert schema.word_count == 100
        assert schema.duration_seconds == 60.0


class TestTranscriptionStatusResponse:
    """Tests for TranscriptionStatusResponse schema."""

    def test_with_transcript(self) -> None:
        """Test response when transcript exists."""
        response = TranscriptionStatusResponse(
            session_id=uuid.uuid4(),
            has_transcript=True,
            job_status=DomainTranscriptionJobStatus.COMPLETED,
        )

        assert response.has_transcript is True
        assert response.job_status == DomainTranscriptionJobStatus.COMPLETED

    def test_processing(self) -> None:
        """Test response when still processing."""
        response = TranscriptionStatusResponse(
            session_id=uuid.uuid4(),
            has_transcript=False,
            job_status=DomainTranscriptionJobStatus.PROCESSING,
        )

        assert response.has_transcript is False
        assert response.job_status == DomainTranscriptionJobStatus.PROCESSING

    def test_failed(self) -> None:
        """Test response when failed."""
        response = TranscriptionStatusResponse(
            session_id=uuid.uuid4(),
            has_transcript=False,
            job_status=DomainTranscriptionJobStatus.FAILED,
            error_message="Transcription failed",
        )

        assert response.has_transcript is False
        assert response.error_message == "Transcription failed"
