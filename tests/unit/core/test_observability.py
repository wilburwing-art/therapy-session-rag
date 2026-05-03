"""Tests for Sentry scrubber and init guard."""

from unittest.mock import patch

from src.core.config import Settings
from src.core.observability import _scrub_event, init_sentry


def _settings(dsn: str = "") -> Settings:
    return Settings(
        database_url="postgresql://u:p@localhost/t",  # type: ignore[arg-type]
        redis_url="redis://localhost:6379",  # type: ignore[arg-type]
        sentry_dsn=dsn,
    )


def test_init_sentry_skipped_without_dsn() -> None:
    with patch("src.core.observability.sentry_sdk.init") as init:
        active = init_sentry(_settings(""))
    assert active is False
    init.assert_not_called()


def test_init_sentry_called_when_configured() -> None:
    with patch("src.core.observability.sentry_sdk.init") as init:
        active = init_sentry(_settings("https://abc@sentry.io/123"))
    assert active is True
    init.assert_called_once()


def test_scrub_event_redacts_auth_headers() -> None:
    event = {
        "request": {
            "headers": {
                "Authorization": "Bearer secret",
                "Cookie": "therapyrag_session=abc",
                "X-API-Key": "trag_abc",
                "User-Agent": "curl/8",
            },
        }
    }
    scrubbed = _scrub_event(event, {})
    assert scrubbed is not None
    headers = scrubbed["request"]["headers"]
    assert headers["Authorization"] == "[redacted]"
    assert headers["Cookie"] == "[redacted]"
    assert headers["X-API-Key"] == "[redacted]"
    assert headers["User-Agent"] == "curl/8"


def test_scrub_event_redacts_request_body_and_user() -> None:
    event = {
        "request": {
            "data": "transcript full text here",
            "cookies": "therapyrag_session=abc",
        },
        "user": {"email": "p@example.com", "username": "p", "id": "u_1"},
    }
    scrubbed = _scrub_event(event, {})
    assert scrubbed is not None
    assert scrubbed["request"]["data"] == "[redacted:body]"
    assert scrubbed["request"]["cookies"] == "[redacted]"
    assert "email" not in scrubbed["user"]
    assert "username" not in scrubbed["user"]
    assert scrubbed["user"]["id"] == "u_1"
