"""Tests for exception handling."""

from fastapi import status

from src.core.exceptions import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    UnauthorizedError,
    ValidationError,
)


class TestAppError:
    """Tests for base AppError class."""

    def test_app_error_creation(self) -> None:
        """Test AppError can be created with required fields."""
        error = AppError(
            title="Test Error",
            detail="This is a test error",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

        assert error.title == "Test Error"
        assert error.detail == "This is a test error"
        assert error.status_code == status.HTTP_400_BAD_REQUEST

    def test_app_error_to_problem_detail(self) -> None:
        """Test AppError converts to RFC 7807 format."""
        error = AppError(
            title="Test Error",
            detail="This is a test error",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_type="test-error",
            instance="/test/1",
            extra={"field": "value"},
        )

        problem = error.to_problem_detail()

        assert problem["type"] == "test-error"
        assert problem["title"] == "Test Error"
        assert problem["status"] == status.HTTP_400_BAD_REQUEST
        assert problem["detail"] == "This is a test error"
        assert problem["instance"] == "/test/1"
        assert problem["field"] == "value"

    def test_app_error_default_type(self) -> None:
        """Test AppError generates default type from status code."""
        error = AppError(
            title="Test",
            detail="Test",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

        assert error.error_type == f"about:blank#{status.HTTP_400_BAD_REQUEST}"


class TestNotFoundError:
    """Tests for NotFoundError."""

    def test_not_found_basic(self) -> None:
        """Test NotFoundError with resource name only."""
        error = NotFoundError(resource="User")

        assert error.status_code == status.HTTP_404_NOT_FOUND
        assert error.detail == "User not found"

    def test_not_found_with_id(self) -> None:
        """Test NotFoundError with resource ID."""
        error = NotFoundError(resource="User", resource_id="123")

        assert error.detail == "User with id '123' not found"

    def test_not_found_custom_detail(self) -> None:
        """Test NotFoundError with custom detail."""
        error = NotFoundError(resource="User", detail="Custom message")

        assert error.detail == "Custom message"


class TestValidationError:
    """Tests for ValidationError."""

    def test_validation_error_basic(self) -> None:
        """Test ValidationError with detail only."""
        error = ValidationError(detail="Invalid input")

        assert error.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert error.detail == "Invalid input"
        assert error.extra["errors"] == []

    def test_validation_error_with_errors(self) -> None:
        """Test ValidationError with error list."""
        errors = [{"field": "email", "message": "Invalid email format"}]
        error = ValidationError(detail="Invalid input", errors=errors)

        assert error.extra["errors"] == errors


class TestUnauthorizedError:
    """Tests for UnauthorizedError."""

    def test_unauthorized_default(self) -> None:
        """Test UnauthorizedError with default message."""
        error = UnauthorizedError()

        assert error.status_code == status.HTTP_401_UNAUTHORIZED
        assert error.detail == "Authentication required"

    def test_unauthorized_custom(self) -> None:
        """Test UnauthorizedError with custom message."""
        error = UnauthorizedError(detail="Invalid token")

        assert error.detail == "Invalid token"


class TestForbiddenError:
    """Tests for ForbiddenError."""

    def test_forbidden_default(self) -> None:
        """Test ForbiddenError with default message."""
        error = ForbiddenError()

        assert error.status_code == status.HTTP_403_FORBIDDEN
        assert error.detail == "Permission denied"


class TestConflictError:
    """Tests for ConflictError."""

    def test_conflict_error(self) -> None:
        """Test ConflictError."""
        error = ConflictError(detail="Resource already exists")

        assert error.status_code == status.HTTP_409_CONFLICT
        assert error.detail == "Resource already exists"


class TestRateLimitError:
    """Tests for RateLimitError."""

    def test_rate_limit_default(self) -> None:
        """Test RateLimitError with default message."""
        error = RateLimitError()

        assert error.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert error.detail == "Rate limit exceeded"

    def test_rate_limit_with_retry(self) -> None:
        """Test RateLimitError with retry_after."""
        error = RateLimitError(retry_after=60)

        assert error.extra["retry_after"] == 60
