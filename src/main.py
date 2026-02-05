"""FastAPI application entry point."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1 import router as v1_router
from src.core.config import get_settings
from src.core.database import close_database, get_db_session, init_database
from src.core.event_middleware import EventTrackingMiddleware
from src.core.exceptions import setup_exception_handlers
from src.core.health import HealthCheckService, HealthStatus
from src.core.logging import setup_logging, setup_request_logging

logger = logging.getLogger("therapy_rag")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:  # noqa: ARG001
    """Application lifespan handler for startup and shutdown."""
    # Startup
    settings = get_settings()
    init_database(settings)
    logger.info("Application started", extra={"env": settings.app_env})
    yield
    # Shutdown
    logger.info("Application shutting down")
    await close_database()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    # Setup structured logging first
    setup_logging(settings)

    app = FastAPI(
        title="TherapyRAG API",
        description="Therapy session recording, transcription, and RAG chatbot platform",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Setup request logging middleware (must be added before CORS)
    setup_request_logging(app)

    # Event tracking middleware (request timing and context)
    app.add_middleware(EventTrackingMiddleware)

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Setup exception handlers
    setup_exception_handlers(app)

    # Health check endpoints (no auth required)
    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Simple health check endpoint for basic liveness probes."""
        return {"status": "healthy"}

    @app.get("/health/live", tags=["health"])
    async def liveness_check() -> dict[str, str]:
        """Kubernetes liveness probe endpoint.

        Returns 200 if the application is running.
        """
        return {"status": "healthy"}

    @app.get("/health/ready", tags=["health"])
    async def readiness_check(
        db_session: AsyncSession = Depends(get_db_session),
    ) -> Response:
        """Kubernetes readiness probe endpoint.

        Returns 200 if all dependencies are healthy,
        503 if any critical dependency is unhealthy.
        """
        health_service = HealthCheckService(db_session=db_session, settings=settings)
        result = await health_service.check_readiness()

        status_code = 200 if result.status != HealthStatus.UNHEALTHY else 503
        return JSONResponse(content=result.to_dict(), status_code=status_code)

    @app.get("/health/detailed", tags=["health"])
    async def detailed_health_check(
        db_session: AsyncSession = Depends(get_db_session),
    ) -> dict[str, Any]:
        """Detailed health check with all component statuses.

        Useful for debugging and monitoring dashboards.
        """
        health_service = HealthCheckService(db_session=db_session, settings=settings)
        result = await health_service.check_all()
        return result.to_dict()

    # Include API routers
    app.include_router(v1_router)

    return app


# Create application instance
app = create_app()


def run() -> None:
    """Run the application with uvicorn."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development,
        log_level=settings.app_log_level.lower(),
    )


if __name__ == "__main__":
    run()
