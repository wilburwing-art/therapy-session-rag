"""Unit tests for Patients API endpoints.

Covers the therapist-facing clinical views: themes, conversation review,
assessments. Services are mocked — no Claude, no LLM, no DB required.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.dependencies import get_api_key_auth, get_event_publisher
from src.api.v1.endpoints.patients import (
    get_assessment_service,
    get_conversation_service,
    get_themes_service,
    router,
)
from src.core.database import get_db_session
from src.core.exceptions import NotFoundError, ValidationError, setup_exception_handlers
from src.models.domain.assessment import AssessmentInstrument, AssessmentRead
from src.models.domain.chat import ConversationRead, ConversationSummary
from src.models.domain.patient_themes import (
    CopingStrategy,
    EmotionalPattern,
    PatientThemesRead,
    RecurringTopic,
)


def _make_themes_read(patient_id: uuid.UUID) -> PatientThemesRead:
    now = datetime(2026, 4, 21, 10, 0, 0, tzinfo=UTC)
    return PatientThemesRead(
        id=uuid.uuid4(),
        patient_id=patient_id,
        recurring_topics=[
            RecurringTopic(topic="work-stress", session_count=3, summary="Recurring"),
        ],
        emotional_patterns=[
            EmotionalPattern(pattern="anxiety-spike", evidence="spikes midweek"),
        ],
        coping_strategies=[
            CopingStrategy(strategy="breathing", notes="daily"),
        ],
        progress_indicators=["reports better sleep"],
        ongoing_concerns=["job uncertainty"],
        source_session_count=4,
        model_name="claude-sonnet-4",
        generated_at=now,
        created_at=now,
        updated_at=now,
    )


def _make_assessment_read(
    patient_id: uuid.UUID,
    instrument: AssessmentInstrument = AssessmentInstrument.PHQ9,
    total_score: int = 12,
    severity: str = "moderate",
) -> AssessmentRead:
    now = datetime(2026, 4, 21, 10, 0, 0, tzinfo=UTC)
    # PHQ9 has 9 items, GAD7 has 7.
    n = 9 if instrument == AssessmentInstrument.PHQ9 else 7
    responses = [total_score // n] * n
    return AssessmentRead(
        id=uuid.uuid4(),
        patient_id=patient_id,
        administered_by_user_id=uuid.uuid4(),
        instrument=instrument,
        responses=responses,
        total_score=total_score,
        severity=severity,
        notes=None,
        administered_at=now,
        created_at=now,
    )


def _make_conversation_summary(
    patient_id: uuid.UUID,
    title: str = "First chat",
) -> ConversationSummary:
    return ConversationSummary(
        id=uuid.uuid4(),
        patient_id=patient_id,
        title=title,
        message_count=4,
        created_at=datetime(2026, 4, 20, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 20, 11, 0, 0, tzinfo=UTC),
    )


def _make_conversation_read(
    patient_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> ConversationRead:
    return ConversationRead(
        id=uuid.uuid4(),
        patient_id=patient_id,
        organization_id=organization_id,
        title="Some chat",
        message_count=2,
        messages=[],
        created_at=datetime(2026, 4, 20, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 20, 11, 0, 0, tzinfo=UTC),
    )


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
def mock_themes_service() -> MagicMock:
    svc = MagicMock()
    svc.get_themes = AsyncMock()
    svc.generate_themes = AsyncMock()
    return svc


@pytest.fixture
def mock_conversation_service() -> MagicMock:
    svc = MagicMock()
    svc.list_for_therapist = AsyncMock()
    svc.get_for_therapist = AsyncMock()
    return svc


@pytest.fixture
def mock_assessment_service() -> MagicMock:
    svc = MagicMock()
    svc.record = AsyncMock()
    svc.list_for_patient = AsyncMock()
    return svc


@pytest.fixture
def app(
    mock_auth_context: MagicMock,
    mock_themes_service: MagicMock,
    mock_conversation_service: MagicMock,
    mock_assessment_service: MagicMock,
) -> FastAPI:
    test_app = FastAPI()
    setup_exception_handlers(test_app)
    test_app.include_router(router, prefix="/patients")

    mock_events = MagicMock()
    mock_events.publish = AsyncMock(return_value=None)

    test_app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    test_app.dependency_overrides[get_api_key_auth] = lambda: mock_auth_context
    test_app.dependency_overrides[get_event_publisher] = lambda: mock_events
    test_app.dependency_overrides[get_themes_service] = lambda: mock_themes_service
    test_app.dependency_overrides[get_conversation_service] = lambda: mock_conversation_service
    test_app.dependency_overrides[get_assessment_service] = lambda: mock_assessment_service

    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


class TestGetPatientThemes:
    def test_get_themes_success(
        self,
        client: TestClient,
        mock_themes_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        mock_themes_service.get_themes.return_value = _make_themes_read(patient_id)

        response = client.get(f"/patients/{patient_id}/themes")

        assert response.status_code == 200
        body = response.json()
        assert body["patient_id"] == str(patient_id)
        assert body["source_session_count"] == 4
        assert body["model_name"] == "claude-sonnet-4"
        assert len(body["recurring_topics"]) == 1
        assert body["recurring_topics"][0]["topic"] == "work-stress"
        assert body["progress_indicators"] == ["reports better sleep"]

    def test_get_themes_missing_returns_404(
        self,
        client: TestClient,
        mock_themes_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        mock_themes_service.get_themes.side_effect = NotFoundError(
            resource="PatientThemes",
            detail=f"No themes exist for patient {patient_id}",
        )

        response = client.get(f"/patients/{patient_id}/themes")

        assert response.status_code == 404


class TestGeneratePatientThemes:
    def test_generate_themes_success(
        self,
        client: TestClient,
        mock_themes_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        mock_themes_service.generate_themes.return_value = _make_themes_read(patient_id)

        response = client.post(f"/patients/{patient_id}/themes")

        assert response.status_code == 201
        body = response.json()
        assert body["patient_id"] == str(patient_id)
        assert body["source_session_count"] == 4
        mock_themes_service.generate_themes.assert_awaited_once_with(patient_id)


class TestListPatientConversations:
    def test_list_conversations_success(
        self,
        client: TestClient,
        mock_conversation_service: MagicMock,
        mock_auth_context: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        mock_conversation_service.list_for_therapist.return_value = [
            _make_conversation_summary(patient_id, "Chat 1"),
            _make_conversation_summary(patient_id, "Chat 2"),
        ]

        response = client.get(f"/patients/{patient_id}/conversations")

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 2
        assert body[0]["title"] == "Chat 1"
        assert body[1]["title"] == "Chat 2"
        mock_conversation_service.list_for_therapist.assert_awaited_once_with(
            patient_id=patient_id,
            organization_id=mock_auth_context.organization_id,
            limit=20,
            offset=0,
        )


class TestGetPatientConversation:
    def test_get_conversation_success(
        self,
        client: TestClient,
        mock_conversation_service: MagicMock,
        mock_auth_context: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        convo = _make_conversation_read(patient_id, mock_auth_context.organization_id)
        mock_conversation_service.get_for_therapist.return_value = convo

        response = client.get(
            f"/patients/{patient_id}/conversations/{convo.id}"
        )

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(convo.id)
        assert body["patient_id"] == str(patient_id)
        assert body["organization_id"] == str(mock_auth_context.organization_id)
        assert body["messages"] == []

    def test_get_conversation_wrong_org_returns_404(
        self,
        client: TestClient,
        mock_conversation_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        """Out-of-tenant conversation: service raises NotFoundError → 404."""
        mock_conversation_service.get_for_therapist.side_effect = NotFoundError(
            resource="Conversation"
        )

        bogus_convo_id = uuid.uuid4()
        response = client.get(
            f"/patients/{patient_id}/conversations/{bogus_convo_id}"
        )

        assert response.status_code == 404


class TestRecordPatientAssessment:
    def test_record_phq9_success(
        self,
        client: TestClient,
        mock_assessment_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        mock_assessment_service.record.return_value = _make_assessment_read(
            patient_id,
            instrument=AssessmentInstrument.PHQ9,
            total_score=14,
            severity="moderate",
        )

        response = client.post(
            f"/patients/{patient_id}/assessments",
            json={
                "instrument": "phq9",
                "responses": [2, 2, 1, 2, 1, 2, 1, 2, 1],
                "notes": "session 4 intake",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["instrument"] == "phq9"
        assert body["total_score"] == 14
        assert body["severity"] == "moderate"
        assert body["patient_id"] == str(patient_id)
        mock_assessment_service.record.assert_awaited_once()

    def test_record_assessment_validation_error_returns_422(
        self,
        client: TestClient,
        mock_assessment_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        """Service's ValidationError must propagate to 422."""
        mock_assessment_service.record.side_effect = ValidationError(
            detail="PHQ9 expects 9 responses, got 7"
        )

        response = client.post(
            f"/patients/{patient_id}/assessments",
            json={
                "instrument": "phq9",
                # 7 responses — valid at Pydantic layer (min_length=7) but
                # invalid for PHQ9 which expects 9.
                "responses": [1, 1, 1, 1, 1, 1, 1],
            },
        )

        assert response.status_code == 422
        body = response.json()
        assert "9 responses" in body["detail"]


