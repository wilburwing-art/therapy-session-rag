"""Stripe billing integration for therapist subscriptions.

Thin wrapper over the Stripe SDK that handles:
- Creating customers on first checkout
- Generating Checkout Session URLs (used by the signup/billing UI)
- Generating Customer Portal URLs (cancel, update card, invoices)
- Processing webhooks to mirror subscription state into Postgres
- Metered billing: recording per-session usage and reporting to Stripe
- Subscription item quantity updates (e.g. seat count changes)
- Preview invoice rendering for upcoming charges

Stripe mutations are isolated here so the rest of the app depends only
on the `Organization.subscription_status` column and `BillingUsage`
counters.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

import stripe
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.exceptions import AppError, NotFoundError
from src.models.db.billing_usage import BillingUsage
from src.models.db.organization import Organization, SubscriptionStatus
from src.models.db.user import User, UserRole

logger = logging.getLogger(__name__)


_STATUS_MAP: dict[str, SubscriptionStatus] = {
    "trialing": SubscriptionStatus.TRIALING,
    "active": SubscriptionStatus.ACTIVE,
    "past_due": SubscriptionStatus.PAST_DUE,
    "incomplete": SubscriptionStatus.INCOMPLETE,
    "incomplete_expired": SubscriptionStatus.CANCELED,
    "unpaid": SubscriptionStatus.UNPAID,
    "canceled": SubscriptionStatus.CANCELED,
    "paused": SubscriptionStatus.PAST_DUE,
}


# Metered billing event names as registered with Stripe meters.
METER_EVENT_SESSIONS_TRANSCRIBED = "sessions_transcribed"
METER_EVENT_RECAPS_GENERATED = "recaps_generated"
METER_EVENT_CHAT_MESSAGES = "chat_messages"


class BillingServiceError(AppError):
    """Billing operation failed (Stripe error, misconfig, etc.)."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            title="Billing Error",
            detail=detail,
            status_code=502,
            error_type="about:blank#billing-error",
        )


class StripeGateway(Protocol):
    """Protocol over the Stripe SDK; makes the service testable."""

    def create_customer(self, *, name: str, email: str, metadata: dict[str, str]) -> Any: ...
    def create_checkout_session(
        self,
        *,
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        trial_days: int,
        client_reference_id: str,
    ) -> Any: ...
    def create_portal_session(self, *, customer_id: str, return_url: str) -> Any: ...
    def construct_event(self, payload: bytes, sig_header: str, secret: str) -> Any: ...
    def create_meter_event(
        self,
        *,
        event_name: str,
        stripe_customer_id: str,
        value: int,
        identifier: str,
        timestamp: int | None = None,
    ) -> Any: ...
    def update_subscription_item_quantity(
        self,
        *,
        subscription_item_id: str,
        quantity: int,
    ) -> Any: ...
    def preview_upcoming_invoice(self, *, customer_id: str) -> Any: ...


