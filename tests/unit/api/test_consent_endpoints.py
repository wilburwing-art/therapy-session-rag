"""Unit tests for Consent API endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.dependencies import get_api_key_auth
from src.api.v1.endpoints.consent import get_consent_service, router
from src.core.database import get_db_session
from src.models.domain.consent import (
    ConsentAuditEntry,
    ConsentCheck,
    ConsentRead,
    ConsentStatus,
    ConsentType,
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
def mock_consent_service() -> MagicMock:
    """Create a mock consent service."""
    return MagicMock()


@pytest.fixture
def app(mock_auth_context: MagicMock, mock_consent_service: MagicMock) -> FastAPI:
    """Create test app with mocked dependencies."""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/consent")

    test_app.dependency_overrides[get_api_key_auth] = lambda: mock_auth_context
    test_app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    test_app.dependency_overrides[get_consent_service] = lambda: mock_consent_service

    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def patient_id() -> uuid.UUID:
    """Create a test patient ID."""
    return uuid.uuid4()


@pytest.fixture
def therapist_id() -> uuid.UUID:
    """Create a test therapist ID."""
    return uuid.uuid4()


def make_consent_read(
    patient_id: uuid.UUID,
    therapist_id: uuid.UUID,
    consent_type: ConsentType = ConsentType.RECORDING,
    status: ConsentStatus = ConsentStatus.GRANTED,
) -> ConsentRead:
    """Create a ConsentRead response."""
    return ConsentRead(
        id=uuid.uuid4(),
        patient_id=patient_id,
        therapist_id=therapist_id,
        consent_type=consent_type,
        status=status,
        granted_at=datetime.now(UTC),
        revoked_at=None,
        ip_address="testclient",
        user_agent="testclient",
        consent_metadata=None,
    )


def make_consent_audit_entry(
    consent_type: ConsentType = ConsentType.RECORDING,
    status: ConsentStatus = ConsentStatus.GRANTED,
) -> ConsentAuditEntry:
    """Create a ConsentAuditEntry response."""
    return ConsentAuditEntry(
        id=uuid.uuid4(),
        consent_type=consent_type,
        status=status,
        granted_at=datetime.now(UTC),
        revoked_at=None,
        ip_address="testclient",
        user_agent="testclient",
    )


class TestGrantConsentEndpoint:
    """Tests for POST /consent endpoint."""

    def test_grant_consent_success(
        self,
        client: TestClient,
        mock_consent_service: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test successful consent grant."""
        mock_result = make_consent_read(patient_id, therapist_id)
        mock_consent_service.grant_consent = AsyncMock(return_value=mock_result)

        response = client.post(
            "/consent",
            json={
                "patient_id": str(patient_id),
                "therapist_id": str(therapist_id),
                "consent_type": "recording",
            },
        )

        assert response.status_code == 201
        mock_consent_service.grant_consent.assert_called_once()

    def test_grant_consent_with_metadata(
        self,
        client: TestClient,
        mock_consent_service: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test grant consent with metadata."""
        mock_result = make_consent_read(patient_id, therapist_id)
        mock_consent_service.grant_consent = AsyncMock(return_value=mock_result)

        response = client.post(
            "/consent",
            json={
                "patient_id": str(patient_id),
                "therapist_id": str(therapist_id),
                "consent_type": "transcription",
                "consent_metadata": {"source": "web"},
            },
        )

        assert response.status_code == 201


class TestRevokeConsentEndpoint:
    """Tests for DELETE /consent endpoint."""

    def test_revoke_consent_success(
        self,
        client: TestClient,
        mock_consent_service: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test successful consent revocation."""
        mock_result = make_consent_read(
            patient_id, therapist_id, status=ConsentStatus.REVOKED
        )
        mock_consent_service.revoke_consent = AsyncMock(return_value=mock_result)

        response = client.request(
            "DELETE",
            "/consent",
            json={
                "patient_id": str(patient_id),
                "therapist_id": str(therapist_id),
                "consent_type": "recording",
            },
        )

        assert response.status_code == 200
        mock_consent_service.revoke_consent.assert_called_once()


class TestCheckConsentEndpoint:
    """Tests for GET /consent/{patient_id}/check endpoint."""

    def test_check_consent_active(
        self,
        client: TestClient,
        mock_consent_service: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test check consent when active."""
        mock_consent = make_consent_read(patient_id, therapist_id)
        mock_result = ConsentCheck(
            patient_id=patient_id,
            consent_type=ConsentType.RECORDING,
            has_consent=True,
            consent=mock_consent,
        )
        mock_consent_service.check_consent = AsyncMock(return_value=mock_result)

        response = client.get(
            f"/consent/{patient_id}/check",
            params={"therapist_id": str(therapist_id), "consent_type": "recording"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_consent"] is True
        mock_consent_service.check_consent.assert_called_once()

    def test_check_consent_not_active(
        self,
        client: TestClient,
        mock_consent_service: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test check consent when not active."""
        mock_result = ConsentCheck(
            patient_id=patient_id,
            consent_type=ConsentType.RECORDING,
            has_consent=False,
            consent=None,
        )
        mock_consent_service.check_consent = AsyncMock(return_value=mock_result)

        response = client.get(
            f"/consent/{patient_id}/check",
            params={"therapist_id": str(therapist_id), "consent_type": "recording"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_consent"] is False


class TestGetActiveConsentsEndpoint:
    """Tests for GET /consent/{patient_id}/active endpoint."""

    def test_get_active_consents(
        self,
        client: TestClient,
        mock_consent_service: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test get all active consents."""
        mock_consents = [
            make_consent_read(patient_id, therapist_id, ConsentType.RECORDING),
            make_consent_read(patient_id, therapist_id, ConsentType.TRANSCRIPTION),
        ]
        mock_consent_service.get_all_active = AsyncMock(return_value=mock_consents)

        response = client.get(
            f"/consent/{patient_id}/active",
            params={"therapist_id": str(therapist_id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        mock_consent_service.get_all_active.assert_called_once()

    def test_get_active_consents_empty(
        self,
        client: TestClient,
        mock_consent_service: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test get active consents when none exist."""
        mock_consent_service.get_all_active = AsyncMock(return_value=[])

        response = client.get(
            f"/consent/{patient_id}/active",
            params={"therapist_id": str(therapist_id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0


class TestGetAuditLogEndpoint:
    """Tests for GET /consent/{patient_id}/audit endpoint."""

    def test_get_audit_log(
        self,
        client: TestClient,
        mock_consent_service: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test get audit log."""
        mock_entries = [
            make_consent_audit_entry(ConsentType.RECORDING, ConsentStatus.GRANTED),
            make_consent_audit_entry(ConsentType.RECORDING, ConsentStatus.REVOKED),
        ]
        mock_consent_service.get_audit_log = AsyncMock(return_value=mock_entries)

        response = client.get(
            f"/consent/{patient_id}/audit",
            params={"therapist_id": str(therapist_id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        mock_consent_service.get_audit_log.assert_called_once()

    def test_get_audit_log_with_type_filter(
        self,
        client: TestClient,
        mock_consent_service: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test get audit log with consent type filter."""
        mock_consent_service.get_audit_log = AsyncMock(return_value=[])

        response = client.get(
            f"/consent/{patient_id}/audit",
            params={
                "therapist_id": str(therapist_id),
                "consent_type": "recording",
            },
        )

        assert response.status_code == 200

    def test_get_audit_log_empty(
        self,
        client: TestClient,
        mock_consent_service: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test get audit log when empty."""
        mock_consent_service.get_audit_log = AsyncMock(return_value=[])

        response = client.get(
            f"/consent/{patient_id}/audit",
            params={"therapist_id": str(therapist_id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0


class TestConsentEndpointValidation:
    """Tests for consent endpoint input validation."""

    def test_grant_consent_invalid_consent_type(
        self,
        client: TestClient,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test grant consent with invalid consent type."""
        response = client.post(
            "/consent",
            json={
                "patient_id": str(patient_id),
                "therapist_id": str(therapist_id),
                "consent_type": "invalid_type",
            },
        )

        assert response.status_code == 422

    def test_grant_consent_missing_patient_id(
        self,
        client: TestClient,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test grant consent without patient_id."""
        response = client.post(
            "/consent",
            json={
                "therapist_id": str(therapist_id),
                "consent_type": "recording",
            },
        )

        assert response.status_code == 422

    def test_check_consent_invalid_uuid(
        self,
        client: TestClient,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test check consent with invalid UUID."""
        response = client.get(
            "/consent/not-a-uuid/check",
            params={"therapist_id": str(therapist_id), "consent_type": "recording"},
        )

        assert response.status_code == 422
