"""Tests for Consent model and schemas."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.models.db.consent import Consent, ConsentStatus, ConsentType
from src.models.domain.consent import (
    ConsentCheck,
    ConsentGrant,
    ConsentRead,
    ConsentRevoke,
)
from src.models.domain.consent import ConsentStatus as DomainConsentStatus
from src.models.domain.consent import ConsentType as DomainConsentType


class TestConsentType:
    """Tests for ConsentType enum."""

    def test_consent_type_values(self) -> None:
        """Test ConsentType has correct values."""
        assert ConsentType.RECORDING.value == "recording"
        assert ConsentType.TRANSCRIPTION.value == "transcription"
        assert ConsentType.AI_ANALYSIS.value == "ai_analysis"


class TestConsentStatus:
    """Tests for ConsentStatus enum."""

    def test_consent_status_values(self) -> None:
        """Test ConsentStatus has correct values."""
        assert ConsentStatus.GRANTED.value == "granted"
        assert ConsentStatus.REVOKED.value == "revoked"


class TestConsentModel:
    """Tests for Consent database model."""

    def test_consent_creation(self) -> None:
        """Test Consent model can be instantiated."""
        patient_id = uuid.uuid4()
        therapist_id = uuid.uuid4()

        consent = Consent(
            patient_id=patient_id,
            therapist_id=therapist_id,
            consent_type=ConsentType.RECORDING,
            status=ConsentStatus.GRANTED,
        )

        assert consent.patient_id == patient_id
        assert consent.therapist_id == therapist_id
        assert consent.consent_type == ConsentType.RECORDING
        assert consent.status == ConsentStatus.GRANTED

    def test_consent_has_uuid_id(self) -> None:
        """Test Consent model has UUID primary key."""
        id_type = Consent.__table__.c.id.type
        assert id_type.__class__.__name__ == "UUID"

    def test_consent_tablename(self) -> None:
        """Test Consent model has correct table name."""
        assert Consent.__tablename__ == "consents"

    def test_consent_has_patient_fk(self) -> None:
        """Test Consent model has foreign key to users for patient."""
        patient_id_col = Consent.__table__.c.patient_id
        fk = list(patient_id_col.foreign_keys)[0]
        assert fk.column.table.name == "users"

    def test_consent_has_therapist_fk(self) -> None:
        """Test Consent model has foreign key to users for therapist."""
        therapist_id_col = Consent.__table__.c.therapist_id
        fk = list(therapist_id_col.foreign_keys)[0]
        assert fk.column.table.name == "users"


class TestConsentGrant:
    """Tests for ConsentGrant schema."""

    def test_grant_with_valid_data(self) -> None:
        """Test ConsentGrant with valid data."""
        patient_id = uuid.uuid4()
        therapist_id = uuid.uuid4()

        schema = ConsentGrant(
            patient_id=patient_id,
            therapist_id=therapist_id,
            consent_type=DomainConsentType.RECORDING,
        )

        assert schema.patient_id == patient_id
        assert schema.therapist_id == therapist_id
        assert schema.consent_type == DomainConsentType.RECORDING

    def test_grant_with_consent_metadata(self) -> None:
        """Test ConsentGrant with consent_metadata."""
        schema = ConsentGrant(
            patient_id=uuid.uuid4(),
            therapist_id=uuid.uuid4(),
            consent_type=DomainConsentType.TRANSCRIPTION,
            consent_metadata={"source": "web", "version": "1.0"},
        )

        assert schema.consent_metadata == {"source": "web", "version": "1.0"}

    def test_grant_requires_patient_id(self) -> None:
        """Test ConsentGrant requires patient_id."""
        with pytest.raises(ValidationError):
            ConsentGrant(
                therapist_id=uuid.uuid4(),
                consent_type=DomainConsentType.RECORDING,
            )  # type: ignore[call-arg]

    def test_grant_requires_valid_consent_type(self) -> None:
        """Test ConsentGrant validates consent_type."""
        with pytest.raises(ValidationError):
            ConsentGrant(
                patient_id=uuid.uuid4(),
                therapist_id=uuid.uuid4(),
                consent_type="invalid_type",  # type: ignore[arg-type]
            )


class TestConsentRevoke:
    """Tests for ConsentRevoke schema."""

    def test_revoke_with_valid_data(self) -> None:
        """Test ConsentRevoke with valid data."""
        patient_id = uuid.uuid4()
        therapist_id = uuid.uuid4()

        schema = ConsentRevoke(
            patient_id=patient_id,
            therapist_id=therapist_id,
            consent_type=DomainConsentType.AI_ANALYSIS,
        )

        assert schema.patient_id == patient_id
        assert schema.consent_type == DomainConsentType.AI_ANALYSIS


class TestConsentRead:
    """Tests for ConsentRead schema."""

    def test_read_from_dict(self) -> None:
        """Test ConsentRead can be created from dict."""
        now = datetime.now(UTC)
        data = {
            "id": uuid.uuid4(),
            "patient_id": uuid.uuid4(),
            "therapist_id": uuid.uuid4(),
            "consent_type": DomainConsentType.RECORDING,
            "status": DomainConsentStatus.GRANTED,
            "granted_at": now,
            "revoked_at": None,
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0",
            "consent_metadata": {"key": "value"},
        }

        schema = ConsentRead.model_validate(data)

        assert schema.status == DomainConsentStatus.GRANTED
        assert schema.ip_address == "192.168.1.1"


class TestConsentCheck:
    """Tests for ConsentCheck schema."""

    def test_check_with_consent(self) -> None:
        """Test ConsentCheck with active consent."""
        now = datetime.now(UTC)
        consent_data = {
            "id": uuid.uuid4(),
            "patient_id": uuid.uuid4(),
            "therapist_id": uuid.uuid4(),
            "consent_type": DomainConsentType.RECORDING,
            "status": DomainConsentStatus.GRANTED,
            "granted_at": now,
            "revoked_at": None,
            "ip_address": None,
            "user_agent": None,
            "consent_metadata": None,
        }
        consent = ConsentRead.model_validate(consent_data)

        check = ConsentCheck(
            patient_id=consent_data["patient_id"],
            consent_type=DomainConsentType.RECORDING,
            has_consent=True,
            consent=consent,
        )

        assert check.has_consent is True
        assert check.consent is not None

    def test_check_without_consent(self) -> None:
        """Test ConsentCheck without active consent."""
        check = ConsentCheck(
            patient_id=uuid.uuid4(),
            consent_type=DomainConsentType.RECORDING,
            has_consent=False,
            consent=None,
        )

        assert check.has_consent is False
        assert check.consent is None
