"""Repository for analytics event operations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Text, and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.event import AnalyticsEvent, EventCategory


class EventRepository:
    """Repository for analytics event database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, event: AnalyticsEvent) -> AnalyticsEvent:
        """Insert a single event."""
        self.session.add(event)
        await self.session.flush()
        return event

    async def create_batch(self, events: list[AnalyticsEvent]) -> list[AnalyticsEvent]:
        """Insert multiple events."""
        self.session.add_all(events)
        await self.session.flush()
        return events

    async def get_by_id(self, event_id: uuid.UUID) -> AnalyticsEvent | None:
        """Get a single event by ID."""
        result = await self.session.execute(
            select(AnalyticsEvent).where(AnalyticsEvent.id == event_id)
        )
        return result.scalar_one_or_none()

    async def query(
        self,
        organization_id: uuid.UUID | None = None,
        event_name: str | None = None,
        event_category: EventCategory | None = None,
        session_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AnalyticsEvent]:
        """Query events with filters."""
        conditions: list[Any] = []

        if organization_id is not None:
            conditions.append(AnalyticsEvent.organization_id == organization_id)
        if event_name is not None:
            conditions.append(AnalyticsEvent.event_name == event_name)
        if event_category is not None:
            conditions.append(AnalyticsEvent.event_category == event_category)
        if session_id is not None:
            conditions.append(AnalyticsEvent.session_id == session_id)
        if actor_id is not None:
            conditions.append(AnalyticsEvent.actor_id == actor_id)
        if from_timestamp is not None:
            conditions.append(AnalyticsEvent.event_timestamp >= from_timestamp)
        if to_timestamp is not None:
            conditions.append(AnalyticsEvent.event_timestamp <= to_timestamp)

        query = select(AnalyticsEvent)
        if conditions:
            query = query.where(and_(*conditions))
        stmt = (
            query
            .order_by(AnalyticsEvent.event_timestamp.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_name(
        self,
        organization_id: uuid.UUID,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
    ) -> list[tuple[str, int]]:
        """Count events grouped by event_name."""
        conditions: list[Any] = [
            AnalyticsEvent.organization_id == organization_id,
        ]
        if from_timestamp is not None:
            conditions.append(AnalyticsEvent.event_timestamp >= from_timestamp)
        if to_timestamp is not None:
            conditions.append(AnalyticsEvent.event_timestamp <= to_timestamp)

        stmt = (
            select(
                AnalyticsEvent.event_name,
                func.count().label("count"),
            )
            .where(and_(*conditions))
            .group_by(AnalyticsEvent.event_name)
            .order_by(text("count DESC"))
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def aggregate_by_period(
        self,
        organization_id: uuid.UUID,
        event_name: str | None = None,
        event_category: EventCategory | None = None,
        period: str = "day",
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
    ) -> list[tuple[str, str, int]]:
        """Aggregate event counts by time period.

        Args:
            organization_id: Organization to filter by
            event_name: Optional event name filter
            event_category: Optional event category filter
            period: Aggregation period ('hour', 'day', 'week', 'month')
            from_timestamp: Start of time range
            to_timestamp: End of time range

        Returns:
            List of (event_name, period_label, count) tuples
        """
        conditions: list[Any] = [
            AnalyticsEvent.organization_id == organization_id,
        ]
        if event_name is not None:
            conditions.append(AnalyticsEvent.event_name == event_name)
        if event_category is not None:
            conditions.append(AnalyticsEvent.event_category == event_category)
        if from_timestamp is not None:
            conditions.append(AnalyticsEvent.event_timestamp >= from_timestamp)
        if to_timestamp is not None:
            conditions.append(AnalyticsEvent.event_timestamp <= to_timestamp)

        trunc_expr = func.date_trunc(period, AnalyticsEvent.event_timestamp)

        stmt = (
            select(
                AnalyticsEvent.event_name,
                func.cast(trunc_expr, type_=Text()).label("period"),
                func.count().label("count"),
            )
            .where(and_(*conditions))
            .group_by(AnalyticsEvent.event_name, trunc_expr)
            .order_by(trunc_expr.desc())
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1], row[2]) for row in result.all()]
