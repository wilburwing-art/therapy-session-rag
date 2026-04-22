"""Sentry initialization and PHI-safe event scrubbing.

Sentry is opt-in: disabled when `SENTRY_DSN` is empty so local dev and
tests don't depend on it. When enabled, a `before_send` hook strips
request bodies, cookies, and auth headers so nothing we classify as
PHI leaves the app.
"""

from __future__ import annotations

import logging
from typing import Any, cast

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from src.core.config import Settings

logger = logging.getLogger(__name__)

_PHI_HEADER_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "stripe-signature",
}


def _scrub_event(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any] | None:
    """Strip PHI-likely fields from a Sentry event before it's sent."""
    request = event.get("request")
    if isinstance(request, dict):
        headers = request.get("headers")
        if isinstance(headers, dict):
            for key in list(headers.keys()):
                if key.lower() in _PHI_HEADER_KEYS:
                    headers[key] = "[redacted]"
        # We never want request bodies: they may contain transcripts,
        # chat messages, or patient-authored prose.
        if "data" in request:
            request["data"] = "[redacted:body]"
        if "cookies" in request:
            request["cookies"] = "[redacted]"
    user = event.get("user")
    if isinstance(user, dict):
        user.pop("email", None)
        user.pop("username", None)
    return event


def init_sentry(settings: Settings) -> bool:
    """Initialize Sentry if configured. Returns True if active."""
    if not settings.sentry_dsn:
        logger.info("Sentry disabled (no DSN configured)")
        return False

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,  # never auto-attach user identifiers
        before_send=cast(Any, _scrub_event),
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            StarletteIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
        ],
    )
    logger.info(
        "Sentry initialized (environment=%s, traces=%.2f)",
        settings.sentry_environment,
        settings.sentry_traces_sample_rate,
    )
    return True
