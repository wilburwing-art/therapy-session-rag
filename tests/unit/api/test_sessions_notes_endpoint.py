"""Tests for therapist notes and recording URL endpoints."""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.dependencies import get_api_key_auth, get_event_publisher
from src.api.v1.endpoints.sessions import (
    get_session_service,
    get_storage_service,
    get_transcription_service,
    router,
)
from src.core.database import get_db_session
from src.core.exceptions import NotFoundError, setup_exception_handlers
from src.models.domain.session import (
    SessionRead,
    SessionStatus,
    SessionType,
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

    setup_exception_handlers(test_app)

    test_app.dependency_overrides[get_api_key_auth] = lambda: mock_auth_context
    test_app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    test_app.dependency_overrides[get_session_service] = lambda: mock_session_service
    test_app.dependency_overrides[get_storage_service] = lambda: mock_storage_service
    test_app.dependency_overrides[get_transcription_service] = (
        lambda: mock_transcription_service
    )

    mock_events = MagicMock()
    mock_events.publish = AsyncMock(return_value=None)
    test_app.dependency_overrides[get_event_publisher] = lambda: mock_events

    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def session_id() -> uuid.UUID:
    """Create test session ID."""
    return uuid.uuid4()


@pytest.fixture
def patient_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def therapist_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def consent_id() -> uuid.UUID:
    return uuid.uuid4()


def _session_read(
    session_id: uuid.UUID,
    patient_id: uuid.UUID,
    therapist_id: uuid.UUID,
    consent_id: uuid.UUID,
    *,
    recording_path: str | None = None,
    therapist_notes: str | None = None,
) -> SessionRead:
    return SessionRead(
        id=session_id,
        patient_id=patient_id,
        therapist_id=therapist_id,
        consent_id=consent_id,
        session_date=datetime.utcnow(),
        recording_path=recording_path,
        recording_duration_seconds=None,
        status=SessionStatus.READY,
        session_type=SessionType.UPLOAD,
        error_message=None,
        therapist_notes=therapist_notes,
        session_metadata=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


class TestUpdateNotes:
    """Tests for PATCH /sessions/{session_id}/notes."""

    def test_updates_notes(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        session_id: uuid.UUID,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
    ) -> None:
        updated = _session_read(
            session_id,
            patient_id,
            therapist_id,
            consent_id,
            therapist_notes="Follow up on sleep issues",
        )
        mock_session_service.update_notes = AsyncMock(return_value=updated)

        response = client.patch(
            f"/sessions/{session_id}/notes",
            json={"notes": "Follow up on sleep issues"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(session_id)
        assert data["therapist_notes"] == "Follow up on sleep issues"
        mock_session_service.update_notes.assert_awaited_once_with(
            session_id, "Follow up on sleep issues"
        )

    def test_clears_notes_with_null(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        session_id: uuid.UUID,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
    ) -> None:
        updated = _session_read(
            session_id,
            patient_id,
            therapist_id,
            consent_id,
            therapist_notes=None,
        )
        mock_session_service.update_notes = AsyncMock(return_value=updated)

        response = client.patch(
            f"/sessions/{session_id}/notes",
            json={"notes": None},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["therapist_notes"] is None
        mock_session_service.update_notes.assert_awaited_once_with(session_id, None)

    def test_rejects_overly_long_notes(
        self,
        client: TestClient,
        session_id: uuid.UUID,
    ) -> None:
        too_long = "x" * 20001
        response = client.patch(
            f"/sessions/{session_id}/notes",
            json={"notes": too_long},
        )

        assert response.status_code == 422

    def test_returns_404_when_session_missing(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        session_id: uuid.UUID,
    ) -> None:
        mock_session_service.update_notes = AsyncMock(
            side_effect=NotFoundError(resource="Session")
        )

        response = client.patch(
            f"/sessions/{session_id}/notes",
            json={"notes": "anything"},
        )

        assert response.status_code == 404


class TestGetRecordingUrl:
    """Tests for GET /sessions/{session_id}/recording/url."""

    def test_returns_presigned_url(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        mock_storage_service: MagicMock,
        session_id: uuid.UUID,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
    ) -> None:
        session = _session_read(
            session_id,
            patient_id,
            therapist_id,
            consent_id,
            recording_path="recordings/abc.mp3",
        )
        mock_session_service.get_session = AsyncMock(return_value=session)
        mock_storage_service.get_presigned_url = AsyncMock(
            return_value="https://minio.example/recordings/abc.mp3?sig=xyz"
        )

        response = client.get(f"/sessions/{session_id}/recording/url")

        assert response.status_code == 200
        data = response.json()
        assert data["url"] == "https://minio.example/recordings/abc.mp3?sig=xyz"
        assert "expires_at" in data
        mock_storage_service.get_presigned_url.assert_awaited_once()

    def test_returns_404_when_no_recording(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        mock_storage_service: MagicMock,
        session_id: uuid.UUID,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
    ) -> None:
        session = _session_read(
            session_id,
            patient_id,
            therapist_id,
            consent_id,
            recording_path=None,
        )
        mock_session_service.get_session = AsyncMock(return_value=session)
        mock_storage_service.get_presigned_url = AsyncMock()

        response = client.get(f"/sessions/{session_id}/recording/url")

        assert response.status_code == 404
        mock_storage_service.get_presigned_url.assert_not_awaited()

    def test_returns_404_when_session_missing(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        session_id: uuid.UUID,
    ) -> None:
        mock_session_service.get_session = AsyncMock(
            side_effect=NotFoundError(resource="Session")
        )

        response = client.get(f"/sessions/{session_id}/recording/url")

        assert response.status_code == 404
