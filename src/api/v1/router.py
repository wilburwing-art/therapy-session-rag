"""API v1 router configuration."""

from fastapi import APIRouter, Depends

from src.api.v1.endpoints import (
    admin,
    analytics,
    auth,
    billing,
    chat,
    consent,
    experiments,
    invites,
    organizations,
    patients,
    search,
    sessions,
    users,
    video,
)
from src.core.admin_gate import require_admin_rate_limit
from src.core.billing_gate import require_entitled_subscription

router = APIRouter(prefix="/api/v1")

# Routers that are always accessible regardless of subscription status:
# - /auth: sign up, log in, reset password (can't pay if you can't log in)
# - /billing: manage or restore the subscription
# - /organization, /users: account bookkeeping
# - /admin: the operator panel must reach a suspended org, so it is
#   intentionally not behind the entitlement gate
router.include_router(
    admin.router,
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin_rate_limit)],
)
router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(billing.router, prefix="/billing", tags=["billing"])
router.include_router(invites.router, prefix="/invites", tags=["invites"])
router.include_router(organizations.router, prefix="/organization", tags=["organization"])
router.include_router(users.router, prefix="/users", tags=["users"])

# Product endpoints require an entitled subscription when billing_enforced=true.
_gated_dependency = [Depends(require_entitled_subscription)]
router.include_router(
    chat.router, prefix="/chat", tags=["chat"], dependencies=_gated_dependency
)
router.include_router(
    consent.router, prefix="/consent", tags=["consent"], dependencies=_gated_dependency
)
router.include_router(
    experiments.router,
    prefix="/experiments",
    tags=["experiments"],
    dependencies=_gated_dependency,
)
router.include_router(
    patients.router,
    prefix="/patients",
    tags=["patients"],
    dependencies=_gated_dependency,
)
router.include_router(
    search.router, prefix="/search", tags=["search"], dependencies=_gated_dependency
)
router.include_router(
    sessions.router,
    prefix="/sessions",
    tags=["sessions"],
    dependencies=_gated_dependency,
)
router.include_router(
    video.router, prefix="/video", tags=["video"], dependencies=_gated_dependency
)
