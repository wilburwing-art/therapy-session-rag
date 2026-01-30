"""API v1 router configuration."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1")

# Endpoint routers will be included here as they are created
# Example:
# from src.api.v1.endpoints import consent, sessions, chat
# router.include_router(consent.router, prefix="/consent", tags=["consent"])
