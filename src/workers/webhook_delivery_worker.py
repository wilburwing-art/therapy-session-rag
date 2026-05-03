"""Webhook delivery worker.

Pulls a delivery row from the ``webhook_delivery`` queue, claims it via
DB row-level lock (``FOR UPDATE SKIP LOCKED``), signs the body with the
endpoint's current secret, and POSTs. Non-2xx responses and transport
failures schedule an exponential-backoff retry; the delivery row stays
the source of truth for operator-visible status.

Signature format (Stripe-compatible):

    Webhook-Signature: t=<unix>,v1=<hex_hmac_sha256(secret, f"{t}.{body}")>

The ``t=`` / ``v1=`` pair is what customers familiar with Stripe already
know, which is the whole point of copying the scheme.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from redis import Redis
from rq import Queue

from src.core.config import Settings, get_settings
from src.core.database import get_session_factory
from src.repositories.webhook_repo import (
    WebhookDeliveryRepository,
    WebhookEndpointRepository,
)
from src.services.webhook_dispatcher import serialize_payload

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
# Minutes between attempts for attempts 1..5: 1, 5, 30, 120, 360. After
# that we give up and mark the row FAILED. Customers who need longer
# retention re-deliver via the admin panel.
_BACKOFF_MINUTES = [1, 5, 30, 120, 360]
_HTTP_TIMEOUT_SECONDS = 10.0
_RESPONSE_SNIPPET_BYTES = 1024


def _signature_header(secret: str, body: bytes, now: int) -> str:
    """Compute the Webhook-Signature header value."""
    signed_payload = f"{now}.{body.decode('utf-8')}".encode()
    mac = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={now},v1={mac}"


def _backoff_for_attempt(attempt: int) -> timedelta | None:
    """Return the delay until the next retry, or None if we're done.

    ``attempt`` is the attempt number that just failed (1-indexed).
    """
    if attempt >= MAX_ATTEMPTS:
        return None
    idx = min(attempt, len(_BACKOFF_MINUTES) - 1)
    return timedelta(minutes=_BACKOFF_MINUTES[idx])


def get_redis_connection(settings: Settings | None = None) -> Redis:  # type: ignore[type-arg]
    settings = settings or get_settings()
    return Redis.from_url(str(settings.redis_url))


def get_webhook_delivery_queue(
    settings: Settings | None = None,
    queue_name: str = "webhook_delivery",
) -> Queue:
    conn = get_redis_connection(settings)
    return Queue(queue_name, connection=conn)


async def process_webhook_delivery_job(delivery_id: str) -> dict[str, Any]:
    """Deliver one webhook row.

    Concurrency-safe: the first worker to `claim_for_delivery` flips the
    row to in_flight. Any other worker handed the same ID sees a
    non-pending status and bows out.
    """
    delivery_uuid = uuid.UUID(delivery_id)
    session_factory = get_session_factory()

    async with session_factory() as db_session:
        deliveries = WebhookDeliveryRepository(db_session)
        endpoints = WebhookEndpointRepository(db_session)

        delivery = await deliveries.claim_for_delivery(delivery_uuid)
        if delivery is None:
            # Either the row is gone, it's already delivered, or another
            # worker has it. Nothing to do.
            await db_session.commit()
            return {"delivery_id": delivery_id, "status": "skipped"}

        endpoint = await endpoints.get_by_id(delivery.endpoint_id)
        if endpoint is None or not endpoint.is_active or endpoint.disabled_at:
            await deliveries.mark_failed(
                delivery,
                response_status_code=None,
                response_body_snippet=None,
                error_message="Endpoint deleted or disabled",
                next_attempt_at=None,
            )
            await db_session.commit()
            return {"delivery_id": delivery_id, "status": "failed"}

        body = serialize_payload(delivery.payload)
        now = int(time.time())
        signature = _signature_header(endpoint.secret, body, now)

        response_status: int | None = None
        response_snippet: str | None = None
        error_message: str | None = None
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    endpoint.url,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "Webhook-Signature": signature,
                        "Webhook-Event-Id": str(delivery.event_id),
                        "Webhook-Event-Type": delivery.event_type,
                    },
                )
            response_status = response.status_code
            response_snippet = response.text[:_RESPONSE_SNIPPET_BYTES]
            if 200 <= response.status_code < 300:
                await deliveries.mark_delivered(
                    delivery,
                    response_status_code=response.status_code,
                    response_body_snippet=response_snippet,
                )
                await db_session.commit()
                return {"delivery_id": delivery_id, "status": "delivered"}
            error_message = f"Non-2xx response: {response.status_code}"
        except httpx.HTTPError as exc:
            error_message = f"Transport error: {exc}"
        except Exception as exc:  # noqa: BLE001
            error_message = f"Unexpected delivery error: {exc}"

        backoff = _backoff_for_attempt(delivery.attempt_count)
        next_attempt_at = datetime.now(UTC) + backoff if backoff is not None else None
        await deliveries.mark_failed(
            delivery,
            response_status_code=response_status,
            response_body_snippet=response_snippet,
            error_message=error_message or "Delivery failed",
            next_attempt_at=next_attempt_at,
        )
        await db_session.commit()

        if next_attempt_at is not None:
            queue_webhook_delivery(delivery.id, delay=backoff)
            return {"delivery_id": delivery_id, "status": "retry"}
        return {"delivery_id": delivery_id, "status": "failed"}


def queue_webhook_delivery(
    delivery_id: uuid.UUID,
    settings: Settings | None = None,
    queue_name: str = "webhook_delivery",
    delay: timedelta | None = None,
) -> str:
    """Enqueue a delivery job.

    When ``delay`` is non-None we use RQ's scheduler-friendly
    ``enqueue_in`` so the worker doesn't pull a row before its backoff
    window elapses.
    """
    queue = get_webhook_delivery_queue(settings, queue_name)
    if delay is not None:
        rq_job = queue.enqueue_in(
            delay,
            "src.workers.webhook_delivery_worker.process_webhook_delivery_job_sync",
            str(delivery_id),
            job_timeout="5m",
            result_ttl=86400,
            failure_ttl=86400,
        )
    else:
        rq_job = queue.enqueue(
            "src.workers.webhook_delivery_worker.process_webhook_delivery_job_sync",
            str(delivery_id),
            job_timeout="5m",
            result_ttl=86400,
            failure_ttl=86400,
        )
    logger.info("Queued webhook delivery %s as RQ job %s", delivery_id, rq_job.id)
    return str(rq_job.id)


def process_webhook_delivery_job_sync(delivery_id: str) -> dict[str, Any]:
    """RQ-callable sync wrapper."""
    import asyncio

    from src.core.database import init_database

    settings = get_settings()
    init_database(settings)
    return asyncio.run(process_webhook_delivery_job(delivery_id))
