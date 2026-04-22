"""Unit tests for the PDF download endpoints.

Covers:
- GET /sessions/{id}/recap.pdf
- GET /patients/{id}/record.pdf
- GET /patients/{id}/themes.pdf

All real work is mocked out — the PDF service is replaced with a
MagicMock that returns a byte payload starting with the PDF magic.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.dependencies import get_api_key_auth, get_event_publisher
from src.api.v1.endpoints.patients import get_pdf_service as get_patient_pdf_service
from src.api.v1.endpoints.patients import router as patients_router
from src.api.v1.endpoints.sessions import (
    get_pdf_service as get_session_pdf_service,
)
from src.api.v1.endpoints.sessions import (
    get_session_service,
    get_storage_service,
    get_transcription_service,
)
from src.api.v1.endpoints.sessions import (
    router as sessions_router,
)
from src.core.database import get_db_session
from src.core.exceptions import ForbiddenError, NotFoundError, setup_exception_handlers

_FAKE_PDF = b"%PDF-1.4\n% fake pdf bytes for tests\n%%EOF\n"


@pytest.fixture
def organization_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def session_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def patient_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def therapist_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def mock_auth_context(organization_id: uuid.UUID) -> MagicMock:
    ctx = MagicMock()
    ctx.api_key_id = uuid.uuid4()
    ctx.organization_id = organization_id
    ctx.api_key_name = "test"
    return ctx


@pytest.fixture
def mock_pdf_service() -> MagicMock:
    svc = MagicMock()
    svc.render_session_recap_pdf = AsyncMock(return_value=_FAKE_PDF)
    svc.render_patient_record_pdf = AsyncMock(return_value=_FAKE_PDF)
    svc.render_themes_pdf = AsyncMock(return_value=_FAKE_PDF)
    # For the sessions endpoint we need .session_repo.get_by_id.
    svc.session_repo = MagicMock()
    svc.session_repo.get_by_id = AsyncMock()
    return svc


@pytest.fixture
def app(
    mock_auth_context: MagicMock,
    mock_pdf_service: MagicMock,
) -> FastAPI:
    test_app = FastAPI()
    setup_exception_handlers(test_app)
    test_app.include_router(sessions_router, prefix="/sessions")
    test_app.include_router(patients_router, prefix="/patients")

    mock_events = MagicMock()
    mock_events.publish = AsyncMock(return_value=None)

    test_app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    test_app.dependency_overrides[get_api_key_auth] = lambda: mock_auth_context
    test_app.dependency_overrides[get_event_publisher] = lambda: mock_events
    test_app.dependency_overrides[get_session_pdf_service] = lambda: mock_pdf_service
    test_app.dependency_overrides[get_patient_pdf_service] = lambda: mock_pdf_service
    # Session-endpoint-specific deps we don't exercise but that FastAPI
    # still resolves at route-registration time.
    test_app.dependency_overrides[get_session_service] = lambda: MagicMock()
    test_app.dependency_overrides[get_storage_service] = lambda: MagicMock()
    test_app.dependency_overrides[get_transcription_service] = lambda: MagicMock()

    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


class TestSessionRecapPdf:
    def test_returns_pdf_with_correct_headers(
        self,
        client: TestClient,
        mock_pdf_service: MagicMock,
        session_id: uuid.UUID,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        session_row = MagicMock()
        session_row.id = session_id
        session_row.patient_id = patient_id
        session_row.therapist_id = therapist_id
        session_row.session_date = datetime(2026, 4, 10, 14, 0, 0, tzinfo=UTC)
        mock_pdf_service.session_repo.get_by_id.return_value = session_row

        response = client.get(f"/sessions/{session_id}/recap.pdf")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        disposition = response.headers["content-disposition"]
        assert disposition.startswith("attachment")
        assert 'filename="session-2026-04-10.pdf"' in disposition
        assert response.content.startswith(b"%PDF")

    def test_returns_404_when_session_missing(
        self,
        client: TestClient,
        mock_pdf_service: MagicMock,
        session_id: uuid.UUID,
    ) -> None:
        mock_pdf_service.session_repo.get_by_id.return_value = None

        response = client.get(f"/sessions/{session_id}/recap.pdf")

        assert response.status_code == 404

    def test_returns_404_when_recap_service_raises_not_found(
        self,
        client: TestClient,
        mock_pdf_service: MagicMock,
        session_id: uuid.UUID,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        session_row = MagicMock()
        session_row.id = session_id
        session_row.patient_id = patient_id
        session_row.therapist_id = therapist_id
        session_row.session_date = datetime(2026, 4, 10, 14, 0, 0, tzinfo=UTC)
        mock_pdf_service.session_repo.get_by_id.return_value = session_row
        mock_pdf_service.render_session_recap_pdf.side_effect = NotFoundError(
            resource="SessionRecap",
        )

        response = client.get(f"/sessions/{session_id}/recap.pdf")

        assert response.status_code == 404

    def test_returns_403_when_org_mismatch(
        self,
        client: TestClient,
        mock_pdf_service: MagicMock,
        session_id: uuid.UUID,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        session_row = MagicMock()
        session_row.id = session_id
        session_row.patient_id = patient_id
        session_row.therapist_id = therapist_id
        session_row.session_date = datetime(2026, 4, 10, 14, 0, 0, tzinfo=UTC)
        mock_pdf_service.session_repo.get_by_id.return_value = session_row
        mock_pdf_service.render_session_recap_pdf.side_effect = ForbiddenError(
            detail="Session does not belong to your organization"
        )

        response = client.get(f"/sessions/{session_id}/recap.pdf")

        assert response.status_code == 403


class TestPatientRecordPdf:
    def test_returns_pdf_with_correct_headers(
        self,
        client: TestClient,
        patient_id: uuid.UUID,
    ) -> None:
        response = client.get(f"/patients/{patient_id}/record.pdf")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        disposition = response.headers["content-disposition"]
        assert disposition.startswith("attachment")
        assert f"{patient_id}-record.pdf" in disposition
        assert response.content.startswith(b"%PDF")

    def test_returns_404_when_patient_missing(
        self,
        client: TestClient,
        mock_pdf_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        mock_pdf_service.render_patient_record_pdf.side_effect = NotFoundError(
            resource="Patient"
        )

        response = client.get(f"/patients/{patient_id}/record.pdf")

        assert response.status_code == 404

    def test_returns_403_when_org_mismatch(
        self,
        client: TestClient,
        mock_pdf_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        mock_pdf_service.render_patient_record_pdf.side_effect = ForbiddenError(
            detail="Patient does not belong to your organization"
        )

        response = client.get(f"/patients/{patient_id}/record.pdf")

        assert response.status_code == 403


class TestPatientThemesPdf:
    def test_returns_pdf_with_correct_headers(
        self,
        client: TestClient,
        patient_id: uuid.UUID,
    ) -> None:
        response = client.get(f"/patients/{patient_id}/themes.pdf")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert (
            f"{patient_id}-themes.pdf" in response.headers["content-disposition"]
        )
        assert response.content.startswith(b"%PDF")

    def test_returns_404_when_no_themes(
        self,
        client: TestClient,
        mock_pdf_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        mock_pdf_service.render_themes_pdf.side_effect = NotFoundError(
            resource="PatientThemes"
        )

        response = client.get(f"/patients/{patient_id}/themes.pdf")

        assert response.status_code == 404
