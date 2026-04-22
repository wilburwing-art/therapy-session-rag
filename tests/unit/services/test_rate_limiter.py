"""Tests for rate limiter service."""

import uuid
from unittest.mock import MagicMock

import pytest

from src.services.rate_limiter import (
    AuthRateLimiter,
    ChatRateLimiter,
    RateLimiter,
    RateLimitExceeded,
)


@pytest.fixture
def mock_redis() -> MagicMock:
    """Create mock Redis client."""
    return MagicMock()


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings."""
    settings = MagicMock()
    settings.redis_url = "redis://localhost:6379"
    settings.chat_rate_limit_per_hour = 20
    return settings


@pytest.fixture
def rate_limiter(mock_redis: MagicMock, mock_settings: MagicMock) -> RateLimiter:
    """Create rate limiter with mocks."""
    return RateLimiter(
        redis_client=mock_redis,
        settings=mock_settings,
        window_seconds=3600,
    )


class TestRateLimiter:
    """Tests for RateLimiter class."""

    def test_make_key(self, rate_limiter: RateLimiter) -> None:
        """Test key generation."""
        key = rate_limiter._make_key("chat", "test-id")
        assert key == "rate_limit:chat:test-id"

    def test_make_key_with_uuid(self, rate_limiter: RateLimiter) -> None:
        """Test key generation with UUID."""
        patient_id = uuid.uuid4()
        key = rate_limiter._make_key("chat", str(patient_id))
        assert f"rate_limit:chat:{patient_id}" == key

    @pytest.mark.asyncio
    async def test_check_rate_limit_under_limit(
        self,
        rate_limiter: RateLimiter,
        mock_redis: MagicMock,
    ) -> None:
        """Test check when under limit."""
        mock_redis.get.return_value = b"5"
        mock_redis.ttl.return_value = 1800

        result = await rate_limiter.check_rate_limit(
            key_type="chat",
            identifier="test-id",
            max_requests=20,
        )

        assert result["current_count"] == 5
        assert result["remaining"] == 15
        assert result["reset_time"] == 1800

    @pytest.mark.asyncio
    async def test_check_rate_limit_at_limit(
        self,
        rate_limiter: RateLimiter,
        mock_redis: MagicMock,
    ) -> None:
        """Test check when at limit."""
        mock_redis.get.return_value = b"20"
        mock_redis.ttl.return_value = 600

        with pytest.raises(RateLimitExceeded) as exc_info:
            await rate_limiter.check_rate_limit(
                key_type="chat",
                identifier="test-id",
                max_requests=20,
            )

        assert exc_info.value.remaining == 0
        assert exc_info.value.reset_time == 600

    @pytest.mark.asyncio
    async def test_check_rate_limit_no_key(
        self,
        rate_limiter: RateLimiter,
        mock_redis: MagicMock,
    ) -> None:
        """Test check when key doesn't exist."""
        mock_redis.get.return_value = None
        mock_redis.ttl.return_value = -2  # Key doesn't exist

        result = await rate_limiter.check_rate_limit(
            key_type="chat",
            identifier="test-id",
            max_requests=20,
        )

        assert result["current_count"] == 0
        assert result["remaining"] == 20
        assert result["reset_time"] == 3600

    @pytest.mark.asyncio
    async def test_increment(
        self,
        rate_limiter: RateLimiter,
        mock_redis: MagicMock,
    ) -> None:
        """Test incrementing counter."""
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [5, True]
        mock_redis.pipeline.return_value = mock_pipe

        result = await rate_limiter.increment(
            key_type="chat",
            identifier="test-id",
        )

        assert result == 5
        mock_pipe.incr.assert_called_once()
        mock_pipe.expire.assert_called_once_with(
            "rate_limit:chat:test-id",
            3600,
        )

    @pytest.mark.asyncio
    async def test_check_and_increment_under_limit(
        self,
        rate_limiter: RateLimiter,
        mock_redis: MagicMock,
    ) -> None:
        """Test check and increment when under limit."""
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [5, True, 1800]
        mock_redis.pipeline.return_value = mock_pipe

        result = await rate_limiter.check_and_increment(
            key_type="chat",
            identifier="test-id",
            max_requests=20,
        )

        assert result["current_count"] == 5
        assert result["remaining"] == 15
        assert result["reset_time"] == 1800

    @pytest.mark.asyncio
    async def test_check_and_increment_exceeds_limit(
        self,
        rate_limiter: RateLimiter,
        mock_redis: MagicMock,
    ) -> None:
        """Test check and increment when exceeding limit."""
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [21, True, 600]  # Over limit
        mock_redis.pipeline.return_value = mock_pipe

        with pytest.raises(RateLimitExceeded) as exc_info:
            await rate_limiter.check_and_increment(
                key_type="chat",
                identifier="test-id",
                max_requests=20,
            )

        assert exc_info.value.remaining == 0
        assert exc_info.value.reset_time == 600

    @pytest.mark.asyncio
    async def test_get_usage(
        self,
        rate_limiter: RateLimiter,
        mock_redis: MagicMock,
    ) -> None:
        """Test getting usage without incrementing."""
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [b"10", 1500]
        mock_redis.pipeline.return_value = mock_pipe

        result = await rate_limiter.get_usage(
            key_type="chat",
            identifier="test-id",
        )

        assert result["current_count"] == 10
        assert result["reset_time"] == 1500

    @pytest.mark.asyncio
    async def test_get_usage_no_key(
        self,
        rate_limiter: RateLimiter,
        mock_redis: MagicMock,
    ) -> None:
        """Test getting usage when key doesn't exist."""
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [None, -2]
        mock_redis.pipeline.return_value = mock_pipe

        result = await rate_limiter.get_usage(
            key_type="chat",
            identifier="test-id",
        )

        assert result["current_count"] == 0
        assert result["reset_time"] == 0

    @pytest.mark.asyncio
    async def test_reset(
        self,
        rate_limiter: RateLimiter,
        mock_redis: MagicMock,
    ) -> None:
        """Test resetting counter."""
        mock_redis.delete.return_value = 1

        result = await rate_limiter.reset(
            key_type="chat",
            identifier="test-id",
        )

        assert result is True
        mock_redis.delete.assert_called_once_with("rate_limit:chat:test-id")

    @pytest.mark.asyncio
    async def test_reset_nonexistent(
        self,
        rate_limiter: RateLimiter,
        mock_redis: MagicMock,
    ) -> None:
        """Test resetting nonexistent counter."""
        mock_redis.delete.return_value = 0

        result = await rate_limiter.reset(
            key_type="chat",
            identifier="test-id",
        )

        assert result is False


