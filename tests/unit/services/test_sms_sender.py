"""Tests for the SMS sender abstractions."""

from unittest.mock import MagicMock, patch

from src.core.config import Settings
from src.services.notifications.sms_sender import (
    NoopSmsSender,
    SmsResult,
    TwilioSmsSender,
    build_sms_sender,
)


def _settings_without_twilio(**overrides: object) -> Settings:
    env = {
        "database_url": "postgresql+asyncpg://user:pw@localhost:5432/db",
        "redis_url": "redis://localhost:6379/0",
    }
    env.update(overrides)  # type: ignore[arg-type]
    return Settings(**env)  # type: ignore[arg-type]


def _settings_with_twilio(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "twilio_account_sid": "AC_test",
        "twilio_auth_token": "secret",
        "twilio_from_number": "+15005550006",
    }
    base.update(overrides)
    return _settings_without_twilio(**base)


class TestNoopSmsSender:
    def test_returns_skipped_result(self) -> None:
        sender = NoopSmsSender()
        result = sender.send_sms("+15551234567", "hello")
        assert isinstance(result, SmsResult)
        assert result.delivered is False
        assert result.skipped is True
        assert result.error == "twilio_not_configured"
        assert result.provider_message_id is None


class TestBuildSmsSender:
    def test_returns_noop_when_twilio_not_configured(self) -> None:
        settings = _settings_without_twilio()
        sender = build_sms_sender(settings)
        assert isinstance(sender, NoopSmsSender)

    def test_returns_twilio_when_configured(self) -> None:
        settings = _settings_with_twilio()
        with patch(
            "src.services.notifications.sms_sender.TwilioSmsSender",
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            sender = build_sms_sender(settings)
            mock_cls.assert_called_once_with(settings)
            assert sender is mock_cls.return_value

    def test_falls_back_to_noop_on_twilio_import_error(self) -> None:
        """If twilio package is missing, build_sms_sender must still work."""
        settings = _settings_with_twilio()
        from src.services.notifications.sms_sender import SmsSenderError

        with patch(
            "src.services.notifications.sms_sender.TwilioSmsSender",
            side_effect=SmsSenderError("twilio not installed"),
        ):
            sender = build_sms_sender(settings)
            assert isinstance(sender, NoopSmsSender)


class TestTwilioSmsSender:
    def test_delivery_success_returns_provider_id(self) -> None:
        settings = _settings_with_twilio()
        fake_message = MagicMock()
        fake_message.sid = "SM123"
        fake_client = MagicMock()
        fake_client.messages.create.return_value = fake_message

        sender = TwilioSmsSender.__new__(TwilioSmsSender)
        sender._client = fake_client  # type: ignore[attr-defined]
        sender._from_number = settings.twilio_from_number  # type: ignore[attr-defined]
        sender._messaging_service_sid = ""  # type: ignore[attr-defined]

        result = sender.send_sms("+15551234567", "hi")
        assert result.delivered is True
        assert result.provider_message_id == "SM123"
        fake_client.messages.create.assert_called_once_with(
            to="+15551234567",
            body="hi",
            from_=settings.twilio_from_number,
        )

    def test_delivery_failure_is_captured_not_raised(self) -> None:
        fake_client = MagicMock()
        fake_client.messages.create.side_effect = RuntimeError("twilio rejected")

        sender = TwilioSmsSender.__new__(TwilioSmsSender)
        sender._client = fake_client  # type: ignore[attr-defined]
        sender._from_number = "+15005550006"  # type: ignore[attr-defined]
        sender._messaging_service_sid = ""  # type: ignore[attr-defined]

        result = sender.send_sms("+15551234567", "hi")
        assert result.delivered is False
        assert result.provider_message_id is None
        assert result.error is not None
        assert "twilio rejected" in result.error

    def test_messaging_service_sid_takes_precedence(self) -> None:
        fake_message = MagicMock()
        fake_message.sid = "SM999"
        fake_client = MagicMock()
        fake_client.messages.create.return_value = fake_message

        sender = TwilioSmsSender.__new__(TwilioSmsSender)
        sender._client = fake_client  # type: ignore[attr-defined]
        sender._from_number = "+15005550006"  # type: ignore[attr-defined]
        sender._messaging_service_sid = "MG123"  # type: ignore[attr-defined]

        sender.send_sms("+15551234567", "hi")
        # When messaging_service_sid is set, from_ must not be present.
        call_kwargs = fake_client.messages.create.call_args.kwargs
        assert call_kwargs.get("messaging_service_sid") == "MG123"
        assert "from_" not in call_kwargs


class TestSettingsTwilioConfigured:
    def test_false_when_empty(self) -> None:
        settings = _settings_without_twilio()
        assert settings.twilio_configured is False

    def test_true_with_from_number(self) -> None:
        settings = _settings_with_twilio()
        assert settings.twilio_configured is True

    def test_true_with_messaging_service_sid(self) -> None:
        settings = _settings_with_twilio(
            twilio_from_number="",
            twilio_messaging_service_sid="MG123",
        )
        assert settings.twilio_configured is True

    def test_false_when_auth_missing(self) -> None:
        settings = _settings_with_twilio(twilio_auth_token="")
        assert settings.twilio_configured is False
