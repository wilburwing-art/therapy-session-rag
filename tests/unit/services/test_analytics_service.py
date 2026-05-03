"""Unit tests for AnalyticsService."""

import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.db.assessment import AssessmentInstrument
from src.models.db.event import AnalyticsEvent, EventCategory
from src.models.db.session import SessionStatus
from src.services.analytics_service import AnalyticsService


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async session."""
    return AsyncMock()


@pytest.fixture
def service(mock_session: AsyncMock) -> AnalyticsService:
    """Create an AnalyticsService with mocked session."""
    return AnalyticsService(mock_session)


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_utilization_row(
    therapist_id: uuid.UUID,
    org_id: uuid.UUID,
) -> MagicMock:
    """Create a mock Row object matching therapist_utilization query."""
    row = MagicMock()
    row.therapist_id = therapist_id
    row.organization_id = org_id
    row.therapist_email = "therapist@example.com"
    row.period_start = date(2026, 1, 27)
    row.period_end = date(2026, 2, 3)
    row.sessions_in_period = 8
    row.patients_in_period = 5
    row.total_hours = 6.5
    row.avg_duration_seconds = 2925.0
    row.success_rate_pct = 87.5
    return row


def _make_outcome_row() -> MagicMock:
    """Create a mock Row object matching session_outcomes query."""
    row = MagicMock()
    row.period_start = date(2026, 1, 27)
    row.period_end = date(2026, 2, 3)
    row.total_sessions = 10
    row.sessions_ready = 8
    row.sessions_failed = 1
    row.avg_recording_duration_seconds = 3000.0
    row.avg_word_count = 5000.0
    row.avg_seconds_to_ready = 120.0
    return row


def _make_engagement_row() -> MagicMock:
    """Create a mock Row object matching patient_engagement query."""
    row = MagicMock()
    row.period_start = date(2026, 1, 27)
    row.period_end = date(2026, 2, 3)
    row.active_patients = 15
    row.total_patients = 50
    row.total_messages = 45
    return row


def _make_safety_row() -> MagicMock:
    """Create a mock Row object matching ai_safety_metrics query."""
    row = MagicMock()
    row.period_start = date(2026, 1, 27)
    row.period_end = date(2026, 2, 3)
    row.total_messages = 100
    row.avg_sources_per_response = 3.2
    row.grounded_responses = 85
    row.zero_source_responses = 15
    row.risk_detections = 2
    row.guardrail_triggers = 1
    row.escalations = 0
    return row


class TestGetTherapistUtilization:
    """Tests for AnalyticsService.get_therapist_utilization()."""

    async def test_returns_utilization_data(
        self, service: AnalyticsService, org_id: uuid.UUID
    ) -> None:
        therapist_id = uuid.uuid4()
        mock_row = _make_utilization_row(therapist_id, org_id)

        with patch.object(
            service._analytics_repo,
            "therapist_utilization",
            new_callable=AsyncMock,
            return_value=[mock_row],
        ):
            result = await service.get_therapist_utilization(org_id)

        assert len(result) == 1
        assert result[0].therapist_id == therapist_id
        assert result[0].sessions_in_period == 8
        assert result[0].total_hours == 6.5

    async def test_returns_empty_list(self, service: AnalyticsService, org_id: uuid.UUID) -> None:
        with patch.object(
            service._analytics_repo,
            "therapist_utilization",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await service.get_therapist_utilization(org_id)

        assert result == []


class TestGetSessionOutcomes:
    """Tests for AnalyticsService.get_session_outcomes()."""

    async def test_returns_outcomes(self, service: AnalyticsService, org_id: uuid.UUID) -> None:
        mock_row = _make_outcome_row()

        with patch.object(
            service._analytics_repo,
            "session_outcomes",
            new_callable=AsyncMock,
            return_value=[mock_row],
        ):
            result = await service.get_session_outcomes(org_id)

        assert len(result) == 1
        assert result[0].total_sessions == 10
        assert result[0].success_rate_pct == 80.0
        assert result[0].failure_rate_pct == 10.0

    async def test_zero_sessions_division(
        self, service: AnalyticsService, org_id: uuid.UUID
    ) -> None:
        mock_row = _make_outcome_row()
        mock_row.total_sessions = 0
        mock_row.sessions_ready = 0
        mock_row.sessions_failed = 0

        with patch.object(
            service._analytics_repo,
            "session_outcomes",
            new_callable=AsyncMock,
            return_value=[mock_row],
        ):
            result = await service.get_session_outcomes(org_id)

        assert result[0].success_rate_pct == 0
        assert result[0].failure_rate_pct == 0


class TestGetPatientEngagement:
    """Tests for AnalyticsService.get_patient_engagement()."""

    async def test_returns_engagement(self, service: AnalyticsService, org_id: uuid.UUID) -> None:
        mock_row = _make_engagement_row()

        with patch.object(
            service._analytics_repo,
            "patient_engagement",
            new_callable=AsyncMock,
            return_value=[mock_row],
        ):
            result = await service.get_patient_engagement(org_id)

        assert len(result) == 1
        assert result[0].active_patients == 15
        assert result[0].total_patients == 50
        assert result[0].patient_activation_rate_pct == 30.0

    async def test_zero_patients(self, service: AnalyticsService, org_id: uuid.UUID) -> None:
        mock_row = _make_engagement_row()
        mock_row.total_patients = 0
        mock_row.active_patients = 0
        mock_row.total_messages = 0

        with patch.object(
            service._analytics_repo,
            "patient_engagement",
            new_callable=AsyncMock,
            return_value=[mock_row],
        ):
            result = await service.get_patient_engagement(org_id)

        assert result[0].patient_activation_rate_pct == 0
        assert result[0].avg_messages_per_patient == 0


class TestGetAISafetyMetrics:
    """Tests for AnalyticsService.get_ai_safety_metrics()."""

    async def test_returns_safety_metrics(
        self, service: AnalyticsService, org_id: uuid.UUID
    ) -> None:
        mock_row = _make_safety_row()

        with patch.object(
            service._analytics_repo,
            "ai_safety_metrics",
            new_callable=AsyncMock,
            return_value=[mock_row],
        ):
            result = await service.get_ai_safety_metrics(org_id)

        assert len(result) == 1
        assert result[0].grounding_rate_pct == 85.0
        assert result[0].risk_detections == 2


class TestGetEventTimeline:
    """Tests for AnalyticsService.get_event_timeline()."""

    async def test_returns_timeline(self, service: AnalyticsService, org_id: uuid.UUID) -> None:
        now = datetime.now(UTC)
        mock_event = MagicMock(spec=AnalyticsEvent)
        mock_event.id = uuid.uuid4()
        mock_event.event_name = "chat.message_sent"
        mock_event.event_category = EventCategory.USER_ACTION
        mock_event.session_id = None
        mock_event.event_timestamp = now
        mock_event.properties = {"top_k": 5}

        with patch.object(
            service._analytics_repo,
            "event_timeline",
            new_callable=AsyncMock,
            return_value=[mock_event],
        ):
            result = await service.get_event_timeline(org_id, limit=50)

        assert len(result.events) == 1
        assert result.has_more is False
        assert result.next_cursor is None

    async def test_timeline_pagination(self, service: AnalyticsService, org_id: uuid.UUID) -> None:
        now = datetime.now(UTC)
        events = []
        for _ in range(3):
            e = MagicMock(spec=AnalyticsEvent)
            e.id = uuid.uuid4()
            e.event_name = "test"
            e.event_category = EventCategory.SYSTEM
            e.session_id = None
            e.event_timestamp = now
            e.properties = None
            events.append(e)

        with patch.object(
            service._analytics_repo,
            "event_timeline",
            new_callable=AsyncMock,
            return_value=events,
        ):
            result = await service.get_event_timeline(org_id, limit=2)

        assert len(result.events) == 2
        assert result.has_more is True
        assert result.next_cursor is not None


class TestGetEventAggregates:
    """Tests for AnalyticsService.get_event_aggregates()."""

    async def test_returns_aggregates(self, service: AnalyticsService, org_id: uuid.UUID) -> None:
        with patch.object(
            service._event_repo,
            "aggregate_by_period",
            new_callable=AsyncMock,
            return_value=[
                ("chat.message_sent", "2026-02-05", 42),
                ("session.created", "2026-02-05", 10),
            ],
        ):
            result = await service.get_event_aggregates(org_id, period="day")

        assert len(result.aggregates) == 2
        assert result.period_type == "day"
        assert result.aggregates[0].count == 42

    async def test_returns_empty_aggregates(
        self, service: AnalyticsService, org_id: uuid.UUID
    ) -> None:
        with patch.object(
            service._event_repo,
            "aggregate_by_period",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await service.get_event_aggregates(org_id, period="week")

        assert result.aggregates == []
        assert result.period_type == "week"


# ----------------------------------------------------------------------
# Therapist dashboard analytics
# ----------------------------------------------------------------------


def _execute_result(rows: list[MagicMock]) -> MagicMock:
    """Build a mock object that mimics session.execute()'s return."""
    res = MagicMock()
    res.all.return_value = rows
    res.one_or_none.return_value = rows[0] if rows else None
    return res


