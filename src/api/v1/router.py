"""API v1 router configuration."""

from fastapi import APIRouter

from src.api.v1.endpoints import chat, consent, sessions

router = APIRouter(prefix="/api/v1")

router.include_router(chat.router, prefix="/chat", tags=["chat"])
router.include_router(consent.router, prefix="/consent", tags=["consent"])
router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
