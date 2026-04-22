"""Tests for EmailService."""

from unittest.mock import MagicMock

import pytest

from src.core.config import Settings
from src.services.email_service import EmailService, EmailServiceError


def _settings(api_key: str = "re_test_fake") -> Settings:
    return Settings(
        database_url="postgresql://u:p@localhost/t",  # type: ignore[arg-type]
        redis_url="redis://localhost:6379",  # type: ignore[arg-type]
        resend_api_key=api_key,
        email_from_address="no-reply@therapyrag.test",
        email_from_name="TherapyRAG Test",
        web_app_url="https://app.therapyrag.test",
    )


def test_send_skipped_when_no_api_key_configured() -> None:
    service = EmailService(settings=_settings(api_key="placeholder"), gateway=MagicMock())
    result = service.send_magic_link(
        to_email="p@example.com",
        magic_link_url="https://example.com/chat?t=abc",
        therapist_name="Dr. A",
    )
    assert result.delivered is False
    assert result.skipped_reason == "no_api_key"
    # Gateway should not have been called
    service.gateway.send.assert_not_called()


def test_send_magic_link_invokes_gateway() -> None:
    gateway = MagicMock()
    gateway.send.return_value = {"id": "email_123"}
    service = EmailService(settings=_settings(), gateway=gateway)

    result = service.send_magic_link(
        to_email="p@example.com",
        magic_link_url="https://app.therapyrag.test/chat?t=token",
        therapist_name="Dr. Amina",
        patient_name="Sam",
    )

    assert result.delivered is True
    assert result.provider_id == "email_123"
    gateway.send.assert_called_once()
    params = gateway.send.call_args.args[0]
    assert params["to"] == "p@example.com"
    assert "TherapyRAG Test" in params["from"]
    assert "Dr. Amina" in params["subject"]
    assert "https://app.therapyrag.test/chat?t=token" in params["html"]
    assert "Sam" in params["html"]


def test_gateway_error_wrapped_in_email_service_error() -> None:
    gateway = MagicMock()
    gateway.send.side_effect = RuntimeError("upstream 500")
    service = EmailService(settings=_settings(), gateway=gateway)
    with pytest.raises(EmailServiceError):
        service.send_password_reset(
            to_email="p@example.com",
            reset_url="https://example.com/reset/abc",
        )


def test_from_header_combines_name_and_address() -> None:
    service = EmailService(settings=_settings(), gateway=MagicMock())
    assert service._from_header == "TherapyRAG Test <no-reply@therapyrag.test>"
