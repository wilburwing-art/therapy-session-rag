"""Integration tests for Analytics API endpoints with live database."""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.event import AnalyticsEvent, EventCategory
from src.models.db.organization import Organization


@pytest_asyncio.fixture(loop_scope="session")
async def sample_events(
    db_session: AsyncSession, test_org: Organization
) -> list[AnalyticsEvent]:
    """Seed analytics events for testing."""
    events = []
    event_definitions = [
        ("chat.message_sent", EventCategory.USER_ACTION),
        ("chat.message_sent", EventCategory.USER_ACTION),
        ("session.created", EventCategory.SYSTEM),
        ("transcription.completed", EventCategory.SYSTEM),
        ("safety.risk_detected", EventCategory.CLINICAL),
    ]

    for event_name, category in event_definitions:
        event = AnalyticsEvent(
            id=uuid.uuid4(),
            event_name=event_name,
            event_category=category,
            actor_id=None,
            organization_id=test_org.id,
            session_id=None,
            properties={"source": "integration_test"},
            contexts=None,
        )
        db_session.add(event)
        events.append(event)

    await db_session.flush()
    for e in events:
        await db_session.refresh(e)
    return events


@pytest.mark.integration
class TestAnalyticsEndpoints:
    """Integration tests for analytics endpoints."""

    @pytest.mark.asyncio(loop_scope="session")
    async def test_therapist_utilization(self, async_client: AsyncClient) -> None:
        response = await async_client.get("/api/v1/analytics/therapist-utilization")

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_outcomes(self, async_client: AsyncClient) -> None:
        response = await async_client.get("/api/v1/analytics/session-outcomes")

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_patient_engagement(self, async_client: AsyncClient) -> None:
        response = await async_client.get("/api/v1/analytics/patient-engagement")

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_ai_safety_metrics(self, async_client: AsyncClient) -> None:
        response = await async_client.get("/api/v1/analytics/ai-safety-metrics")

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_event_timeline(
        self, async_client: AsyncClient, sample_events: list[AnalyticsEvent]
    ) -> None:
        response = await async_client.get("/api/v1/analytics/events/timeline")

        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "has_more" in data
        assert isinstance(data["events"], list)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_event_timeline_with_filter(
        self, async_client: AsyncClient, sample_events: list[AnalyticsEvent]
    ) -> None:
        response = await async_client.get(
            "/api/v1/analytics/events/timeline",
            params={"event_name": "chat.message_sent"},
        )

        assert response.status_code == 200
        data = response.json()
        for event in data["events"]:
            assert event["event_name"] == "chat.message_sent"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_event_timeline_pagination(
        self, async_client: AsyncClient, sample_events: list[AnalyticsEvent]
    ) -> None:
        response = await async_client.get(
            "/api/v1/analytics/events/timeline",
            params={"limit": 2},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) <= 2

    @pytest.mark.asyncio(loop_scope="session")
    async def test_event_aggregates(
        self, async_client: AsyncClient, sample_events: list[AnalyticsEvent]
    ) -> None:
        response = await async_client.get(
            "/api/v1/analytics/events/aggregate",
            params={"period": "day"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "aggregates" in data
        assert data["period_type"] == "day"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_event_aggregates_invalid_period(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get(
            "/api/v1/analytics/events/aggregate",
            params={"period": "century"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio(loop_scope="session")
    async def test_date_range_filtering(self, async_client: AsyncClient) -> None:
        response = await async_client.get(
            "/api/v1/analytics/therapist-utilization",
            params={
                "from_date": "2026-01-01T00:00:00",
                "to_date": "2026-12-31T23:59:59",
            },
        )

        assert response.status_code == 200
