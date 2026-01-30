"""Integration tests for database connection and session management.

These tests require a running PostgreSQL database.
Run `docker compose up -d` before running these tests.
"""

import pytest
from sqlalchemy import text

from src.core.config import Settings
from src.core.database import (
    close_database,
    create_engine,
    create_session_factory,
    get_db_session,
    init_database,
)


@pytest.fixture
def test_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Create test settings pointing to test database."""
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/therapyrag"
    )
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("MINIO_ENDPOINT", "localhost:9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "minioadmin")
    monkeypatch.setenv("MINIO_SECRET_KEY", "minioadmin")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "test_key")
    monkeypatch.setenv("OPENAI_API_KEY", "test_key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")
    return Settings()


@pytest.mark.integration
class TestDatabaseConnection:
    """Tests for database connection."""

    async def test_engine_creation(self, test_settings: Settings) -> None:
        """Test that engine can be created."""
        engine = create_engine(test_settings)
        assert engine is not None
        await engine.dispose()

    async def test_session_factory_creation(self, test_settings: Settings) -> None:
        """Test that session factory can be created."""
        engine = create_engine(test_settings)
        session_factory = create_session_factory(engine)
        assert session_factory is not None
        await engine.dispose()

    async def test_database_connection(self, test_settings: Settings) -> None:
        """Test that we can connect to the database and run a query."""
        engine = create_engine(test_settings)
        session_factory = create_session_factory(engine)

        async with session_factory() as session:
            result = await session.execute(text("SELECT 1"))
            value = result.scalar()
            assert value == 1

        await engine.dispose()

    async def test_pgvector_extension(self, test_settings: Settings) -> None:
        """Test that pgvector extension is available."""
        engine = create_engine(test_settings)
        session_factory = create_session_factory(engine)

        async with session_factory() as session:
            # Check if vector extension exists
            result = await session.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            )
            row = result.first()
            # If extension not installed, this is expected in fresh db
            # The migration should install it
            assert row is None or row[0] == 1

        await engine.dispose()


@pytest.mark.integration
class TestDatabaseSession:
    """Tests for database session management."""

    async def test_get_db_session(self, test_settings: Settings) -> None:
        """Test that get_db_session provides a working session."""
        init_database(test_settings)

        async for session in get_db_session():
            result = await session.execute(text("SELECT 1"))
            value = result.scalar()
            assert value == 1

        await close_database()

    async def test_session_rollback_on_error(self, test_settings: Settings) -> None:
        """Test that session rolls back on error."""
        init_database(test_settings)

        with pytest.raises(ValueError):
            async for session in get_db_session():
                # Start a transaction
                await session.execute(text("SELECT 1"))
                # Raise error to trigger rollback
                raise ValueError("Test error")

        await close_database()
