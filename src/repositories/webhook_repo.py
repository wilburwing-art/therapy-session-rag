"""Repository for webhook endpoints and deliveries."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.webhook_delivery import WebhookDelivery, WebhookDeliveryStatus
from src.models.db.webhook_endpoint import WebhookEndpoint


class WebhookEndpointRepository:
    """CRUD for customer-configured webhook endpoints."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, endpoint: WebhookEndpoint) -> WebhookEndpoint:
        self.session.add(endpoint)
        await self.session.flush()
        await self.session.refresh(endpoint)
        return endpoint

    async def get_by_id(
        self, endpoint_id: uuid.UUID
    ) -> WebhookEndpoint | None:
        result = await self.session.execute(
            select(WebhookEndpoint).where(WebhookEndpoint.id == endpoint_id)
        )
        return result.scalar_one_or_none()

    async def get_for_org(
        self,
        endpoint_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> WebhookEndpoint | None:
        result = await self.session.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.id == endpoint_id,
                WebhookEndpoint.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_org(
        self, organization_id: uuid.UUID
    ) -> list[WebhookEndpoint]:
        result = await self.session.execute(
            select(WebhookEndpoint)
            .where(WebhookEndpoint.organization_id == organization_id)
            .order_by(WebhookEndpoint.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_active_for_event(
        self,
        organization_id: uuid.UUID,
        event_type: str,
    ) -> list[WebhookEndpoint]:
        """Find every active endpoint that subscribes to ``event_type``.

        Active means both ``is_active`` True and ``disabled_at`` null.
        Membership in ``event_types`` is checked in Python to keep the
        query simple across SQLAlchemy's ARRAY dialects; the index on
        ``(organization_id, is_active)`` already narrows the row set.
        """
        result = await self.session.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.organization_id == organization_id,
                WebhookEndpoint.is_active.is_(True),
                WebhookEndpoint.disabled_at.is_(None),
            )
        )
        all_active = list(result.scalars().all())
        return [e for e in all_active if event_type in e.event_types]

    async def delete(
        self, endpoint_id: uuid.UUID, organization_id: uuid.UUID
    ) -> bool:
        endpoint = await self.get_for_org(endpoint_id, organization_id)
        if endpoint is None:
            return False
        await self.session.delete(endpoint)
        await self.session.flush()
        return True


class WebhookDeliveryRepository:
    """CRUD for delivery attempt records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, delivery: WebhookDelivery) -> WebhookDelivery:
        self.session.add(delivery)
        await self.session.flush()
        await self.session.refresh(delivery)
        return delivery

    async def get_by_id(
        self, delivery_id: uuid.UUID
    ) -> WebhookDelivery | None:
        result = await self.session.execute(
            select(WebhookDelivery).where(WebhookDelivery.id == delivery_id)
        )
        return result.scalar_one_or_none()

    async def claim_for_delivery(
        self, delivery_id: uuid.UUID
    ) -> WebhookDelivery | None:
        """Atomically flip a pending row to in_flight.

        Uses ``FOR UPDATE SKIP LOCKED`` semantics via a row-level lock so
        two workers pulling the same job ID simultaneously only produce
        one in-flight row; the loser sees a non-pending status and backs
        off without resending.
        """
        result = await self.session.execute(
            select(WebhookDelivery)
            .where(WebhookDelivery.id == delivery_id)
            .with_for_update(skip_locked=True)
        )
        delivery = result.scalar_one_or_none()
        if delivery is None:
            return None
        if delivery.status != WebhookDeliveryStatus.PENDING:
            return None
        delivery.status = WebhookDeliveryStatus.IN_FLIGHT
        delivery.attempt_count += 1
        await self.session.flush()
        return delivery

    async def mark_delivered(
        self,
        delivery: WebhookDelivery,
        response_status_code: int,
        response_body_snippet: str | None,
    ) -> None:
        delivery.status = WebhookDeliveryStatus.DELIVERED
        delivery.response_status_code = response_status_code
        delivery.response_body_snippet = response_body_snippet
        delivery.delivered_at = datetime.now(UTC)
        delivery.next_attempt_at = None
        await self.session.flush()

    async def mark_failed(
        self,
        delivery: WebhookDelivery,
        response_status_code: int | None,
        response_body_snippet: str | None,
        error_message: str,
        next_attempt_at: datetime | None,
    ) -> None:
        if next_attempt_at is None:
            delivery.status = WebhookDeliveryStatus.FAILED
        else:
            delivery.status = WebhookDeliveryStatus.PENDING
        delivery.response_status_code = response_status_code
        delivery.response_body_snippet = response_body_snippet
        delivery.error_message = error_message
        delivery.next_attempt_at = next_attempt_at
        await self.session.flush()

    async def list_recent(
        self,
        limit: int = 50,
        organization_id: uuid.UUID | None = None,
        endpoint_id: uuid.UUID | None = None,
        status: WebhookDeliveryStatus | None = None,
    ) -> list[WebhookDelivery]:
        """Operator view: the most recent deliveries, optionally filtered."""
        query = select(WebhookDelivery).order_by(
            WebhookDelivery.created_at.desc()
        )
        if organization_id is not None:
            query = query.where(
                WebhookDelivery.organization_id == organization_id
            )
        if endpoint_id is not None:
            query = query.where(WebhookDelivery.endpoint_id == endpoint_id)
        if status is not None:
            query = query.where(WebhookDelivery.status == status)
        result = await self.session.execute(query.limit(limit))
        return list(result.scalars().all())
