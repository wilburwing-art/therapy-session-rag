"""Analytics service for dashboard and reporting queries."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.event import EventCategory
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
from src.repositories.analytics_repo import AnalyticsRepository
from src.repositories.event_repo import EventRepository


class AnalyticsService:
    """Service layer for analytics queries."""

    def __init__(self, db_session: AsyncSession) -> None:
        self._analytics_repo = AnalyticsRepository(db_session)
        self._event_repo = EventRepository(db_session)

    async def get_therapist_utilization(
        self,
        organization_id: uuid.UUID,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[TherapistUtilization]:
        """Get weekly therapist utilization metrics."""
        rows = await self._analytics_repo.therapist_utilization(
            organization_id, from_date, to_date
        )
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
        rows = await self._analytics_repo.session_outcomes(
            organization_id, from_date, to_date
        )
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
                    avg_word_count=(
                        float(row.avg_word_count) if row.avg_word_count else None
                    ),
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
        rows = await self._analytics_repo.patient_engagement(
            organization_id, from_date, to_date
        )
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
                    avg_messages_per_patient=(
                        round(messages / active, 2) if active > 0 else 0
                    ),
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
        rows = await self._analytics_repo.ai_safety_metrics(
            organization_id, from_date, to_date
        )
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
                    grounding_rate_pct=(
                        round(grounded / total * 100, 2) if total > 0 else 0
                    ),
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
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> EventAggregateResponse:
        """Get event counts aggregated by time period."""
        rows = await self._event_repo.aggregate_by_period(
            organization_id=organization_id,
            event_name=event_name,
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
