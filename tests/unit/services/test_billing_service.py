"""Tests for BillingService Stripe integration."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import stripe

from src.core.exceptions import NotFoundError
from src.models.db.organization import Organization, SubscriptionStatus
from src.services.billing_service import BillingService, BillingServiceError


def _mock_settings() -> MagicMock:
    s = MagicMock()
    s.stripe_secret_key = "sk_test_fake"
    s.stripe_webhook_secret = "whsec_fake"
    s.stripe_price_id = "price_fake"
    s.stripe_trial_days = 14
    s.stripe_success_url = "https://example.com/ok"
    s.stripe_cancel_url = "https://example.com/cancel"
    s.stripe_portal_return_url = "https://example.com/billing"
    return s


def _mock_org(
    org_id: uuid.UUID | None = None,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    status: SubscriptionStatus = SubscriptionStatus.NONE,
) -> Organization:
    org = MagicMock(spec=Organization)
    org.id = org_id or uuid.uuid4()
    org.name = "Test Practice"
    org.stripe_customer_id = stripe_customer_id
    org.stripe_subscription_id = stripe_subscription_id
    org.subscription_status = status
    org.trial_ends_at = None
    org.current_period_end = None
    return org


@pytest.fixture
def service() -> BillingService:
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    gateway = MagicMock()
    return BillingService(
        db_session=db,
        settings=_mock_settings(),
        gateway=gateway,
    )


def _execute_returning(service: BillingService, value: object) -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalar_one.return_value = value
    service.db_session.execute = AsyncMock(return_value=result)


@pytest.mark.asyncio
async def test_checkout_session_creates_customer_on_first_call(
    service: BillingService,
) -> None:
    org = _mock_org()
    _execute_returning(service, org)

    service.gateway.create_customer.return_value = SimpleNamespace(id="cus_new")
    service.gateway.create_checkout_session.return_value = SimpleNamespace(
        url="https://checkout.stripe.com/fake"
    )

    url = await service.create_checkout_session_url(
        organization_id=org.id,
        therapist_email="t@example.com",
    )
    assert url == "https://checkout.stripe.com/fake"
    service.gateway.create_customer.assert_called_once()
    assert org.stripe_customer_id == "cus_new"


@pytest.mark.asyncio
async def test_checkout_session_reuses_existing_customer(
    service: BillingService,
) -> None:
    org = _mock_org(stripe_customer_id="cus_existing")
    _execute_returning(service, org)

    service.gateway.create_checkout_session.return_value = SimpleNamespace(
        url="https://checkout.stripe.com/fake"
    )

    await service.create_checkout_session_url(
        organization_id=org.id, therapist_email="t@example.com"
    )
    service.gateway.create_customer.assert_not_called()


@pytest.mark.asyncio
async def test_checkout_raises_when_org_missing(service: BillingService) -> None:
    _execute_returning(service, None)
    with pytest.raises(NotFoundError):
        await service.create_checkout_session_url(
            organization_id=uuid.uuid4(), therapist_email="t@example.com"
        )


@pytest.mark.asyncio
async def test_portal_requires_existing_stripe_customer(
    service: BillingService,
) -> None:
    org = _mock_org()
    _execute_returning(service, org)
    with pytest.raises(BillingServiceError):
        await service.create_portal_session_url(org.id)


@pytest.mark.asyncio
async def test_portal_returns_url_when_customer_exists(
    service: BillingService,
) -> None:
    org = _mock_org(stripe_customer_id="cus_123")
    _execute_returning(service, org)
    service.gateway.create_portal_session.return_value = SimpleNamespace(
        url="https://billing.stripe.com/fake"
    )
    url = await service.create_portal_session_url(org.id)
    assert url.startswith("https://billing.stripe.com/")


@pytest.mark.asyncio
async def test_webhook_invalid_signature_raises(service: BillingService) -> None:
    service.gateway.construct_event.side_effect = stripe.SignatureVerificationError(
        "bad", sig_header="sig"
    )
    with pytest.raises(BillingServiceError):
        await service.handle_webhook(payload=b"{}", signature="sig")


@pytest.mark.asyncio
async def test_webhook_subscription_updated_mirrors_state(
    service: BillingService,
) -> None:
    org = _mock_org(stripe_customer_id="cus_456")
    _execute_returning(service, org)

    trial_end = int(datetime(2026, 5, 1, tzinfo=UTC).timestamp())
    period_end = int(datetime(2026, 5, 14, tzinfo=UTC).timestamp())

    service.gateway.construct_event.return_value = {
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_123",
                "customer": "cus_456",
                "status": "trialing",
                "trial_end": trial_end,
                "current_period_end": period_end,
            }
        },
    }

    result = await service.handle_webhook(payload=b"{}", signature="sig")
    assert result["type"] == "customer.subscription.updated"
    assert org.subscription_status == SubscriptionStatus.TRIALING
    assert org.stripe_subscription_id == "sub_123"
    assert org.trial_ends_at is not None
    assert org.current_period_end is not None


@pytest.mark.asyncio
async def test_webhook_checkout_completed_links_subscription(
    service: BillingService,
) -> None:
    org = _mock_org()
    _execute_returning(service, org)
    service.gateway.construct_event.return_value = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": str(org.id),
                "subscription": "sub_new",
                "customer": "cus_new",
            }
        },
    }
    await service.handle_webhook(payload=b"{}", signature="sig")
    assert org.stripe_subscription_id == "sub_new"
    assert org.stripe_customer_id == "cus_new"


@pytest.mark.asyncio
async def test_webhook_ignores_unknown_event(service: BillingService) -> None:
    service.gateway.construct_event.return_value = {
        "type": "invoice.paid",
        "data": {"object": {}},
    }
    result = await service.handle_webhook(payload=b"{}", signature="sig")
    assert result == {"received": True, "type": "invoice.paid"}
