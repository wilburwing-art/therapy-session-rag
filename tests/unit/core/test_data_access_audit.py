"""Tests for src.core.data_access_audit.log_data_access."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.data_access_audit import log_data_access
from src.models.db.event import EventCategory


@pytest.fixture
def publisher() -> MagicMock:
    """Mock EventPublisher with an async publish method."""
    pub = MagicMock()
    pub.publish = AsyncMock(return_value=MagicMock())
    return pub


async def test_log_data_access_publishes_event_with_data_access_category(
    publisher: MagicMock,
) -> None:
    actor = uuid.uuid4()
    org = uuid.uuid4()

    await log_data_access(
        publisher,
        actor_id=actor,
        organization_id=org,
        subject="session",
        event_name="session.transcript_viewed",
        properties={"session_id": "abc"},
    )

    publisher.publish.assert_awaited_once()
    kwargs = publisher.publish.await_args.kwargs
    assert kwargs["event_name"] == "session.transcript_viewed"
    assert kwargs["category"] == EventCategory.DATA_ACCESS
    assert kwargs["organization_id"] == org
    assert kwargs["actor_id"] == actor
    # subject mirrored into properties so downstream queries don't have to
    # parse the event name.
    assert kwargs["properties"]["subject"] == "session"
    assert kwargs["properties"]["session_id"] == "abc"


async def test_log_data_access_without_properties(publisher: MagicMock) -> None:
    await log_data_access(
        publisher,
        actor_id=None,
        organization_id=uuid.uuid4(),
        subject="patient",
        event_name="patient.themes_viewed",
    )
    kwargs = publisher.publish.await_args.kwargs
    # subject-only payload when the caller has no extras.
    assert kwargs["properties"] == {"subject": "patient"}
    assert kwargs["actor_id"] is None


async def test_log_data_access_swallows_publisher_exceptions(
    publisher: MagicMock,
) -> None:
    publisher.publish = AsyncMock(side_effect=RuntimeError("db lost"))
    # Must not raise — read endpoints fall back to returning the record.
    await log_data_access(
        publisher,
        actor_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        subject="session",
        event_name="session.recap_viewed",
    )