def _current_monday() -> date:
    today = datetime.now(UTC).date()
    return today - timedelta(days=today.weekday())


class TestSessionsByWeek:
    """Tests for AnalyticsService.sessions_by_week()."""

    async def test_zero_fills_twelve_weeks(
        self, service: AnalyticsService, org_id: uuid.UUID
    ) -> None:
        service._db.execute = AsyncMock(return_value=_execute_result([]))

        points = await service.sessions_by_week(org_id, weeks_back=12)

        assert len(points) == 12
        assert all(p.count == 0 for p in points)
        # Ascending order by week_start.
        assert points == sorted(points, key=lambda p: p.week_start)
        # Last bucket is the current Monday.
        assert points[-1].week_start == _current_monday()

    async def test_maps_rows_to_buckets(self, service: AnalyticsService, org_id: uuid.UUID) -> None:
        monday = _current_monday()
        prev = monday - timedelta(weeks=1)
        row_now = MagicMock()
        row_now.week_start = monday
        row_now.session_count = 7
        row_prev = MagicMock()
        row_prev.week_start = prev
        row_prev.session_count = 3

        service._db.execute = AsyncMock(return_value=_execute_result([row_now, row_prev]))

        points = await service.sessions_by_week(org_id, weeks_back=4)

        assert len(points) == 4
        by_start = {p.week_start: p.count for p in points}
        assert by_start[monday] == 7
        assert by_start[prev] == 3
        # Any week not returned by the query is zero-filled.
        assert sum(p.count for p in points) == 10

    async def test_respects_weeks_back_argument(
        self, service: AnalyticsService, org_id: uuid.UUID
    ) -> None:
        service._db.execute = AsyncMock(return_value=_execute_result([]))

        points = await service.sessions_by_week(org_id, weeks_back=4)

        assert len(points) == 4


