"""Event publishing service for analytics tracking."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.event import AnalyticsEvent, EventCategory
from src.repositories.event_repo import EventRepository

logger = logging.getLogger(__name__)


class EventPublisher:
    """Publishes analytics events to the database.

    Non-blocking: failures log warnings but never raise to callers.
    """

    def __init__(self, db_session: AsyncSession) -> None:
        self._repo = EventRepository(db_session)
        self._session = db_session

    async def publish(
        self,
        event_name: str,
        category: EventCategory,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
        properties: dict[str, Any] | None = None,
        contexts: dict[str, Any] | None = None,
        event_timestamp: datetime | None = None,
    ) -> AnalyticsEvent | None:
        """Publish a single analytics event.

        Returns the created event, or None if publishing failed.
        Failures are logged but never raised.
        """
        try:
            event = AnalyticsEvent(
                event_name=event_name,
                event_category=category,
                organization_id=organization_id,
                actor_id=actor_id,
                session_id=session_id,
                properties=properties,
                contexts=contexts,
                event_timestamp=event_timestamp or datetime.now(UTC),
                received_at=datetime.now(UTC),
            )
            return await self._repo.create(event)
        except Exception:
            logger.warning("Failed to publish event %s", event_name, exc_info=True)
            return None

    async def publish_batch(
        self,
        events: list[dict[str, Any]],
    ) -> list[AnalyticsEvent]:
        """Publish multiple analytics events.

        Each dict should contain keys matching AnalyticsEvent fields.
        Returns created events. Failed events are skipped with a warning.
        """
        now = datetime.now(UTC)
        db_events: list[AnalyticsEvent] = []

        for event_data in events:
            try:
                db_events.append(
                    AnalyticsEvent(
                        event_name=event_data["event_name"],
                        event_category=event_data["event_category"],
                        organization_id=event_data["organization_id"],
                        actor_id=event_data.get("actor_id"),
                        session_id=event_data.get("session_id"),
                        properties=event_data.get("properties"),
                        contexts=event_data.get("contexts"),
                        event_timestamp=event_data.get("event_timestamp", now),
                        received_at=now,
                    )
                )
            except Exception:
                logger.warning(
                    "Failed to create event from data: %s",
                    event_data.get("event_name", "unknown"),
                    exc_info=True,
                )

        if not db_events:
            return []

        try:
            return await self._repo.create_batch(db_events)
        except Exception:
            logger.warning("Failed to publish event batch", exc_info=True)
            return []