class _RealStripeGateway:
    """Adapter wrapping the `stripe` SDK to match StripeGateway."""

    def __init__(self, api_key: str) -> None:
        self._client = stripe.StripeClient(api_key)
        self._api_key = api_key

    def create_customer(self, *, name: str, email: str, metadata: dict[str, str]) -> Any:
        return self._client.customers.create(
            params={"name": name, "email": email, "metadata": metadata}
        )

    def create_checkout_session(
        self,
        *,
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        trial_days: int,
        client_reference_id: str,
    ) -> Any:
        return self._client.checkout.sessions.create(
            params={
                "mode": "subscription",
                "customer": customer_id,
                "line_items": [{"price": price_id, "quantity": 1}],
                "success_url": success_url,
                "cancel_url": cancel_url,
                "client_reference_id": client_reference_id,
                "subscription_data": {"trial_period_days": trial_days},
                "allow_promotion_codes": True,
            }
        )

    def create_portal_session(self, *, customer_id: str, return_url: str) -> Any:
        return self._client.billing_portal.sessions.create(
            params={"customer": customer_id, "return_url": return_url}
        )

    def construct_event(self, payload: bytes, sig_header: str, secret: str) -> Any:
        return stripe.Webhook.construct_event(  # type: ignore[no-untyped-call]
            payload=payload, sig_header=sig_header, secret=secret
        )

    def create_meter_event(
        self,
        *,
        event_name: str,
        stripe_customer_id: str,
        value: int,
        identifier: str,
        timestamp: int | None = None,
    ) -> Any:
        """Report a metered usage event to Stripe.

        Requires the Stripe billing-meters API (released 2024). If the
        installed SDK lacks `stripe.billing.MeterEvent.create`, raises
        a BillingServiceError so callers degrade gracefully.
        """
        meter_event_cls = getattr(
            getattr(stripe, "billing", None), "MeterEvent", None
        )
        if meter_event_cls is None or not hasattr(meter_event_cls, "create"):
            raise BillingServiceError(
                "Stripe SDK is missing billing.MeterEvent.create; "
                "upgrade to a version that supports the 2024 meters API."
            )
        payload: dict[str, Any] = {
            "event_name": event_name,
            "payload": {
                "stripe_customer_id": stripe_customer_id,
                "value": str(value),
            },
            "identifier": identifier,
        }
        if timestamp is not None:
            payload["timestamp"] = timestamp
        return meter_event_cls.create(api_key=self._api_key, **payload)

    def update_subscription_item_quantity(
        self,
        *,
        subscription_item_id: str,
        quantity: int,
    ) -> Any:
        return stripe.SubscriptionItem.modify(
            subscription_item_id,
            api_key=self._api_key,
            quantity=quantity,
            proration_behavior="create_prorations",
        )

    def preview_upcoming_invoice(self, *, customer_id: str) -> Any:
        # Stripe 2024 renamed Invoice.upcoming -> Invoice.create_preview;
        # fall back to the older endpoint if the new one is missing so
        # we work across SDK versions.
        create_preview = getattr(stripe.Invoice, "create_preview", None)
        if callable(create_preview):
            return create_preview(api_key=self._api_key, customer=customer_id)
        upcoming = getattr(stripe.Invoice, "upcoming", None)
        if callable(upcoming):
            return upcoming(api_key=self._api_key, customer=customer_id)
        raise BillingServiceError(
            "Stripe SDK is missing Invoice.create_preview and Invoice.upcoming."
        )


