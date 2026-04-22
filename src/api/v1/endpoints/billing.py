"""Billing endpoints: Stripe checkout, customer portal, webhook, status."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from src.api.v1.dependencies import CurrentTherapist
from src.core.database import DbSession
from src.core.exceptions import UnauthorizedError
from src.models.domain.billing import (
    CheckoutSessionResponse,
    PortalSessionResponse,
    SubscriptionStatusResponse,
)
from src.services.billing_service import BillingService

router = APIRouter()


def get_billing_service(session: DbSession) -> BillingService:
    return BillingService(session)


BillingSvc = Annotated[BillingService, Depends(get_billing_service)]


@router.post("/checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    billing: BillingSvc,
    therapist: CurrentTherapist,
) -> CheckoutSessionResponse:
    """Start a Stripe Checkout for the authenticated therapist's practice."""
    url = await billing.create_checkout_session_url(
        organization_id=therapist.organization_id,
        therapist_email=therapist.email,
    )
    return CheckoutSessionResponse(url=url)


@router.post("/portal-session", response_model=PortalSessionResponse)
async def create_portal_session(
    billing: BillingSvc,
    therapist: CurrentTherapist,
) -> PortalSessionResponse:
    """Open the Stripe Customer Portal (cancel, update card, invoices)."""
    url = await billing.create_portal_session_url(therapist.organization_id)
    return PortalSessionResponse(url=url)


@router.get("/subscription", response_model=SubscriptionStatusResponse)
async def get_subscription_status(
    therapist: CurrentTherapist,
    billing: BillingSvc,  # noqa: ARG001 - kept for future expansion  # pragma: no cover
) -> SubscriptionStatusResponse:
    from sqlalchemy import select

    from src.models.db.organization import Organization

    result = await billing.db_session.execute(
        select(Organization).where(Organization.id == therapist.organization_id)
    )
    org = result.scalar_one()
    return SubscriptionStatusResponse(
        subscription_status=org.subscription_status.value,
        trial_ends_at=org.trial_ends_at,
        current_period_end=org.current_period_end,
        has_stripe_customer=org.stripe_customer_id is not None,
        is_entitled=org.is_entitled(),
    )


@router.post("/webhook", status_code=200)
async def stripe_webhook(
    request: Request,
    billing: BillingSvc,
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
) -> dict[str, object]:
    """Receive Stripe subscription lifecycle events.

    Signature verification uses the configured webhook secret; requests
    without a valid signature are rejected with 401.
    """
    if not stripe_signature:
        raise UnauthorizedError("Missing Stripe-Signature header")
    payload = await request.body()
    return await billing.handle_webhook(payload=payload, signature=stripe_signature)
