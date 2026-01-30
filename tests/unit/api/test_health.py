"""Tests for health endpoint."""

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from src.main import create_app


@pytest.fixture
def test_app():  # type: ignore[no-untyped-def]
    """Create test application."""
    return create_app()


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    async def test_health_returns_healthy(self, test_app) -> None:  # type: ignore[no-untyped-def]
        """Test that health endpoint returns healthy status."""
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "healthy"}

    async def test_health_no_auth_required(self, test_app) -> None:  # type: ignore[no-untyped-def]
        """Test that health endpoint does not require authentication."""
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # No auth headers provided
            response = await client.get("/health")

        assert response.status_code == status.HTTP_200_OK