class BillingService:
    """Subscription lifecycle for therapist practices."""

    def __init__(
        self,
        db_session: AsyncSession,
        settings: Settings | None = None,
        gateway: StripeGateway | None = None,
    ) -> None:
        self.db_session = db_session
        self.settings = settings or get_settings()
        self._gateway = gateway

    @property
    def gateway(self) -> StripeGateway:
        if self._gateway is None:
            self._gateway = _RealStripeGateway(self.settings.stripe_secret_key)
        return self._gateway

    async def _get_organization(self, org_id: Any) -> Organization:
        result = await self.db_session.execute(
            select(Organization).where(Organization.id == org_id)
        )
        org = result.scalar_one_or_none()
        if org is None:
            raise NotFoundError(resource="Organization", resource_id=str(org_id))
        return org

    async def _ensure_stripe_customer(
        self, org: Organization, therapist_email: str
    ) -> str:
        """Create a Stripe customer for this org if one doesn't exist yet."""
        if org.stripe_customer_id:
            return org.stripe_customer_id
        try:
            customer = self.gateway.create_customer(
                name=org.name,
                email=therapist_email,
                metadata={"organization_id": str(org.id)},
            )
        except stripe.StripeError as exc:
            raise BillingServiceError(f"Stripe customer creation failed: {exc}") from exc

        org.stripe_customer_id = str(customer.id)
        await self.db_session.flush()
        return str(customer.id)

    async def create_checkout_session_url(
        self,
        organization_id: Any,
        therapist_email: str,
    ) -> str:
        """Return a one-time Stripe Checkout URL for the org's subscription."""
        org = await self._get_organization(organization_id)
        customer_id = await self._ensure_stripe_customer(org, therapist_email)
        try:
            session = self.gateway.create_checkout_session(
                customer_id=customer_id,
                price_id=self.settings.stripe_price_id,
                success_url=self.settings.stripe_success_url,
                cancel_url=self.settings.stripe_cancel_url,
                trial_days=self.settings.stripe_trial_days,
                client_reference_id=str(org.id),
            )
        except stripe.StripeError as exc:
            raise BillingServiceError(f"Stripe checkout failed: {exc}") from exc

        url = getattr(session, "url", None)
        if not isinstance(url, str):
            raise BillingServiceError("Stripe did not return a checkout URL")
        return str(url)

    async def create_portal_session_url(self, organization_id: Any) -> str:
        """Return a one-time Stripe Customer Portal URL for the org."""
        org = await self._get_organization(organization_id)
        if not org.stripe_customer_id:
            raise BillingServiceError(
                "Practice has no Stripe customer yet; start a checkout first"
            )
        try:
            session = self.gateway.create_portal_session(
                customer_id=org.stripe_customer_id,
                return_url=self.settings.stripe_portal_return_url,
            )
        except stripe.StripeError as exc:
            raise BillingServiceError(f"Stripe portal failed: {exc}") from exc
        url = getattr(session, "url", None)
        if not isinstance(url, str):
            raise BillingServiceError("Stripe did not return a portal URL")
        return url

    async def handle_webhook(
        self, payload: bytes, signature: str
    ) -> dict[str, Any]:
        """Verify and process a Stripe webhook event.

        Only subscription.* events are acted on; other event types are
        acknowledged but ignored.
        """
        try:
            event = self.gateway.construct_event(
                payload=payload,
                sig_header=signature,
                secret=self.settings.stripe_webhook_secret,
            )
        except stripe.SignatureVerificationError as exc:
            raise BillingServiceError(f"Invalid webhook signature: {exc}") from exc
        except Exception as exc:
            raise BillingServiceError(f"Malformed webhook payload: {exc}") from exc

        event_type = event["type"]
        data_object = event["data"]["object"]
        logger.info("Stripe webhook received: %s", event_type)

        if event_type.startswith("customer.subscription."):
            await self._apply_subscription_update(data_object)
        elif event_type == "checkout.session.completed":
            await self._apply_checkout_completion(data_object)

        return {"received": True, "type": event_type}

    async def _apply_checkout_completion(self, session_object: Any) -> None:
        """Link a fresh subscription back to the org record on first checkout."""
        org_id = session_object.get("client_reference_id")
        subscription_id = session_object.get("subscription")
        customer_id = session_object.get("customer")
        if not org_id or not subscription_id:
            return
        org = await self._get_organization(org_id)
        org.stripe_subscription_id = subscription_id
        if customer_id and not org.stripe_customer_id:
            org.stripe_customer_id = customer_id
        await self.db_session.flush()

    async def _apply_subscription_update(self, subscription: Any) -> None:
        """Mirror Stripe's subscription state into the org record."""
        customer_id = subscription.get("customer")
        if not customer_id:
            return

        result = await self.db_session.execute(
            select(Organization).where(Organization.stripe_customer_id == customer_id)
        )
        org = result.scalar_one_or_none()
        if org is None:
            logger.warning(
                "Received Stripe subscription update for unknown customer %s",
                customer_id,
            )
            return

        raw_status = subscription.get("status") or "canceled"
        org.subscription_status = _STATUS_MAP.get(raw_status, SubscriptionStatus.CANCELED)
        org.stripe_subscription_id = subscription.get("id") or org.stripe_subscription_id

        trial_end = subscription.get("trial_end")
        org.trial_ends_at = (
            datetime.fromtimestamp(trial_end, tz=UTC) if trial_end else None
        )
        period_end = subscription.get("current_period_end")
        org.current_period_end = (
            datetime.fromtimestamp(period_end, tz=UTC) if period_end else None
        )
        await self.db_session.flush()
        logger.info(
            "Synced org %s subscription: status=%s",
            org.id,
            org.subscription_status,
        )

    # ------------------------------------------------------------------
    # Metered billing
    # ------------------------------------------------------------------

    async def _current_usage_row(
        self,
        organization_id: uuid.UUID,
        *,
        now: datetime | None = None,
        org: Organization | None = None,
    ) -> BillingUsage:
        """Return (creating if needed) the BillingUsage row for the period
        containing `now`.

        Callers that already have the Organization loaded may pass it
        via ``org`` to avoid a second DB lookup.

        Period boundaries are derived from the org's
        `current_period_end` when available; otherwise the fallback
        window is a 30-day anchor starting at the org's creation.
        """
        if org is None:
            org = await self._get_organization(organization_id)
        timestamp = now or datetime.now(UTC)
        period_start, period_end = _period_bounds_for(org, timestamp)

        result = await self.db_session.execute(
            select(BillingUsage).where(
                BillingUsage.organization_id == organization_id,
                BillingUsage.period_start == period_start,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = BillingUsage(
                organization_id=organization_id,
                period_start=period_start,
                period_end=period_end,
                sessions_transcribed=0,
                recaps_generated=0,
                chat_messages=0,
            )
            self.db_session.add(row)
            await self.db_session.flush()
        return row

    async def record_sessions_transcribed(
        self,
        organization_id: uuid.UUID,
        *,
        count: int = 1,
        now: datetime | None = None,
    ) -> BillingUsage:
        """Increment the sessions_transcribed counter for the current period.

        Best-effort: DB update is authoritative, Stripe reporting happens
        at period close. Raising here would fail the upstream worker,
        so errors from Stripe are swallowed and logged.
        """
        if count < 1:
            raise ValueError("count must be >= 1")
        row = await self._current_usage_row(organization_id, now=now)
        row.sessions_transcribed += count
        await self.db_session.flush()
        return row

    async def record_recaps_generated(
        self,
        organization_id: uuid.UUID,
        *,
        count: int = 1,
        now: datetime | None = None,
    ) -> BillingUsage:
        if count < 1:
            raise ValueError("count must be >= 1")
        row = await self._current_usage_row(organization_id, now=now)
        row.recaps_generated += count
        await self.db_session.flush()
        return row

    async def record_chat_messages(
        self,
        organization_id: uuid.UUID,
        *,
        count: int = 1,
        now: datetime | None = None,
    ) -> BillingUsage:
        if count < 1:
            raise ValueError("count must be >= 1")
        row = await self._current_usage_row(organization_id, now=now)
        row.chat_messages += count
        await self.db_session.flush()
        return row

    async def report_usage_to_stripe(
        self,
        organization_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> BillingUsage:
        """Push the current period's counters to Stripe as meter events.

        Called at period close. Safe to re-run: uses a deterministic
        identifier so Stripe dedupes repeat calls.
        """
        org = await self._get_organization(organization_id)
        if not org.stripe_customer_id:
            raise BillingServiceError(
                "Org has no Stripe customer; cannot report metered usage."
            )
        row = await self._current_usage_row(organization_id, now=now, org=org)

        events = (
            (METER_EVENT_SESSIONS_TRANSCRIBED, row.sessions_transcribed),
            (METER_EVENT_RECAPS_GENERATED, row.recaps_generated),
            (METER_EVENT_CHAT_MESSAGES, row.chat_messages),
        )
        reported_at = now or datetime.now(UTC)
        last_event_id: str | None = None
        for event_name, value in events:
            if value <= 0:
                continue
            identifier = f"usage:{row.id}:{event_name}"
            try:
                event = self.gateway.create_meter_event(
                    event_name=event_name,
                    stripe_customer_id=org.stripe_customer_id,
                    value=value,
                    identifier=identifier,
                    timestamp=int(reported_at.timestamp()),
                )
            except stripe.StripeError as exc:
                raise BillingServiceError(
                    f"Stripe meter event '{event_name}' failed: {exc}"
                ) from exc
            event_id = getattr(event, "identifier", None) or getattr(
                event, "id", None
            )
            if isinstance(event_id, str):
                last_event_id = event_id

        row.reported_to_stripe_at = reported_at
        if last_event_id is not None:
            row.stripe_meter_event_id = last_event_id
        await self.db_session.flush()
        return row

    # ------------------------------------------------------------------
    # Seats & subscription item quantity
    # ------------------------------------------------------------------

    async def count_active_seats(self, organization_id: uuid.UUID) -> int:
        """Number of therapist/admin seats currently in use for the org."""
        stmt = select(func.count(User.id)).where(
            User.organization_id == organization_id,
            User.role.in_([UserRole.THERAPIST, UserRole.ADMIN]),
        )
        result = await self.db_session.execute(stmt)
        raw = result.scalar()
        return int(raw or 0)

    async def sync_subscription_seats(
        self,
        organization_id: uuid.UUID,
        *,
        subscription_item_id: str,
    ) -> int:
        """Push the current seat count to Stripe's subscription item.

        Returns the seat count that was reported.
        """
        seats = await self.count_active_seats(organization_id)
        try:
            self.gateway.update_subscription_item_quantity(
                subscription_item_id=subscription_item_id,
                quantity=seats,
            )
        except stripe.StripeError as exc:
            raise BillingServiceError(
                f"Stripe subscription item quantity update failed: {exc}"
            ) from exc
        return seats

    async def preview_upcoming_invoice(
        self, organization_id: uuid.UUID
    ) -> dict[str, Any]:
        """Return a summary of the customer's next invoice.

        Used by the billing page to show users an upfront preview of
        their metered charges and any proration from seat changes.
        """
        org = await self._get_organization(organization_id)
        if not org.stripe_customer_id:
            raise BillingServiceError(
                "Practice has no Stripe customer yet; start a checkout first"
            )
        try:
            invoice = self.gateway.preview_upcoming_invoice(
                customer_id=org.stripe_customer_id,
            )
        except stripe.StripeError as exc:
            raise BillingServiceError(
                f"Stripe preview invoice failed: {exc}"
            ) from exc

        amount_due = _invoice_field(invoice, "amount_due")
        amount_total = _invoice_field(invoice, "total")
        currency = _invoice_field(invoice, "currency")
        period_end = _invoice_field(invoice, "period_end")
        return {
            "amount_due": int(amount_due) if amount_due is not None else 0,
            "amount_total": int(amount_total) if amount_total is not None else 0,
            "currency": str(currency) if currency is not None else "usd",
            "period_end": (
                datetime.fromtimestamp(int(period_end), tz=UTC)
                if period_end is not None
                else None
            ),
        }


def _period_bounds_for(
    org: Organization, now: datetime
) -> tuple[datetime, datetime]:
    """Return the (period_start, period_end) window that contains `now`.

    Prefers the Stripe-synced `current_period_end` when available. If
    not (e.g. no active subscription yet), rolls a calendar-month
    window anchored on the 1st of the month of `now`.
    """
    period_end = org.current_period_end
    if period_end is not None:
        # Assume monthly cadence: period_start = period_end - 30 days.
        # This matches Stripe billing cycles for all of our price tiers.
        period_start = period_end.replace(hour=0, minute=0, second=0, microsecond=0)
        # If `now` is still before the current period_end, shift back 30 days.
        if period_start > now:
            from datetime import timedelta

            period_start = period_end - timedelta(days=30)
        return period_start, period_end

    # Fallback: current calendar month in UTC.
    start = datetime(now.year, now.month, 1, tzinfo=UTC)
    # End of month: first of next month minus 1 microsecond.
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1, tzinfo=UTC)
    else:
        next_month = datetime(now.year, now.month + 1, 1, tzinfo=UTC)
    return start, next_month


def _invoice_field(invoice: Any, key: str) -> Any:
    """Fetch a field off a Stripe invoice-like object, supporting both
    dict and attribute access."""
    if isinstance(invoice, dict):
        return invoice.get(key)
    return getattr(invoice, key, None)