class TestListPatientAssessments:
    def test_list_assessments_returns_list(
        self,
        client: TestClient,
        mock_assessment_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        mock_assessment_service.list_for_patient.return_value = [
            _make_assessment_read(
                patient_id,
                instrument=AssessmentInstrument.PHQ9,
                total_score=15,
                severity="moderately_severe",
            ),
            _make_assessment_read(
                patient_id,
                instrument=AssessmentInstrument.GAD7,
                total_score=7,
                severity="mild",
            ),
        ]

        response = client.get(f"/patients/{patient_id}/assessments")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        instruments = {item["instrument"] for item in body}
        assert instruments == {"phq9", "gad7"}
        mock_assessment_service.list_for_patient.assert_awaited_once()
        _, kwargs = mock_assessment_service.list_for_patient.call_args
        assert kwargs["patient_id"] == patient_id
        assert kwargs["limit"] == 50

    def test_list_assessments_with_instrument_filter(
        self,
        client: TestClient,
        mock_assessment_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        mock_assessment_service.list_for_patient.return_value = [
            _make_assessment_read(
                patient_id,
                instrument=AssessmentInstrument.GAD7,
                total_score=5,
                severity="mild",
            ),
        ]

        response = client.get(
            f"/patients/{patient_id}/assessments",
            params={"instrument": "gad7"},
        )

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["instrument"] == "gad7"
        _, kwargs = mock_assessment_service.list_for_patient.call_args
        assert kwargs["instrument"] == AssessmentInstrument.GAD7
