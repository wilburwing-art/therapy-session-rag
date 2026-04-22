"""Tests for subscription gate dependency."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.v1.dependencies import AuthContext
from src.core.billing_gate import PaymentRequiredError, require_entitled_subscription
from src.models.db.organization import SubscriptionStatus


def _auth() -> AuthContext:
    return AuthContext(
        api_key_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        api_key_name="test",
    )


def _settings(enforced: bool) -> MagicMock:
    s = MagicMock()
    s.billing_enforced = enforced
    return s


def _session_returning(org: object | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = org
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_gate_is_noop_when_not_enforced() -> None:
    await require_entitled_subscription(
        auth=_auth(),
        session=_session_returning(None),
        settings=_settings(enforced=False),
    )


@pytest.mark.asyncio
async def test_gate_allows_trialing() -> None:
    org = MagicMock()
    org.is_entitled.return_value = True
    org.subscription_status = SubscriptionStatus.TRIALING
    await require_entitled_subscription(
        auth=_auth(),
        session=_session_returning(org),
        settings=_settings(enforced=True),
    )


@pytest.mark.asyncio
async def test_gate_blocks_unentitled() -> None:
    org = MagicMock()
    org.is_entitled.return_value = False
    with pytest.raises(PaymentRequiredError):
        await require_entitled_subscription(
            auth=_auth(),
            session=_session_returning(org),
            settings=_settings(enforced=True),
        )


@pytest.mark.asyncio
async def test_gate_blocks_missing_org() -> None:
    with pytest.raises(PaymentRequiredError):
        await require_entitled_subscription(
            auth=_auth(),
            session=_session_returning(None),
            settings=_settings(enforced=True),
        )
