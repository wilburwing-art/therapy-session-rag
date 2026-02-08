"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: PostgresDsn = Field(
        default=...,
        description="PostgreSQL connection URL with asyncpg driver",
    )

    # Redis
    redis_url: RedisDsn = Field(
        default=...,
        description="Redis connection URL",
    )

    # MinIO (S3-compatible storage)
    minio_endpoint: str = Field(
        default=...,
        description="MinIO server endpoint (host:port)",
    )
    minio_access_key: str = Field(
        default=...,
        description="MinIO access key",
    )
    minio_secret_key: str = Field(
        default=...,
        description="MinIO secret key",
    )
    minio_bucket: str = Field(
        default="therapy-recordings",
        description="MinIO bucket for storing recordings",
    )
    minio_secure: bool = Field(
        default=False,
        description="Use HTTPS for MinIO connections",
    )

    # Deepgram (Transcription)
    deepgram_api_key: str = Field(
        default=...,
        description="Deepgram API key for transcription",
    )

    # OpenAI (Embeddings)
    openai_api_key: str = Field(
        default=...,
        description="OpenAI API key for embeddings",
    )
    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        description="OpenAI embedding model name",
    )

    # Anthropic (Claude Chat)
    anthropic_api_key: str = Field(
        default=...,
        description="Anthropic API key for Claude",
    )
    anthropic_model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Claude model to use for chat",
    )

    # Application
    app_env: Literal["development", "staging", "production", "test"] = Field(
        default="development",
        description="Application environment",
    )
    app_debug: bool = Field(
        default=False,
        description="Enable debug mode",
    )
    app_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level",
    )

    # CORS
    cors_origins: str = Field(
        default="*",
        description="Comma-separated list of allowed CORS origins",
    )

    # Rate limits
    api_rate_limit_per_hour: int = Field(
        default=1000,
        description="API rate limit per hour per API key",
    )
    chat_rate_limit_per_hour: int = Field(
        default=20,
        description="Chat rate limit per hour per patient",
    )

    # Safety
    safety_enabled: bool = Field(
        default=True,
        description="Enable clinical AI safety guardrails",
    )

    # File upload
    max_upload_size: int = Field(
        default=524288000,  # 500MB
        description="Maximum upload file size in bytes",
    )

    # Video Chat (Metered.ca TURN server)
    turn_enabled: bool = Field(
        default=False,
        description="Enable video chat TURN server",
    )
    metered_turn_username: str = Field(
        default="",
        description="Metered.ca TURN username",
    )
    metered_turn_credential: str = Field(
        default="",
        description="Metered.ca TURN credential",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins into a list."""
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance (singleton pattern)."""
    return Settings()
