"""Tests for EventPublisher service."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.db.event import EventCategory
from src.services.event_service import EventPublisher


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async session."""
    return AsyncMock()


@pytest.fixture
def publisher(mock_session: AsyncMock) -> EventPublisher:
    """Create an EventPublisher with mocked session."""
    return EventPublisher(mock_session)


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def actor_id() -> uuid.UUID:
    return uuid.uuid4()


class TestPublish:
    """Tests for EventPublisher.publish()."""

    async def test_publish_creates_event(
        self, publisher: EventPublisher, org_id: uuid.UUID
    ) -> None:
        with patch.object(publisher._repo, "create", new_callable=AsyncMock) as mock_create:
            mock_event = MagicMock()
            mock_create.return_value = mock_event

            result = await publisher.publish(
                event_name="chat.message_sent",
                category=EventCategory.USER_ACTION,
                organization_id=org_id,
                properties={"top_k": 5},
            )

            assert result is mock_event
            mock_create.assert_called_once()
            created_event = mock_create.call_args[0][0]
            assert created_event.event_name == "chat.message_sent"
            assert created_event.event_category == EventCategory.USER_ACTION
            assert created_event.organization_id == org_id
            assert created_event.properties == {"top_k": 5}

    async def test_publish_with_all_fields(
        self,
        publisher: EventPublisher,
        org_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        session_id = uuid.uuid4()
        now = datetime.now(UTC)

        with patch.object(publisher._repo, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock()

            await publisher.publish(
                event_name="session.created",
                category=EventCategory.SYSTEM,
                organization_id=org_id,
                actor_id=actor_id,
                session_id=session_id,
                properties={"patient_id": "abc"},
                contexts={"request": {"method": "POST"}},
                event_timestamp=now,
            )

            created_event = mock_create.call_args[0][0]
            assert created_event.actor_id == actor_id
            assert created_event.session_id == session_id
            assert created_event.event_timestamp == now
            assert created_event.contexts == {"request": {"method": "POST"}}

    async def test_publish_sets_default_timestamp(
        self, publisher: EventPublisher, org_id: uuid.UUID
    ) -> None:
        with patch.object(publisher._repo, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock()

            await publisher.publish(
                event_name="test.event",
                category=EventCategory.PERFORMANCE,
                organization_id=org_id,
            )

            created_event = mock_create.call_args[0][0]
            assert created_event.event_timestamp is not None
            assert created_event.received_at is not None

    async def test_publish_swallows_exceptions(
        self, publisher: EventPublisher, org_id: uuid.UUID
    ) -> None:
        with patch.object(
            publisher._repo, "create", new_callable=AsyncMock, side_effect=RuntimeError("db error")
        ):
            result = await publisher.publish(
                event_name="test.event",
                category=EventCategory.SYSTEM,
                organization_id=org_id,
            )
            assert result is None

    async def test_publish_returns_none_on_failure(
        self, publisher: EventPublisher, org_id: uuid.UUID
    ) -> None:
        with patch.object(
            publisher._repo, "create", new_callable=AsyncMock, side_effect=Exception("fail")
        ):
            result = await publisher.publish(
                event_name="test",
                category=EventCategory.SYSTEM,
                organization_id=org_id,
            )
            assert result is None


class TestPublishBatch:
    """Tests for EventPublisher.publish_batch()."""

    async def test_publish_batch_creates_events(
        self, publisher: EventPublisher, org_id: uuid.UUID
    ) -> None:
        events_data = [
            {
                "event_name": "chat.message_sent",
                "event_category": EventCategory.USER_ACTION,
                "organization_id": org_id,
            },
            {
                "event_name": "session.created",
                "event_category": EventCategory.SYSTEM,
                "organization_id": org_id,
            },
        ]

        with patch.object(publisher._repo, "create_batch", new_callable=AsyncMock) as mock_batch:
            mock_batch.return_value = [MagicMock(), MagicMock()]

            result = await publisher.publish_batch(events_data)

            assert len(result) == 2
            mock_batch.assert_called_once()
            batch_arg = mock_batch.call_args[0][0]
            assert len(batch_arg) == 2
            assert batch_arg[0].event_name == "chat.message_sent"
            assert batch_arg[1].event_name == "session.created"

    async def test_publish_batch_empty_list(
        self, publisher: EventPublisher
    ) -> None:
        result = await publisher.publish_batch([])
        assert result == []

    async def test_publish_batch_swallows_db_error(
        self, publisher: EventPublisher, org_id: uuid.UUID
    ) -> None:
        events_data = [
            {
                "event_name": "test",
                "event_category": EventCategory.SYSTEM,
                "organization_id": org_id,
            },
        ]

        with patch.object(
            publisher._repo, "create_batch", new_callable=AsyncMock, side_effect=Exception("fail")
        ):
            result = await publisher.publish_batch(events_data)
            assert result == []

    async def test_publish_batch_skips_invalid_events(
        self, publisher: EventPublisher, org_id: uuid.UUID
    ) -> None:
        events_data = [
            {"event_name": "valid", "event_category": EventCategory.SYSTEM, "organization_id": org_id},
            {},  # missing required fields
        ]

        with patch.object(publisher._repo, "create_batch", new_callable=AsyncMock) as mock_batch:
            mock_batch.return_value = [MagicMock()]
            await publisher.publish_batch(events_data)
            # The valid event should still be created
            batch_arg = mock_batch.call_args[0][0]
            assert len(batch_arg) == 1