class TestSessionsByStatus:
    """Tests for AnalyticsService.sessions_by_status()."""

    async def test_aggregates_status_counts(
        self, service: AnalyticsService, org_id: uuid.UUID
    ) -> None:
        ready_row = MagicMock()
        ready_row.status = SessionStatus.READY
        ready_row.session_count = 12
        failed_row = MagicMock()
        failed_row.status = SessionStatus.FAILED
        failed_row.session_count = 2

        service._db.execute = AsyncMock(return_value=_execute_result([ready_row, failed_row]))

        counts = await service.sessions_by_status(org_id)

        assert counts == {"ready": 12, "failed": 2}

    async def test_empty_result_returns_empty_dict(
        self, service: AnalyticsService, org_id: uuid.UUID
    ) -> None:
        service._db.execute = AsyncMock(return_value=_execute_result([]))

        counts = await service.sessions_by_status(org_id)

        assert counts == {}


class TestActivePatients:
    """Tests for AnalyticsService.active_patients()."""

    async def test_returns_count(self, service: AnalyticsService, org_id: uuid.UUID) -> None:
        row = MagicMock()
        row.active_patients = 7
        service._db.execute = AsyncMock(return_value=_execute_result([row]))

        count = await service.active_patients(org_id, days=30)

        assert count == 7

    async def test_returns_zero_when_null(
        self, service: AnalyticsService, org_id: uuid.UUID
    ) -> None:
        row = MagicMock()
        row.active_patients = None
        service._db.execute = AsyncMock(return_value=_execute_result([row]))

        count = await service.active_patients(org_id, days=30)

        assert count == 0


