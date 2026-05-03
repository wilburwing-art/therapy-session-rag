"""SMS sender abstraction.

A thin Protocol with two concrete implementations:

- ``TwilioSmsSender`` — real Twilio REST client. Imported lazily so the
  twilio package stays optional. Only instantiated when credentials are
  configured.
- ``NoopSmsSender`` — returns a deterministic ``skipped`` result and does
  no network I/O. Used when Twilio settings are placeholders (the default
  in dev/test environments).

Callers obtain a sender via :func:`build_sms_sender` which picks the
right implementation based on ``Settings.twilio_configured``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from src.core.config import Settings

logger = logging.getLogger(__name__)


class SmsSenderError(Exception):
    """Raised when the SMS provider reports a non-retryable failure."""


@dataclass(frozen=True)
class SmsResult:
    """Outcome of a single send_sms call.

    Attributes:
        delivered: True when the provider accepted the message.
        provider_message_id: External id (e.g. Twilio Message SID),
            or None when we didn't talk to a provider.
        error: Short error description when delivered=False.
        skipped: True when the sender is a no-op stub (no credentials).
    """

    delivered: bool
    provider_message_id: str | None = None
    error: str | None = None
    skipped: bool = False


@runtime_checkable
class SmsSender(Protocol):
    """Protocol every SMS sender implementation satisfies."""

    def send_sms(self, to: str, body: str) -> SmsResult:
        """Send an SMS synchronously.

        Args:
            to: Destination phone number in E.164 format.
            body: Message text (already rendered, already under 1600 chars).

        Returns:
            An :class:`SmsResult` describing the outcome. Implementations
            must not raise on delivery failure; they should return
            ``delivered=False`` with ``error`` populated so the caller can
            record the attempt in ``reminders_sent``.
        """
        ...


class NoopSmsSender:
    """Stub sender used when Twilio credentials are absent.

    Writes a debug log and returns a ``skipped`` result. This keeps
    development environments free of provider dependencies while
    preserving the reminder audit trail.
    """

    def send_sms(self, to: str, body: str) -> SmsResult:  # noqa: ARG002
        logger.debug(
            "sms_sender.skipped",
            extra={"to": _mask_phone(to), "body_len": len(body)},
        )
        return SmsResult(
            delivered=False,
            skipped=True,
            error="twilio_not_configured",
        )


class TwilioSmsSender:
    """Twilio-backed SMS sender.

    Imports the twilio package lazily so production builds that don't
    install the ``notifications`` extra still work.
    """

    def __init__(self, settings: Settings) -> None:
        if not settings.twilio_configured:
            raise SmsSenderError(
                "TwilioSmsSender constructed without complete credentials"
            )
        # Local import: twilio is an optional dependency.
        try:
            from twilio.rest import Client
        except ImportError as exc:  # pragma: no cover - import guard
            raise SmsSenderError(
                "twilio package is not installed; install the 'notifications' extra"
            ) from exc

        self._client = Client(
            settings.twilio_account_sid,
            settings.twilio_auth_token,
        )
        self._from_number = settings.twilio_from_number
        self._messaging_service_sid = settings.twilio_messaging_service_sid

    def send_sms(self, to: str, body: str) -> SmsResult:
        try:
            create_kwargs: dict[str, str] = {"to": to, "body": body}
            if self._messaging_service_sid:
                create_kwargs["messaging_service_sid"] = self._messaging_service_sid
            else:
                create_kwargs["from_"] = self._from_number

            message = self._client.messages.create(**create_kwargs)
            sid = getattr(message, "sid", None)
            return SmsResult(
                delivered=True,
                provider_message_id=str(sid) if sid else None,
            )
        except Exception as exc:  # noqa: BLE001 - provider failures must not propagate
            logger.warning(
                "sms_sender.failed",
                extra={"to": _mask_phone(to), "error": str(exc)},
            )
            return SmsResult(delivered=False, error=str(exc)[:1024])


def build_sms_sender(settings: Settings) -> SmsSender:
    """Return a sender appropriate for the current settings."""
    if settings.twilio_configured:
        try:
            return TwilioSmsSender(settings)
        except SmsSenderError as exc:
            logger.warning(
                "sms_sender.fallback_to_noop",
                extra={"error": str(exc)},
            )
            return NoopSmsSender()
    return NoopSmsSender()


def _mask_phone(number: str) -> str:
    """Redact a phone number for logging (keeps country code + last 2)."""
    if len(number) <= 4:
        return "***"
    return f"{number[:2]}***{number[-2:]}"


__all__ = [
    "NoopSmsSender",
    "SmsResult",
    "SmsSender",
    "SmsSenderError",
    "TwilioSmsSender",
    "build_sms_sender",
]
