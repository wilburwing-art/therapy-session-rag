"""Pytest configuration and shared fixtures."""

import os

import pytest

# Set test environment variables before any imports from src
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
os.environ.setdefault("DEEPGRAM_API_KEY", "test_key")
os.environ.setdefault("OPENAI_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")


@pytest.fixture(autouse=True)
def reset_settings_cache() -> None:
    """Reset settings cache before each test."""
    from src.core.config import get_settings

    get_settings.cache_clear()
