"""Billing endpoints: Stripe checkout, customer portal, webhook, status."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select

from src.api.v1.dependencies import CurrentTherapist
from src.core.database import DbSession
from src.core.exceptions import UnauthorizedError
from src.models.db.billing_usage import BillingUsage
from src.models.domain.billing import (
    BillingUsageResponse,
    CheckoutSessionResponse,
    PortalSessionResponse,
    SubscriptionStatusResponse,
    UpcomingInvoiceResponse,
)
from src.services.billing_service import BillingService

router = APIRouter()


# Seats included per tier. Surfaced in the UI alongside the live seat
# count so therapists can see how close they are to the plan limit.
_TIER_SEATS: dict[str, int] = {
    "starter": 1,
    "pro": 5,
    "scale": 50,
}


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


@router.get("/usage", response_model=BillingUsageResponse)
async def get_current_usage(
    therapist: CurrentTherapist,
    billing: BillingSvc,
) -> BillingUsageResponse:
    """Return the caller org's current-period metered usage and seats."""
    now = datetime.now(UTC)
    # Read the row if it exists; don't create one implicitly for a plain
    # GET. A missing row just means no billable activity this period.
    result = await billing.db_session.execute(
        select(BillingUsage)
        .where(BillingUsage.organization_id == therapist.organization_id)
        .order_by(BillingUsage.period_start.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()

    seats_used = await billing.count_active_seats(therapist.organization_id)
    # Best-effort tier inference: the pro tier is the default ceiling
    # until per-org tier columns exist. Webhooks-engineer + orchestrator
    # may add a dedicated tier column in a later round.
    seats_included = _TIER_SEATS["pro"]

    if row is None:
        # Fall back to a synthetic zero-usage row so the UI still has
        # meaningful period bounds to render.
        from src.models.db.organization import Organization
        from src.services.billing_service import _period_bounds_for

        org_row = await billing.db_session.execute(
            select(Organization).where(Organization.id == therapist.organization_id)
        )
        org = org_row.scalar_one()
        period_start, period_end = _period_bounds_for(org, now)
        return BillingUsageResponse(
            period_start=period_start,
            period_end=period_end,
            sessions_transcribed=0,
            recaps_generated=0,
            chat_messages=0,
            seats_used=seats_used,
            seats_included=seats_included,
        )

    return BillingUsageResponse(
        period_start=row.period_start,
        period_end=row.period_end,
        sessions_transcribed=row.sessions_transcribed,
        recaps_generated=row.recaps_generated,
        chat_messages=row.chat_messages,
        seats_used=seats_used,
        seats_included=seats_included,
    )


@router.get("/upcoming-invoice", response_model=UpcomingInvoiceResponse)
async def get_upcoming_invoice(
    therapist: CurrentTherapist,
    billing: BillingSvc,
) -> UpcomingInvoiceResponse:
    """Preview the therapist's next Stripe invoice (metered + subscription)."""
    preview = await billing.preview_upcoming_invoice(therapist.organization_id)
    return UpcomingInvoiceResponse(
        amount_due=int(preview["amount_due"]),
        amount_total=int(preview["amount_total"]),
        currency=str(preview["currency"]),
        period_end=preview["period_end"],
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
