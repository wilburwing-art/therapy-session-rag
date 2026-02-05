"""Health check service for monitoring application dependencies."""

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from redis import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class HealthStatus(StrEnum):
    """Health check status values."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"


@dataclass
class ComponentHealth:
    """Health status for a single component."""

    name: str
    status: HealthStatus
    message: str | None = None
    latency_ms: float | None = None


@dataclass
class HealthCheckResult:
    """Overall health check result."""

    status: HealthStatus
    components: list[ComponentHealth]
    version: str = "0.1.0"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            "status": self.status.value,
            "version": self.version,
            "components": {
                c.name: {
                    "status": c.status.value,
                    "message": c.message,
                    "latency_ms": c.latency_ms,
                }
                for c in self.components
            },
        }


class HealthCheckService:
    """Service for checking health of application dependencies."""

    def __init__(
        self,
        db_session: AsyncSession | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Initialize health check service.

        Args:
            db_session: Database session for DB health checks
            settings: Application settings
        """
        self.db_session = db_session
        self.settings = settings or get_settings()

    async def check_database(self) -> ComponentHealth:
        """Check database connectivity.

        Returns:
            ComponentHealth for database
        """
        if self.db_session is None:
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message="No database session available",
            )

        import time

        start = time.perf_counter()
        try:
            # Execute simple query to verify connection
            result = await self.db_session.execute(text("SELECT 1"))
            result.scalar()
            latency = (time.perf_counter() - start) * 1000

            return ComponentHealth(
                name="database",
                status=HealthStatus.HEALTHY,
                message="Connected",
                latency_ms=round(latency, 2),
            )
        except Exception as e:
            logger.warning(f"Database health check failed: {e}")
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )

    async def check_redis(self) -> ComponentHealth:
        """Check Redis connectivity.

        Returns:
            ComponentHealth for Redis
        """
        import time

        start = time.perf_counter()
        try:
            redis_client: Redis = Redis.from_url(  # type: ignore[type-arg]
                str(self.settings.redis_url),
                socket_timeout=5,
            )
            redis_client.ping()
            latency = (time.perf_counter() - start) * 1000
            redis_client.close()

            return ComponentHealth(
                name="redis",
                status=HealthStatus.HEALTHY,
                message="Connected",
                latency_ms=round(latency, 2),
            )
        except Exception as e:
            logger.warning(f"Redis health check failed: {e}")
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )

    async def check_all(self) -> HealthCheckResult:
        """Check all dependencies and return overall health.

        Returns:
            HealthCheckResult with all component statuses
        """
        components = [
            await self.check_database(),
            await self.check_redis(),
        ]

        # Determine overall status
        if all(c.status == HealthStatus.HEALTHY for c in components):
            overall_status = HealthStatus.HEALTHY
        elif any(c.status == HealthStatus.UNHEALTHY for c in components):
            # If any critical component is unhealthy, overall is unhealthy
            critical_components = {"database"}
            critical_unhealthy = any(
                c.status == HealthStatus.UNHEALTHY and c.name in critical_components
                for c in components
            )
            overall_status = (
                HealthStatus.UNHEALTHY if critical_unhealthy else HealthStatus.DEGRADED
            )
        else:
            overall_status = HealthStatus.DEGRADED

        return HealthCheckResult(
            status=overall_status,
            components=components,
        )

    async def check_liveness(self) -> ComponentHealth:
        """Simple liveness check (is the app running).

        Returns:
            ComponentHealth for liveness
        """
        return ComponentHealth(
            name="liveness",
            status=HealthStatus.HEALTHY,
            message="Application is running",
        )

    async def check_readiness(self) -> HealthCheckResult:
        """Check if application is ready to serve traffic.

        This is the same as check_all - verifies all dependencies.

        Returns:
            HealthCheckResult
        """
        return await self.check_all()
