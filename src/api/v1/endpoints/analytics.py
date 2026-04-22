"""Analytics API endpoints for dashboards and reporting."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.api.v1.dependencies import Auth, CurrentTherapist
from src.core.database import DbSession
from src.models.db.assessment import AssessmentInstrument
from src.models.db.event import EventCategory
from src.models.domain.analytics import (
    ActivePatientsResponse,
    AISafetyMetrics,
    AssessmentTrendResponse,
    ChatActivityPoint,
    EventAggregateResponse,
    EventTimelineResponse,
    PatientEngagementTrend,
    SessionOutcomeSummary,
    SessionsByStatusResponse,
    SessionsByWeekPoint,
    TherapistUtilization,
)
from src.services.analytics_service import AnalyticsService

router = APIRouter()


def get_analytics_service(session: DbSession) -> AnalyticsService:
    """Get analytics service instance."""
    return AnalyticsService(session)


AnalyticsSvc = Annotated[AnalyticsService, Depends(get_analytics_service)]


class AggregationPeriod(StrEnum):
    """Valid aggregation period values."""

    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


@router.get("/therapist-utilization", response_model=list[TherapistUtilization])
async def get_therapist_utilization(
    auth: Auth,
    service: AnalyticsSvc,
    from_date: datetime | None = Query(None, description="Start of date range"),
    to_date: datetime | None = Query(None, description="End of date range"),
) -> list[TherapistUtilization]:
    """Get weekly therapist utilization metrics.

    Returns session volume, patient count, hours worked, and success rates
    per therapist per week.
    """
    return await service.get_therapist_utilization(
        organization_id=auth.organization_id,
        from_date=from_date,
        to_date=to_date,
    )


@router.get("/session-outcomes", response_model=list[SessionOutcomeSummary])
async def get_session_outcomes(
    auth: Auth,
    service: AnalyticsSvc,
    from_date: datetime | None = Query(None, description="Start of date range"),
    to_date: datetime | None = Query(None, description="End of date range"),
) -> list[SessionOutcomeSummary]:
    """Get weekly session processing outcomes.

    Returns pipeline reliability, content quality, and processing SLA metrics
    per week.
    """
    return await service.get_session_outcomes(
        organization_id=auth.organization_id,
        from_date=from_date,
        to_date=to_date,
    )


@router.get("/patient-engagement", response_model=list[PatientEngagementTrend])
async def get_patient_engagement(
    auth: Auth,
    service: AnalyticsSvc,
    from_date: datetime | None = Query(None, description="Start of date range"),
    to_date: datetime | None = Query(None, description="End of date range"),
) -> list[PatientEngagementTrend]:
    """Get weekly patient engagement trends.

    Returns activation rates, session/message activity, and consent health
    per week.
    """
    return await service.get_patient_engagement(
        organization_id=auth.organization_id,
        from_date=from_date,
        to_date=to_date,
    )


@router.get("/ai-safety-metrics", response_model=list[AISafetyMetrics])
async def get_ai_safety_metrics(
    auth: Auth,
    service: AnalyticsSvc,
    from_date: datetime | None = Query(None, description="Start of date range"),
    to_date: datetime | None = Query(None, description="End of date range"),
) -> list[AISafetyMetrics]:
    """Get weekly AI safety and RAG quality metrics.

    Returns grounding rates, safety events, and guardrail effectiveness
    per week.
    """
    return await service.get_ai_safety_metrics(
        organization_id=auth.organization_id,
        from_date=from_date,
        to_date=to_date,
    )


@router.get("/events/timeline", response_model=EventTimelineResponse)
async def get_event_timeline(
    auth: Auth,
    service: AnalyticsSvc,
    cursor: datetime | None = Query(None, description="Cursor for pagination (event_timestamp)"),
    limit: int = Query(50, ge=1, le=200, description="Number of events per page"),
    event_name: str | None = Query(None, description="Filter by event name"),
    event_category: EventCategory | None = Query(None, description="Filter by event category"),
) -> EventTimelineResponse:
    """Get cursor-paginated event timeline.

    Returns events in reverse chronological order with cursor-based pagination.
    """
    return await service.get_event_timeline(
        organization_id=auth.organization_id,
        cursor=cursor,
        limit=limit,
        event_name=event_name,
        event_category=event_category,
    )


@router.get("/events/aggregate", response_model=EventAggregateResponse)
async def get_event_aggregates(
    auth: Auth,
    service: AnalyticsSvc,
    period: AggregationPeriod = Query(
        AggregationPeriod.DAY, description="Aggregation period"
    ),
    event_name: str | None = Query(None, description="Filter by event name"),
    event_category: EventCategory | None = Query(None, description="Filter by event category"),
    from_date: datetime | None = Query(None, description="Start of date range"),
    to_date: datetime | None = Query(None, description="End of date range"),
) -> EventAggregateResponse:
    """Get event counts aggregated by time period.

    Groups events by name and time bucket, returning counts for each combination.
    """
    return await service.get_event_aggregates(
        organization_id=auth.organization_id,
        period=period.value,
        event_name=event_name,
        event_category=event_category,
        from_date=from_date,
        to_date=to_date,
    )


# ----------------------------------------------------------------------
# Therapist dashboard analytics — JWT cookie auth, org-scoped
# ----------------------------------------------------------------------


class TherapistAssessmentInstrument(StrEnum):
    """Enum mirroring AssessmentInstrument for query-string validation."""

    PHQ9 = "phq9"
    GAD7 = "gad7"


@router.get(
    "/therapist/sessions-by-week",
    response_model=list[SessionsByWeekPoint],
)
async def therapist_sessions_by_week(
    therapist: CurrentTherapist,
    service: AnalyticsSvc,
    weeks_back: int = Query(12, ge=1, le=52),
) -> list[SessionsByWeekPoint]:
    """Session counts per ISO week for the last ``weeks_back`` weeks."""
    return await service.sessions_by_week(
        organization_id=therapist.organization_id,
        weeks_back=weeks_back,
    )


@router.get(
    "/therapist/sessions-by-status",
    response_model=SessionsByStatusResponse,
)
async def therapist_sessions_by_status(
    therapist: CurrentTherapist,
    service: AnalyticsSvc,
) -> SessionsByStatusResponse:
    """Session counts bucketed by processing status."""
    return await service.sessions_by_status_response(
        organization_id=therapist.organization_id,
    )


@router.get(
    "/therapist/active-patients",
    response_model=ActivePatientsResponse,
)
async def therapist_active_patients(
    therapist: CurrentTherapist,
    service: AnalyticsSvc,
    days: int = Query(30, ge=1, le=365),
) -> ActivePatientsResponse:
    """Distinct patients with a session in the last ``days`` days."""
    return await service.active_patients_response(
        organization_id=therapist.organization_id,
        days=days,
    )


@router.get(
    "/therapist/chat-activity",
    response_model=list[ChatActivityPoint],
)
async def therapist_chat_activity(
    therapist: CurrentTherapist,
    service: AnalyticsSvc,
    days: int = Query(30, ge=1, le=180),
) -> list[ChatActivityPoint]:
    """Daily chat message volume for the org's conversations."""
    return await service.chat_activity_by_day(
        organization_id=therapist.organization_id,
        days=days,
    )


@router.get(
    "/therapist/assessment-trend",
    response_model=AssessmentTrendResponse,
)
async def therapist_assessment_trend(
    therapist: CurrentTherapist,
    service: AnalyticsSvc,
    instrument: TherapistAssessmentInstrument = Query(
        ...,
        description="Assessment instrument (phq9 or gad7)",
    ),
    weeks: int = Query(12, ge=1, le=52),
) -> AssessmentTrendResponse:
    """Weekly average PHQ-9 / GAD-7 scores for the org."""
    return await service.assessment_trend_response(
        organization_id=therapist.organization_id,
        instrument=AssessmentInstrument(instrument.value),
        weeks=weeks,
    )
