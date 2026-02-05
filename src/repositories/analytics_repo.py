"""Repository for analytics aggregation queries."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Row, and_, case, cast, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Date, Float, Integer, Numeric

from src.models.db.event import AnalyticsEvent, EventCategory
from src.models.db.session import Session
from src.models.db.transcript import Transcript
from src.models.db.user import User


class AnalyticsRepository:
    """Raw SQL aggregation queries for analytics endpoints."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def therapist_utilization(
        self,
        organization_id: uuid.UUID,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[Row[Any]]:
        """Weekly therapist utilization metrics."""
        conditions: list[Any] = [
            User.organization_id == organization_id,
            User.role == "therapist",
        ]
        session_conditions: list[Any] = []
        if from_date is not None:
            session_conditions.append(Session.session_date >= from_date)
        if to_date is not None:
            session_conditions.append(Session.session_date <= to_date)

        period_start = func.date_trunc("week", Session.session_date)

        stmt = (
            select(
                User.id.label("therapist_id"),
                User.organization_id,
                User.email.label("therapist_email"),
                cast(period_start, Date).label("period_start"),
                cast(period_start + text("interval '7 days'"), Date).label("period_end"),
                func.count(Session.id).label("sessions_in_period"),
                func.count(func.distinct(Session.patient_id)).label("patients_in_period"),
                func.round(
                    cast(
                        func.coalesce(func.sum(Session.recording_duration_seconds), 0), Numeric
                    )
                    / 3600.0,
                    2,
                ).label("total_hours"),
                func.avg(Session.recording_duration_seconds).label("avg_duration_seconds"),
                case(
                    (
                        func.count(Session.id) > 0,
                        func.round(
                            cast(
                                func.count(case((Session.status == "ready", 1))), Numeric
                            )
                            / cast(func.count(Session.id), Numeric)
                            * 100,
                            2,
                        ),
                    ),
                    else_=cast(0, Numeric),
                ).label("success_rate_pct"),
            )
            .select_from(User)
            .join(Session, Session.therapist_id == User.id)
            .where(and_(*conditions, *session_conditions))
            .group_by(User.id, User.organization_id, User.email, period_start)
            .order_by(period_start.desc())
        )

        result = await self.session.execute(stmt)
        return list(result.all())

    async def session_outcomes(
        self,
        organization_id: uuid.UUID,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[Row[Any]]:
        """Weekly session processing outcomes."""
        conditions: list[Any] = [
            User.organization_id == organization_id,
        ]
        if from_date is not None:
            conditions.append(Session.session_date >= from_date)
        if to_date is not None:
            conditions.append(Session.session_date <= to_date)

        period_start = func.date_trunc("week", Session.session_date)

        stmt = (
            select(
                cast(period_start, Date).label("period_start"),
                cast(period_start + text("interval '7 days'"), Date).label("period_end"),
                func.count(Session.id).label("total_sessions"),
                func.count(case((Session.status == "ready", 1))).label("sessions_ready"),
                func.count(case((Session.status == "failed", 1))).label("sessions_failed"),
                func.avg(Session.recording_duration_seconds).label(
                    "avg_recording_duration_seconds"
                ),
                func.avg(Transcript.word_count).label("avg_word_count"),
                func.avg(
                    func.extract(
                        "epoch",
                        Session.updated_at - Session.created_at,
                    )
                ).label("avg_seconds_to_ready"),
            )
            .select_from(Session)
            .join(User, Session.patient_id == User.id)
            .outerjoin(Transcript, Transcript.session_id == Session.id)
            .where(and_(*conditions))
            .group_by(period_start)
            .order_by(period_start.desc())
        )

        result = await self.session.execute(stmt)
        return list(result.all())

    async def patient_engagement(
        self,
        organization_id: uuid.UUID,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[Row[Any]]:
        """Weekly patient engagement trends."""
        event_conditions: list[Any] = [
            AnalyticsEvent.organization_id == organization_id,
            AnalyticsEvent.event_name == "chat.message_sent",
        ]
        if from_date is not None:
            event_conditions.append(AnalyticsEvent.event_timestamp >= from_date)
        if to_date is not None:
            event_conditions.append(AnalyticsEvent.event_timestamp <= to_date)

        period_start = func.date_trunc("week", AnalyticsEvent.event_timestamp)

        # Count total patients in the org for activation rate
        total_patients_subq = (
            select(func.count(User.id).label("cnt"))
            .where(
                and_(
                    User.organization_id == organization_id,
                    User.role == "patient",
                )
            )
            .scalar_subquery()
        )

        stmt = (
            select(
                cast(period_start, Date).label("period_start"),
                cast(period_start + text("interval '7 days'"), Date).label("period_end"),
                func.count(func.distinct(AnalyticsEvent.actor_id)).label("active_patients"),
                total_patients_subq.label("total_patients"),
                func.count(AnalyticsEvent.id).label("total_messages"),
            )
            .where(and_(*event_conditions))
            .group_by(period_start)
            .order_by(period_start.desc())
        )

        result = await self.session.execute(stmt)
        return list(result.all())

    async def ai_safety_metrics(
        self,
        organization_id: uuid.UUID,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[Row[Any]]:
        """Weekly AI safety and RAG quality metrics."""
        conditions: list[Any] = [
            AnalyticsEvent.organization_id == organization_id,
            AnalyticsEvent.event_name.in_(
                ["chat.message_sent", "safety.risk_detected",
                 "safety.guardrail_triggered", "safety.escalation_created"]
            ),
        ]
        if from_date is not None:
            conditions.append(AnalyticsEvent.event_timestamp >= from_date)
        if to_date is not None:
            conditions.append(AnalyticsEvent.event_timestamp <= to_date)

        period_start = func.date_trunc("week", AnalyticsEvent.event_timestamp)

        stmt = (
            select(
                cast(period_start, Date).label("period_start"),
                cast(period_start + text("interval '7 days'"), Date).label("period_end"),
                func.count(
                    case((AnalyticsEvent.event_name == "chat.message_sent", 1))
                ).label("total_messages"),
                func.avg(
                    case(
                        (
                            AnalyticsEvent.event_name == "chat.message_sent",
                            cast(
                                AnalyticsEvent.properties["source_count"].as_string(),
                                Float,
                            ),
                        ),
                    )
                ).label("avg_sources_per_response"),
                func.count(
                    case(
                        (
                            and_(
                                AnalyticsEvent.event_name == "chat.message_sent",
                                cast(
                                    AnalyticsEvent.properties["source_count"].as_string(),
                                    Integer,
                                )
                                > 0,
                            ),
                            1,
                        )
                    )
                ).label("grounded_responses"),
                func.count(
                    case(
                        (
                            and_(
                                AnalyticsEvent.event_name == "chat.message_sent",
                                cast(
                                    AnalyticsEvent.properties["source_count"].as_string(),
                                    Integer,
                                )
                                == 0,
                            ),
                            1,
                        )
                    )
                ).label("zero_source_responses"),
                func.count(
                    case((AnalyticsEvent.event_name == "safety.risk_detected", 1))
                ).label("risk_detections"),
                func.count(
                    case((AnalyticsEvent.event_name == "safety.guardrail_triggered", 1))
                ).label("guardrail_triggers"),
                func.count(
                    case((AnalyticsEvent.event_name == "safety.escalation_created", 1))
                ).label("escalations"),
            )
            .where(and_(*conditions))
            .group_by(period_start)
            .order_by(period_start.desc())
        )

        result = await self.session.execute(stmt)
        return list(result.all())

    async def event_timeline(
        self,
        organization_id: uuid.UUID,
        cursor: datetime | None = None,
        limit: int = 50,
        event_name: str | None = None,
        event_category: EventCategory | None = None,
    ) -> list[AnalyticsEvent]:
        """Cursor-paginated event timeline."""
        conditions: list[Any] = [
            AnalyticsEvent.organization_id == organization_id,
        ]
        if cursor is not None:
            conditions.append(AnalyticsEvent.event_timestamp < cursor)
        if event_name is not None:
            conditions.append(AnalyticsEvent.event_name == event_name)
        if event_category is not None:
            conditions.append(AnalyticsEvent.event_category == event_category)

        stmt = (
            select(AnalyticsEvent)
            .where(and_(*conditions))
            .order_by(AnalyticsEvent.event_timestamp.desc())
            .limit(limit + 1)  # Fetch one extra to determine has_more
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())
