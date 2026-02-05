"""Rate limiter service using Redis."""

import logging
import uuid

from redis import Redis

from src.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Exception raised when rate limit is exceeded."""

    def __init__(
        self,
        message: str,
        remaining: int = 0,
        reset_time: int = 0,
    ) -> None:
        super().__init__(message)
        self.remaining = remaining
        self.reset_time = reset_time


class RateLimiter:
    """Rate limiter using Redis for counter storage.

    Implements a sliding window counter for rate limiting.
    Counters are stored in Redis with automatic expiration.
    """

    KEY_PREFIX = "rate_limit"
    DEFAULT_WINDOW_SECONDS = 3600  # 1 hour

    def __init__(
        self,
        redis_client: Redis | None = None,  # type: ignore[type-arg]
        settings: Settings | None = None,
        window_seconds: int | None = None,
    ) -> None:
        """Initialize the rate limiter.

        Args:
            redis_client: Redis client instance. If None, creates from settings.
            settings: Application settings. Defaults to get_settings().
            window_seconds: Window size in seconds. Defaults to 3600 (1 hour).
        """
        self.settings = settings or get_settings()
        self._redis: Redis | None = redis_client  # type: ignore[type-arg]
        self.window_seconds = window_seconds or self.DEFAULT_WINDOW_SECONDS

    @property
    def redis(self) -> Redis:  # type: ignore[type-arg]
        """Get or create Redis client (lazy initialization)."""
        if self._redis is None:
            self._redis = Redis.from_url(str(self.settings.redis_url))
        return self._redis

    def _make_key(self, key_type: str, identifier: str) -> str:
        """Generate a Redis key.

        Args:
            key_type: Type of rate limit (e.g., "chat", "api")
            identifier: Unique identifier (e.g., patient_id, api_key_id)

        Returns:
            Redis key string
        """
        return f"{self.KEY_PREFIX}:{key_type}:{identifier}"

    async def check_rate_limit(
        self,
        key_type: str,
        identifier: uuid.UUID | str,
        max_requests: int,
    ) -> dict[str, int]:
        """Check if a request is within rate limits.

        Args:
            key_type: Type of rate limit (e.g., "chat", "api")
            identifier: Unique identifier (e.g., patient_id)
            max_requests: Maximum requests allowed in the window

        Returns:
            Dict with current_count, remaining, and reset_time

        Raises:
            RateLimitExceeded: If rate limit is exceeded
        """
        key = self._make_key(key_type, str(identifier))

        # Get current count
        current = self.redis.get(key)
        current_count = int(current) if current else 0

        # Get TTL for reset time
        ttl = self.redis.ttl(key)
        reset_time = max(0, ttl) if ttl > 0 else self.window_seconds

        remaining = max(0, max_requests - current_count)

        if current_count >= max_requests:
            raise RateLimitExceeded(
                f"Rate limit exceeded. Max {max_requests} requests per {self.window_seconds} seconds.",
                remaining=0,
                reset_time=reset_time,
            )

        return {
            "current_count": current_count,
            "remaining": remaining,
            "reset_time": reset_time,
        }

    async def increment(
        self,
        key_type: str,
        identifier: uuid.UUID | str,
    ) -> int:
        """Increment the counter for an identifier.

        Args:
            key_type: Type of rate limit (e.g., "chat", "api")
            identifier: Unique identifier (e.g., patient_id)

        Returns:
            New count value
        """
        key = self._make_key(key_type, str(identifier))

        # Use INCR with EXPIRE in a pipeline for atomicity
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, self.window_seconds)
        results = pipe.execute()

        new_count: int = int(results[0])
        logger.debug(f"Rate limit increment for {key}: {new_count}")

        return new_count

    async def check_and_increment(
        self,
        key_type: str,
        identifier: uuid.UUID | str,
        max_requests: int,
    ) -> dict[str, int]:
        """Check rate limit and increment counter atomically.

        This combines check_rate_limit and increment for efficiency.

        Args:
            key_type: Type of rate limit (e.g., "chat", "api")
            identifier: Unique identifier (e.g., patient_id)
            max_requests: Maximum requests allowed in the window

        Returns:
            Dict with current_count, remaining, and reset_time

        Raises:
            RateLimitExceeded: If rate limit is exceeded
        """
        key = self._make_key(key_type, str(identifier))

        # Use a pipeline for atomicity
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, self.window_seconds)
        pipe.ttl(key)
        results = pipe.execute()

        new_count = results[0]
        ttl = results[2]
        reset_time = max(0, ttl) if ttl > 0 else self.window_seconds

        if new_count > max_requests:
            # We already incremented, so remaining is 0
            raise RateLimitExceeded(
                f"Rate limit exceeded. Max {max_requests} requests per {self.window_seconds} seconds.",
                remaining=0,
                reset_time=reset_time,
            )

        remaining = max_requests - new_count

        return {
            "current_count": new_count,
            "remaining": remaining,
            "reset_time": reset_time,
        }

    async def get_usage(
        self,
        key_type: str,
        identifier: uuid.UUID | str,
    ) -> dict[str, int]:
        """Get current usage without incrementing.

        Args:
            key_type: Type of rate limit (e.g., "chat", "api")
            identifier: Unique identifier (e.g., patient_id)

        Returns:
            Dict with current_count and reset_time
        """
        key = self._make_key(key_type, str(identifier))

        pipe = self.redis.pipeline()
        pipe.get(key)
        pipe.ttl(key)
        results = pipe.execute()

        current = results[0]
        ttl = results[1]

        return {
            "current_count": int(current) if current else 0,
            "reset_time": max(0, ttl) if ttl > 0 else 0,
        }

    async def reset(
        self,
        key_type: str,
        identifier: uuid.UUID | str,
    ) -> bool:
        """Reset the counter for an identifier.

        Args:
            key_type: Type of rate limit (e.g., "chat", "api")
            identifier: Unique identifier (e.g., patient_id)

        Returns:
            True if key was deleted, False if it didn't exist
        """
        key = self._make_key(key_type, str(identifier))
        deleted = self.redis.delete(key)
        return deleted > 0


class ChatRateLimiter:
    """Specialized rate limiter for chat endpoint.

    Provides a simpler interface specifically for chat rate limiting.
    """

    RATE_LIMIT_TYPE = "chat"

    def __init__(
        self,
        rate_limiter: RateLimiter | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Initialize chat rate limiter.

        Args:
            rate_limiter: Base rate limiter. Creates new one if None.
            settings: Application settings.
        """
        self.settings = settings or get_settings()
        self._rate_limiter = rate_limiter or RateLimiter(settings=self.settings)

    @property
    def max_requests(self) -> int:
        """Get maximum chat requests per hour from settings."""
        return self.settings.chat_rate_limit_per_hour

    async def check_and_consume(
        self,
        patient_id: uuid.UUID,
    ) -> dict[str, int]:
        """Check rate limit and consume one request.

        Args:
            patient_id: The patient's UUID

        Returns:
            Dict with current_count, remaining, and reset_time

        Raises:
            RateLimitExceeded: If rate limit is exceeded
        """
        return await self._rate_limiter.check_and_increment(
            key_type=self.RATE_LIMIT_TYPE,
            identifier=patient_id,
            max_requests=self.max_requests,
        )

    async def get_remaining(
        self,
        patient_id: uuid.UUID,
    ) -> int:
        """Get remaining requests for a patient.

        Args:
            patient_id: The patient's UUID

        Returns:
            Number of remaining requests
        """
        usage = await self._rate_limiter.get_usage(
            key_type=self.RATE_LIMIT_TYPE,
            identifier=patient_id,
        )
        return max(0, self.max_requests - usage["current_count"])
