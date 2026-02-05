"""Tests for Session model and schemas."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

# Import related models to ensure SQLAlchemy mappers are configured
from src.models.db.consent import Consent  # noqa: F401
from src.models.db.session import Session, SessionStatus
from src.models.db.user import User  # noqa: F401
from src.models.domain.session import (
    SessionCreate,
    SessionFilter,
    SessionRead,
    SessionSummary,
    SessionUpdate,
    SessionUploadResponse,
)
from src.models.domain.session import SessionStatus as DomainSessionStatus


class TestSessionStatus:
    """Tests for SessionStatus enum."""

    def test_session_status_values(self) -> None:
        """Test SessionStatus has correct values."""
        assert SessionStatus.PENDING.value == "pending"
        assert SessionStatus.UPLOADED.value == "uploaded"
        assert SessionStatus.TRANSCRIBING.value == "transcribing"
        assert SessionStatus.EMBEDDING.value == "embedding"
        assert SessionStatus.READY.value == "ready"
        assert SessionStatus.FAILED.value == "failed"

    def test_session_status_count(self) -> None:
        """Test SessionStatus has expected number of values."""
        assert len(SessionStatus) == 6


class TestSessionModel:
    """Tests for Session database model."""

    def test_session_creation(self) -> None:
        """Test Session model can be instantiated."""
        patient_id = uuid.uuid4()
        therapist_id = uuid.uuid4()
        consent_id = uuid.uuid4()
        session_date = datetime.now(UTC)

        session = Session(
            patient_id=patient_id,
            therapist_id=therapist_id,
            consent_id=consent_id,
            session_date=session_date,
            status=SessionStatus.PENDING,
        )

        assert session.patient_id == patient_id
        assert session.therapist_id == therapist_id
        assert session.consent_id == consent_id
        assert session.status == SessionStatus.PENDING

    def test_session_has_uuid_id(self) -> None:
        """Test Session model has UUID primary key."""
        id_type = Session.__table__.c.id.type
        assert id_type.__class__.__name__ == "UUID"

    def test_session_tablename(self) -> None:
        """Test Session model has correct table name."""
        assert Session.__tablename__ == "sessions"

    def test_session_has_patient_fk(self) -> None:
        """Test Session model has foreign key to users for patient."""
        patient_id_col = Session.__table__.c.patient_id
        fk = list(patient_id_col.foreign_keys)[0]
        assert fk.column.table.name == "users"

    def test_session_has_therapist_fk(self) -> None:
        """Test Session model has foreign key to users for therapist."""
        therapist_id_col = Session.__table__.c.therapist_id
        fk = list(therapist_id_col.foreign_keys)[0]
        assert fk.column.table.name == "users"

    def test_session_has_consent_fk(self) -> None:
        """Test Session model has foreign key to consents."""
        consent_id_col = Session.__table__.c.consent_id
        fk = list(consent_id_col.foreign_keys)[0]
        assert fk.column.table.name == "consents"


class TestSessionCreate:
    """Tests for SessionCreate schema."""

    def test_create_with_valid_data(self) -> None:
        """Test SessionCreate with valid data."""
        patient_id = uuid.uuid4()
        therapist_id = uuid.uuid4()
        consent_id = uuid.uuid4()
        session_date = datetime.now(UTC)

        schema = SessionCreate(
            patient_id=patient_id,
            therapist_id=therapist_id,
            consent_id=consent_id,
            session_date=session_date,
        )

        assert schema.patient_id == patient_id
        assert schema.therapist_id == therapist_id
        assert schema.consent_id == consent_id

    def test_create_with_metadata(self) -> None:
        """Test SessionCreate with metadata."""
        schema = SessionCreate(
            patient_id=uuid.uuid4(),
            therapist_id=uuid.uuid4(),
            consent_id=uuid.uuid4(),
            session_date=datetime.now(UTC),
            session_metadata={"platform": "web", "client_version": "1.0"},
        )

        assert schema.session_metadata == {"platform": "web", "client_version": "1.0"}

    def test_create_requires_patient_id(self) -> None:
        """Test SessionCreate requires patient_id."""
        with pytest.raises(ValidationError):
            SessionCreate(
                therapist_id=uuid.uuid4(),
                consent_id=uuid.uuid4(),
                session_date=datetime.now(UTC),
            )  # type: ignore[call-arg]

    def test_create_requires_consent_id(self) -> None:
        """Test SessionCreate requires consent_id."""
        with pytest.raises(ValidationError):
            SessionCreate(
                patient_id=uuid.uuid4(),
                therapist_id=uuid.uuid4(),
                session_date=datetime.now(UTC),
            )  # type: ignore[call-arg]


class TestSessionUpdate:
    """Tests for SessionUpdate schema."""

    def test_update_status(self) -> None:
        """Test SessionUpdate can update status."""
        schema = SessionUpdate(status=DomainSessionStatus.TRANSCRIBING)
        assert schema.status == DomainSessionStatus.TRANSCRIBING

    def test_update_recording_path(self) -> None:
        """Test SessionUpdate can update recording path."""
        schema = SessionUpdate(
            recording_path="recordings/2025/01/session-abc123.mp3"
        )
        assert schema.recording_path == "recordings/2025/01/session-abc123.mp3"

    def test_update_error_message(self) -> None:
        """Test SessionUpdate can set error message."""
        schema = SessionUpdate(
            status=DomainSessionStatus.FAILED,
            error_message="Transcription failed: API error",
        )
        assert schema.status == DomainSessionStatus.FAILED
        assert schema.error_message == "Transcription failed: API error"

    def test_update_all_fields_optional(self) -> None:
        """Test SessionUpdate allows all fields to be None."""
        schema = SessionUpdate()
        assert schema.status is None
        assert schema.recording_path is None
        assert schema.error_message is None


class TestSessionRead:
    """Tests for SessionRead schema."""

    def test_read_from_dict(self) -> None:
        """Test SessionRead can be created from dict."""
        now = datetime.now(UTC)
        data = {
            "id": uuid.uuid4(),
            "patient_id": uuid.uuid4(),
            "therapist_id": uuid.uuid4(),
            "consent_id": uuid.uuid4(),
            "session_date": now,
            "recording_path": "recordings/session.mp3",
            "recording_duration_seconds": 1800,
            "status": DomainSessionStatus.READY,
            "error_message": None,
            "session_metadata": {"notes": "Good session"},
            "created_at": now,
            "updated_at": now,
        }

        schema = SessionRead.model_validate(data)

        assert schema.status == DomainSessionStatus.READY
        assert schema.recording_duration_seconds == 1800


class TestSessionSummary:
    """Tests for SessionSummary schema."""

    def test_summary_from_dict(self) -> None:
        """Test SessionSummary can be created from dict."""
        now = datetime.now(UTC)
        data = {
            "id": uuid.uuid4(),
            "patient_id": uuid.uuid4(),
            "therapist_id": uuid.uuid4(),
            "session_date": now,
            "status": DomainSessionStatus.READY,
            "recording_duration_seconds": 3600,
            "created_at": now,
        }

        schema = SessionSummary.model_validate(data)

        assert schema.recording_duration_seconds == 3600


class TestSessionUploadResponse:
    """Tests for SessionUploadResponse schema."""

    def test_upload_response(self) -> None:
        """Test SessionUploadResponse creation."""
        session_id = uuid.uuid4()
        response = SessionUploadResponse(
            session_id=session_id,
            recording_path="recordings/abc123-test.mp3",
            file_size=1024000,
            status=DomainSessionStatus.UPLOADED,
        )

        assert response.session_id == session_id
        assert response.recording_path == "recordings/abc123-test.mp3"
        assert response.file_size == 1024000
        assert response.status == DomainSessionStatus.UPLOADED


class TestSessionFilter:
    """Tests for SessionFilter schema."""

    def test_filter_by_patient(self) -> None:
        """Test SessionFilter can filter by patient."""
        patient_id = uuid.uuid4()
        filter_schema = SessionFilter(patient_id=patient_id)
        assert filter_schema.patient_id == patient_id

    def test_filter_by_status(self) -> None:
        """Test SessionFilter can filter by status."""
        filter_schema = SessionFilter(status=DomainSessionStatus.TRANSCRIBING)
        assert filter_schema.status == DomainSessionStatus.TRANSCRIBING

    def test_filter_by_date_range(self) -> None:
        """Test SessionFilter can filter by date range."""
        date_from = datetime(2025, 1, 1, tzinfo=UTC)
        date_to = datetime(2025, 1, 31, tzinfo=UTC)
        filter_schema = SessionFilter(date_from=date_from, date_to=date_to)
        assert filter_schema.date_from == date_from
        assert filter_schema.date_to == date_to

    def test_filter_all_optional(self) -> None:
        """Test SessionFilter allows all fields to be None."""
        filter_schema = SessionFilter()
        assert filter_schema.patient_id is None
        assert filter_schema.therapist_id is None
        assert filter_schema.status is None
