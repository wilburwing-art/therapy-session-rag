"""Analytics event Pydantic schemas."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EventCategory(StrEnum):
    """Category of analytics event."""

    USER_ACTION = "user_action"
    SYSTEM = "system"
    CLINICAL = "clinical"
    PERFORMANCE = "performance"


class EventCreate(BaseModel):
    """Schema for creating an analytics event."""

    event_name: str = Field(..., max_length=255, description="Event name (e.g. 'chat.message_sent')")
    event_category: EventCategory = Field(..., description="Event category")
    actor_id: UUID | None = Field(None, description="User who triggered the event")
    organization_id: UUID = Field(..., description="Organization the event belongs to")
    session_id: UUID | None = Field(None, description="Therapy session ID if applicable")
    properties: dict[str, Any] | None = Field(None, description="Event-specific payload")
    contexts: dict[str, Any] | None = Field(None, description="Snowplow-style contexts")
    event_timestamp: datetime | None = Field(None, description="When the event occurred (defaults to now)")


class EventRead(BaseModel):
    """Schema for reading an analytics event."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Event unique identifier")
    event_name: str = Field(..., description="Event name")
    event_category: EventCategory = Field(..., description="Event category")
    actor_id: UUID | None = Field(None, description="User who triggered the event")
    organization_id: UUID = Field(..., description="Organization ID")
    session_id: UUID | None = Field(None, description="Therapy session ID")
    properties: dict[str, Any] | None = Field(None, description="Event payload")
    contexts: dict[str, Any] | None = Field(None, description="Event contexts")
    event_timestamp: datetime = Field(..., description="When the event occurred")
    received_at: datetime = Field(..., description="When the server received the event")


class EventFilter(BaseModel):
    """Schema for filtering events."""

    event_name: str | None = Field(None, description="Filter by event name")
    event_category: EventCategory | None = Field(None, description="Filter by category")
    organization_id: UUID | None = Field(None, description="Filter by organization")
    session_id: UUID | None = Field(None, description="Filter by therapy session")
    actor_id: UUID | None = Field(None, description="Filter by actor")
    from_timestamp: datetime | None = Field(None, description="Events after this time")
    to_timestamp: datetime | None = Field(None, description="Events before this time")


class EventAggregate(BaseModel):
    """Aggregated event counts for a time bucket."""

    event_name: str = Field(..., description="Event name")
    period: str = Field(..., description="Time period (e.g. '2026-02-05')")
    count: int = Field(..., description="Number of events in this period")
