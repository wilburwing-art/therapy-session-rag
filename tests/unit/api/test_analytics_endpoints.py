"""Unit tests for Analytics API endpoints."""

import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.dependencies import get_api_key_auth, get_event_publisher
from src.api.v1.endpoints.analytics import get_analytics_service, router
from src.core.database import get_db_session
from src.models.domain.analytics import (
    AISafetyMetrics,
    EventAggregateItem,
    EventAggregateResponse,
    EventTimelineItem,
    EventTimelineResponse,
    PatientEngagementTrend,
    SessionOutcomeSummary,
    TherapistUtilization,
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
def mock_analytics_service() -> MagicMock:
    """Create a mock analytics service."""
    return MagicMock()


@pytest.fixture
def app(mock_auth_context: MagicMock, mock_analytics_service: MagicMock) -> FastAPI:
    """Create test app with mocked dependencies."""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/analytics")

    mock_events = MagicMock()
    mock_events.publish = AsyncMock(return_value=None)

    test_app.dependency_overrides[get_api_key_auth] = lambda: mock_auth_context
    test_app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    test_app.dependency_overrides[get_analytics_service] = lambda: mock_analytics_service
    test_app.dependency_overrides[get_event_publisher] = lambda: mock_events

    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


def _make_utilization(org_id: uuid.UUID) -> TherapistUtilization:
    return TherapistUtilization(
        therapist_id=uuid.uuid4(),
        organization_id=org_id,
        therapist_email="doc@example.com",
        period_start=date(2026, 1, 27),
        period_end=date(2026, 2, 3),
        sessions_in_period=8,
        patients_in_period=5,
        total_hours=6.5,
        avg_duration_seconds=2925.0,
        success_rate_pct=87.5,
    )


def _make_outcome(org_id: uuid.UUID) -> SessionOutcomeSummary:
    return SessionOutcomeSummary(
        organization_id=org_id,
        period_start=date(2026, 1, 27),
        period_end=date(2026, 2, 3),
        total_sessions=10,
        sessions_ready=8,
        sessions_failed=1,
        success_rate_pct=80.0,
        failure_rate_pct=10.0,
        avg_recording_duration_seconds=3000.0,
        avg_word_count=5000.0,
        avg_seconds_to_ready=120.0,
        p95_seconds_to_ready=300.0,
    )


def _make_engagement(org_id: uuid.UUID) -> PatientEngagementTrend:
    return PatientEngagementTrend(
        organization_id=org_id,
        period_start=date(2026, 1, 27),
        period_end=date(2026, 2, 3),
        active_patients=15,
        total_patients=50,
        patient_activation_rate_pct=30.0,
        total_sessions=20,
        total_messages=45,
        avg_sessions_per_patient=1.33,
        avg_messages_per_patient=3.0,
        net_consent_change=2,
    )


def _make_safety(org_id: uuid.UUID) -> AISafetyMetrics:
    return AISafetyMetrics(
        organization_id=org_id,
        period_start=date(2026, 1, 27),
        period_end=date(2026, 2, 3),
        total_messages=100,
        avg_sources_per_response=3.2,
        grounded_responses=85,
        zero_source_responses=15,
        grounding_rate_pct=85.0,
        risk_detections=2,
        guardrail_triggers=1,
        escalations=0,
    )


class TestTherapistUtilizationEndpoint:
    """Tests for GET /analytics/therapist-utilization."""

    def test_get_utilization(
        self,
        client: TestClient,
        mock_analytics_service: MagicMock,
        mock_auth_context: MagicMock,
    ) -> None:
        mock_data = [_make_utilization(mock_auth_context.organization_id)]
        mock_analytics_service.get_therapist_utilization = AsyncMock(return_value=mock_data)

        response = client.get("/analytics/therapist-utilization")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["sessions_in_period"] == 8
        assert data[0]["success_rate_pct"] == 87.5
        mock_analytics_service.get_therapist_utilization.assert_called_once()

    def test_get_utilization_empty(
        self,
        client: TestClient,
        mock_analytics_service: MagicMock,
    ) -> None:
        mock_analytics_service.get_therapist_utilization = AsyncMock(return_value=[])

        response = client.get("/analytics/therapist-utilization")

        assert response.status_code == 200
        assert response.json() == []

    def test_get_utilization_with_date_range(
        self,
        client: TestClient,
        mock_analytics_service: MagicMock,
    ) -> None:
        mock_analytics_service.get_therapist_utilization = AsyncMock(return_value=[])

        response = client.get(
            "/analytics/therapist-utilization",
            params={
                "from_date": "2026-01-01T00:00:00",
                "to_date": "2026-02-01T00:00:00",
            },
        )

        assert response.status_code == 200
        call_kwargs = mock_analytics_service.get_therapist_utilization.call_args.kwargs
        assert call_kwargs["from_date"] is not None
        assert call_kwargs["to_date"] is not None


class TestSessionOutcomesEndpoint:
    """Tests for GET /analytics/session-outcomes."""

    def test_get_outcomes(
        self,
        client: TestClient,
        mock_analytics_service: MagicMock,
        mock_auth_context: MagicMock,
    ) -> None:
        mock_data = [_make_outcome(mock_auth_context.organization_id)]
        mock_analytics_service.get_session_outcomes = AsyncMock(return_value=mock_data)

        response = client.get("/analytics/session-outcomes")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["total_sessions"] == 10
        assert data[0]["success_rate_pct"] == 80.0

    def test_get_outcomes_empty(
        self,
        client: TestClient,
        mock_analytics_service: MagicMock,
    ) -> None:
        mock_analytics_service.get_session_outcomes = AsyncMock(return_value=[])

        response = client.get("/analytics/session-outcomes")

        assert response.status_code == 200
        assert response.json() == []


class TestPatientEngagementEndpoint:
    """Tests for GET /analytics/patient-engagement."""

    def test_get_engagement(
        self,
        client: TestClient,
        mock_analytics_service: MagicMock,
        mock_auth_context: MagicMock,
    ) -> None:
        mock_data = [_make_engagement(mock_auth_context.organization_id)]
        mock_analytics_service.get_patient_engagement = AsyncMock(return_value=mock_data)

        response = client.get("/analytics/patient-engagement")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["active_patients"] == 15
        assert data[0]["patient_activation_rate_pct"] == 30.0

    def test_get_engagement_with_date_filter(
        self,
        client: TestClient,
        mock_analytics_service: MagicMock,
    ) -> None:
        mock_analytics_service.get_patient_engagement = AsyncMock(return_value=[])

        response = client.get(
            "/analytics/patient-engagement",
            params={"from_date": "2026-01-01T00:00:00"},
        )

        assert response.status_code == 200


class TestAISafetyMetricsEndpoint:
    """Tests for GET /analytics/ai-safety-metrics."""

    def test_get_safety_metrics(
        self,
        client: TestClient,
        mock_analytics_service: MagicMock,
        mock_auth_context: MagicMock,
    ) -> None:
        mock_data = [_make_safety(mock_auth_context.organization_id)]
        mock_analytics_service.get_ai_safety_metrics = AsyncMock(return_value=mock_data)

        response = client.get("/analytics/ai-safety-metrics")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["grounding_rate_pct"] == 85.0
        assert data[0]["risk_detections"] == 2

    def test_get_safety_metrics_empty(
        self,
        client: TestClient,
        mock_analytics_service: MagicMock,
    ) -> None:
        mock_analytics_service.get_ai_safety_metrics = AsyncMock(return_value=[])

        response = client.get("/analytics/ai-safety-metrics")

        assert response.status_code == 200
        assert response.json() == []


class TestEventTimelineEndpoint:
    """Tests for GET /analytics/events/timeline."""

    def test_get_timeline(
        self,
        client: TestClient,
        mock_analytics_service: MagicMock,
    ) -> None:
        mock_response = EventTimelineResponse(
            events=[
                EventTimelineItem(
                    id=uuid.uuid4(),
                    event_name="chat.message_sent",
                    event_category="user_action",
                    session_id=None,
                    event_timestamp=datetime(2026, 2, 5, 12, 0, 0),
                    properties={"top_k": 5},
                )
            ],
            next_cursor=None,
            has_more=False,
        )
        mock_analytics_service.get_event_timeline = AsyncMock(return_value=mock_response)

        response = client.get("/analytics/events/timeline")

        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == 1
        assert data["has_more"] is False
        assert data["events"][0]["event_name"] == "chat.message_sent"

    def test_get_timeline_with_pagination(
        self,
        client: TestClient,
        mock_analytics_service: MagicMock,
    ) -> None:
        mock_response = EventTimelineResponse(
            events=[
                EventTimelineItem(
                    id=uuid.uuid4(),
                    event_name="session.created",
                    event_category="system",
                    session_id=uuid.uuid4(),
                    event_timestamp=datetime(2026, 2, 5, 10, 0, 0),
                    properties=None,
                )
            ],
            next_cursor="2026-02-05T10:00:00",
            has_more=True,
        )
        mock_analytics_service.get_event_timeline = AsyncMock(return_value=mock_response)

        response = client.get(
            "/analytics/events/timeline",
            params={"limit": 1},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_more"] is True
        assert data["next_cursor"] is not None

    def test_get_timeline_with_filters(
        self,
        client: TestClient,
        mock_analytics_service: MagicMock,
    ) -> None:
        mock_response = EventTimelineResponse(events=[], has_more=False)
        mock_analytics_service.get_event_timeline = AsyncMock(return_value=mock_response)

        response = client.get(
            "/analytics/events/timeline",
            params={"event_name": "chat.message_sent", "event_category": "user_action"},
        )

        assert response.status_code == 200
        call_kwargs = mock_analytics_service.get_event_timeline.call_args.kwargs
        assert call_kwargs["event_name"] == "chat.message_sent"


class TestEventAggregateEndpoint:
    """Tests for GET /analytics/events/aggregate."""

    def test_get_aggregates(
        self,
        client: TestClient,
        mock_analytics_service: MagicMock,
    ) -> None:
        mock_response = EventAggregateResponse(
            aggregates=[
                EventAggregateItem(
                    event_name="chat.message_sent",
                    period="2026-02-05",
                    count=42,
                ),
                EventAggregateItem(
                    event_name="session.created",
                    period="2026-02-05",
                    count=10,
                ),
            ],
            period_type="day",
        )
        mock_analytics_service.get_event_aggregates = AsyncMock(return_value=mock_response)

        response = client.get("/analytics/events/aggregate")

        assert response.status_code == 200
        data = response.json()
        assert len(data["aggregates"]) == 2
        assert data["period_type"] == "day"

    def test_get_aggregates_with_period(
        self,
        client: TestClient,
        mock_analytics_service: MagicMock,
    ) -> None:
        mock_response = EventAggregateResponse(aggregates=[], period_type="week")
        mock_analytics_service.get_event_aggregates = AsyncMock(return_value=mock_response)

        response = client.get(
            "/analytics/events/aggregate",
            params={"period": "week"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["period_type"] == "week"

    def test_get_aggregates_invalid_period(
        self,
        client: TestClient,
    ) -> None:
        response = client.get(
            "/analytics/events/aggregate",
            params={"period": "invalid"},
        )

        assert response.status_code == 422

    def test_get_aggregates_with_event_filter(
        self,
        client: TestClient,
        mock_analytics_service: MagicMock,
    ) -> None:
        mock_response = EventAggregateResponse(aggregates=[], period_type="day")
        mock_analytics_service.get_event_aggregates = AsyncMock(return_value=mock_response)

        response = client.get(
            "/analytics/events/aggregate",
            params={"event_name": "chat.message_sent", "period": "hour"},
        )

        assert response.status_code == 200
        call_kwargs = mock_analytics_service.get_event_aggregates.call_args.kwargs
        assert call_kwargs["event_name"] == "chat.message_sent"
        assert call_kwargs["period"] == "hour"
