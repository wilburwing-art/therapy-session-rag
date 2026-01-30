"""Custom exceptions and error handling for RFC 7807 Problem Details."""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base application error with RFC 7807 Problem Details support."""

    def __init__(
        self,
        title: str,
        detail: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_type: str | None = None,
        instance: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.title = title
        self.detail = detail
        self.status_code = status_code
        self.error_type = error_type or f"about:blank#{status_code}"
        self.instance = instance
        self.extra = extra or {}
        super().__init__(detail)

    def to_problem_detail(self) -> dict[str, Any]:
        """Convert to RFC 7807 Problem Details format."""
        problem = {
            "type": self.error_type,
            "title": self.title,
            "status": self.status_code,
            "detail": self.detail,
        }
        if self.instance:
            problem["instance"] = self.instance
        problem.update(self.extra)
        return problem


class NotFoundError(AppError):
    """Resource not found error."""

    def __init__(
        self,
        resource: str,
        resource_id: str | None = None,
        detail: str | None = None,
    ) -> None:
        if detail is None:
            detail = f"{resource} not found"
            if resource_id:
                detail = f"{resource} with id '{resource_id}' not found"
        super().__init__(
            title="Not Found",
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            error_type="about:blank#not-found",
        )


class ValidationError(AppError):
    """Validation error."""

    def __init__(
        self,
        detail: str,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            title="Validation Error",
            detail=detail,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_type="about:blank#validation-error",
            extra={"errors": errors or []},
        )


class UnauthorizedError(AppError):
    """Authentication required error."""

    def __init__(self, detail: str = "Authentication required") -> None:
        super().__init__(
            title="Unauthorized",
            detail=detail,
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_type="about:blank#unauthorized",
        )


class ForbiddenError(AppError):
    """Permission denied error."""

    def __init__(self, detail: str = "Permission denied") -> None:
        super().__init__(
            title="Forbidden",
            detail=detail,
            status_code=status.HTTP_403_FORBIDDEN,
            error_type="about:blank#forbidden",
        )


class ConflictError(AppError):
    """Resource conflict error."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            title="Conflict",
            detail=detail,
            status_code=status.HTTP_409_CONFLICT,
            error_type="about:blank#conflict",
        )


class RateLimitError(AppError):
    """Rate limit exceeded error."""

    def __init__(
        self,
        detail: str = "Rate limit exceeded",
        retry_after: int | None = None,
    ) -> None:
        extra = {}
        if retry_after:
            extra["retry_after"] = retry_after
        super().__init__(
            title="Too Many Requests",
            detail=detail,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_type="about:blank#rate-limit",
            extra=extra,
        )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:  # noqa: ARG001
    """Handle AppError exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_problem_detail(),
        media_type="application/problem+json",
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001
    """Handle unexpected exceptions."""
    error = AppError(
        title="Internal Server Error",
        detail="An unexpected error occurred",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
    return JSONResponse(
        status_code=error.status_code,
        content=error.to_problem_detail(),
        media_type="application/problem+json",
    )


def setup_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers with the FastAPI application."""
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, generic_exception_handler)
