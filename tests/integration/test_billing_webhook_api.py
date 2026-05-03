"""Integration tests for the Stripe webhook endpoint."""

import uuid
from unittest.mock import patch

import pytest
import stripe
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.main import app
from src.models.db.organization import Organization, SubscriptionStatus


@pytest.mark.asyncio(loop_scope="session")
async def test_webhook_rejects_missing_signature(
    db_session: AsyncSession,
) -> None:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/billing/webhook",
                content=b"{}",
                headers={"content-type": "application/json"},
            )
            # Missing Stripe-Signature should be rejected as unauthorized.
            assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_db_session, None)


@pytest.mark.asyncio(loop_scope="session")
async def test_webhook_rejects_bad_signature(db_session: AsyncSession) -> None:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/billing/webhook",
                content=b'{"type":"customer.subscription.updated"}',
                headers={
                    "content-type": "application/json",
                    "Stripe-Signature": "t=1,v1=badbadbad",
                },
            )
            # Our BillingServiceError maps to 502 via AppError.
            assert resp.status_code == 502
    finally:
        app.dependency_overrides.pop(get_db_session, None)


@pytest.mark.asyncio(loop_scope="session")
async def test_webhook_subscription_updated_mirrors_state(
    db_session: AsyncSession,
) -> None:
    # Seed an org with a known stripe_customer_id.
    customer_id = f"cus_{uuid.uuid4().hex[:16]}"
    org = Organization(
        id=uuid.uuid4(),
        name="Webhook Test Practice",
        stripe_customer_id=customer_id,
    )
    db_session.add(org)
    await db_session.flush()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db
    try:
        transport = ASGITransport(app=app)

        fake_event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_abc",
                    "customer": customer_id,
                    "status": "active",
                    "trial_end": None,
                    "current_period_end": 1800000000,
                }
            },
        }
        with patch.object(stripe.Webhook, "construct_event", return_value=fake_event):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/billing/webhook",
                    content=b'{"type":"customer.subscription.updated"}',
                    headers={
                        "content-type": "application/json",
                        "Stripe-Signature": "t=1,v1=anything",
                    },
                )
                assert resp.status_code == 200
                assert resp.json()["type"] == "customer.subscription.updated"

        refreshed = await db_session.execute(select(Organization).where(Organization.id == org.id))
        updated = refreshed.scalar_one()
        assert updated.subscription_status == SubscriptionStatus.ACTIVE
        assert updated.stripe_subscription_id == "sub_abc"
    finally:
        app.dependency_overrides.pop(get_db_session, None)
