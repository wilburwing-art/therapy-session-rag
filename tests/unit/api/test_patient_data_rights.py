"""Unit tests for the HIPAA patient data-rights endpoints.

Covers the export and hard-delete routes that live on the patients
router. Kept in a separate file from the themes/conversations tests so
merge risk stays low while multiple agents touch ``patients.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.dependencies import get_api_key_auth, get_event_publisher
from src.api.v1.endpoints.patients import (
    get_assessment_service,
    get_auth_service,
    get_conversation_service,
    get_data_export_service,
    get_themes_service,
    router,
)
from src.core.database import get_db_session
from src.core.exceptions import ForbiddenError, NotFoundError, setup_exception_handlers
from src.models.db.user import User, UserRole


def _mock_patient(email: str = "pt@example.com") -> MagicMock:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.organization_id = uuid.uuid4()
    u.email = email
    u.full_name = "Pat Patient"
    u.role = UserRole.PATIENT
    u.created_at = datetime(2026, 2, 1, tzinfo=UTC)
    u.updated_at = datetime(2026, 2, 1, tzinfo=UTC)
    u.email_verified_at = None
    return u


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def patient_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def mock_auth_context(org_id: uuid.UUID) -> MagicMock:
    ctx = MagicMock()
    ctx.api_key_id = uuid.uuid4()
    ctx.organization_id = org_id
    ctx.api_key_name = "test"
    return ctx


@pytest.fixture
def mock_export_service() -> MagicMock:
    svc = MagicMock()
    svc.export_patient = AsyncMock()
    svc.delete_patient = AsyncMock()
    return svc


@pytest.fixture
def mock_auth_service() -> MagicMock:
    svc = MagicMock()
    svc.get_user_by_id = AsyncMock()
    return svc


@pytest.fixture
def app(
    mock_auth_context: MagicMock,
    mock_export_service: MagicMock,
    mock_auth_service: MagicMock,
) -> FastAPI:
    test_app = FastAPI()
    setup_exception_handlers(test_app)
    test_app.include_router(router, prefix="/patients")

    mock_events = MagicMock()
    mock_events.publish = AsyncMock(return_value=None)

    test_app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    test_app.dependency_overrides[get_api_key_auth] = lambda: mock_auth_context
    test_app.dependency_overrides[get_event_publisher] = lambda: mock_events
    test_app.dependency_overrides[get_themes_service] = lambda: MagicMock()
    test_app.dependency_overrides[get_conversation_service] = lambda: MagicMock()
    test_app.dependency_overrides[get_assessment_service] = lambda: MagicMock()
    test_app.dependency_overrides[get_data_export_service] = lambda: mock_export_service
    test_app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


class TestExportPatientData:
    def test_export_returns_bundle(
        self,
        client: TestClient,
        mock_export_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        bundle = {
            "exported_at": "2026-04-21T12:00:00+00:00",
            "patient": {"id": str(patient_id), "email": "pt@example.com"},
            "consents": [],
            "sessions": [{"id": str(uuid.uuid4())}],
            "recaps": [],
            "transcripts": [],
            "themes": None,
            "conversations": [],
            "assessments": [],
        }
        mock_export_service.export_patient.return_value = bundle

        response = client.get(f"/patients/{patient_id}/export")

        assert response.status_code == 200
        body = response.json()
        assert body["patient"]["id"] == str(patient_id)
        assert len(body["sessions"]) == 1
        mock_export_service.export_patient.assert_awaited_once()

    def test_export_cross_org_returns_403(
        self,
        client: TestClient,
        mock_export_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        mock_export_service.export_patient.side_effect = ForbiddenError(
            "Patient does not belong to your organization"
        )

        response = client.get(f"/patients/{patient_id}/export")

        assert response.status_code == 403

    def test_export_missing_patient_returns_404(
        self,
        client: TestClient,
        mock_export_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        mock_export_service.export_patient.side_effect = NotFoundError(
            resource="Patient",
            resource_id=str(patient_id),
        )

        response = client.get(f"/patients/{patient_id}/export")

        assert response.status_code == 404


class TestDeletePatientData:
    def test_delete_with_matching_email_succeeds(
        self,
        client: TestClient,
        mock_export_service: MagicMock,
        mock_auth_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        patient = _mock_patient(email="pt@example.com")
        patient.id = patient_id
        mock_auth_service.get_user_by_id.return_value = patient
        mock_export_service.delete_patient.return_value = {
            "patient_id": str(patient_id),
            "session_count_deleted": 2,
            "transcript_count_deleted": 2,
            "conversation_count_deleted": 1,
            "deleted_at": "2026-04-21T12:00:00+00:00",
        }

        response = client.request(
            "DELETE",
            f"/patients/{patient_id}",
            json={"confirm_email": "pt@example.com"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["patient_id"] == str(patient_id)
        assert body["session_count_deleted"] == 2
        mock_export_service.delete_patient.assert_awaited_once()

    def test_delete_accepts_case_insensitive_email(
        self,
        client: TestClient,
        mock_export_service: MagicMock,
        mock_auth_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        """Clinicians type in whatever case; the confirmation is normalized."""
        patient = _mock_patient(email="pt@example.com")
        patient.id = patient_id
        mock_auth_service.get_user_by_id.return_value = patient
        mock_export_service.delete_patient.return_value = {
            "patient_id": str(patient_id),
            "session_count_deleted": 0,
            "transcript_count_deleted": 0,
            "conversation_count_deleted": 0,
            "deleted_at": "2026-04-21T12:00:00+00:00",
        }

        response = client.request(
            "DELETE",
            f"/patients/{patient_id}",
            json={"confirm_email": "PT@Example.COM"},
        )

        assert response.status_code == 200
        mock_export_service.delete_patient.assert_awaited_once()

    def test_delete_with_wrong_email_returns_422(
        self,
        client: TestClient,
        mock_export_service: MagicMock,
        mock_auth_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        patient = _mock_patient(email="pt@example.com")
        patient.id = patient_id
        mock_auth_service.get_user_by_id.return_value = patient

        response = client.request(
            "DELETE",
            f"/patients/{patient_id}",
            json={"confirm_email": "someone-else@example.com"},
        )

        assert response.status_code == 422
        mock_export_service.delete_patient.assert_not_called()

    def test_delete_unknown_patient_returns_404(
        self,
        client: TestClient,
        mock_auth_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        mock_auth_service.get_user_by_id.side_effect = NotFoundError(
            resource="User", resource_id=str(patient_id)
        )

        response = client.request(
            "DELETE",
            f"/patients/{patient_id}",
            json={"confirm_email": "whatever@example.com"},
        )

        assert response.status_code == 404
