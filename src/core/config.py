"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, model_validator
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
        default="placeholder",
        description="MinIO server endpoint (host:port)",
    )
    minio_access_key: str = Field(
        default="placeholder",
        description="MinIO access key",
    )
    minio_secret_key: str = Field(
        default="placeholder",
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
        default="placeholder",
        description="Deepgram API key for transcription",
    )

    # OpenAI (Embeddings)
    openai_api_key: str = Field(
        default="placeholder",
        description="OpenAI API key for embeddings",
    )
    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        description="OpenAI embedding model name",
    )

    # Anthropic (Claude Chat)
    anthropic_api_key: str = Field(
        default="placeholder",
        description="Anthropic API key for Claude",
    )
    anthropic_model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Claude model to use for chat",
    )

    @model_validator(mode="before")
    @classmethod
    def _rewrite_database_url(cls, values: dict) -> dict:  # type: ignore[type-arg]
        """Rewrite postgresql:// to postgresql+asyncpg:// for Railway compatibility."""
        url = values.get("database_url")
        if isinstance(url, str) and url.startswith("postgresql://"):
            values["database_url"] = url.replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )
        return values

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

    # Auth
    jwt_secret: str = Field(
        default="insecure-dev-secret-change-me",
        description="Secret used to sign JWT session tokens",
    )
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = Field(
        default="HS256",
        description="JWT signing algorithm",
    )
    jwt_access_token_ttl_seconds: int = Field(
        default=43200,  # 12 hours
        description="Lifetime of therapist JWT session tokens in seconds",
    )
    jwt_cookie_name: str = Field(
        default="therapyrag_session",
        description="Name of the cookie storing the therapist JWT",
    )
    jwt_cookie_secure: bool = Field(
        default=True,
        description="Require HTTPS on JWT cookies (set to false for local dev)",
    )
    magic_link_ttl_seconds: int = Field(
        default=900,  # 15 minutes
        description="Lifetime of patient magic-link tokens in seconds",
    )

    # Stripe billing
    stripe_secret_key: str = Field(
        default="placeholder",
        description="Stripe secret API key",
    )
    stripe_webhook_secret: str = Field(
        default="placeholder",
        description="Stripe webhook signing secret for verifying events",
    )
    stripe_price_id: str = Field(
        default="placeholder",
        description="Stripe Price ID for the $149/mo therapist plan",
    )
    stripe_trial_days: int = Field(
        default=14,
        description="Free trial length in days on new subscriptions",
    )
    stripe_success_url: str = Field(
        default="http://localhost:3000/dashboard?checkout=success",
        description="Stripe redirect URL after successful checkout",
    )
    stripe_cancel_url: str = Field(
        default="http://localhost:3000/billing?checkout=canceled",
        description="Stripe redirect URL after canceled checkout",
    )
    stripe_portal_return_url: str = Field(
        default="http://localhost:3000/billing",
        description="Stripe customer portal return URL",
    )
    billing_enforced: bool = Field(
        default=False,
        description=(
            "When true, subscription-gating middleware blocks API access "
            "for orgs without an active/trialing subscription"
        ),
    )

    # Transactional email (Resend)
    resend_api_key: str = Field(
        default="placeholder",
        description="Resend API key for transactional email",
    )
    email_from_address: str = Field(
        default="noreply@therapyrag.local",
        description="From address for transactional email",
    )
    email_from_name: str = Field(
        default="TherapyRAG",
        description="From name for transactional email",
    )
    web_app_url: str = Field(
        default="http://localhost:3000",
        description="Public base URL of the web app (used in email links)",
    )

    # Error tracking
    sentry_dsn: str = Field(
        default="",
        description="Sentry DSN. Empty disables Sentry.",
    )
    sentry_environment: str = Field(
        default="development",
        description="Sentry environment tag",
    )
    sentry_traces_sample_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Fraction of transactions to record for performance monitoring",
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
