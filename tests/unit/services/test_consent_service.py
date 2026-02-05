"""Tests for ConsentService."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import ConflictError, NotFoundError
from src.models.domain.consent import ConsentGrant, ConsentRevoke
from src.models.domain.consent import ConsentStatus as DomainConsentStatus
from src.models.domain.consent import ConsentType as DomainConsentType


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async session."""
    return AsyncMock()


@pytest.fixture
def patient_id() -> uuid.UUID:
    """Create a test patient ID."""
    return uuid.uuid4()


@pytest.fixture
def therapist_id() -> uuid.UUID:
    """Create a test therapist ID."""
    return uuid.uuid4()


def make_mock_consent(
    patient_id: uuid.UUID,
    therapist_id: uuid.UUID,
    consent_type: str = "recording",
    status: str = "granted",
    granted_at: datetime | None = None,
    revoked_at: datetime | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    consent_metadata: dict | None = None,
) -> MagicMock:
    """Create a mock consent object."""
    mock = MagicMock()
    mock.id = uuid.uuid4()
    mock.patient_id = patient_id
    mock.therapist_id = therapist_id
    mock.consent_type = MagicMock()
    mock.consent_type.value = consent_type
    mock.status = MagicMock()
    mock.status.value = status
    mock.granted_at = granted_at or datetime.now(UTC)
    mock.revoked_at = revoked_at
    mock.ip_address = ip_address
    mock.user_agent = user_agent
    mock.consent_metadata = consent_metadata
    return mock


