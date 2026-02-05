"""Tests for structured logging."""

import json
import logging
from unittest.mock import MagicMock

import pytest

from src.core.logging import (
    JSONFormatter,
    get_request_id,
    redact_sensitive_data,
    request_id_var,
    setup_logging,
)


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings."""
    settings = MagicMock()
    settings.app_log_level = "INFO"
    return settings


class TestRedactSensitiveData:
    """Tests for sensitive data redaction."""

    def test_redacts_password(self) -> None:
        """Test password field is redacted."""
        data = {"username": "user", "password": "secret123"}
        result = redact_sensitive_data(data)
        assert result["username"] == "user"
        assert result["password"] == "[REDACTED]"

    def test_redacts_api_key(self) -> None:
        """Test API key fields are redacted."""
        data = {
            "api_key": "sk-123",
            "x-api-key": "key-456",
            "anthropic_api_key": "key-789",
        }
        result = redact_sensitive_data(data)
        assert result["api_key"] == "[REDACTED]"
        assert result["x-api-key"] == "[REDACTED]"
        assert result["anthropic_api_key"] == "[REDACTED]"

    def test_redacts_nested_sensitive_data(self) -> None:
        """Test nested sensitive fields are redacted."""
        data = {
            "config": {
                "database": "postgres",
                "secret_key": "super-secret",
            }
        }
        result = redact_sensitive_data(data)
        assert result["config"]["database"] == "postgres"
        assert result["config"]["secret_key"] == "[REDACTED]"

    def test_redacts_in_lists(self) -> None:
        """Test sensitive fields in lists are redacted."""
        data = {
            "users": [
                {"name": "Alice", "password": "pass1"},
                {"name": "Bob", "password": "pass2"},
            ]
        }
        result = redact_sensitive_data(data)
        assert result["users"][0]["name"] == "Alice"
        assert result["users"][0]["password"] == "[REDACTED]"
        assert result["users"][1]["password"] == "[REDACTED]"

    def test_preserves_non_sensitive_data(self) -> None:
        """Test non-sensitive data is preserved."""
        data = {
            "name": "John",
            "email": "john@example.com",
            "count": 42,
        }
        result = redact_sensitive_data(data)
        assert result == data

    def test_case_insensitive_matching(self) -> None:
        """Test redaction is case insensitive."""
        data = {
            "PASSWORD": "secret",
            "Api_Key": "key123",
            "Secret_Token": "token",
        }
        result = redact_sensitive_data(data)
        assert result["PASSWORD"] == "[REDACTED]"
        assert result["Api_Key"] == "[REDACTED]"
        assert result["Secret_Token"] == "[REDACTED]"


class TestJSONFormatter:
    """Tests for JSON log formatter."""

    def test_formats_basic_log(self) -> None:
        """Test basic log formatting."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert data["level"] == "INFO"
        assert data["logger"] == "test.logger"
        assert data["message"] == "Test message"
        assert "timestamp" in data
        assert data["location"]["file"] == "/path/to/file.py"
        assert data["location"]["line"] == 42

    def test_includes_request_id(self) -> None:
        """Test request ID is included when set."""
        formatter = JSONFormatter()

        # Set request ID
        request_id_var.set("test-request-123")

        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert data["request_id"] == "test-request-123"

        # Clean up
        request_id_var.set(None)

    def test_excludes_request_id_when_not_set(self) -> None:
        """Test request ID is excluded when not set."""
        formatter = JSONFormatter()
        request_id_var.set(None)

        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert "request_id" not in data

    def test_formats_exception(self) -> None:
        """Test exception formatting."""
        formatter = JSONFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert data["exception"]["type"] == "ValueError"
        assert data["exception"]["message"] == "Test error"
        assert "Traceback" in data["exception"]["traceback"]

    def test_formats_extra_fields(self) -> None:
        """Test extra fields are included."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.user_id = "user-123"
        record.action = "login"

        result = formatter.format(record)
        data = json.loads(result)

        assert data["extra"]["user_id"] == "user-123"
        assert data["extra"]["action"] == "login"

    def test_redacts_sensitive_extra_fields(self) -> None:
        """Test sensitive extra fields are redacted."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.api_key = "secret-key"
        record.username = "user123"

        result = formatter.format(record)
        data = json.loads(result)

        assert data["extra"]["api_key"] == "[REDACTED]"
        assert data["extra"]["username"] == "user123"


class TestRequestIdContext:
    """Tests for request ID context variable."""

    def test_get_request_id_default(self) -> None:
        """Test default request ID is None."""
        request_id_var.set(None)
        assert get_request_id() is None

    def test_get_request_id_set(self) -> None:
        """Test getting set request ID."""
        request_id_var.set("test-id-456")
        assert get_request_id() == "test-id-456"
        request_id_var.set(None)


class TestSetupLogging:
    """Tests for logging setup."""

    def test_configures_root_logger(self, mock_settings: MagicMock) -> None:
        """Test root logger is configured."""
        setup_logging(mock_settings)

        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO
        assert len(root_logger.handlers) > 0

    def test_respects_log_level(self, mock_settings: MagicMock) -> None:
        """Test log level from settings is used."""
        mock_settings.app_log_level = "DEBUG"
        setup_logging(mock_settings)

        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG

    def test_configures_app_logger(self, mock_settings: MagicMock) -> None:
        """Test application logger is configured."""
        setup_logging(mock_settings)

        app_logger = logging.getLogger("therapy_rag")
        assert app_logger.level == logging.INFO

    def test_reduces_third_party_noise(self, mock_settings: MagicMock) -> None:
        """Test third-party loggers are quieted."""
        setup_logging(mock_settings)

        uvicorn_access = logging.getLogger("uvicorn.access")
        httpx_logger = logging.getLogger("httpx")

        assert uvicorn_access.level == logging.WARNING
        assert httpx_logger.level == logging.WARNING
