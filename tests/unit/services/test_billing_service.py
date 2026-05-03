"""Tests for BillingService Stripe integration."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import stripe

from src.core.exceptions import NotFoundError
from src.models.db.billing_usage import BillingUsage
from src.models.db.organization import Organization, SubscriptionStatus
from src.services.billing_service import (
    BillingService,
    BillingServiceError,
    _period_bounds_for,
)


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


# ----------------------------------------------------------------------
# Metered billing
# ----------------------------------------------------------------------


def _stub_usage_row_fetch(
    service: BillingService,
    org: Organization,
    existing_row: BillingUsage | None = None,
) -> None:
    """Make db.execute() return the org first, then the usage row."""
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    org_result.scalar_one.return_value = org
    row_result = MagicMock()
    row_result.scalar_one_or_none.return_value = existing_row

    async def execute_side_effect(*_args: object, **_kwargs: object) -> MagicMock:
        return execute_side_effect.queue.pop(0)  # type: ignore[attr-defined]

    execute_side_effect.queue = [org_result, row_result]  # type: ignore[attr-defined]
    service.db_session.execute = AsyncMock(side_effect=execute_side_effect)


@pytest.mark.asyncio
async def test_record_sessions_transcribed_creates_row(
    service: BillingService,
) -> None:
    org = _mock_org(stripe_customer_id="cus_meter")
    org.current_period_end = datetime(2026, 5, 1, tzinfo=UTC)
    _stub_usage_row_fetch(service, org, existing_row=None)

    captured: dict[str, BillingUsage] = {}

    def _add(obj: BillingUsage) -> None:
        captured["row"] = obj

    service.db_session.add = MagicMock(side_effect=_add)

    row = await service.record_sessions_transcribed(org.id)

    assert row.sessions_transcribed == 1
    assert captured["row"] is row
    service.db_session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_record_sessions_transcribed_increments_existing(
    service: BillingService,
) -> None:
    org = _mock_org(stripe_customer_id="cus_meter")
    org.current_period_end = datetime(2026, 5, 1, tzinfo=UTC)
    existing = BillingUsage(
        organization_id=org.id,
        period_start=datetime(2026, 4, 1, tzinfo=UTC),
        period_end=datetime(2026, 5, 1, tzinfo=UTC),
        sessions_transcribed=3,
        recaps_generated=1,
        chat_messages=7,
    )
    _stub_usage_row_fetch(service, org, existing_row=existing)

    row = await service.record_sessions_transcribed(org.id, count=2)
    assert row is existing
    assert row.sessions_transcribed == 5


@pytest.mark.asyncio
async def test_record_usage_rejects_zero_count(service: BillingService) -> None:
    with pytest.raises(ValueError):
        await service.record_sessions_transcribed(uuid.uuid4(), count=0)


@pytest.mark.asyncio
async def test_report_usage_to_stripe_creates_meter_events(
    service: BillingService,
) -> None:
    org = _mock_org(stripe_customer_id="cus_meter")
    org.current_period_end = datetime(2026, 5, 1, tzinfo=UTC)
    existing = BillingUsage(
        organization_id=org.id,
        period_start=datetime(2026, 4, 1, tzinfo=UTC),
        period_end=datetime(2026, 5, 1, tzinfo=UTC),
        sessions_transcribed=4,
        recaps_generated=0,
        chat_messages=2,
    )
    existing.id = uuid.uuid4()
    _stub_usage_row_fetch(service, org, existing_row=existing)

    service.gateway.create_meter_event.return_value = SimpleNamespace(identifier="meter-evt-abc")

    now = datetime(2026, 5, 1, 12, tzinfo=UTC)
    row = await service.report_usage_to_stripe(org.id, now=now)

    # Only two meters had positive counters, so two events should fire.
    assert service.gateway.create_meter_event.call_count == 2
    event_names = {
        call.kwargs["event_name"] for call in service.gateway.create_meter_event.call_args_list
    }
    assert event_names == {"sessions_transcribed", "chat_messages"}
    assert row.reported_to_stripe_at == now
    assert row.stripe_meter_event_id == "meter-evt-abc"


@pytest.mark.asyncio
async def test_report_usage_requires_stripe_customer(
    service: BillingService,
) -> None:
    org = _mock_org()  # No stripe_customer_id
    _execute_returning(service, org)
    with pytest.raises(BillingServiceError):
        await service.report_usage_to_stripe(org.id)


@pytest.mark.asyncio
async def test_report_usage_wraps_stripe_errors(
    service: BillingService,
) -> None:
    org = _mock_org(stripe_customer_id="cus_meter")
    org.current_period_end = datetime(2026, 5, 1, tzinfo=UTC)
    existing = BillingUsage(
        organization_id=org.id,
        period_start=datetime(2026, 4, 1, tzinfo=UTC),
        period_end=datetime(2026, 5, 1, tzinfo=UTC),
        sessions_transcribed=1,
        recaps_generated=0,
        chat_messages=0,
    )
    existing.id = uuid.uuid4()
    _stub_usage_row_fetch(service, org, existing_row=existing)
    service.gateway.create_meter_event.side_effect = stripe.APIError("meters down")

    with pytest.raises(BillingServiceError):
        await service.report_usage_to_stripe(org.id)


# ----------------------------------------------------------------------
# Seats
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_count_active_seats_uses_query_result(
    service: BillingService,
) -> None:
    seat_result = MagicMock()
    seat_result.scalar.return_value = 3
    service.db_session.execute = AsyncMock(return_value=seat_result)

    count = await service.count_active_seats(uuid.uuid4())
    assert count == 3


@pytest.mark.asyncio
async def test_sync_subscription_seats_updates_stripe(
    service: BillingService,
) -> None:
    seat_result = MagicMock()
    seat_result.scalar.return_value = 5
    service.db_session.execute = AsyncMock(return_value=seat_result)

    seats = await service.sync_subscription_seats(uuid.uuid4(), subscription_item_id="si_abc")
    assert seats == 5
    service.gateway.update_subscription_item_quantity.assert_called_once_with(
        subscription_item_id="si_abc", quantity=5
    )


@pytest.mark.asyncio
async def test_sync_subscription_seats_wraps_stripe_error(
    service: BillingService,
) -> None:
    seat_result = MagicMock()
    seat_result.scalar.return_value = 5
    service.db_session.execute = AsyncMock(return_value=seat_result)
    service.gateway.update_subscription_item_quantity.side_effect = stripe.APIError(
        "quantity update failed"
    )
    with pytest.raises(BillingServiceError):
        await service.sync_subscription_seats(uuid.uuid4(), subscription_item_id="si_a")


# ----------------------------------------------------------------------
# Upcoming invoice
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preview_upcoming_invoice_returns_summary(
    service: BillingService,
) -> None:
    org = _mock_org(stripe_customer_id="cus_preview")
    _execute_returning(service, org)
    period_end = int(datetime(2026, 5, 15, tzinfo=UTC).timestamp())
    service.gateway.preview_upcoming_invoice.return_value = SimpleNamespace(
        amount_due=14900,
        total=14900,
        currency="usd",
        period_end=period_end,
    )
    summary = await service.preview_upcoming_invoice(org.id)
    assert summary["amount_due"] == 14900
    assert summary["currency"] == "usd"
    assert summary["period_end"] is not None


@pytest.mark.asyncio
async def test_preview_upcoming_invoice_requires_customer(
    service: BillingService,
) -> None:
    org = _mock_org()
    _execute_returning(service, org)
    with pytest.raises(BillingServiceError):
        await service.preview_upcoming_invoice(org.id)


# ----------------------------------------------------------------------
# Period bounds
# ----------------------------------------------------------------------


def test_period_bounds_prefers_current_period_end() -> None:
    org = _mock_org()
    org.current_period_end = datetime(2026, 5, 1, tzinfo=UTC)
    start, end = _period_bounds_for(org, datetime(2026, 4, 14, tzinfo=UTC))
    # period_start is 30 days before the period_end when now is before it.
    assert end == datetime(2026, 5, 1, tzinfo=UTC)
    assert start <= datetime(2026, 4, 14, tzinfo=UTC)
    assert end - start <= timedelta(days=31)


def test_period_bounds_falls_back_to_calendar_month() -> None:
    org = _mock_org()
    org.current_period_end = None
    now = datetime(2026, 4, 14, tzinfo=UTC)
    start, end = _period_bounds_for(org, now)
    assert start == datetime(2026, 4, 1, tzinfo=UTC)
    assert end == datetime(2026, 5, 1, tzinfo=UTC)


def test_period_bounds_falls_back_handles_december() -> None:
    org = _mock_org()
    org.current_period_end = None
    now = datetime(2026, 12, 14, tzinfo=UTC)
    _, end = _period_bounds_for(org, now)
    assert end == datetime(2027, 1, 1, tzinfo=UTC)
