"""Unit tests for the patient-authenticated portal endpoints.

Covers /patient/me, /patient/sessions, and /patient/sessions/{id}/recap.
The point of these tests is to lock in the two security invariants the
router is built around:

1. Every route is scoped to the authenticated patient — no caller can
   pass in an arbitrary patient_id.
2. The recap view never exposes therapist_notes, risk_flags, or the
   raw transcript to the patient, even if those fields exist on the
   stored recap.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.dependencies import get_current_patient, get_event_publisher
from src.api.v1.endpoints.patient_portal import (
    get_session_service,
    get_summarization_service,
    router,
)
from src.core.database import get_db_session
from src.core.exceptions import NotFoundError, setup_exception_handlers
from src.models.db.user import User, UserRole
from src.models.domain.session import SessionStatus, SessionSummary, SessionType
from src.models.domain.session_recap import HomeworkItem, SessionRecapRead


def _make_patient(
    patient_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
) -> MagicMock:
    patient = MagicMock(spec=User)
    patient.id = patient_id or uuid.uuid4()
    patient.organization_id = org_id or uuid.uuid4()
    patient.email = "pt@example.com"
    patient.full_name = "Pat Ient"
    patient.role = UserRole.PATIENT
    return patient


def _make_session_summary(
    session_id: uuid.UUID,
    patient_id: uuid.UUID,
) -> SessionSummary:
    now = datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC)
    return SessionSummary(
        id=session_id,
        patient_id=patient_id,
        therapist_id=uuid.uuid4(),
        session_date=now,
        status=SessionStatus.READY,
        session_type=SessionType.UPLOAD,
        recording_duration_seconds=1800,
        created_at=now,
    )


def _make_recap_read(session_id: uuid.UUID) -> SessionRecapRead:
    """Recap with all fields populated — including the ones a patient
    must NOT receive — so tests can assert they are dropped on the wire.
    """
    now = datetime(2026, 4, 1, 11, 0, 0, tzinfo=UTC)
    return SessionRecapRead(
        id=uuid.uuid4(),
        session_id=session_id,
        brief="Patient reported improved sleep over the past week.",
        key_topics=["sleep hygiene", "workplace stress"],
        emotional_tone="calm, reflective",
        homework_assigned=[
            HomeworkItem(task="Keep a sleep log", notes="Note bedtime and wake time"),
        ],
        follow_ups=["revisit sleep log next session"],
        risk_flags=["mentioned fleeting SI without plan"],
        model_name="claude-opus",
        generated_at=now,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def patient_user() -> MagicMock:
    return _make_patient()


@pytest.fixture
def mock_session_service(patient_user: MagicMock) -> MagicMock:
    service = MagicMock()

    session_id = uuid.uuid4()
    summary = _make_session_summary(session_id=session_id, patient_id=patient_user.id)

    service.get_sessions_for_patient = AsyncMock(return_value=[summary])

    # session_repo mimics what the endpoint touches directly. Default: a
    # session that belongs to the authenticated patient. Individual
    # tests override this to simulate cross-patient or missing-session
    # cases.
    db_session = MagicMock()
    db_session.id = session_id
    db_session.patient_id = patient_user.id
    db_session.session_date = summary.session_date

    session_repo = MagicMock()
    session_repo.get_by_id = AsyncMock(return_value=db_session)
    service.session_repo = session_repo
    service._summary = summary
    service._db_session = db_session
    return service


@pytest.fixture
def mock_summarization_service() -> MagicMock:
    service = MagicMock()
    service.get_recap = AsyncMock()
    return service


@pytest.fixture
def app(
    patient_user: MagicMock,
    mock_session_service: MagicMock,
    mock_summarization_service: MagicMock,
) -> FastAPI:
    test_app = FastAPI()
    setup_exception_handlers(test_app)
    test_app.include_router(router, prefix="/patient")

    mock_events = MagicMock()
    mock_events.publish = AsyncMock(return_value=None)

    test_app.dependency_overrides[get_current_patient] = lambda: patient_user
    test_app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    test_app.dependency_overrides[get_session_service] = lambda: mock_session_service
    test_app.dependency_overrides[get_summarization_service] = (
        lambda: mock_summarization_service
    )
    test_app.dependency_overrides[get_event_publisher] = lambda: mock_events

    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


class TestPatientMe:
    def test_me_returns_the_authenticated_patient(
        self,
        client: TestClient,
        patient_user: MagicMock,
    ) -> None:
        response = client.get("/patient/me")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(patient_user.id)
        assert body["organization_id"] == str(patient_user.organization_id)
        assert body["email"] == patient_user.email


class TestListOwnSessions:
    def test_list_returns_only_the_authenticated_patients_sessions(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        patient_user: MagicMock,
    ) -> None:
        response = client.get("/patient/sessions")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["patient_id"] == str(patient_user.id)

        # Critical: the service must have been called with the patient
        # id from the token, not one supplied by the client.
        mock_session_service.get_sessions_for_patient.assert_awaited_once_with(
            patient_id=patient_user.id
        )

    def test_list_ignores_a_supplied_patient_id_query(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        patient_user: MagicMock,
    ) -> None:
        """A patient cannot enumerate another patient's data by passing
        ?patient_id=... — the endpoint doesn't even accept that param,
        so it is silently dropped and the authenticated id is used."""
        someone_else = uuid.uuid4()
        response = client.get(f"/patient/sessions?patient_id={someone_else}")

        assert response.status_code == 200
        mock_session_service.get_sessions_for_patient.assert_awaited_once_with(
            patient_id=patient_user.id
        )


class TestGetOwnSessionRecap:
    def test_returns_patient_safe_view_and_strips_clinical_fields(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        mock_summarization_service: MagicMock,
    ) -> None:
        session_id = mock_session_service._summary.id
        mock_summarization_service.get_recap.return_value = _make_recap_read(
            session_id=session_id
        )

        response = client.get(f"/patient/sessions/{session_id}/recap")
        assert response.status_code == 200
        body = response.json()

        # Patient-visible fields are present.
        assert body["session_id"] == str(session_id)
        assert body["brief"].startswith("Patient reported")
        assert body["key_topics"] == ["sleep hygiene", "workplace stress"]
        assert body["homework_assigned"][0]["task"] == "Keep a sleep log"
        assert body["follow_ups"] == ["revisit sleep log next session"]

        # Clinician-only fields are physically absent from the wire
        # shape. Dropping them at the response_model layer is the whole
        # point of the PatientRecapView schema.
        assert "risk_flags" not in body
        assert "therapist_notes" not in body
        assert "emotional_tone" not in body
        assert "transcript" not in body
        assert "model_name" not in body

    def test_returns_403_when_session_belongs_to_another_patient(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        mock_summarization_service: MagicMock,
    ) -> None:
        """The session exists but is owned by a different patient. The
        endpoint must refuse with 403, not 404 (we acknowledge the
        resource exists) and must NOT call the recap service — i.e. the
        patient never even learns the recap's brief."""
        session_id = uuid.uuid4()
        foreign_session = MagicMock()
        foreign_session.id = session_id
        foreign_session.patient_id = uuid.uuid4()  # different patient
        foreign_session.session_date = datetime(2026, 4, 1, tzinfo=UTC)
        mock_session_service.session_repo.get_by_id = AsyncMock(
            return_value=foreign_session
        )

        response = client.get(f"/patient/sessions/{session_id}/recap")
        assert response.status_code == 403
        mock_summarization_service.get_recap.assert_not_awaited()

    def test_returns_404_when_session_does_not_exist(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        mock_summarization_service: MagicMock,
    ) -> None:
        mock_session_service.session_repo.get_by_id = AsyncMock(return_value=None)

        response = client.get(f"/patient/sessions/{uuid.uuid4()}/recap")
        assert response.status_code == 404
        mock_summarization_service.get_recap.assert_not_awaited()

    def test_returns_404_when_recap_has_not_been_generated_yet(
        self,
        client: TestClient,
        mock_session_service: MagicMock,
        mock_summarization_service: MagicMock,
    ) -> None:
        """Session belongs to the patient but no recap has been synthesized
        yet. The summarization service raises NotFoundError, which the
        exception handler translates into a 404."""
        mock_summarization_service.get_recap.side_effect = NotFoundError(
            resource="SessionRecap",
            detail="No recap exists for session",
        )

        session_id = mock_session_service._summary.id
        response = client.get(f"/patient/sessions/{session_id}/recap")
        assert response.status_code == 404