class TestChatActivityByDay:
    """Tests for AnalyticsService.chat_activity_by_day()."""

    async def test_zero_fills_window(self, service: AnalyticsService, org_id: uuid.UUID) -> None:
        service._db.execute = AsyncMock(return_value=_execute_result([]))

        points = await service.chat_activity_by_day(org_id, days=30)

        assert len(points) == 30
        assert all(p.message_count == 0 for p in points)
        assert points == sorted(points, key=lambda p: p.day)
        today = datetime.now(UTC).date()
        assert points[-1].day == today

    async def test_maps_rows_and_fills_gaps(
        self, service: AnalyticsService, org_id: uuid.UUID
    ) -> None:
        today = datetime.now(UTC).date()
        row_today = MagicMock()
        row_today.day = today
        row_today.message_count = 5

        service._db.execute = AsyncMock(return_value=_execute_result([row_today]))

        points = await service.chat_activity_by_day(org_id, days=7)

        assert len(points) == 7
        by_day = {p.day: p.message_count for p in points}
        assert by_day[today] == 5
        # Everything except today is filled with zeros.
        assert sum(p.message_count for p in points) == 5


class TestAssessmentScoreTrend:
    """Tests for AnalyticsService.assessment_score_trend()."""

    async def test_zero_fills_empty(self, service: AnalyticsService, org_id: uuid.UUID) -> None:
        service._db.execute = AsyncMock(return_value=_execute_result([]))

        points = await service.assessment_score_trend(org_id, AssessmentInstrument.PHQ9, weeks=12)

        assert len(points) == 12
        assert all(p.avg_score is None and p.count == 0 for p in points)

    async def test_maps_avg_score(self, service: AnalyticsService, org_id: uuid.UUID) -> None:
        monday = _current_monday()
        row = MagicMock()
        row.week_start = monday
        row.avg_score = 11.5
        row.assessment_count = 4

        service._db.execute = AsyncMock(return_value=_execute_result([row]))

        points = await service.assessment_score_trend(org_id, AssessmentInstrument.GAD7, weeks=4)

        assert len(points) == 4
        current = [p for p in points if p.week_start == monday][0]
        assert current.avg_score == pytest.approx(11.5)
        assert current.count == 4


class TestResponseWrappers:
    """Tests for the thin wrapper methods used by the endpoints."""

    async def test_sessions_by_status_response_wraps_counts(
        self, service: AnalyticsService, org_id: uuid.UUID
    ) -> None:
        row = MagicMock()
        row.status = SessionStatus.READY
        row.session_count = 3
        service._db.execute = AsyncMock(return_value=_execute_result([row]))

        response = await service.sessions_by_status_response(org_id)

        assert response.counts == {"ready": 3}

    async def test_active_patients_response_includes_window(
        self, service: AnalyticsService, org_id: uuid.UUID
    ) -> None:
        row = MagicMock()
        row.active_patients = 5
        service._db.execute = AsyncMock(return_value=_execute_result([row]))

        response = await service.active_patients_response(org_id, days=7)

        assert response.window_days == 7
        assert response.active_patients == 5

    async def test_assessment_trend_response_includes_instrument(
        self, service: AnalyticsService, org_id: uuid.UUID
    ) -> None:
        service._db.execute = AsyncMock(return_value=_execute_result([]))

        response = await service.assessment_trend_response(
            org_id, AssessmentInstrument.PHQ9, weeks=4
        )

        assert response.instrument == AssessmentInstrument.PHQ9
        assert len(response.points) == 4
