"""Tests for session API endpoints."""

import io
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.dependencies import get_api_key_auth
from src.api.v1.endpoints.sessions import (
    get_session_service,
    get_storage_service,
    get_transcription_service,
    router,
)
from src.core.database import get_db_session
from src.core.exceptions import ForbiddenError, NotFoundError, setup_exception_handlers
from src.models.domain.session import (
    SessionRead,
    SessionStatus,
    SessionSummary,
)
from src.models.domain.transcript import (
    TranscriptionJobRead,
    TranscriptionJobStatus,
    TranscriptionStatusResponse,
    TranscriptRead,
)


@pytest.fixture
def mock_auth_context() -> MagicMock:
    """Create a mock auth context."""
    ctx = MagicMock()
    ctx.api_key_id = uuid.uuid4()
    ctx.organization_id = uuid.uuid4()
    ctx.api_key_name = "test-key"
    return ctx


@pytest.fixture
def mock_session_service() -> MagicMock:
    """Create a mock session service."""
    return MagicMock()


@pytest.fixture
def mock_storage_service() -> MagicMock:
    """Create a mock storage service."""
    return MagicMock()


@pytest.fixture
def mock_transcription_service() -> MagicMock:
    """Create a mock transcription service."""
    return MagicMock()


@pytest.fixture
def app(
    mock_auth_context: MagicMock,
    mock_session_service: MagicMock,
    mock_storage_service: MagicMock,
    mock_transcription_service: MagicMock,
) -> FastAPI:
    """Create test app with mocked dependencies."""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/sessions")

    # Setup exception handlers
    setup_exception_handlers(test_app)

    test_app.dependency_overrides[get_api_key_auth] = lambda: mock_auth_context
    test_app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    test_app.dependency_overrides[get_session_service] = lambda: mock_session_service
    test_app.dependency_overrides[get_storage_service] = lambda: mock_storage_service
    test_app.dependency_overrides[get_transcription_service] = (
        lambda: mock_transcription_service
    )

    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def patient_id() -> uuid.UUID:
    """Create test patient ID."""
    return uuid.uuid4()


@pytest.fixture
def therapist_id() -> uuid.UUID:
    """Create test therapist ID."""
    return uuid.uuid4()


@pytest.fixture
def consent_id() -> uuid.UUID:
    """Create test consent ID."""
    return uuid.uuid4()


@pytest.fixture
def session_id() -> uuid.UUID:
    """Create test session ID."""
    return uuid.uuid4()


