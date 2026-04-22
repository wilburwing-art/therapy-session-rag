"""Unit tests for Billing API endpoints.

Mounts the billing router in isolation and stubs out the BillingService
so we can drive response codes, webhook paths, and the subscription-
status view without needing Stripe or Postgres.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.dependencies import get_current_therapist
from src.api.v1.endpoints.billing import get_billing_service, router
from src.core.database import get_db_session
from src.core.exceptions import setup_exception_handlers
from src.models.db.user import User, UserRole
from src.services.billing_service import BillingServiceError


@pytest.fixture
def therapist_user() -> MagicMock:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.organization_id = uuid.uuid4()
    u.email = "doc@example.com"
    u.role = UserRole.THERAPIST
    u.full_name = "Dr. Example"
    u.email_verified_at = None
    u.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    u.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    return u


@pytest.fixture
def mock_billing_service() -> MagicMock:
    svc = MagicMock()
    svc.create_checkout_session_url = AsyncMock()
    svc.create_portal_session_url = AsyncMock()
    svc.handle_webhook = AsyncMock()
    # db_session is accessed directly from the subscription endpoint.
    svc.db_session = AsyncMock()
    return svc


@pytest.fixture
def app(
    mock_billing_service: MagicMock,
    therapist_user: MagicMock,
) -> FastAPI:
    test_app = FastAPI()
    setup_exception_handlers(test_app)
    test_app.include_router(router, prefix="/billing")

    test_app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    test_app.dependency_overrides[get_billing_service] = lambda: mock_billing_service
    test_app.dependency_overrides[get_current_therapist] = lambda: therapist_user

    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


class TestCheckoutSession:
    def test_checkout_session_returns_url(
        self,
        client: TestClient,
        mock_billing_service: MagicMock,
        therapist_user: MagicMock,
    ) -> None:
        mock_billing_service.create_checkout_session_url.return_value = (
            "https://checkout.stripe.com/c/pay/cs_test_123"
        )

        response = client.post("/billing/checkout-session")

        assert response.status_code == 200
        body = response.json()
        assert body == {"url": "https://checkout.stripe.com/c/pay/cs_test_123"}
        mock_billing_service.create_checkout_session_url.assert_awaited_once_with(
            organization_id=therapist_user.organization_id,
            therapist_email=therapist_user.email,
        )


class TestPortalSession:
    def test_portal_session_returns_url(
        self,
        client: TestClient,
        mock_billing_service: MagicMock,
        therapist_user: MagicMock,
    ) -> None:
        mock_billing_service.create_portal_session_url.return_value = (
            "https://billing.stripe.com/p/session/bps_test_abc"
        )

        response = client.post("/billing/portal-session")

        assert response.status_code == 200
        assert response.json() == {
            "url": "https://billing.stripe.com/p/session/bps_test_abc"
        }
        mock_billing_service.create_portal_session_url.assert_awaited_once_with(
            therapist_user.organization_id
        )


class TestSubscriptionStatus:
    def test_subscription_status_reflects_org_row(
        self,
        client: TestClient,
        mock_billing_service: MagicMock,
    ) -> None:
        trial_end = datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC)
        period_end = datetime(2026, 6, 5, 12, 0, 0, tzinfo=UTC)

        org = MagicMock()
        org.subscription_status = MagicMock()
        org.subscription_status.value = "trialing"
        org.trial_ends_at = trial_end
        org.current_period_end = period_end
        org.stripe_customer_id = "cus_12345"
        org.is_entitled = MagicMock(return_value=True)

        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = org
        mock_billing_service.db_session.execute = AsyncMock(return_value=scalar_result)

        response = client.get("/billing/subscription")

        assert response.status_code == 200
        body = response.json()
        assert body["subscription_status"] == "trialing"
        assert body["is_entitled"] is True
        assert body["has_stripe_customer"] is True
        assert body["trial_ends_at"] is not None
        assert body["trial_ends_at"].startswith("2026-05-05")
        assert body["current_period_end"].startswith("2026-06-05")
        org.is_entitled.assert_called_once()


class TestStripeWebhook:
    def test_webhook_without_signature_returns_401(
        self,
        client: TestClient,
    ) -> None:
        response = client.post("/billing/webhook", content=b"{}")
        assert response.status_code == 401

    def test_webhook_success_returns_200_and_forwards_to_service(
        self,
        client: TestClient,
        mock_billing_service: MagicMock,
    ) -> None:
        mock_billing_service.handle_webhook.return_value = {
            "received": True,
            "type": "customer.subscription.updated",
        }
        payload = b'{"id":"evt_123","type":"customer.subscription.updated"}'

        response = client.post(
            "/billing/webhook",
            content=payload,
            headers={"Stripe-Signature": "t=1,v1=sig"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "received": True,
            "type": "customer.subscription.updated",
        }
        mock_billing_service.handle_webhook.assert_awaited_once()
        _, kwargs = mock_billing_service.handle_webhook.call_args
        assert kwargs["payload"] == payload
        assert kwargs["signature"] == "t=1,v1=sig"

    def test_webhook_bad_signature_returns_502(
        self,
        client: TestClient,
        mock_billing_service: MagicMock,
    ) -> None:
        # BillingServiceError maps to 502 via AppError's status_code.
        mock_billing_service.handle_webhook.side_effect = BillingServiceError(
            "Invalid webhook signature: bad mac"
        )

        response = client.post(
            "/billing/webhook",
            content=b"{}",
            headers={"Stripe-Signature": "bogus"},
        )

        assert response.status_code == 502
        body = response.json()
        assert body["status"] == 502
        assert "Invalid webhook signature" in body["detail"]
