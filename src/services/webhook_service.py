"""Customer-facing webhook endpoint management."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.models.db.webhook_endpoint import WebhookEndpoint
from src.models.domain.webhook import (
    WebhookEndpointCreate,
    WebhookEndpointUpdate,
    WebhookEventType,
)
from src.repositories.webhook_repo import WebhookEndpointRepository

# 32 bytes URL-safe ≈ 43 characters; fits comfortably under the 128-char column.
_SECRET_BYTES = 32


def generate_webhook_secret() -> str:
    """Generate a fresh signing secret.

    Returned plaintext. The caller is responsible for surfacing it to
    the customer exactly once — we store it plaintext because customers
    need the same value to verify signatures, but we never log it.
    """
    return secrets.token_urlsafe(_SECRET_BYTES)


class WebhookService:
    """CRUD for webhook endpoints owned by the caller's organization."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = WebhookEndpointRepository(session)

    async def create_endpoint(
        self,
        organization_id: uuid.UUID,
        payload: WebhookEndpointCreate,
    ) -> WebhookEndpoint:
        endpoint = WebhookEndpoint(
            organization_id=organization_id,
            url=str(payload.url),
            description=payload.description,
            secret=generate_webhook_secret(),
            event_types=[et.value for et in payload.event_types],
            is_active=True,
        )
        return await self.repo.create(endpoint)

    async def list_endpoints(
        self, organization_id: uuid.UUID
    ) -> list[WebhookEndpoint]:
        return await self.repo.list_for_org(organization_id)

    async def get_endpoint(
        self,
        endpoint_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> WebhookEndpoint:
        endpoint = await self.repo.get_for_org(endpoint_id, organization_id)
        if endpoint is None:
            raise NotFoundError(
                resource="Webhook endpoint", resource_id=str(endpoint_id)
            )
        return endpoint

    async def update_endpoint(
        self,
        endpoint_id: uuid.UUID,
        organization_id: uuid.UUID,
        payload: WebhookEndpointUpdate,
    ) -> WebhookEndpoint:
        endpoint = await self.get_endpoint(endpoint_id, organization_id)
        if payload.url is not None:
            endpoint.url = str(payload.url)
        if payload.event_types is not None:
            endpoint.event_types = [et.value for et in payload.event_types]
        if payload.description is not None:
            endpoint.description = payload.description
        if payload.is_active is not None:
            endpoint.is_active = payload.is_active
            endpoint.disabled_at = (
                None if payload.is_active else datetime.now(UTC)
            )
        await self.session.flush()
        return endpoint

    async def rotate_secret(
        self,
        endpoint_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> WebhookEndpoint:
        endpoint = await self.get_endpoint(endpoint_id, organization_id)
        endpoint.secret = generate_webhook_secret()
        endpoint.last_rotated_at = datetime.now(UTC)
        await self.session.flush()
        return endpoint

    async def delete_endpoint(
        self,
        endpoint_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> None:
        ok = await self.repo.delete(endpoint_id, organization_id)
        if not ok:
            raise NotFoundError(
                resource="Webhook endpoint", resource_id=str(endpoint_id)
            )


def supported_event_types() -> list[str]:
    """Canonical list of dispatchable event types."""
    return [et.value for et in WebhookEventType]
