"""Structured JSON logging configuration."""

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from src.core.config import Settings

# Context variable for request ID tracking
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Sensitive fields to redact from logs
SENSITIVE_FIELDS = {
    "password",
    "api_key",
    "secret",
    "token",
    "authorization",
    "x-api-key",
    "anthropic_api_key",
    "openai_api_key",
    "deepgram_api_key",
    "minio_secret_key",
    "minio_access_key",
}


def get_request_id() -> str | None:
    """Get the current request ID from context."""
    return request_id_var.get()


def redact_sensitive_data(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively redact sensitive fields from a dictionary.

    Args:
        data: Dictionary to redact

    Returns:
        Dictionary with sensitive values replaced with "[REDACTED]"
    """
    redacted: dict[str, Any] = {}
    for key, value in data.items():
        key_lower = key.lower()
        if any(sensitive in key_lower for sensitive in SENSITIVE_FIELDS):
            redacted[key] = "[REDACTED]"
        elif isinstance(value, dict):
            redacted[key] = redact_sensitive_data(value)
        elif isinstance(value, list):
            redacted[key] = [
                redact_sensitive_data(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            redacted[key] = value
    return redacted


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: Log record to format

        Returns:
            JSON string representation of the log record
        """
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add request ID if available
        request_id = get_request_id()
        if request_id:
            log_data["request_id"] = request_id

        # Add location info
        if record.pathname:
            log_data["location"] = {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
            }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info),
            }

        # Add extra fields from record
        extra_fields = {
            key: value
            for key, value in record.__dict__.items()
            if key
            not in {
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "exc_info",
                "exc_text",
                "thread",
                "threadName",
                "taskName",
                "message",
            }
        }
        if extra_fields:
            log_data["extra"] = redact_sensitive_data(extra_fields)

        return json.dumps(log_data, default=str)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging HTTP requests with request ID tracking."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process request with logging.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in chain

        Returns:
            HTTP response
        """
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request_id_var.set(request_id)

        # Log request start
        logger = logging.getLogger("therapy_rag.request")
        start_time = datetime.now(UTC)

        logger.info(
            "Request started",
            extra={
                "method": request.method,
                "path": str(request.url.path),
                "query": str(request.query_params) if request.query_params else None,
                "client_ip": request.client.host if request.client else None,
            },
        )

        try:
            response = await call_next(request)

            # Calculate duration
            duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

            # Log request completion
            logger.info(
                "Request completed",
                extra={
                    "method": request.method,
                    "path": str(request.url.path),
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                },
            )

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            # Calculate duration
            duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

            # Log error
            logger.exception(
                "Request failed",
                extra={
                    "method": request.method,
                    "path": str(request.url.path),
                    "duration_ms": round(duration_ms, 2),
                    "error": str(e),
                },
            )
            raise

        finally:
            # Clear request ID
            request_id_var.set(None)


def setup_logging(settings: Settings) -> None:
    """Configure structured logging for the application.

    Args:
        settings: Application settings
    """
    # Get log level from settings
    log_level = getattr(logging, settings.app_log_level.upper(), logging.INFO)

    # Create JSON formatter
    json_formatter = JSONFormatter()

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add stdout handler with JSON formatter
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(json_formatter)
    stdout_handler.setLevel(log_level)
    root_logger.addHandler(stdout_handler)

    # Configure specific loggers
    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Application loggers
    app_logger = logging.getLogger("therapy_rag")
    app_logger.setLevel(log_level)


def setup_request_logging(app: FastAPI) -> None:
    """Add request logging middleware to FastAPI application.

    Args:
        app: FastAPI application instance
    """
    app.add_middleware(RequestLoggingMiddleware)
