"""Webhook fan-out: event sources call dispatch, we persist + enqueue.

Every call path into this module is write-the-row-first, then enqueue.
If the enqueue fails the DB row is still there and the operator panel
(admin /webhook-deliveries) surfaces it as pending; a supervisor job
can re-kick stale pending rows without losing audit data.

The payload envelope is stable across retries — ``event_id`` stays the
same between attempts so customers can dedupe. Each attempt gets its
own ``delivery_id`` so the audit trail is append-only per attempt.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.webhook_delivery import WebhookDelivery
from src.models.db.webhook_endpoint import WebhookEndpoint
from src.repositories.webhook_repo import (
    WebhookDeliveryRepository,
    WebhookEndpointRepository,
)

logger = logging.getLogger(__name__)


def build_envelope(
    event_type: str,
    event_id: uuid.UUID,
    data: dict[str, Any],
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the JSON body POSTed to customer endpoints.

    Kept intentionally boring so customers can parse it with any JSON
    library. ``type`` mirrors Stripe's ``{domain}.{verb}`` convention,
    ``data`` is the event-specific subobject, ``id`` is stable across
    retries, and ``created`` is seconds-since-epoch for parity with
    Stripe's event shape.
    """
    occurred_at = occurred_at or datetime.now(UTC)
    return {
        "id": str(event_id),
        "type": event_type,
        "created": int(occurred_at.timestamp()),
        "data": data,
    }


class WebhookDispatcher:
    """Persist and enqueue webhook deliveries.

    Usage:

        dispatcher = WebhookDispatcher(db_session)
        await dispatcher.dispatch(
            organization_id=org_id,
            event_type="recap.ready",
            data={"session_id": str(sid), "recap_id": str(rid)},
        )

    Dispatcher never fails the caller: if no endpoints are subscribed,
    the call is a no-op. If the enqueue fails after the DB write, the
    row stays ``pending`` for a supervisor sweep to pick up.
    """

    def __init__(self, db_session: AsyncSession) -> None:
        self._session = db_session
        self._endpoints = WebhookEndpointRepository(db_session)
        self._deliveries = WebhookDeliveryRepository(db_session)

    async def dispatch(
        self,
        organization_id: uuid.UUID,
        event_type: str,
        data: dict[str, Any],
        occurred_at: datetime | None = None,
    ) -> list[WebhookDelivery]:
        """Fan out one logical event to every subscribed endpoint.

        Returns the created delivery rows. Enqueue errors are swallowed
        after logging — the row is still pending and the supervisor
        will reclaim it.
        """
        endpoints = await self._endpoints.list_active_for_event(
            organization_id=organization_id,
            event_type=event_type,
        )
        if not endpoints:
            return []

        event_id = uuid.uuid4()
        envelope = build_envelope(
            event_type=event_type,
            event_id=event_id,
            data=data,
            occurred_at=occurred_at,
        )

        created: list[WebhookDelivery] = []
        for endpoint in endpoints:
            delivery = await self._deliveries.create(
                WebhookDelivery(
                    endpoint_id=endpoint.id,
                    organization_id=organization_id,
                    event_type=event_type,
                    event_id=event_id,
                    payload=envelope,
                )
            )
            created.append(delivery)

        # Enqueue after flush so the worker is guaranteed to see rows.
        try:
            from src.workers.webhook_delivery_worker import (
                queue_webhook_delivery,
            )

            for delivery in created:
                queue_webhook_delivery(delivery.id)
        except Exception:
            logger.warning(
                "Failed to enqueue webhook deliveries for event %s; "
                "rows remain pending for supervisor sweep",
                event_type,
                exc_info=True,
            )

        return created


def serialize_payload(payload: dict[str, Any]) -> bytes:
    """Serialize a payload deterministically for HMAC signing."""
    return json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")


def _endpoint_has_subscribed(endpoint: WebhookEndpoint, event_type: str) -> bool:
    return event_type in endpoint.event_types
