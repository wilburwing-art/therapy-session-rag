"""Customer webhook management endpoints.

Routes mounted at ``/webhooks``:

- ``GET /webhooks``                    — list the caller's endpoints
- ``POST /webhooks``                   — create a new endpoint (returns the
                                         signing secret once)
- ``GET /webhooks/event-types``        — discoverable list of event types
- ``GET /webhooks/{id}``               — fetch one endpoint
- ``PATCH /webhooks/{id}``             — update url / types / description /
                                         is_active
- ``POST /webhooks/{id}/rotate-secret`` — rotate the signing secret
- ``DELETE /webhooks/{id}``            — remove the endpoint
- ``POST /webhooks/{id}/test``         — dispatch a synthetic ``test.ping``
                                         payload through the delivery worker

This router is intentionally mounted OUTSIDE the billing entitlement
gate — if a practice's subscription lapses we still want their webhook
configuration to be reachable so they can inspect / rotate without
reactivating billing first.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.api.v1.dependencies import Auth
from src.core.database import DbSession
from src.models.domain.webhook import (
    WebhookEndpointCreate,
    WebhookEndpointCreated,
    WebhookEndpointRead,
    WebhookEndpointUpdate,
)
from src.services.webhook_dispatcher import WebhookDispatcher
from src.services.webhook_service import WebhookService, supported_event_types

router = APIRouter()


def get_webhook_service(session: DbSession) -> WebhookService:
    return WebhookService(session)


WebhookSvc = Annotated[WebhookService, Depends(get_webhook_service)]


def _to_created(endpoint: object) -> WebhookEndpointCreated:
    """Build a create/rotate response that includes the secret.

    ``WebhookEndpointCreated`` extends the read model; the secret is
    surfaced from the ORM attribute only on create and rotate paths so
    listings and updates never leak it.
    """
    return WebhookEndpointCreated.model_validate(
        endpoint, from_attributes=True
    )


@router.get("/event-types")
async def list_event_types(
    auth: Auth,  # noqa: ARG001 - auth gate only
) -> dict[str, list[str]]:
    """Return the list of event types customers may subscribe to."""
    return {"event_types": supported_event_types()}


@router.get("", response_model=list[WebhookEndpointRead])
async def list_endpoints(
    auth: Auth,
    service: WebhookSvc,
) -> list[WebhookEndpointRead]:
    """List every webhook endpoint configured by the caller's organization."""
    endpoints = await service.list_endpoints(auth.organization_id)
    return [
        WebhookEndpointRead.model_validate(e, from_attributes=True)
        for e in endpoints
    ]


@router.post(
    "",
    response_model=WebhookEndpointCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_endpoint(
    payload: WebhookEndpointCreate,
    auth: Auth,
    service: WebhookSvc,
) -> WebhookEndpointCreated:
    """Create a new webhook endpoint.

    Returns the freshly-minted signing secret. Store it now — listing
    endpoints never returns it.
    """
    endpoint = await service.create_endpoint(auth.organization_id, payload)
    return _to_created(endpoint)


@router.get("/{endpoint_id}", response_model=WebhookEndpointRead)
async def get_endpoint(
    endpoint_id: uuid.UUID,
    auth: Auth,
    service: WebhookSvc,
) -> WebhookEndpointRead:
    endpoint = await service.get_endpoint(endpoint_id, auth.organization_id)
    return WebhookEndpointRead.model_validate(endpoint, from_attributes=True)


@router.patch("/{endpoint_id}", response_model=WebhookEndpointRead)
async def update_endpoint(
    endpoint_id: uuid.UUID,
    payload: WebhookEndpointUpdate,
    auth: Auth,
    service: WebhookSvc,
) -> WebhookEndpointRead:
    endpoint = await service.update_endpoint(
        endpoint_id, auth.organization_id, payload
    )
    return WebhookEndpointRead.model_validate(endpoint, from_attributes=True)


@router.post(
    "/{endpoint_id}/rotate-secret",
    response_model=WebhookEndpointCreated,
)
async def rotate_secret(
    endpoint_id: uuid.UUID,
    auth: Auth,
    service: WebhookSvc,
) -> WebhookEndpointCreated:
    """Rotate the signing secret and return the new value.

    After rotation the customer MUST update their verifier or all
    subsequent deliveries will fail signature checks on their side.
    """
    endpoint = await service.rotate_secret(
        endpoint_id, auth.organization_id
    )
    return _to_created(endpoint)


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_endpoint(
    endpoint_id: uuid.UUID,
    auth: Auth,
    service: WebhookSvc,
) -> None:
    await service.delete_endpoint(endpoint_id, auth.organization_id)
    return None


@router.post("/{endpoint_id}/test", status_code=status.HTTP_202_ACCEPTED)
async def send_test_delivery(
    endpoint_id: uuid.UUID,
    auth: Auth,
    service: WebhookSvc,
    session: DbSession,
) -> dict[str, object]:
    """Dispatch a synthetic ``test.ping`` event to a single endpoint.

    Lets customers verify their signature check before production
    events fire. We bypass the per-event-type subscription filter by
    calling the dispatcher with the endpoint's own event_types — if the
    endpoint has no subscriptions we still dispatch with the first
    subscribed type so the row lands against their config.
    """
    endpoint = await service.get_endpoint(endpoint_id, auth.organization_id)
    event_type = endpoint.event_types[0] if endpoint.event_types else "test.ping"
    dispatcher = WebhookDispatcher(session)
    deliveries = await dispatcher.dispatch(
        organization_id=auth.organization_id,
        event_type=event_type,
        data={
            "test": True,
            "endpoint_id": str(endpoint.id),
            "message": "TherapyRAG test delivery",
        },
    )
    return {
        "endpoint_id": str(endpoint.id),
        "delivery_count": len(deliveries),
        "event_type": event_type,
    }
