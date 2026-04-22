"""Stripe billing integration for therapist subscriptions.

Thin wrapper over the Stripe SDK that handles:
- Creating customers on first checkout
- Generating Checkout Session URLs (used by the signup/billing UI)
- Generating Customer Portal URLs (cancel, update card, invoices)
- Processing webhooks to mirror subscription state into Postgres

Stripe mutations are isolated here so the rest of the app depends only
on the `Organization.subscription_status` column.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Protocol

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.exceptions import AppError, NotFoundError
from src.models.db.organization import Organization, SubscriptionStatus

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


class _RealStripeGateway:
    """Adapter wrapping the `stripe` SDK to match StripeGateway."""

    def __init__(self, api_key: str) -> None:
        self._client = stripe.StripeClient(api_key)

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
