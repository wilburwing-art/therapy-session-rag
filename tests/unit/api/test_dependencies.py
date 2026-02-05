"""Tests for API dependencies."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.v1.dependencies import AuthContext, get_api_key_auth
from src.core.exceptions import UnauthorizedError
from src.core.security import create_api_key
from src.models.db.api_key import ApiKey


class TestGetApiKeyAuth:
    """Tests for get_api_key_auth dependency."""

    async def test_missing_api_key_raises_unauthorized(self) -> None:
        """Test that missing API key raises UnauthorizedError."""
        mock_session = AsyncMock()

        with pytest.raises(UnauthorizedError) as exc_info:
            await get_api_key_auth(x_api_key=None, session=mock_session)

        assert "API key required" in str(exc_info.value.detail)

    async def test_invalid_format_raises_unauthorized(self) -> None:
        """Test that invalid API key format raises UnauthorizedError."""
        mock_session = AsyncMock()

        with pytest.raises(UnauthorizedError) as exc_info:
            await get_api_key_auth(x_api_key="invalid_key", session=mock_session)

        assert "Invalid API key format" in str(exc_info.value.detail)

    async def test_valid_key_returns_auth_context(self) -> None:
        """Test that valid API key returns AuthContext."""
        # Create a test API key
        plain_key, hashed_key = create_api_key()
        org_id = uuid.uuid4()
        key_id = uuid.uuid4()

        # Mock the API key model
        mock_api_key = MagicMock(spec=ApiKey)
        mock_api_key.id = key_id
        mock_api_key.organization_id = org_id
        mock_api_key.key_hash = hashed_key
        mock_api_key.name = "Test Key"
        mock_api_key.is_active = True

        # Mock the database query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_api_key]

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        # Mock the repository
        with patch(
            "src.api.v1.dependencies.ApiKeyRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo

            result = await get_api_key_auth(x_api_key=plain_key, session=mock_session)

        assert isinstance(result, AuthContext)
        assert result.api_key_id == key_id
        assert result.organization_id == org_id
        assert result.api_key_name == "Test Key"

    async def test_invalid_key_raises_unauthorized(self) -> None:
        """Test that wrong API key raises UnauthorizedError."""
        # Create a test API key but use a different one
        _, hashed_key = create_api_key()
        wrong_key, _ = create_api_key()

        # Mock the API key model
        mock_api_key = MagicMock(spec=ApiKey)
        mock_api_key.id = uuid.uuid4()
        mock_api_key.organization_id = uuid.uuid4()
        mock_api_key.key_hash = hashed_key
        mock_api_key.name = "Test Key"
        mock_api_key.is_active = True

        # Mock the database query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_api_key]

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        with pytest.raises(UnauthorizedError) as exc_info:
            await get_api_key_auth(x_api_key=wrong_key, session=mock_session)

        assert "Invalid API key" in str(exc_info.value.detail)

    async def test_no_active_keys_raises_unauthorized(self) -> None:
        """Test that when no active keys exist, raises UnauthorizedError."""
        plain_key, _ = create_api_key()

        # Mock empty database result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        with pytest.raises(UnauthorizedError) as exc_info:
            await get_api_key_auth(x_api_key=plain_key, session=mock_session)

        assert "Invalid API key" in str(exc_info.value.detail)


class TestAuthContext:
    """Tests for AuthContext dataclass."""

    def test_auth_context_creation(self) -> None:
        """Test AuthContext can be created with required fields."""
        api_key_id = uuid.uuid4()
        org_id = uuid.uuid4()

        context = AuthContext(
            api_key_id=api_key_id,
            organization_id=org_id,
            api_key_name="Test Key",
        )

        assert context.api_key_id == api_key_id
        assert context.organization_id == org_id
        assert context.api_key_name == "Test Key"
