"""Analytics service for dashboard and reporting queries."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Date, Integer, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.assessment import Assessment, AssessmentInstrument
from src.models.db.conversation import Conversation, ConversationMessage
from src.models.db.event import EventCategory
from src.models.db.session import Session as SessionModel
from src.models.db.user import User
from src.models.domain.analytics import (
    ActivePatientsResponse,
    AISafetyMetrics,
    AssessmentTrendPoint,
    AssessmentTrendResponse,
    ChatActivityPoint,
    EventAggregateItem,
    EventAggregateResponse,
    EventTimelineItem,
    EventTimelineResponse,
    PatientEngagementTrend,
    SessionOutcomeSummary,
    SessionsByStatusResponse,
    SessionsByWeekPoint,
    TherapistUtilization,
)
from src.repositories.analytics_repo import AnalyticsRepository
from src.repositories.event_repo import EventRepository


class AnalyticsService:
    """Service layer for analytics queries."""

    def __init__(self, db_session: AsyncSession) -> None:
        self._db = db_session
        self._analytics_repo = AnalyticsRepository(db_session)
        self._event_repo = EventRepository(db_session)

    async def get_therapist_utilization(
        self,
        organization_id: uuid.UUID,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[TherapistUtilization]:
        """Get weekly therapist utilization metrics."""
        rows = await self._analytics_repo.therapist_utilization(organization_id, from_date, to_date)
        return [
            TherapistUtilization(
                therapist_id=row.therapist_id,
                organization_id=row.organization_id,
                therapist_email=row.therapist_email,
                period_start=row.period_start,
                period_end=row.period_end,
                sessions_in_period=row.sessions_in_period,
                patients_in_period=row.patients_in_period,
                total_hours=float(row.total_hours),
                avg_duration_seconds=(
                    float(row.avg_duration_seconds) if row.avg_duration_seconds else None
                ),
                success_rate_pct=float(row.success_rate_pct),
            )
            for row in rows
        ]

    async def get_session_outcomes(
        self,
        organization_id: uuid.UUID,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[SessionOutcomeSummary]:
        """Get weekly session processing outcomes."""
        rows = await self._analytics_repo.session_outcomes(organization_id, from_date, to_date)
        results: list[SessionOutcomeSummary] = []
        for row in rows:
            total = row.total_sessions
            ready = row.sessions_ready
            failed = row.sessions_failed
            results.append(
                SessionOutcomeSummary(
                    organization_id=organization_id,
                    period_start=row.period_start,
                    period_end=row.period_end,
                    total_sessions=total,
                    sessions_ready=ready,
                    sessions_failed=failed,
                    success_rate_pct=round(ready / total * 100, 2) if total > 0 else 0,
                    failure_rate_pct=round(failed / total * 100, 2) if total > 0 else 0,
                    avg_recording_duration_seconds=(
                        float(row.avg_recording_duration_seconds)
                        if row.avg_recording_duration_seconds
                        else None
                    ),
                    avg_word_count=(float(row.avg_word_count) if row.avg_word_count else None),
                    avg_seconds_to_ready=(
                        float(row.avg_seconds_to_ready) if row.avg_seconds_to_ready else None
                    ),
                    p95_seconds_to_ready=None,  # Requires percentile query not in base
                )
            )
        return results

    async def get_patient_engagement(
        self,
        organization_id: uuid.UUID,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[PatientEngagementTrend]:
        """Get weekly patient engagement trends."""
        rows = await self._analytics_repo.patient_engagement(organization_id, from_date, to_date)
        results: list[PatientEngagementTrend] = []
        for row in rows:
            active = row.active_patients
            total = row.total_patients or 0
            messages = row.total_messages
            results.append(
                PatientEngagementTrend(
                    organization_id=organization_id,
                    period_start=row.period_start,
                    period_end=row.period_end,
                    active_patients=active,
                    total_patients=total,
                    patient_activation_rate_pct=(
                        round(active / total * 100, 2) if total > 0 else 0
                    ),
                    total_sessions=0,  # Session count from separate query
                    total_messages=messages,
                    avg_sessions_per_patient=0,
                    avg_messages_per_patient=(round(messages / active, 2) if active > 0 else 0),
                    net_consent_change=0,
                )
            )
        return results

    async def get_ai_safety_metrics(
        self,
        organization_id: uuid.UUID,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[AISafetyMetrics]:
        """Get weekly AI safety and RAG quality metrics."""
        rows = await self._analytics_repo.ai_safety_metrics(organization_id, from_date, to_date)
        results: list[AISafetyMetrics] = []
        for row in rows:
            total = row.total_messages
            grounded = row.grounded_responses
            results.append(
                AISafetyMetrics(
                    organization_id=organization_id,
                    period_start=row.period_start,
                    period_end=row.period_end,
                    total_messages=total,
                    avg_sources_per_response=(
                        float(row.avg_sources_per_response)
                        if row.avg_sources_per_response
                        else None
                    ),
                    grounded_responses=grounded,
                    zero_source_responses=row.zero_source_responses,
                    grounding_rate_pct=(round(grounded / total * 100, 2) if total > 0 else 0),
                    risk_detections=row.risk_detections,
                    guardrail_triggers=row.guardrail_triggers,
                    escalations=row.escalations,
                )
            )
        return results

    async def get_event_timeline(
        self,
        organization_id: uuid.UUID,
        cursor: datetime | None = None,
        limit: int = 50,
        event_name: str | None = None,
        event_category: EventCategory | None = None,
    ) -> EventTimelineResponse:
        """Get cursor-paginated event timeline."""
        events = await self._analytics_repo.event_timeline(
            organization_id=organization_id,
            cursor=cursor,
            limit=limit,
            event_name=event_name,
            event_category=event_category,
        )

        has_more = len(events) > limit
        page_events = events[:limit]

        items = [
            EventTimelineItem(
                id=e.id,
                event_name=e.event_name,
                event_category=e.event_category.value,
                session_id=e.session_id,
                event_timestamp=e.event_timestamp,
                properties=e.properties,
            )
            for e in page_events
        ]

        next_cursor: str | None = None
        if has_more and page_events:
            next_cursor = page_events[-1].event_timestamp.isoformat()

        return EventTimelineResponse(
            events=items,
            next_cursor=next_cursor,
            has_more=has_more,
        )

    async def get_event_aggregates(
        self,
        organization_id: uuid.UUID,
        period: str = "day",
        event_name: str | None = None,
        event_category: EventCategory | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> EventAggregateResponse:
        """Get event counts aggregated by time period."""
        rows = await self._event_repo.aggregate_by_period(
            organization_id=organization_id,
            event_name=event_name,
            event_category=event_category,
            period=period,
            from_timestamp=from_date,
            to_timestamp=to_date,
        )

        aggregates = [
            EventAggregateItem(
                event_name=name,
                period=period_label,
                count=count,
            )
            for name, period_label, count in rows
        ]

        return EventAggregateResponse(
            aggregates=aggregates,
            period_type=period,
        )

    # ------------------------------------------------------------------
    # Therapist dashboard analytics
    # ------------------------------------------------------------------

    async def sessions_by_week(
        self,
        organization_id: uuid.UUID,
        weeks_back: int = 12,
        patient_id: uuid.UUID | None = None,
    ) -> list[SessionsByWeekPoint]:
        """Return session counts per ISO week for the last ``weeks_back`` weeks.

        Missing weeks are zero-filled so the resulting list always has
        ``weeks_back`` entries in ascending chronological order.
        """
        today = datetime.now(UTC).date()
        # Monday of the current week.
        current_week_start = today - timedelta(days=today.weekday())
        earliest_week_start = current_week_start - timedelta(weeks=weeks_back - 1)
        window_start = datetime.combine(earliest_week_start, datetime.min.time(), tzinfo=UTC)

        period_start = func.date_trunc("week", SessionModel.session_date)
        conditions: list[Any] = [
            User.organization_id == organization_id,
            SessionModel.session_date >= window_start,
        ]
        if patient_id is not None:
            conditions.append(SessionModel.patient_id == patient_id)

        stmt = (
            select(
                cast(period_start, Date).label("week_start"),
                func.count(SessionModel.id).label("session_count"),
            )
            .select_from(SessionModel)
            .join(User, SessionModel.patient_id == User.id)
            .where(and_(*conditions))
            .group_by(period_start)
        )

        result = await self._db.execute(stmt)
        rows = result.all()
        by_week: dict[date, int] = {row.week_start: int(row.session_count) for row in rows}

        points: list[SessionsByWeekPoint] = []
        for offset in range(weeks_back):
            week_start = earliest_week_start + timedelta(weeks=offset)
            points.append(
                SessionsByWeekPoint(week_start=week_start, count=by_week.get(week_start, 0))
            )
        return points

    async def sessions_by_status(
        self,
        organization_id: uuid.UUID,
        patient_id: uuid.UUID | None = None,
    ) -> dict[str, int]:
        """Return a mapping of SessionStatus value -> count for the org."""
        conditions: list[Any] = [
            User.organization_id == organization_id,
        ]
        if patient_id is not None:
            conditions.append(SessionModel.patient_id == patient_id)

        stmt = (
            select(
                SessionModel.status.label("status"),
                func.count(SessionModel.id).label("session_count"),
            )
            .select_from(SessionModel)
            .join(User, SessionModel.patient_id == User.id)
            .where(and_(*conditions))
            .group_by(SessionModel.status)
        )

        result = await self._db.execute(stmt)
        counts: dict[str, int] = {}
        for row in result.all():
            # status is an enum; the .value attribute gives the DB string.
            raw = row.status
            key = raw.value if hasattr(raw, "value") else str(raw)
            counts[key] = int(row.session_count)
        return counts

    async def active_patients(
        self,
        organization_id: uuid.UUID,
        days: int = 30,
    ) -> int:
        """Count distinct patients that have a session in the last ``days`` days."""
        window_start = datetime.now(UTC) - timedelta(days=days)

        stmt = (
            select(
                func.count(func.distinct(SessionModel.patient_id)).label("active_patients"),
            )
            .select_from(SessionModel)
            .join(User, SessionModel.patient_id == User.id)
            .where(
                and_(
                    User.organization_id == organization_id,
                    SessionModel.session_date >= window_start,
                )
            )
        )

        result = await self._db.execute(stmt)
        row = result.one_or_none()
        if row is None:
            return 0
        return int(row.active_patients or 0)

    async def chat_activity_by_day(
        self,
        organization_id: uuid.UUID,
        days: int = 30,
        patient_id: uuid.UUID | None = None,
    ) -> list[ChatActivityPoint]:
        """Count ConversationMessage rows per day for the org's conversations.

        Zero-fills missing days so the response always has ``days`` points.
        """
        today = datetime.now(UTC).date()
        earliest_day = today - timedelta(days=days - 1)
        window_start = datetime.combine(earliest_day, datetime.min.time(), tzinfo=UTC)

        conditions: list[Any] = [
            Conversation.organization_id == organization_id,
            ConversationMessage.created_at >= window_start,
        ]
        if patient_id is not None:
            conditions.append(Conversation.patient_id == patient_id)

        day_expr = cast(ConversationMessage.created_at, Date)
        stmt = (
            select(
                day_expr.label("day"),
                func.count(ConversationMessage.id).label("message_count"),
            )
            .select_from(ConversationMessage)
            .join(Conversation, ConversationMessage.conversation_id == Conversation.id)
            .where(and_(*conditions))
            .group_by(day_expr)
        )

        result = await self._db.execute(stmt)
        by_day: dict[date, int] = {row.day: int(row.message_count) for row in result.all()}

        points: list[ChatActivityPoint] = []
        for offset in range(days):
            day = earliest_day + timedelta(days=offset)
            points.append(ChatActivityPoint(day=day, message_count=by_day.get(day, 0)))
        return points

    async def assessment_score_trend(
        self,
        organization_id: uuid.UUID,
        instrument: AssessmentInstrument,
        weeks: int = 12,
        patient_id: uuid.UUID | None = None,
    ) -> list[AssessmentTrendPoint]:
        """Weekly average PHQ-9 / GAD-7 scores for the org.

        Zero-fills missing weeks with ``avg_score=None, count=0``.
        """
        today = datetime.now(UTC).date()
        current_week_start = today - timedelta(days=today.weekday())
        earliest_week_start = current_week_start - timedelta(weeks=weeks - 1)
        window_start = datetime.combine(earliest_week_start, datetime.min.time(), tzinfo=UTC)

        period_start = func.date_trunc("week", Assessment.administered_at)
        conditions: list[Any] = [
            User.organization_id == organization_id,
            Assessment.instrument == instrument,
            Assessment.administered_at >= window_start,
        ]
        if patient_id is not None:
            conditions.append(Assessment.patient_id == patient_id)

        stmt = (
            select(
                cast(period_start, Date).label("week_start"),
                func.avg(cast(Assessment.total_score, Integer)).label("avg_score"),
                func.count(Assessment.id).label("assessment_count"),
            )
            .select_from(Assessment)
            .join(User, Assessment.patient_id == User.id)
            .where(and_(*conditions))
            .group_by(period_start)
        )

        result = await self._db.execute(stmt)
        by_week: dict[date, tuple[float | None, int]] = {}
        for row in result.all():
            by_week[row.week_start] = (
                float(row.avg_score) if row.avg_score is not None else None,
                int(row.assessment_count),
            )

        points: list[AssessmentTrendPoint] = []
        for offset in range(weeks):
            week_start = earliest_week_start + timedelta(weeks=offset)
            avg, count = by_week.get(week_start, (None, 0))
            points.append(
                AssessmentTrendPoint(
                    week_start=week_start,
                    avg_score=avg,
                    count=count,
                )
            )
        return points

    # Thin response-model wrappers (convenience for endpoint handlers) --

    async def sessions_by_status_response(
        self,
        organization_id: uuid.UUID,
    ) -> SessionsByStatusResponse:
        counts = await self.sessions_by_status(organization_id)
        return SessionsByStatusResponse(counts=counts)

    async def active_patients_response(
        self,
        organization_id: uuid.UUID,
        days: int = 30,
    ) -> ActivePatientsResponse:
        count = await self.active_patients(organization_id, days=days)
        return ActivePatientsResponse(window_days=days, active_patients=count)

    async def assessment_trend_response(
        self,
        organization_id: uuid.UUID,
        instrument: AssessmentInstrument,
        weeks: int = 12,
    ) -> AssessmentTrendResponse:
        points = await self.assessment_score_trend(organization_id, instrument, weeks=weeks)
        return AssessmentTrendResponse(instrument=instrument, points=points)
