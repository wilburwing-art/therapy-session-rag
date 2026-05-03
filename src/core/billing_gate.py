"""Subscription entitlement gate.

FastAPI dependency that blocks access to product endpoints when the
caller's organization has no active or trialing subscription. The gate
is driven by the `billing_enforced` setting so it can be turned off in
dev/test without removing it from routers.
"""

from __future__ import annotations

from fastapi import Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import AuthContext, get_api_key_auth
from src.core.config import Settings, get_settings
from src.core.database import get_db_session
from src.core.exceptions import AppError
from src.models.db.organization import Organization


class PaymentRequiredError(AppError):
    """Returned when a request hits an endpoint but the org isn't paying."""

    def __init__(
        self,
        detail: str = ("Subscription required. Start or renew your plan in the billing portal."),
    ) -> None:
        super().__init__(
            title="Payment Required",
            detail=detail,
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            error_type="about:blank#payment-required",
        )


async def require_entitled_subscription(
    auth: AuthContext = Depends(get_api_key_auth),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> None:
    """Raise PaymentRequiredError if the calling org isn't entitled.

    No-op when billing enforcement is disabled. The dependency uses
    `get_api_key_auth` directly because the production therapist flow
    still falls back to API keys for server-to-server calls.
    """
    if not settings.billing_enforced:
        return
    result = await session.execute(
        select(Organization).where(Organization.id == auth.organization_id)
    )
    org = result.scalar_one_or_none()
    if org is None or not org.is_entitled():
        raise PaymentRequiredError()