class TestChatRateLimiter:
    """Tests for ChatRateLimiter class."""

    @pytest.fixture
    def chat_rate_limiter(
        self,
        mock_redis: MagicMock,
        mock_settings: MagicMock,
    ) -> ChatRateLimiter:
        """Create chat rate limiter with mocks."""
        base_limiter = RateLimiter(
            redis_client=mock_redis,
            settings=mock_settings,
        )
        return ChatRateLimiter(
            rate_limiter=base_limiter,
            settings=mock_settings,
        )

    def test_max_requests_from_settings(
        self,
        chat_rate_limiter: ChatRateLimiter,
    ) -> None:
        """Test max requests comes from settings."""
        assert chat_rate_limiter.max_requests == 20

    @pytest.mark.asyncio
    async def test_check_and_consume_success(
        self,
        chat_rate_limiter: ChatRateLimiter,
        mock_redis: MagicMock,
    ) -> None:
        """Test successful check and consume."""
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [1, True, 3600]
        mock_redis.pipeline.return_value = mock_pipe

        patient_id = uuid.uuid4()
        result = await chat_rate_limiter.check_and_consume(patient_id)

        assert result["current_count"] == 1
        assert result["remaining"] == 19

    @pytest.mark.asyncio
    async def test_check_and_consume_exceeded(
        self,
        chat_rate_limiter: ChatRateLimiter,
        mock_redis: MagicMock,
    ) -> None:
        """Test check and consume when exceeded."""
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [21, True, 600]
        mock_redis.pipeline.return_value = mock_pipe

        patient_id = uuid.uuid4()

        with pytest.raises(RateLimitExceeded):
            await chat_rate_limiter.check_and_consume(patient_id)

    @pytest.mark.asyncio
    async def test_get_remaining(
        self,
        chat_rate_limiter: ChatRateLimiter,
        mock_redis: MagicMock,
    ) -> None:
        """Test getting remaining requests."""
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [b"5", 1800]
        mock_redis.pipeline.return_value = mock_pipe

        patient_id = uuid.uuid4()
        remaining = await chat_rate_limiter.get_remaining(patient_id)

        assert remaining == 15

    @pytest.mark.asyncio
    async def test_get_remaining_no_usage(
        self,
        chat_rate_limiter: ChatRateLimiter,
        mock_redis: MagicMock,
    ) -> None:
        """Test getting remaining when no usage."""
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [None, -2]
        mock_redis.pipeline.return_value = mock_pipe

        patient_id = uuid.uuid4()
        remaining = await chat_rate_limiter.get_remaining(patient_id)

        assert remaining == 20


class TestRateLimitExceeded:
    """Tests for RateLimitExceeded exception."""

    def test_exception_attributes(self) -> None:
        """Test exception has correct attributes."""
        exc = RateLimitExceeded(
            "Rate limit exceeded",
            remaining=0,
            reset_time=1800,
        )

        assert str(exc) == "Rate limit exceeded"
        assert exc.remaining == 0
        assert exc.reset_time == 1800

    def test_exception_defaults(self) -> None:
        """Test exception default values."""
        exc = RateLimitExceeded("Rate limit exceeded")

        assert exc.remaining == 0
        assert exc.reset_time == 0


