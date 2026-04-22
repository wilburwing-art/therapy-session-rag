"""Transactional email via Resend.

The service degrades gracefully: when `resend_api_key == "placeholder"`
it logs the would-be email and returns success, which lets local dev
and tests run without outbound email. Real sends happen only when a
key is configured.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol, cast

import resend

from src.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class EmailServiceError(Exception):
    """Email send failed."""


class EmailGateway(Protocol):
    """Protocol wrapping resend.Emails.send, to support test fakes."""

    def send(self, params: dict[str, Any]) -> dict[str, Any]: ...


class _ResendGateway:
    def __init__(self, api_key: str) -> None:
        resend.api_key = api_key

    def send(self, params: dict[str, Any]) -> dict[str, Any]:
        # resend exposes its own TypedDict for params and a SendResponse
        # return type; we flatten both into plain dicts so the rest of
        # the service doesn't depend on the SDK's internal types.
        result = resend.Emails.send(cast(Any, params))
        return cast(dict[str, Any], result)


@dataclass
class EmailResult:
    delivered: bool
    provider_id: str | None
    skipped_reason: str | None = None


class EmailService:
    """Sends operational emails (magic links, verification, notifications)."""

    def __init__(
        self,
        settings: Settings | None = None,
        gateway: EmailGateway | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._gateway = gateway

    @property
    def gateway(self) -> EmailGateway:
        if self._gateway is None:
            self._gateway = _ResendGateway(self.settings.resend_api_key)
        return self._gateway

    @property
    def _from_header(self) -> str:
        return f"{self.settings.email_from_name} <{self.settings.email_from_address}>"

    def _send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        text: str | None = None,
    ) -> EmailResult:
        if self.settings.resend_api_key == "placeholder":
            logger.info(
                "[email:skipped] to=%s subject=%r (no RESEND_API_KEY configured)",
                to,
                subject,
            )
            return EmailResult(
                delivered=False,
                provider_id=None,
                skipped_reason="no_api_key",
            )

        try:
            response = self.gateway.send(
                {
                    "from": self._from_header,
                    "to": to,
                    "subject": subject,
                    "html": html,
                    **({"text": text} if text else {}),
                }
            )
        except Exception as exc:
            logger.error("Email send failed to=%s subject=%r: %s", to, subject, exc)
            raise EmailServiceError(f"Failed to send email: {exc}") from exc

        provider_id = response.get("id") if isinstance(response, dict) else None
        logger.info(
            "[email:sent] to=%s subject=%r provider_id=%s", to, subject, provider_id
        )
        return EmailResult(delivered=True, provider_id=provider_id)

    def send_magic_link(
        self,
        *,
        to_email: str,
        magic_link_url: str,
        therapist_name: str,
        patient_name: str | None = None,
    ) -> EmailResult:
        greeting = f"Hi {patient_name}," if patient_name else "Hi,"
        # Mobile users tap the therapyrag:// link to open the patient
        # app directly; the web URL above is the fallback for anyone
        # reading email in a browser or without the app installed.
        mobile_deep_link = f"therapyrag://chat?t={magic_link_url.rsplit('t=', 1)[-1]}"
        html = f"""
        <p>{greeting}</p>
        <p>{therapist_name} has opened a chat with your session history. Use the link below to start it — it expires in 15 minutes and can only be used once.</p>
        <p><a href="{magic_link_url}">Open your chat</a></p>
        <p>On a phone with the TherapyRAG app installed? <a href="{mobile_deep_link}">Open in the app</a>.</p>
        <p>If you didn't expect this, you can ignore it — the link will expire automatically.</p>
        <p>— TherapyRAG</p>
        """
        return self._send(
            to=to_email,
            subject=f"Your TherapyRAG chat with {therapist_name}",
            html=html,
        )

    def send_email_verification(
        self,
        *,
        to_email: str,
        verification_url: str,
        therapist_name: str | None = None,
    ) -> EmailResult:
        greeting = f"Hi {therapist_name}," if therapist_name else "Hi,"
        html = f"""
        <p>{greeting}</p>
        <p>Confirm your email to finish setting up your TherapyRAG account.</p>
        <p><a href="{verification_url}">Verify email</a></p>
        """
        return self._send(
            to=to_email,
            subject="Verify your TherapyRAG email",
            html=html,
        )

    def send_password_reset(
        self,
        *,
        to_email: str,
        reset_url: str,
    ) -> EmailResult:
        html = f"""
        <p>A password reset was requested for your TherapyRAG account.</p>
        <p><a href="{reset_url}">Reset your password</a> (expires in 30 minutes).</p>
        <p>If you didn't request this, you can safely ignore this email.</p>
        """
        return self._send(
            to=to_email,
            subject="Reset your TherapyRAG password",
            html=html,
        )

    def send_recap_ready(
        self,
        *,
        to_email: str,
        session_date: str,
        recap_url: str,
    ) -> EmailResult:
        html = f"""
        <p>The session recap for {session_date} is ready to review.</p>
        <p><a href="{recap_url}">Open recap</a></p>
        """
        return self._send(
            to=to_email,
            subject=f"Session recap ready — {session_date}",
            html=html,
        )

    def send_therapist_invite(
        self,
        *,
        to_email: str,
        practice_name: str,
        inviter_name: str,
        invite_url: str,
        role: str = "therapist",
    ) -> EmailResult:
        role_label = "admin" if role == "admin" else "therapist"
        html = f"""
        <p>Hi,</p>
        <p>{inviter_name} has invited you to join <strong>{practice_name}</strong> on TherapyRAG as a {role_label}.</p>
        <p>Use the link below to set a password and get started. The link expires in 7 days.</p>
        <p><a href="{invite_url}">Accept your invite</a></p>
        <p>If you weren't expecting this, you can ignore this email — nothing will change.</p>
        <p>— TherapyRAG</p>
        """
        return self._send(
            to=to_email,
            subject=f"Join {practice_name} on TherapyRAG",
            html=html,
        )

    def send_intake_invitation(
        self,
        *,
        to_email: str,
        practice_name: str,
        therapist_name: str,
        intake_url: str,
        patient_name: str | None = None,
    ) -> EmailResult:
        """Email a prospective patient the intake form link.

        The link is a single-use token; the patient submits answers
        through a public page before their first session.
        """
        greeting = f"Hi {patient_name}," if patient_name else "Hi,"
        html = f"""
        <p>{greeting}</p>
        <p>{therapist_name} at <strong>{practice_name}</strong> has asked you to fill out an intake form before your first session.</p>
        <p>It should take a few minutes. The link expires in 14 days and can only be submitted once.</p>
        <p><a href="{intake_url}">Open your intake form</a></p>
        <p>If you weren't expecting this, you can ignore this email.</p>
        <p>— TherapyRAG</p>
        """
        return self._send(
            to=to_email,
            subject=f"Intake form from {practice_name}",
            html=html,
        )
