"""Tests for health check service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.health import (
    ComponentHealth,
    HealthCheckResult,
    HealthCheckService,
    HealthStatus,
)


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings."""
    settings = MagicMock()
    settings.redis_url = "redis://localhost:6379"
    return settings


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    return session


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.DEGRADED.value == "degraded"


class TestComponentHealth:
    """Tests for ComponentHealth dataclass."""

    def test_creates_component_health(self) -> None:
        """Test creating component health."""
        health = ComponentHealth(
            name="database",
            status=HealthStatus.HEALTHY,
            message="Connected",
            latency_ms=5.2,
        )

        assert health.name == "database"
        assert health.status == HealthStatus.HEALTHY
        assert health.message == "Connected"
        assert health.latency_ms == 5.2

    def test_default_values(self) -> None:
        """Test default values."""
        health = ComponentHealth(
            name="test",
            status=HealthStatus.HEALTHY,
        )

        assert health.message is None
        assert health.latency_ms is None


class TestHealthCheckResult:
    """Tests for HealthCheckResult dataclass."""

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        result = HealthCheckResult(
            status=HealthStatus.HEALTHY,
            components=[
                ComponentHealth(
                    name="database",
                    status=HealthStatus.HEALTHY,
                    message="OK",
                    latency_ms=5.0,
                ),
                ComponentHealth(
                    name="redis",
                    status=HealthStatus.HEALTHY,
                    message="OK",
                    latency_ms=2.0,
                ),
            ],
        )

        data = result.to_dict()

        assert data["status"] == "healthy"
        assert data["version"] == "0.1.0"
        assert "database" in data["components"]
        assert data["components"]["database"]["status"] == "healthy"
        assert data["components"]["database"]["latency_ms"] == 5.0


class TestHealthCheckService:
    """Tests for HealthCheckService."""

    @pytest.mark.asyncio
    async def test_check_database_healthy(
        self,
        mock_db_session: AsyncMock,
        mock_settings: MagicMock,
    ) -> None:
        """Test healthy database check."""
        # Mock successful query
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_db_session.execute.return_value = mock_result

        service = HealthCheckService(
            db_session=mock_db_session,
            settings=mock_settings,
        )

        result = await service.check_database()

        assert result.name == "database"
        assert result.status == HealthStatus.HEALTHY
        assert result.message == "Connected"
        assert result.latency_ms is not None

    @pytest.mark.asyncio
    async def test_check_database_unhealthy(
        self,
        mock_db_session: AsyncMock,
        mock_settings: MagicMock,
    ) -> None:
        """Test unhealthy database check."""
        mock_db_session.execute.side_effect = Exception("Connection refused")

        service = HealthCheckService(
            db_session=mock_db_session,
            settings=mock_settings,
        )

        result = await service.check_database()

        assert result.name == "database"
        assert result.status == HealthStatus.UNHEALTHY
        assert "Connection refused" in result.message

    @pytest.mark.asyncio
    async def test_check_database_no_session(
        self,
        mock_settings: MagicMock,
    ) -> None:
        """Test database check with no session."""
        service = HealthCheckService(
            db_session=None,
            settings=mock_settings,
        )

        result = await service.check_database()

        assert result.status == HealthStatus.UNHEALTHY
        assert "No database session" in result.message

    @pytest.mark.asyncio
    async def test_check_liveness(
        self,
        mock_settings: MagicMock,
    ) -> None:
        """Test liveness check."""
        service = HealthCheckService(settings=mock_settings)

        result = await service.check_liveness()

        assert result.name == "liveness"
        assert result.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_check_all_healthy(
        self,
        mock_db_session: AsyncMock,
        mock_settings: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test check_all when all components healthy."""
        # Mock database
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_db_session.execute.return_value = mock_result

        # Mock Redis
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True

        def mock_from_url(*args, **kwargs):  # noqa: ARG001
            return mock_redis

        monkeypatch.setattr("src.core.health.Redis.from_url", mock_from_url)

        service = HealthCheckService(
            db_session=mock_db_session,
            settings=mock_settings,
        )

        result = await service.check_all()

        assert result.status == HealthStatus.HEALTHY
        assert len(result.components) == 2

    @pytest.mark.asyncio
    async def test_check_all_database_unhealthy(
        self,
        mock_db_session: AsyncMock,
        mock_settings: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test check_all when database is unhealthy."""
        # Mock database failure
        mock_db_session.execute.side_effect = Exception("DB error")

        # Mock Redis healthy
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True

        def mock_from_url(*args, **kwargs):  # noqa: ARG001
            return mock_redis

        monkeypatch.setattr("src.core.health.Redis.from_url", mock_from_url)

        service = HealthCheckService(
            db_session=mock_db_session,
            settings=mock_settings,
        )

        result = await service.check_all()

        # Database is critical, so overall should be unhealthy
        assert result.status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_check_all_redis_unhealthy(
        self,
        mock_db_session: AsyncMock,
        mock_settings: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test check_all when Redis is unhealthy."""
        # Mock database healthy
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_db_session.execute.return_value = mock_result

        # Mock Redis failure
        def mock_from_url(*args, **kwargs):  # noqa: ARG001
            raise Exception("Redis connection failed")

        monkeypatch.setattr("src.core.health.Redis.from_url", mock_from_url)

        service = HealthCheckService(
            db_session=mock_db_session,
            settings=mock_settings,
        )

        result = await service.check_all()

        # Redis is not critical, so overall should be degraded
        assert result.status == HealthStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_check_readiness(
        self,
        mock_db_session: AsyncMock,
        mock_settings: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test readiness check."""
        # Mock all healthy
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_db_session.execute.return_value = mock_result

        mock_redis = MagicMock()
        mock_redis.ping.return_value = True

        def mock_from_url(*args, **kwargs):  # noqa: ARG001
            return mock_redis

        monkeypatch.setattr("src.core.health.Redis.from_url", mock_from_url)

        service = HealthCheckService(
            db_session=mock_db_session,
            settings=mock_settings,
        )

        result = await service.check_readiness()

        assert result.status == HealthStatus.HEALTHY
