"""Tests for configuration module."""

import pytest
from pydantic import ValidationError

from src.core.config import Settings, get_settings


class TestSettings:
    """Tests for Settings class."""

    def test_settings_loads_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that settings load from environment variables."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("MINIO_ENDPOINT", "localhost:9000")
        monkeypatch.setenv("MINIO_ACCESS_KEY", "minioadmin")
        monkeypatch.setenv("MINIO_SECRET_KEY", "minioadmin")
        monkeypatch.setenv("DEEPGRAM_API_KEY", "test_deepgram_key")
        monkeypatch.setenv("OPENAI_API_KEY", "test_openai_key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test_anthropic_key")

        settings = Settings()

        assert str(settings.database_url) == "postgresql+asyncpg://user:pass@localhost:5432/db"
        assert str(settings.redis_url) == "redis://localhost:6379/0"
        assert settings.minio_endpoint == "localhost:9000"
        assert settings.deepgram_api_key == "test_deepgram_key"

    def test_settings_validation_fails_without_required(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that validation fails when required vars are missing."""
        # Clear any existing env vars
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.delenv("MINIO_ENDPOINT", raising=False)

        with pytest.raises(ValidationError):
            # Skip loading from .env file to ensure env vars are truly missing
            Settings(_env_file=None)

    def test_settings_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that default values are applied correctly."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("MINIO_ENDPOINT", "localhost:9000")
        monkeypatch.setenv("MINIO_ACCESS_KEY", "minioadmin")
        monkeypatch.setenv("MINIO_SECRET_KEY", "minioadmin")
        monkeypatch.setenv("DEEPGRAM_API_KEY", "test_deepgram_key")
        monkeypatch.setenv("OPENAI_API_KEY", "test_openai_key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test_anthropic_key")
        # Clear optional vars to test defaults
        monkeypatch.delenv("MINIO_BUCKET", raising=False)
        monkeypatch.delenv("MINIO_SECURE", raising=False)
        monkeypatch.delenv("OPENAI_EMBEDDING_MODEL", raising=False)
        monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("APP_DEBUG", raising=False)
        monkeypatch.delenv("API_RATE_LIMIT_PER_HOUR", raising=False)
        monkeypatch.delenv("CHAT_RATE_LIMIT_PER_HOUR", raising=False)
        monkeypatch.delenv("MAX_UPLOAD_SIZE", raising=False)

        settings = Settings(_env_file=None)

        assert settings.minio_bucket == "therapy-recordings"
        assert settings.minio_secure is False
        assert settings.openai_embedding_model == "text-embedding-3-small"
        assert settings.anthropic_model == "claude-sonnet-4-20250514"
        assert settings.app_env == "development"
        assert settings.app_debug is False
        assert settings.api_rate_limit_per_hour == 1000
        assert settings.chat_rate_limit_per_hour == 20
        assert settings.max_upload_size == 524288000

    def test_cors_origins_list_wildcard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test CORS origins parsing with wildcard."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("MINIO_ENDPOINT", "localhost:9000")
        monkeypatch.setenv("MINIO_ACCESS_KEY", "minioadmin")
        monkeypatch.setenv("MINIO_SECRET_KEY", "minioadmin")
        monkeypatch.setenv("DEEPGRAM_API_KEY", "test_deepgram_key")
        monkeypatch.setenv("OPENAI_API_KEY", "test_openai_key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test_anthropic_key")
        monkeypatch.setenv("CORS_ORIGINS", "*")

        settings = Settings()

        assert settings.cors_origins_list == ["*"]

    def test_cors_origins_list_multiple(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test CORS origins parsing with multiple origins."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("MINIO_ENDPOINT", "localhost:9000")
        monkeypatch.setenv("MINIO_ACCESS_KEY", "minioadmin")
        monkeypatch.setenv("MINIO_SECRET_KEY", "minioadmin")
        monkeypatch.setenv("DEEPGRAM_API_KEY", "test_deepgram_key")
        monkeypatch.setenv("OPENAI_API_KEY", "test_openai_key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test_anthropic_key")
        monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000, https://example.com")

        settings = Settings()

        assert settings.cors_origins_list == ["http://localhost:3000", "https://example.com"]

    def test_is_development(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test is_development property."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("MINIO_ENDPOINT", "localhost:9000")
        monkeypatch.setenv("MINIO_ACCESS_KEY", "minioadmin")
        monkeypatch.setenv("MINIO_SECRET_KEY", "minioadmin")
        monkeypatch.setenv("DEEPGRAM_API_KEY", "test_deepgram_key")
        monkeypatch.setenv("OPENAI_API_KEY", "test_openai_key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test_anthropic_key")
        monkeypatch.setenv("APP_ENV", "development")

        settings = Settings()

        assert settings.is_development is True
        assert settings.is_production is False

    def test_is_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test is_production property."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("MINIO_ENDPOINT", "localhost:9000")
        monkeypatch.setenv("MINIO_ACCESS_KEY", "minioadmin")
        monkeypatch.setenv("MINIO_SECRET_KEY", "minioadmin")
        monkeypatch.setenv("DEEPGRAM_API_KEY", "test_deepgram_key")
        monkeypatch.setenv("OPENAI_API_KEY", "test_openai_key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test_anthropic_key")
        monkeypatch.setenv("APP_ENV", "production")

        settings = Settings()

        assert settings.is_development is False
        assert settings.is_production is True


class TestGetSettings:
    """Tests for get_settings function."""

    def test_get_settings_returns_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that get_settings returns a Settings instance."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("MINIO_ENDPOINT", "localhost:9000")
        monkeypatch.setenv("MINIO_ACCESS_KEY", "minioadmin")
        monkeypatch.setenv("MINIO_SECRET_KEY", "minioadmin")
        monkeypatch.setenv("DEEPGRAM_API_KEY", "test_deepgram_key")
        monkeypatch.setenv("OPENAI_API_KEY", "test_openai_key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test_anthropic_key")

        # Clear the cache to get fresh settings
        get_settings.cache_clear()

        settings = get_settings()

        assert isinstance(settings, Settings)

    def test_get_settings_is_cached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that get_settings returns the same instance (singleton)."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("MINIO_ENDPOINT", "localhost:9000")
        monkeypatch.setenv("MINIO_ACCESS_KEY", "minioadmin")
        monkeypatch.setenv("MINIO_SECRET_KEY", "minioadmin")
        monkeypatch.setenv("DEEPGRAM_API_KEY", "test_deepgram_key")
        monkeypatch.setenv("OPENAI_API_KEY", "test_openai_key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test_anthropic_key")

        # Clear the cache to get fresh settings
        get_settings.cache_clear()

        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2
