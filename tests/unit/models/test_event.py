"""Tests for AnalyticsEvent model and schemas."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.models.db.event import AnalyticsEvent, EventCategory
from src.models.domain.event import EventAggregate, EventCreate, EventFilter, EventRead
from src.models.domain.event import EventCategory as DomainEventCategory


class TestEventCategory:
    """Tests for EventCategory enum."""

    def test_event_category_values(self) -> None:
        assert EventCategory.USER_ACTION.value == "user_action"
        assert EventCategory.SYSTEM.value == "system"
        assert EventCategory.CLINICAL.value == "clinical"
        assert EventCategory.PERFORMANCE.value == "performance"

    def test_domain_event_category_matches_db(self) -> None:
        for db_cat in EventCategory:
            assert db_cat.value in [c.value for c in DomainEventCategory]


class TestAnalyticsEventModel:
    """Tests for AnalyticsEvent database model."""

    def test_event_creation(self) -> None:
        org_id = uuid.uuid4()
        event = AnalyticsEvent(
            event_name="chat.message_sent",
            event_category=EventCategory.USER_ACTION,
            organization_id=org_id,
            properties={"top_k": 5},
        )
        assert event.event_name == "chat.message_sent"
        assert event.event_category == EventCategory.USER_ACTION
        assert event.organization_id == org_id
        assert event.properties == {"top_k": 5}

    def test_event_with_all_fields(self) -> None:
        org_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        session_id = uuid.uuid4()
        now = datetime.now(UTC)

        event = AnalyticsEvent(
            event_name="session.created",
            event_category=EventCategory.SYSTEM,
            actor_id=actor_id,
            organization_id=org_id,
            session_id=session_id,
            properties={"patient_id": str(uuid.uuid4())},
            contexts={"request": {"method": "POST", "path": "/api/v1/sessions"}},
            event_timestamp=now,
            received_at=now,
        )
        assert event.actor_id == actor_id
        assert event.session_id == session_id
        assert event.contexts is not None

    def test_event_nullable_fields(self) -> None:
        event = AnalyticsEvent(
            event_name="test.event",
            event_category=EventCategory.PERFORMANCE,
            organization_id=uuid.uuid4(),
        )
        assert event.actor_id is None
        assert event.session_id is None
        assert event.properties is None
        assert event.contexts is None

    def test_tablename(self) -> None:
        assert AnalyticsEvent.__tablename__ == "analytics_events"


class TestEventCreateSchema:
    """Tests for EventCreate Pydantic schema."""

    def test_valid_event_create(self) -> None:
        data = EventCreate(
            event_name="chat.message_sent",
            event_category=DomainEventCategory.USER_ACTION,
            organization_id=uuid.uuid4(),
        )
        assert data.event_name == "chat.message_sent"

    def test_event_create_with_all_fields(self) -> None:
        now = datetime.now(UTC)
        data = EventCreate(
            event_name="session.created",
            event_category=DomainEventCategory.SYSTEM,
            actor_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            properties={"key": "value"},
            contexts={"request": {}},
            event_timestamp=now,
        )
        assert data.event_timestamp == now
        assert data.properties == {"key": "value"}

    def test_event_create_missing_required(self) -> None:
        with pytest.raises(ValidationError):
            EventCreate(
                event_name="test",
                # missing event_category and organization_id
            )  # type: ignore[call-arg]

    def test_event_name_max_length(self) -> None:
        with pytest.raises(ValidationError):
            EventCreate(
                event_name="x" * 256,
                event_category=DomainEventCategory.SYSTEM,
                organization_id=uuid.uuid4(),
            )


class TestEventReadSchema:
    """Tests for EventRead Pydantic schema."""

    def test_valid_event_read(self) -> None:
        now = datetime.now(UTC)
        data = EventRead(
            id=uuid.uuid4(),
            event_name="chat.message_sent",
            event_category=DomainEventCategory.USER_ACTION,
            organization_id=uuid.uuid4(),
            event_timestamp=now,
            received_at=now,
        )
        assert data.event_name == "chat.message_sent"


class TestEventFilterSchema:
    """Tests for EventFilter Pydantic schema."""

    def test_empty_filter(self) -> None:
        f = EventFilter()
        assert f.event_name is None
        assert f.event_category is None

    def test_filter_with_time_range(self) -> None:
        now = datetime.now(UTC)
        f = EventFilter(
            event_name="chat.message_sent",
            from_timestamp=now,
            to_timestamp=now,
        )
        assert f.from_timestamp == now


class TestEventAggregateSchema:
    """Tests for EventAggregate Pydantic schema."""

    def test_valid_aggregate(self) -> None:
        agg = EventAggregate(
            event_name="chat.message_sent",
            period="2026-02-05",
            count=42,
        )
        assert agg.count == 42