class TestAuthRateLimiter:
    """Tests for AuthRateLimiter class."""

    @pytest.fixture
    def auth_limiter(
        self,
        mock_redis: MagicMock,
        mock_settings: MagicMock,
    ) -> AuthRateLimiter:
        """Create an auth rate limiter sharing a single mock Redis pipeline.

        Every action category gets its own RateLimiter under the hood;
        they all share the mocked client passed here, so individual tests
        can configure pipeline return values once and reuse them across
        all three categories.
        """
        return AuthRateLimiter(
            settings=mock_settings,
            redis_client=mock_redis,
        )

    @pytest.mark.asyncio
    async def test_check_login_allows_under_ip_and_email_limits(
        self,
        auth_limiter: AuthRateLimiter,
        mock_redis: MagicMock,
    ) -> None:
        """Under both limits — no exception raised."""
        mock_pipe = MagicMock()
        # First call (IP bucket): count=1, ttl=60; second (email bucket):
        # count=1, ttl=60. Since AuthRateLimiter reuses one RateLimiter,
        # execute() is called twice.
        mock_pipe.execute.side_effect = [
            [1, True, 60],
            [1, True, 60],
        ]
        mock_redis.pipeline.return_value = mock_pipe

        await auth_limiter.check_login("1.2.3.4", "doc@example.com")

        assert mock_pipe.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_check_login_trips_ip_limit(
        self,
        auth_limiter: AuthRateLimiter,
        mock_redis: MagicMock,
    ) -> None:
        """IP exceeded → RateLimitExceeded before email is touched."""
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [11, True, 45]  # 11 > IP_MAX of 10
        mock_redis.pipeline.return_value = mock_pipe

        with pytest.raises(RateLimitExceeded) as exc:
            await auth_limiter.check_login("1.2.3.4", "doc@example.com")

        assert exc.value.reset_time == 45

    @pytest.mark.asyncio
    async def test_check_login_trips_email_limit(
        self,
        auth_limiter: AuthRateLimiter,
        mock_redis: MagicMock,
    ) -> None:
        """IP under, email over → still raises (on the email step)."""
        mock_pipe = MagicMock()
        mock_pipe.execute.side_effect = [
            [1, True, 60],  # IP under
            [6, True, 30],  # email 6 > EMAIL_MAX of 5
        ]
        mock_redis.pipeline.return_value = mock_pipe

        with pytest.raises(RateLimitExceeded) as exc:
            await auth_limiter.check_login("1.2.3.4", "doc@example.com")

        assert exc.value.reset_time == 30

    @pytest.mark.asyncio
    async def test_check_login_normalizes_email_for_key(
        self,
        auth_limiter: AuthRateLimiter,
        mock_redis: MagicMock,
    ) -> None:
        """Email casing/whitespace must not bypass the email limit."""
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [1, True, 60]
        mock_redis.pipeline.return_value = mock_pipe

        await auth_limiter.check_login("1.2.3.4", "  DOC@Example.com  ")
        # Inspect the keys that were passed to incr — lowercased+stripped.
        call_args = [c.args for c in mock_pipe.incr.call_args_list]
        keys = [a[0] for a in call_args]
        assert any("doc@example.com" in k for k in keys)
        assert not any("DOC@Example.com" in k for k in keys)

    @pytest.mark.asyncio
    async def test_check_registration_under_limit(
        self,
        auth_limiter: AuthRateLimiter,
        mock_redis: MagicMock,
    ) -> None:
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [3, True, 2400]  # under 5/hour
        mock_redis.pipeline.return_value = mock_pipe

        await auth_limiter.check_registration("1.2.3.4")

    @pytest.mark.asyncio
    async def test_check_registration_over_limit(
        self,
        auth_limiter: AuthRateLimiter,
        mock_redis: MagicMock,
    ) -> None:
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [6, True, 1200]  # over 5/hour
        mock_redis.pipeline.return_value = mock_pipe

        with pytest.raises(RateLimitExceeded):
            await auth_limiter.check_registration("1.2.3.4")

    @pytest.mark.asyncio
    async def test_check_password_reset_under_limit(
        self,
        auth_limiter: AuthRateLimiter,
        mock_redis: MagicMock,
    ) -> None:
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [2, True, 1800]
        mock_redis.pipeline.return_value = mock_pipe

        await auth_limiter.check_password_reset("doc@example.com")

    @pytest.mark.asyncio
    async def test_check_password_reset_over_limit(
        self,
        auth_limiter: AuthRateLimiter,
        mock_redis: MagicMock,
    ) -> None:
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [4, True, 1200]  # over 3/hour
        mock_redis.pipeline.return_value = mock_pipe

        with pytest.raises(RateLimitExceeded):
            await auth_limiter.check_password_reset("doc@example.com")

    @pytest.mark.asyncio
    async def test_check_password_reset_uses_normalized_email(
        self,
        auth_limiter: AuthRateLimiter,
        mock_redis: MagicMock,
    ) -> None:
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [1, True, 3600]
        mock_redis.pipeline.return_value = mock_pipe

        await auth_limiter.check_password_reset("  DOC@Example.com  ")
        call_args = [c.args for c in mock_pipe.incr.call_args_list]
        keys = [a[0] for a in call_args]
        assert any("doc@example.com" in k for k in keys)
