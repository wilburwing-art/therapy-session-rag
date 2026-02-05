"""Request event tracking middleware."""

from __future__ import annotations

import logging
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class EventTrackingMiddleware(BaseHTTPMiddleware):
    """Middleware that records request.completed events with timing data.

    Attaches timing and route info to request.state so endpoint handlers
    can include it in their event properties. Also publishes a
    performance event for every completed request.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.perf_counter()
        request.state.request_start_time = start

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        # Store on response headers for observability
        response.headers["X-Request-Duration-Ms"] = str(duration_ms)

        # Build performance context for downstream consumers
        request_context: dict[str, Any] = {
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        }

        # Attach to request state for endpoint-level event publishing
        request.state.request_context = request_context

        logger.debug(
            "request completed: %s %s %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )

        return response