class TestGrantConsent:
    """Tests for grant_consent method."""

    async def test_grant_consent_success(
        self,
        mock_session: AsyncMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test successful consent grant."""
        with (
            patch("src.services.consent_service.ConsentRepository") as MockRepo,
            patch("src.services.consent_service.Consent") as MockConsent,
        ):
            from src.services.consent_service import ConsentService

            mock_repo = MockRepo.return_value
            mock_repo.get_active_consent = AsyncMock(return_value=None)

            created_consent = make_mock_consent(
                patient_id, therapist_id, "recording", "granted"
            )
            mock_repo.create = AsyncMock(return_value=created_consent)
            MockConsent.return_value = created_consent

            service = ConsentService(mock_session)
            service.repo = mock_repo

            grant = ConsentGrant(
                patient_id=patient_id,
                therapist_id=therapist_id,
                consent_type=DomainConsentType.RECORDING,
            )

            result = await service.grant_consent(grant, ip_address="192.168.1.1")

            assert result.patient_id == patient_id
            assert result.consent_type == DomainConsentType.RECORDING

    async def test_grant_consent_conflict(
        self,
        mock_session: AsyncMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test grant raises ConflictError when consent already exists."""
        with patch("src.services.consent_service.ConsentRepository") as MockRepo:
            from src.services.consent_service import ConsentService

            mock_repo = MockRepo.return_value
            existing = make_mock_consent(patient_id, therapist_id)
            mock_repo.get_active_consent = AsyncMock(return_value=existing)

            service = ConsentService(mock_session)
            service.repo = mock_repo

            grant = ConsentGrant(
                patient_id=patient_id,
                therapist_id=therapist_id,
                consent_type=DomainConsentType.RECORDING,
            )

            with pytest.raises(ConflictError):
                await service.grant_consent(grant)

    async def test_grant_consent_captures_ip_and_user_agent(
        self,
        mock_session: AsyncMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test that IP and user agent are captured."""
        with (
            patch("src.services.consent_service.ConsentRepository") as MockRepo,
            patch("src.services.consent_service.Consent") as MockConsent,
        ):
            from src.services.consent_service import ConsentService

            mock_repo = MockRepo.return_value
            mock_repo.get_active_consent = AsyncMock(return_value=None)

            created_consent = make_mock_consent(
                patient_id,
                therapist_id,
                ip_address="10.0.0.1",
                user_agent="Mozilla/5.0",
            )
            mock_repo.create = AsyncMock(return_value=created_consent)
            MockConsent.return_value = created_consent

            service = ConsentService(mock_session)
            service.repo = mock_repo

            grant = ConsentGrant(
                patient_id=patient_id,
                therapist_id=therapist_id,
                consent_type=DomainConsentType.RECORDING,
            )

            result = await service.grant_consent(
                grant, ip_address="10.0.0.1", user_agent="Mozilla/5.0"
            )

            assert result.ip_address == "10.0.0.1"
            assert result.user_agent == "Mozilla/5.0"

    async def test_grant_consent_with_metadata(
        self,
        mock_session: AsyncMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test grant with metadata."""
        with (
            patch("src.services.consent_service.ConsentRepository") as MockRepo,
            patch("src.services.consent_service.Consent") as MockConsent,
        ):
            from src.services.consent_service import ConsentService

            mock_repo = MockRepo.return_value
            mock_repo.get_active_consent = AsyncMock(return_value=None)

            metadata = {"source": "web", "version": "1.0"}
            created_consent = make_mock_consent(
                patient_id, therapist_id, consent_metadata=metadata
            )
            mock_repo.create = AsyncMock(return_value=created_consent)
            MockConsent.return_value = created_consent

            service = ConsentService(mock_session)
            service.repo = mock_repo

            grant = ConsentGrant(
                patient_id=patient_id,
                therapist_id=therapist_id,
                consent_type=DomainConsentType.TRANSCRIPTION,
                consent_metadata=metadata,
            )

            result = await service.grant_consent(grant)

            assert result.consent_metadata == metadata


class TestRevokeConsent:
    """Tests for revoke_consent method."""

    async def test_revoke_consent_success(
        self,
        mock_session: AsyncMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test successful consent revocation."""
        with (
            patch("src.services.consent_service.ConsentRepository") as MockRepo,
            patch("src.services.consent_service.Consent") as MockConsent,
        ):
            from src.services.consent_service import ConsentService

            mock_repo = MockRepo.return_value
            existing = make_mock_consent(patient_id, therapist_id)
            mock_repo.get_active_consent = AsyncMock(return_value=existing)

            revoked_consent = make_mock_consent(
                patient_id,
                therapist_id,
                status="revoked",
                revoked_at=datetime.now(UTC),
            )
            mock_repo.create = AsyncMock(return_value=revoked_consent)
            MockConsent.return_value = revoked_consent

            service = ConsentService(mock_session)
            service.repo = mock_repo

            revoke = ConsentRevoke(
                patient_id=patient_id,
                therapist_id=therapist_id,
                consent_type=DomainConsentType.RECORDING,
            )

            result = await service.revoke_consent(revoke)

            assert result.status == DomainConsentStatus.REVOKED
            assert result.revoked_at is not None

    async def test_revoke_consent_not_found(
        self,
        mock_session: AsyncMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test revoke raises NotFoundError when no active consent."""
        with patch("src.services.consent_service.ConsentRepository") as MockRepo:
            from src.services.consent_service import ConsentService

            mock_repo = MockRepo.return_value
            mock_repo.get_active_consent = AsyncMock(return_value=None)

            service = ConsentService(mock_session)
            service.repo = mock_repo

            revoke = ConsentRevoke(
                patient_id=patient_id,
                therapist_id=therapist_id,
                consent_type=DomainConsentType.AI_ANALYSIS,
            )

            with pytest.raises(NotFoundError):
                await service.revoke_consent(revoke)

    async def test_revoke_captures_ip_and_user_agent(
        self,
        mock_session: AsyncMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test that IP and user agent are captured on revocation."""
        with (
            patch("src.services.consent_service.ConsentRepository") as MockRepo,
            patch("src.services.consent_service.Consent") as MockConsent,
        ):
            from src.services.consent_service import ConsentService

            mock_repo = MockRepo.return_value
            existing = make_mock_consent(patient_id, therapist_id)
            mock_repo.get_active_consent = AsyncMock(return_value=existing)

            revoked_consent = make_mock_consent(
                patient_id,
                therapist_id,
                status="revoked",
                revoked_at=datetime.now(UTC),
                ip_address="192.168.1.100",
                user_agent="Chrome/100",
            )
            mock_repo.create = AsyncMock(return_value=revoked_consent)
            MockConsent.return_value = revoked_consent

            service = ConsentService(mock_session)
            service.repo = mock_repo

            revoke = ConsentRevoke(
                patient_id=patient_id,
                therapist_id=therapist_id,
                consent_type=DomainConsentType.RECORDING,
            )

            result = await service.revoke_consent(
                revoke, ip_address="192.168.1.100", user_agent="Chrome/100"
            )

            assert result.ip_address == "192.168.1.100"
            assert result.user_agent == "Chrome/100"


class TestCheckConsent:
    """Tests for check_consent method."""

    async def test_check_consent_active(
        self,
        mock_session: AsyncMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test check returns has_consent=True when active."""
        with patch("src.services.consent_service.ConsentRepository") as MockRepo:
            from src.services.consent_service import ConsentService

            mock_repo = MockRepo.return_value
            active_consent = make_mock_consent(patient_id, therapist_id)
            mock_repo.get_active_consent = AsyncMock(return_value=active_consent)

            service = ConsentService(mock_session)
            service.repo = mock_repo

            result = await service.check_consent(
                patient_id, therapist_id, DomainConsentType.RECORDING
            )

            assert result.has_consent is True
            assert result.consent is not None
            assert result.consent.consent_type == DomainConsentType.RECORDING

    async def test_check_consent_not_active(
        self,
        mock_session: AsyncMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test check returns has_consent=False when not active."""
        with patch("src.services.consent_service.ConsentRepository") as MockRepo:
            from src.services.consent_service import ConsentService

            mock_repo = MockRepo.return_value
            mock_repo.get_active_consent = AsyncMock(return_value=None)

            service = ConsentService(mock_session)
            service.repo = mock_repo

            result = await service.check_consent(
                patient_id, therapist_id, DomainConsentType.AI_ANALYSIS
            )

            assert result.has_consent is False
            assert result.consent is None


class TestGetAuditLog:
    """Tests for get_audit_log method."""

    async def test_get_audit_log_returns_history(
        self,
        mock_session: AsyncMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test get_audit_log returns all consent history."""
        with patch("src.services.consent_service.ConsentRepository") as MockRepo:
            from src.services.consent_service import ConsentService

            mock_repo = MockRepo.return_value
            now = datetime.now(UTC)
            consents = [
                make_mock_consent(
                    patient_id, therapist_id, status="revoked", revoked_at=now
                ),
                make_mock_consent(patient_id, therapist_id, status="granted"),
            ]
            mock_repo.get_audit_log = AsyncMock(return_value=consents)

            service = ConsentService(mock_session)
            service.repo = mock_repo

            result = await service.get_audit_log(patient_id, therapist_id)

            assert len(result) == 2

    async def test_get_audit_log_with_type_filter(
        self,
        mock_session: AsyncMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test get_audit_log filters by consent type."""
        with (
            patch("src.services.consent_service.ConsentRepository") as MockRepo,
            patch("src.services.consent_service.ConsentType") as MockConsentType,
        ):
            from src.services.consent_service import ConsentService

            mock_repo = MockRepo.return_value
            mock_repo.get_audit_log = AsyncMock(return_value=[])

            mock_consent_type = MagicMock()
            MockConsentType.return_value = mock_consent_type

            service = ConsentService(mock_session)
            service.repo = mock_repo

            await service.get_audit_log(
                patient_id, therapist_id, DomainConsentType.TRANSCRIPTION
            )

            mock_repo.get_audit_log.assert_called_once()

    async def test_get_audit_log_empty(
        self,
        mock_session: AsyncMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test get_audit_log returns empty list when no history."""
        with patch("src.services.consent_service.ConsentRepository") as MockRepo:
            from src.services.consent_service import ConsentService

            mock_repo = MockRepo.return_value
            mock_repo.get_audit_log = AsyncMock(return_value=[])

            service = ConsentService(mock_session)
            service.repo = mock_repo

            result = await service.get_audit_log(patient_id, therapist_id)

            assert result == []


class TestGetAllActive:
    """Tests for get_all_active method."""

    async def test_get_all_active_returns_active_consents(
        self,
        mock_session: AsyncMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test get_all_active returns all active consent types."""
        with patch("src.services.consent_service.ConsentRepository") as MockRepo:
            from src.services.consent_service import ConsentService

            mock_repo = MockRepo.return_value
            consents = [
                make_mock_consent(patient_id, therapist_id, "recording"),
                make_mock_consent(patient_id, therapist_id, "transcription"),
            ]
            mock_repo.get_all_active_for_patient = AsyncMock(return_value=consents)

            service = ConsentService(mock_session)
            service.repo = mock_repo

            result = await service.get_all_active(patient_id, therapist_id)

            assert len(result) == 2
            types = {c.consent_type for c in result}
            assert DomainConsentType.RECORDING in types
            assert DomainConsentType.TRANSCRIPTION in types

    async def test_get_all_active_empty(
        self,
        mock_session: AsyncMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> None:
        """Test get_all_active returns empty when no active consents."""
        with patch("src.services.consent_service.ConsentRepository") as MockRepo:
            from src.services.consent_service import ConsentService

            mock_repo = MockRepo.return_value
            mock_repo.get_all_active_for_patient = AsyncMock(return_value=[])

            service = ConsentService(mock_session)
            service.repo = mock_repo

            result = await service.get_all_active(patient_id, therapist_id)

            assert result == []
