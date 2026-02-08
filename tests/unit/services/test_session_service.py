"""Tests for SessionService."""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import ForbiddenError, NotFoundError
from src.models.db.consent import ConsentType
from src.models.db.session import Session, SessionStatus
from src.models.db.session import SessionType as DbSessionType
from src.models.domain.session import (
    SessionCreate,
    SessionFilter,
    SessionUpdate,
)
from src.models.domain.session import SessionStatus as DomainSessionStatus
from src.services.session_service import SessionService


@pytest.fixture
def mock_db_session() -> MagicMock:
    """Create mock database session."""
    session = MagicMock()
    session.refresh = AsyncMock()
    return session


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


def create_mock_session(
    session_id: uuid.UUID,
    patient_id: uuid.UUID,
    therapist_id: uuid.UUID,
    consent_id: uuid.UUID,
    status: SessionStatus = SessionStatus.PENDING,
    session_type: DbSessionType = DbSessionType.UPLOAD,
    recording_path: str | None = None,
    recording_duration_seconds: int | None = None,
    error_message: str | None = None,
) -> MagicMock:
    """Create a mock Session object."""
    session = MagicMock(spec=Session)
    session.id = session_id
    session.patient_id = patient_id
    session.therapist_id = therapist_id
    session.consent_id = consent_id
    session.session_date = datetime.utcnow()
    session.recording_path = recording_path
    session.recording_duration_seconds = recording_duration_seconds
    session.status = status
    session.session_type = session_type
    session.error_message = error_message
    session.session_metadata = {}
    session.created_at = datetime.utcnow()
    session.updated_at = datetime.utcnow()
    return session


