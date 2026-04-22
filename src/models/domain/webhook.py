"""Webhook Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class WebhookEventType(StrEnum):
    """Events a customer may subscribe to."""

    SESSION_COMPLETED = "session.completed"
    RECAP_READY = "recap.ready"
    PATIENT_DELETED = "patient.deleted"
    PATIENT_CONSENT_GRANTED = "patient.consent_granted"


class WebhookDeliveryStatus(StrEnum):
    """Lifecycle of a single delivery attempt."""

    PENDING = "pending"
    IN_FLIGHT = "in_flight"
    DELIVERED = "delivered"
    FAILED = "failed"


class WebhookEndpointCreate(BaseModel):
    """Create-webhook-endpoint request body."""

    url: HttpUrl
    event_types: list[WebhookEventType] = Field(..., min_length=1)
    description: str | None = Field(default=None, max_length=255)


class WebhookEndpointUpdate(BaseModel):
    """Partial-update for an existing endpoint."""

    url: HttpUrl | None = None
    event_types: list[WebhookEventType] | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class WebhookEndpointRead(BaseModel):
    """Endpoint as surfaced in list / detail responses.

    The signing secret is intentionally NOT included in this model —
    it's only returned from create and rotate endpoints.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    url: str
    description: str | None
    event_types: list[str]
    is_active: bool
    last_rotated_at: datetime | None = None
    disabled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WebhookEndpointCreated(WebhookEndpointRead):
    """Create / rotate response that additionally exposes the secret."""

    secret: str = Field(
        ...,
        description=(
            "HMAC signing secret. Store this now — it is never returned "
            "again unless you rotate the endpoint."
        ),
    )


class WebhookDeliveryRead(BaseModel):
    """Delivery record surfaced on the admin panel."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    endpoint_id: UUID
    organization_id: UUID
    event_type: str
    event_id: UUID
    status: WebhookDeliveryStatus
    attempt_count: int
    response_status_code: int | None = None
    response_body_snippet: str | None = None
    error_message: str | None = None
    delivered_at: datetime | None = None
    next_attempt_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
