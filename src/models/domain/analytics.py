"""Analytics response schemas for executive dashboards."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TherapistUtilization(BaseModel):
    """Weekly therapist utilization metrics."""

    therapist_id: UUID
    organization_id: UUID
    therapist_email: str
    period_start: date
    period_end: date
    sessions_in_period: int
    patients_in_period: int
    total_hours: float
    avg_duration_seconds: float | None
    success_rate_pct: float


class SessionOutcomeSummary(BaseModel):
    """Weekly session processing outcomes."""

    organization_id: UUID
    period_start: date
    period_end: date
    total_sessions: int
    sessions_ready: int
    sessions_failed: int
    success_rate_pct: float
    failure_rate_pct: float
    avg_recording_duration_seconds: float | None
    avg_word_count: float | None
    avg_seconds_to_ready: float | None
    p95_seconds_to_ready: float | None


class PatientEngagementTrend(BaseModel):
    """Weekly patient engagement trends."""

    organization_id: UUID
    period_start: date
    period_end: date
    active_patients: int
    total_patients: int
    patient_activation_rate_pct: float
    total_sessions: int
    total_messages: int
    avg_sessions_per_patient: float
    avg_messages_per_patient: float
    net_consent_change: int


class AISafetyMetrics(BaseModel):
    """Weekly AI safety and RAG quality metrics."""

    organization_id: UUID
    period_start: date
    period_end: date
    total_messages: int
    avg_sources_per_response: float | None
    grounded_responses: int
    zero_source_responses: int
    grounding_rate_pct: float
    risk_detections: int
    guardrail_triggers: int
    escalations: int


class EventTimelineItem(BaseModel):
    """Single event in the timeline view."""

    id: UUID
    event_name: str
    event_category: str
    session_id: UUID | None
    event_timestamp: datetime
    properties: dict[str, object] | None


class EventTimelineResponse(BaseModel):
    """Paginated event timeline."""

    events: list[EventTimelineItem]
    next_cursor: str | None = Field(
        None, description="Cursor for next page (event_timestamp of last item)"
    )
    has_more: bool


class EventAggregateItem(BaseModel):
    """Aggregated event counts for a time bucket."""

    event_name: str
    period: str
    count: int


class EventAggregateResponse(BaseModel):
    """List of aggregated event counts."""

    aggregates: list[EventAggregateItem]
    period_type: str = Field(..., description="Aggregation period (hour/day/week/month)")