class TestCreateSession:
    """Tests for create_session method."""

    async def test_creates_session_with_valid_consent(
        self,
        mock_db_session: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        """Test session creation when consent is valid."""
        mock_consent = MagicMock()
        mock_consent.id = consent_id

        mock_session = create_mock_session(
            session_id=session_id,
            patient_id=patient_id,
            therapist_id=therapist_id,
            consent_id=consent_id,
        )

        with (
            patch(
                "src.services.session_service.ConsentRepository"
            ) as mock_consent_repo_class,
            patch(
                "src.services.session_service.SessionRepository"
            ) as mock_session_repo_class,
        ):
            mock_consent_repo = MagicMock()
            mock_consent_repo.get_active_consent = AsyncMock(
                return_value=mock_consent
            )
            mock_consent_repo_class.return_value = mock_consent_repo

            mock_session_repo = MagicMock()
            mock_session_repo.create = AsyncMock(return_value=mock_session)
            mock_session_repo_class.return_value = mock_session_repo

            service = SessionService(mock_db_session)

            create_data = SessionCreate(
                patient_id=patient_id,
                therapist_id=therapist_id,
                consent_id=consent_id,
                session_date=datetime.utcnow(),
            )

            result = await service.create_session(create_data)

            assert result.id == session_id
            assert result.patient_id == patient_id
            assert result.therapist_id == therapist_id
            mock_consent_repo.get_active_consent.assert_called_once_with(
                patient_id=patient_id,
                therapist_id=therapist_id,
                consent_type=ConsentType.RECORDING,
            )

    async def test_raises_forbidden_without_consent(
        self,
        mock_db_session: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
    ) -> None:
        """Test session creation fails without consent."""
        with (
            patch(
                "src.services.session_service.ConsentRepository"
            ) as mock_consent_repo_class,
            patch("src.services.session_service.SessionRepository"),
        ):
            mock_consent_repo = MagicMock()
            mock_consent_repo.get_active_consent = AsyncMock(return_value=None)
            mock_consent_repo_class.return_value = mock_consent_repo

            service = SessionService(mock_db_session)

            create_data = SessionCreate(
                patient_id=patient_id,
                therapist_id=therapist_id,
                consent_id=consent_id,
                session_date=datetime.utcnow(),
            )

            with pytest.raises(ForbiddenError) as exc_info:
                await service.create_session(create_data)

            assert "consent" in str(exc_info.value.detail).lower()


class TestGetSession:
    """Tests for get_session method."""

    async def test_returns_session_when_found(
        self,
        mock_db_session: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        """Test session retrieval when found."""
        mock_session = create_mock_session(
            session_id=session_id,
            patient_id=patient_id,
            therapist_id=therapist_id,
            consent_id=consent_id,
        )

        with (
            patch("src.services.session_service.ConsentRepository"),
            patch(
                "src.services.session_service.SessionRepository"
            ) as mock_session_repo_class,
        ):
            mock_session_repo = MagicMock()
            mock_session_repo.get_by_id = AsyncMock(return_value=mock_session)
            mock_session_repo_class.return_value = mock_session_repo

            service = SessionService(mock_db_session)
            result = await service.get_session(session_id)

            assert result.id == session_id
            mock_session_repo.get_by_id.assert_called_once_with(session_id)

    async def test_raises_not_found_when_missing(
        self,
        mock_db_session: MagicMock,
        session_id: uuid.UUID,
    ) -> None:
        """Test NotFoundError when session doesn't exist."""
        with (
            patch("src.services.session_service.ConsentRepository"),
            patch(
                "src.services.session_service.SessionRepository"
            ) as mock_session_repo_class,
        ):
            mock_session_repo = MagicMock()
            mock_session_repo.get_by_id = AsyncMock(return_value=None)
            mock_session_repo_class.return_value = mock_session_repo

            service = SessionService(mock_db_session)

            with pytest.raises(NotFoundError):
                await service.get_session(session_id)


class TestUpdateSession:
    """Tests for update_session method."""

    async def test_updates_status(
        self,
        mock_db_session: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        """Test updating session status."""
        mock_session = create_mock_session(
            session_id=session_id,
            patient_id=patient_id,
            therapist_id=therapist_id,
            consent_id=consent_id,
            status=SessionStatus.PENDING,
        )

        with (
            patch("src.services.session_service.ConsentRepository"),
            patch(
                "src.services.session_service.SessionRepository"
            ) as mock_session_repo_class,
        ):
            mock_session_repo = MagicMock()
            mock_session_repo.get_by_id = AsyncMock(return_value=mock_session)
            mock_session_repo.update_status = AsyncMock(return_value=True)
            mock_session_repo_class.return_value = mock_session_repo

            service = SessionService(mock_db_session)

            update_data = SessionUpdate(status=DomainSessionStatus.UPLOADED)
            result = await service.update_session(session_id, update_data)

            assert result.id == session_id
            mock_session_repo.update_status.assert_called_once()

    async def test_updates_recording_info(
        self,
        mock_db_session: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        """Test updating session recording info."""
        mock_session = create_mock_session(
            session_id=session_id,
            patient_id=patient_id,
            therapist_id=therapist_id,
            consent_id=consent_id,
        )

        with (
            patch("src.services.session_service.ConsentRepository"),
            patch(
                "src.services.session_service.SessionRepository"
            ) as mock_session_repo_class,
        ):
            mock_session_repo = MagicMock()
            mock_session_repo.get_by_id = AsyncMock(return_value=mock_session)
            mock_session_repo.update_recording_info = AsyncMock(
                return_value=True
            )
            mock_session_repo_class.return_value = mock_session_repo

            service = SessionService(mock_db_session)

            update_data = SessionUpdate(
                recording_path="recordings/test.mp3",
                recording_duration_seconds=3600,
            )
            result = await service.update_session(session_id, update_data)

            assert result.id == session_id
            mock_session_repo.update_recording_info.assert_called_once_with(
                session_id=session_id,
                recording_path="recordings/test.mp3",
                recording_duration_seconds=3600,
            )

    async def test_raises_not_found_when_missing(
        self,
        mock_db_session: MagicMock,
        session_id: uuid.UUID,
    ) -> None:
        """Test NotFoundError when updating nonexistent session."""
        with (
            patch("src.services.session_service.ConsentRepository"),
            patch(
                "src.services.session_service.SessionRepository"
            ) as mock_session_repo_class,
        ):
            mock_session_repo = MagicMock()
            mock_session_repo.get_by_id = AsyncMock(return_value=None)
            mock_session_repo_class.return_value = mock_session_repo

            service = SessionService(mock_db_session)

            with pytest.raises(NotFoundError):
                await service.update_session(
                    session_id,
                    SessionUpdate(status=DomainSessionStatus.UPLOADED),
                )


class TestUpdateStatus:
    """Tests for update_status method."""

    async def test_updates_status_successfully(
        self,
        mock_db_session: MagicMock,
        session_id: uuid.UUID,
    ) -> None:
        """Test status update returns True on success."""
        with (
            patch("src.services.session_service.ConsentRepository"),
            patch(
                "src.services.session_service.SessionRepository"
            ) as mock_session_repo_class,
        ):
            mock_session_repo = MagicMock()
            mock_session_repo.update_status = AsyncMock(return_value=True)
            mock_session_repo_class.return_value = mock_session_repo

            service = SessionService(mock_db_session)
            result = await service.update_status(
                session_id, DomainSessionStatus.TRANSCRIBING
            )

            assert result is True
            mock_session_repo.update_status.assert_called_once()

    async def test_updates_status_with_error_message(
        self,
        mock_db_session: MagicMock,
        session_id: uuid.UUID,
    ) -> None:
        """Test status update with error message for FAILED status."""
        with (
            patch("src.services.session_service.ConsentRepository"),
            patch(
                "src.services.session_service.SessionRepository"
            ) as mock_session_repo_class,
        ):
            mock_session_repo = MagicMock()
            mock_session_repo.update_status = AsyncMock(return_value=True)
            mock_session_repo_class.return_value = mock_session_repo

            service = SessionService(mock_db_session)
            result = await service.update_status(
                session_id,
                DomainSessionStatus.FAILED,
                error_message="Transcription failed",
            )

            assert result is True
            mock_session_repo.update_status.assert_called_once_with(
                session_id=session_id,
                status=SessionStatus.FAILED,
                error_message="Transcription failed",
            )

    async def test_returns_false_when_session_not_found(
        self,
        mock_db_session: MagicMock,
        session_id: uuid.UUID,
    ) -> None:
        """Test status update returns False when session not found."""
        with (
            patch("src.services.session_service.ConsentRepository"),
            patch(
                "src.services.session_service.SessionRepository"
            ) as mock_session_repo_class,
        ):
            mock_session_repo = MagicMock()
            mock_session_repo.update_status = AsyncMock(return_value=False)
            mock_session_repo_class.return_value = mock_session_repo

            service = SessionService(mock_db_session)
            result = await service.update_status(
                session_id, DomainSessionStatus.UPLOADED
            )

            assert result is False


class TestListSessions:
    """Tests for list_sessions method."""

    async def test_lists_sessions_without_filters(
        self,
        mock_db_session: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        """Test listing sessions without filters."""
        mock_sessions = [
            create_mock_session(
                session_id=session_id,
                patient_id=patient_id,
                therapist_id=therapist_id,
                consent_id=consent_id,
            )
        ]

        with (
            patch("src.services.session_service.ConsentRepository"),
            patch(
                "src.services.session_service.SessionRepository"
            ) as mock_session_repo_class,
        ):
            mock_session_repo = MagicMock()
            mock_session_repo.list_sessions = AsyncMock(
                return_value=mock_sessions
            )
            mock_session_repo_class.return_value = mock_session_repo

            service = SessionService(mock_db_session)
            result = await service.list_sessions()

            assert len(result) == 1
            assert result[0].id == session_id

    async def test_lists_sessions_with_filters(
        self,
        mock_db_session: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        """Test listing sessions with filters."""
        mock_sessions = [
            create_mock_session(
                session_id=session_id,
                patient_id=patient_id,
                therapist_id=therapist_id,
                consent_id=consent_id,
                status=SessionStatus.READY,
            )
        ]

        with (
            patch("src.services.session_service.ConsentRepository"),
            patch(
                "src.services.session_service.SessionRepository"
            ) as mock_session_repo_class,
        ):
            mock_session_repo = MagicMock()
            mock_session_repo.list_sessions = AsyncMock(
                return_value=mock_sessions
            )
            mock_session_repo_class.return_value = mock_session_repo

            service = SessionService(mock_db_session)
            filter_params = SessionFilter(
                patient_id=patient_id,
                status=DomainSessionStatus.READY,
            )
            result = await service.list_sessions(filter_params=filter_params)

            assert len(result) == 1
            mock_session_repo.list_sessions.assert_called_once()


class TestGetSessionsForPatient:
    """Tests for get_sessions_for_patient method."""

    async def test_gets_sessions_for_patient(
        self,
        mock_db_session: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        """Test getting all sessions for a patient."""
        mock_sessions = [
            create_mock_session(
                session_id=session_id,
                patient_id=patient_id,
                therapist_id=therapist_id,
                consent_id=consent_id,
            )
        ]

        with (
            patch("src.services.session_service.ConsentRepository"),
            patch(
                "src.services.session_service.SessionRepository"
            ) as mock_session_repo_class,
        ):
            mock_session_repo = MagicMock()
            mock_session_repo.list_sessions = AsyncMock(
                return_value=mock_sessions
            )
            mock_session_repo_class.return_value = mock_session_repo

            service = SessionService(mock_db_session)
            result = await service.get_sessions_for_patient(patient_id)

            assert len(result) == 1
            assert result[0].patient_id == patient_id
            mock_session_repo.list_sessions.assert_called_once_with(
                patient_id=patient_id,
                therapist_id=None,
                status=None,
            )

    async def test_filters_by_therapist_and_status(
        self,
        mock_db_session: MagicMock,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        """Test filtering sessions by therapist and status."""
        mock_sessions = [
            create_mock_session(
                session_id=session_id,
                patient_id=patient_id,
                therapist_id=therapist_id,
                consent_id=consent_id,
                status=SessionStatus.READY,
            )
        ]

        with (
            patch("src.services.session_service.ConsentRepository"),
            patch(
                "src.services.session_service.SessionRepository"
            ) as mock_session_repo_class,
        ):
            mock_session_repo = MagicMock()
            mock_session_repo.list_sessions = AsyncMock(
                return_value=mock_sessions
            )
            mock_session_repo_class.return_value = mock_session_repo

            service = SessionService(mock_db_session)
            result = await service.get_sessions_for_patient(
                patient_id=patient_id,
                therapist_id=therapist_id,
                status=DomainSessionStatus.READY,
            )

            assert len(result) == 1
            mock_session_repo.list_sessions.assert_called_once_with(
                patient_id=patient_id,
                therapist_id=therapist_id,
                status=SessionStatus.READY,
            )