def create_session_read(
    session_id: uuid.UUID,
    patient_id: uuid.UUID,
    therapist_id: uuid.UUID,
    consent_id: uuid.UUID,
    status: SessionStatus = SessionStatus.PENDING,
) -> SessionRead:
    """Create a SessionRead for testing."""
    return SessionRead(
        id=session_id,
        patient_id=patient_id,
        therapist_id=therapist_id,
        consent_id=consent_id,
        session_date=datetime.utcnow(),
        recording_path=None,
        recording_duration_seconds=None,
        status=status,
        error_message=None,
        session_metadata=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


def create_session_summary(
    session_id: uuid.UUID,
    patient_id: uuid.UUID,
    therapist_id: uuid.UUID,
    status: SessionStatus = SessionStatus.PENDING,
) -> SessionSummary:
    """Create a SessionSummary for testing."""
    return SessionSummary(
        id=session_id,
        patient_id=patient_id,
        therapist_id=therapist_id,
        session_date=datetime.utcnow(),
        status=status,
        recording_duration_seconds=None,
        created_at=datetime.utcnow(),
    )


class TestCreateSession:
    """Tests for POST /sessions."""

    def test_creates_session(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        """Test successful session creation."""
        mock_session = create_session_read(
            session_id=session_id,
            patient_id=patient_id,
            therapist_id=therapist_id,
            consent_id=consent_id,
        )
        mock_session_service.create_session = AsyncMock(return_value=mock_session)

        response = client.post(
            "/sessions",
            json={
                "patient_id": str(patient_id),
                "therapist_id": str(therapist_id),
                "consent_id": str(consent_id),
                "session_date": datetime.utcnow().isoformat(),
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == str(session_id)

    def test_returns_403_without_consent(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
    ) -> None:
        """Test session creation fails without consent."""
        mock_session_service.create_session = AsyncMock(
            side_effect=ForbiddenError(detail="No consent")
        )

        response = client.post(
            "/sessions",
            json={
                "patient_id": str(patient_id),
                "therapist_id": str(therapist_id),
                "consent_id": str(consent_id),
                "session_date": datetime.utcnow().isoformat(),
            },
        )

        assert response.status_code == 403


class TestGetSession:
    """Tests for GET /sessions/{session_id}."""

    def test_returns_session(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        """Test successful session retrieval."""
        mock_session = create_session_read(
            session_id=session_id,
            patient_id=patient_id,
            therapist_id=therapist_id,
            consent_id=consent_id,
        )
        mock_session_service.get_session = AsyncMock(return_value=mock_session)

        response = client.get(f"/sessions/{session_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(session_id)

    def test_returns_404_when_not_found(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        session_id: uuid.UUID,
    ) -> None:
        """Test 404 when session not found."""
        mock_session_service.get_session = AsyncMock(
            side_effect=NotFoundError(resource="Session")
        )

        response = client.get(f"/sessions/{session_id}")

        assert response.status_code == 404


class TestUpdateSession:
    """Tests for PATCH /sessions/{session_id}."""

    def test_updates_session(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        """Test successful session update."""
        mock_session = create_session_read(
            session_id=session_id,
            patient_id=patient_id,
            therapist_id=therapist_id,
            consent_id=consent_id,
            status=SessionStatus.UPLOADED,
        )
        mock_session_service.update_session = AsyncMock(return_value=mock_session)

        response = client.patch(
            f"/sessions/{session_id}",
            json={"status": "uploaded"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "uploaded"


class TestListSessions:
    """Tests for GET /sessions."""

    def test_lists_sessions(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        """Test listing sessions with cursor pagination."""
        from src.core.pagination import CursorPage

        mock_summaries = [
            create_session_summary(
                session_id=session_id,
                patient_id=patient_id,
                therapist_id=therapist_id,
            )
        ]
        mock_page = CursorPage(items=mock_summaries, next_cursor=None, has_more=False)
        mock_session_service.list_sessions_paginated = AsyncMock(return_value=mock_page)

        response = client.get("/sessions")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == str(session_id)
        assert data["has_more"] is False

    def test_lists_with_filters(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        """Test listing sessions with filters."""
        from src.core.pagination import CursorPage

        mock_summaries = [
            create_session_summary(
                session_id=session_id,
                patient_id=patient_id,
                therapist_id=therapist_id,
                status=SessionStatus.READY,
            )
        ]
        mock_page = CursorPage(items=mock_summaries, next_cursor=None, has_more=False)
        mock_session_service.list_sessions_paginated = AsyncMock(return_value=mock_page)

        response = client.get(
            "/sessions",
            params={
                "patient_id": str(patient_id),
                "status": "ready",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data


class TestUploadRecording:
    """Tests for POST /sessions/{session_id}/recording."""

    def test_uploads_recording(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        mock_storage_service: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        """Test successful recording upload."""
        mock_session = create_session_read(
            session_id=session_id,
            patient_id=patient_id,
            therapist_id=therapist_id,
            consent_id=consent_id,
        )

        mock_session_service.get_session = AsyncMock(return_value=mock_session)
        mock_session_service.update_session = AsyncMock(return_value=mock_session)

        mock_storage_service.generate_key.return_value = "recordings/abc123-test.mp3"
        mock_storage_service.upload_file = AsyncMock(
            return_value="recordings/abc123-test.mp3"
        )

        # Create a mock audio file
        audio_content = b"fake audio content for testing"
        files = {
            "file": ("test.mp3", io.BytesIO(audio_content), "audio/mpeg"),
        }

        response = client.post(
            f"/sessions/{session_id}/recording",
            files=files,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == str(session_id)
        assert data["recording_path"] == "recordings/abc123-test.mp3"
        assert data["status"] == "uploaded"

    def test_rejects_invalid_file_type(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        """Test rejection of non-audio file types."""
        mock_session = create_session_read(
            session_id=session_id,
            patient_id=patient_id,
            therapist_id=therapist_id,
            consent_id=consent_id,
        )
        mock_session_service.get_session = AsyncMock(return_value=mock_session)

        # Create a text file instead of audio
        files = {
            "file": ("test.txt", io.BytesIO(b"not audio"), "text/plain"),
        }

        response = client.post(
            f"/sessions/{session_id}/recording",
            files=files,
        )

        assert response.status_code == 422  # Unprocessable Entity for validation errors

    def test_rejects_empty_file(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        """Test rejection of empty files."""
        mock_session = create_session_read(
            session_id=session_id,
            patient_id=patient_id,
            therapist_id=therapist_id,
            consent_id=consent_id,
        )
        mock_session_service.get_session = AsyncMock(return_value=mock_session)

        # Create empty file
        files = {
            "file": ("test.mp3", io.BytesIO(b""), "audio/mpeg"),
        }

        response = client.post(
            f"/sessions/{session_id}/recording",
            files=files,
        )

        assert response.status_code == 422  # Unprocessable Entity for validation errors

    def test_returns_404_for_nonexistent_session(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        session_id: uuid.UUID,
    ) -> None:
        """Test 404 when session doesn't exist."""
        mock_session_service.get_session = AsyncMock(
            side_effect=NotFoundError(resource="Session")
        )

        files = {
            "file": ("test.mp3", io.BytesIO(b"audio"), "audio/mpeg"),
        }

        response = client.post(
            f"/sessions/{session_id}/recording",
            files=files,
        )

        assert response.status_code == 404


class TestGetPatientSessions:
    """Tests for GET /sessions/patient/{patient_id}."""

    def test_gets_patient_sessions(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        """Test getting sessions for a patient."""
        mock_summaries = [
            create_session_summary(
                session_id=session_id,
                patient_id=patient_id,
                therapist_id=therapist_id,
            )
        ]
        mock_session_service.get_sessions_for_patient = AsyncMock(
            return_value=mock_summaries
        )

        response = client.get(f"/sessions/patient/{patient_id}")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["patient_id"] == str(patient_id)

    def test_filters_by_therapist_and_status(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        """Test filtering patient sessions by therapist and status."""
        mock_summaries = [
            create_session_summary(
                session_id=session_id,
                patient_id=patient_id,
                therapist_id=therapist_id,
                status=SessionStatus.READY,
            )
        ]
        mock_session_service.get_sessions_for_patient = AsyncMock(
            return_value=mock_summaries
        )

        response = client.get(
            f"/sessions/patient/{patient_id}",
            params={
                "therapist_id": str(therapist_id),
                "status": "ready",
            },
        )

        assert response.status_code == 200
        mock_session_service.get_sessions_for_patient.assert_called_once()


def create_transcription_job_read(
    job_id: uuid.UUID,
    session_id: uuid.UUID,
    status: TranscriptionJobStatus = TranscriptionJobStatus.PENDING,
) -> TranscriptionJobRead:
    """Create a TranscriptionJobRead for testing."""
    return TranscriptionJobRead(
        id=job_id,
        session_id=session_id,
        status=status,
        started_at=None,
        completed_at=None,
        error_message=None,
        retry_count=0,
        created_at=datetime.utcnow(),
    )


def create_transcript_read(
    transcript_id: uuid.UUID,
    session_id: uuid.UUID,
    job_id: uuid.UUID,
) -> TranscriptRead:
    """Create a TranscriptRead for testing."""
    return TranscriptRead(
        id=transcript_id,
        session_id=session_id,
        job_id=job_id,
        full_text="This is the transcript text.",
        segments=[
            {
                "speaker": 0,
                "text": "Hello, how are you today?",
                "start": 0.0,
                "end": 2.5,
            }
        ],
        word_count=5,
        duration_seconds=120.0,
        language="en",
        confidence=0.95,
        transcript_metadata=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


class TestStartTranscription:
    """Tests for POST /sessions/{session_id}/transcribe."""

    def test_starts_transcription(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        mock_transcription_service: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        """Test successful transcription start."""
        job_id = uuid.uuid4()

        # Session has a recording
        mock_session = create_session_read(
            session_id=session_id,
            patient_id=patient_id,
            therapist_id=therapist_id,
            consent_id=consent_id,
            status=SessionStatus.UPLOADED,
        )
        mock_session.recording_path = "recordings/test.mp3"
        mock_session_service.get_session = AsyncMock(return_value=mock_session)

        # Transcription job created
        mock_job = create_transcription_job_read(job_id, session_id)
        mock_transcription_service.create_transcription_job = AsyncMock(
            return_value=mock_job
        )

        with patch(
            "src.api.v1.endpoints.sessions.queue_transcription"
        ) as mock_queue:
            mock_queue.return_value = "rq-job-123"

            response = client.post(f"/sessions/{session_id}/transcribe")

            assert response.status_code == 202
            data = response.json()
            assert data["id"] == str(job_id)
            assert data["session_id"] == str(session_id)
            assert data["status"] == "pending"

            mock_queue.assert_called_once_with(job_id)

    def test_returns_400_without_recording(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        """Test error when session has no recording."""
        mock_session = create_session_read(
            session_id=session_id,
            patient_id=patient_id,
            therapist_id=therapist_id,
            consent_id=consent_id,
        )
        mock_session.recording_path = None
        mock_session_service.get_session = AsyncMock(return_value=mock_session)

        response = client.post(f"/sessions/{session_id}/transcribe")

        assert response.status_code == 422

    def test_returns_404_when_session_not_found(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        session_id: uuid.UUID,
    ) -> None:
        """Test 404 when session doesn't exist."""
        mock_session_service.get_session = AsyncMock(
            side_effect=NotFoundError(resource="Session")
        )

        response = client.post(f"/sessions/{session_id}/transcribe")

        assert response.status_code == 404


class TestGetTranscript:
    """Tests for GET /sessions/{session_id}/transcript."""

    def test_returns_transcript(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        mock_transcription_service: MagicMock,
        session_id: uuid.UUID,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
    ) -> None:
        """Test successful transcript retrieval."""
        transcript_id = uuid.uuid4()
        job_id = uuid.uuid4()

        # Mock session service for tenant validation
        mock_session = create_session_read(
            session_id=session_id,
            patient_id=patient_id,
            therapist_id=therapist_id,
            consent_id=consent_id,
        )
        mock_session_service.get_session = AsyncMock(return_value=mock_session)

        mock_transcript = create_transcript_read(transcript_id, session_id, job_id)
        mock_transcription_service.get_transcript = AsyncMock(
            return_value=mock_transcript
        )

        response = client.get(f"/sessions/{session_id}/transcript")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(transcript_id)
        assert data["session_id"] == str(session_id)
        assert data["full_text"] == "This is the transcript text."
        assert len(data["segments"]) == 1

    def test_returns_404_when_not_found(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        mock_transcription_service: MagicMock,
        session_id: uuid.UUID,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
    ) -> None:
        """Test 404 when transcript doesn't exist."""
        # Mock session service for tenant validation
        mock_session = create_session_read(
            session_id=session_id,
            patient_id=patient_id,
            therapist_id=therapist_id,
            consent_id=consent_id,
        )
        mock_session_service.get_session = AsyncMock(return_value=mock_session)

        mock_transcription_service.get_transcript = AsyncMock(
            side_effect=NotFoundError(resource="Transcript")
        )

        response = client.get(f"/sessions/{session_id}/transcript")

        assert response.status_code == 404


class TestGetTranscriptionStatus:
    """Tests for GET /sessions/{session_id}/transcription-status."""

    def _setup_session_mock(
        self,
        mock_session_service: MagicMock,
        session_id: uuid.UUID,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
    ) -> None:
        """Helper to setup session service mock for tenant validation."""
        mock_session = create_session_read(
            session_id=session_id,
            patient_id=patient_id,
            therapist_id=therapist_id,
            consent_id=consent_id,
        )
        mock_session_service.get_session = AsyncMock(return_value=mock_session)

    def test_returns_200_when_completed(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        mock_transcription_service: MagicMock,
        session_id: uuid.UUID,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
    ) -> None:
        """Test 200 response when transcription is completed."""
        self._setup_session_mock(
            mock_session_service, session_id, patient_id, therapist_id, consent_id
        )

        mock_status = TranscriptionStatusResponse(
            session_id=session_id,
            has_transcript=True,
            job_status=TranscriptionJobStatus.COMPLETED,
            error_message=None,
        )
        mock_transcription_service.get_transcription_status = AsyncMock(
            return_value=mock_status
        )

        response = client.get(f"/sessions/{session_id}/transcription-status")

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == str(session_id)
        assert data["has_transcript"] is True
        assert data["job_status"] == "completed"

    def test_returns_202_when_processing(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        mock_transcription_service: MagicMock,
        session_id: uuid.UUID,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
    ) -> None:
        """Test 202 response when transcription is in progress."""
        self._setup_session_mock(
            mock_session_service, session_id, patient_id, therapist_id, consent_id
        )

        mock_status = TranscriptionStatusResponse(
            session_id=session_id,
            has_transcript=False,
            job_status=TranscriptionJobStatus.PROCESSING,
            error_message=None,
        )
        mock_transcription_service.get_transcription_status = AsyncMock(
            return_value=mock_status
        )

        response = client.get(f"/sessions/{session_id}/transcription-status")

        assert response.status_code == 202
        data = response.json()
        assert data["session_id"] == str(session_id)
        assert data["has_transcript"] is False
        assert data["job_status"] == "processing"

    def test_returns_202_when_pending(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        mock_transcription_service: MagicMock,
        session_id: uuid.UUID,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
    ) -> None:
        """Test 202 response when transcription is pending."""
        self._setup_session_mock(
            mock_session_service, session_id, patient_id, therapist_id, consent_id
        )

        mock_status = TranscriptionStatusResponse(
            session_id=session_id,
            has_transcript=False,
            job_status=TranscriptionJobStatus.PENDING,
            error_message=None,
        )
        mock_transcription_service.get_transcription_status = AsyncMock(
            return_value=mock_status
        )

        response = client.get(f"/sessions/{session_id}/transcription-status")

        assert response.status_code == 202
        data = response.json()
        assert data["job_status"] == "pending"

    def test_returns_200_when_failed(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        mock_transcription_service: MagicMock,
        session_id: uuid.UUID,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
    ) -> None:
        """Test 200 response when transcription failed."""
        self._setup_session_mock(
            mock_session_service, session_id, patient_id, therapist_id, consent_id
        )

        mock_status = TranscriptionStatusResponse(
            session_id=session_id,
            has_transcript=False,
            job_status=TranscriptionJobStatus.FAILED,
            error_message="Deepgram API error",
        )
        mock_transcription_service.get_transcription_status = AsyncMock(
            return_value=mock_status
        )

        response = client.get(f"/sessions/{session_id}/transcription-status")

        assert response.status_code == 200
        data = response.json()
        assert data["job_status"] == "failed"
        assert data["error_message"] == "Deepgram API error"

    def test_returns_200_with_no_job(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        mock_transcription_service: MagicMock,
        session_id: uuid.UUID,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
    ) -> None:
        """Test 200 response when no transcription job exists."""
        self._setup_session_mock(
            mock_session_service, session_id, patient_id, therapist_id, consent_id
        )

        mock_status = TranscriptionStatusResponse(
            session_id=session_id,
            has_transcript=False,
            job_status=None,
            error_message=None,
        )
        mock_transcription_service.get_transcription_status = AsyncMock(
            return_value=mock_status
        )

        response = client.get(f"/sessions/{session_id}/transcription-status")

        assert response.status_code == 200
        data = response.json()
        assert data["has_transcript"] is False
        assert data["job_status"] is None
