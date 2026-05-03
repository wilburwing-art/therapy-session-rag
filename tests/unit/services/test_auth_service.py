"""Tests for AuthService lockout, 2FA challenge, and session flows.

Focus: the lockout ledger on `users.failed_login_count` + `locked_until`,
and the 2FA branch of `authenticate_therapist` / `complete_totp_challenge`.
Uses a MagicMock(spec=User) with every field auth service touches filled
in to dodge the Pydantic/MagicMock pitfall noted in the task brief.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pyotp
import pytest
from cryptography.fernet import Fernet

from src.core.auth import hash_password
from src.core.crypto import encrypt_secret
from src.core.exceptions import UnauthorizedError
from src.models.db.user import User, UserRole
from src.services.auth_service import AuthService


@pytest.fixture
def test_settings() -> MagicMock:
    s = MagicMock()
    s.jwt_secret = "test-secret"
    s.jwt_algorithm = "HS256"
    s.jwt_access_token_ttl_seconds = 3600
    s.magic_link_ttl_seconds = 900
    s.lockout_threshold = 5
    s.lockout_duration_minutes = 15
    s.totp_challenge_ttl_seconds = 300
    s.totp_encryption_key = Fernet.generate_key().decode("utf-8")
    s.totp_issuer = "TherapyRAG-Test"
    return s


def _make_user(
    *,
    password: str = "correct-horse",
    failed_login_count: int = 0,
    locked_until: datetime | None = None,
    totp_enabled_at: datetime | None = None,
    totp_secret: str | None = None,
    role: UserRole = UserRole.THERAPIST,
) -> MagicMock:
    """Construct a User mock with every auth-service-touched field pre-set."""
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.organization_id = uuid.uuid4()
    u.email = "doc@example.com"
    u.role = role
    u.full_name = "Dr. Test"
    u.password_hash = hash_password(password)
    u.email_verified_at = None
    u.failed_login_count = failed_login_count
    u.locked_until = locked_until
    u.totp_secret = totp_secret
    u.totp_enabled_at = totp_enabled_at
    u.totp_pending_secret = None
    u.created_at = datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)
    u.updated_at = datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)
    return u


@pytest.fixture
def db_session() -> AsyncMock:
    """AsyncSession stub. `flush` is awaited."""
    return AsyncMock()


@pytest.fixture
def auth_service(db_session: AsyncMock, test_settings: MagicMock) -> AuthService:
    return AuthService(db_session, settings=test_settings)


class TestLockout:
    @pytest.mark.asyncio
    async def test_wrong_password_increments_counter(
        self,
        auth_service: AuthService,
        db_session: AsyncMock,
    ) -> None:
        user = _make_user(failed_login_count=2)
        auth_service.get_user_by_email = AsyncMock(return_value=user)

        with pytest.raises(UnauthorizedError):
            await auth_service.authenticate_therapist(user.email, "wrong-password")

        assert user.failed_login_count == 3
        assert user.locked_until is None
        db_session.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_wrong_password_at_threshold_triggers_lockout(
        self,
        auth_service: AuthService,
    ) -> None:
        """On the 5th consecutive wrong password: lock for 15min, reset counter."""
        user = _make_user(failed_login_count=4)
        auth_service.get_user_by_email = AsyncMock(return_value=user)

        before = datetime.now(UTC)
        with pytest.raises(UnauthorizedError):
            await auth_service.authenticate_therapist(user.email, "wrong")

        # Counter reset, lock applied ~15min from now.
        assert user.failed_login_count == 0
        assert user.locked_until is not None
        expected_min = before + timedelta(minutes=14)
        expected_max = datetime.now(UTC) + timedelta(minutes=16)
        assert expected_min <= user.locked_until <= expected_max

    @pytest.mark.asyncio
    async def test_locked_account_rejects_even_correct_password(
        self,
        auth_service: AuthService,
    ) -> None:
        """A lock is hard: correct password while locked still raises."""
        future = datetime.now(UTC) + timedelta(minutes=8)
        user = _make_user(locked_until=future)
        auth_service.get_user_by_email = AsyncMock(return_value=user)

        with pytest.raises(UnauthorizedError) as exc:
            await auth_service.authenticate_therapist(user.email, "correct-horse")

        # Message tells user how long to wait.
        assert "minutes" in str(exc.value.detail).lower()

    @pytest.mark.asyncio
    async def test_expired_lock_allows_login_with_correct_password(
        self,
        auth_service: AuthService,
    ) -> None:
        past = datetime.now(UTC) - timedelta(minutes=5)
        user = _make_user(locked_until=past, failed_login_count=2)
        auth_service.get_user_by_email = AsyncMock(return_value=user)

        result = await auth_service.authenticate_therapist(user.email, "correct-horse")

        user_out, token, expires_at, requires_2fa = result
        assert user_out is user
        assert isinstance(token, str) and token
        assert requires_2fa is False
        # Both counter and lock cleared on successful login.
        assert user.failed_login_count == 0
        assert user.locked_until is None

    @pytest.mark.asyncio
    async def test_correct_password_resets_counter(
        self,
        auth_service: AuthService,
    ) -> None:
        user = _make_user(failed_login_count=3)
        auth_service.get_user_by_email = AsyncMock(return_value=user)

        await auth_service.authenticate_therapist(user.email, "correct-horse")

        assert user.failed_login_count == 0
        assert user.locked_until is None


class TestTotpBranch:
    @pytest.mark.asyncio
    async def test_login_with_2fa_enabled_returns_challenge_token(
        self,
        auth_service: AuthService,
        test_settings: MagicMock,
    ) -> None:
        raw_secret = pyotp.random_base32()
        user = _make_user(
            totp_enabled_at=datetime.now(UTC),
            totp_secret=encrypt_secret(raw_secret, settings=test_settings),
        )
        auth_service.get_user_by_email = AsyncMock(return_value=user)

        user_out, token, expires_at, requires_2fa = await auth_service.authenticate_therapist(
            user.email, "correct-horse"
        )

        assert requires_2fa is True
        assert isinstance(token, str) and token
        # Challenge expiry ~5 min, not the full session TTL.
        window_max = datetime.now(UTC) + timedelta(
            seconds=test_settings.totp_challenge_ttl_seconds + 5
        )
        assert expires_at <= window_max

    @pytest.mark.asyncio
    async def test_complete_totp_challenge_returns_session_token(
        self,
        auth_service: AuthService,
        test_settings: MagicMock,
    ) -> None:
        raw_secret = pyotp.random_base32()
        user = _make_user(
            totp_enabled_at=datetime.now(UTC),
            totp_secret=encrypt_secret(raw_secret, settings=test_settings),
        )
        auth_service.get_user_by_email = AsyncMock(return_value=user)
        auth_service.get_user_by_id = AsyncMock(return_value=user)

        _, challenge, _, _ = await auth_service.authenticate_therapist(user.email, "correct-horse")

        user_out, session_token, _ = await auth_service.complete_totp_challenge(
            challenge_token=challenge,
            code=pyotp.TOTP(raw_secret).now(),
        )
        assert user_out is user
        assert isinstance(session_token, str) and session_token

    @pytest.mark.asyncio
    async def test_complete_totp_challenge_rejects_wrong_code(
        self,
        auth_service: AuthService,
        test_settings: MagicMock,
    ) -> None:
        raw_secret = pyotp.random_base32()
        user = _make_user(
            totp_enabled_at=datetime.now(UTC),
            totp_secret=encrypt_secret(raw_secret, settings=test_settings),
        )
        auth_service.get_user_by_email = AsyncMock(return_value=user)
        auth_service.get_user_by_id = AsyncMock(return_value=user)

        _, challenge, _, _ = await auth_service.authenticate_therapist(user.email, "correct-horse")

        with pytest.raises(UnauthorizedError):
            await auth_service.complete_totp_challenge(
                challenge_token=challenge,
                code="000000",
            )

    @pytest.mark.asyncio
    async def test_complete_totp_challenge_rejects_garbage_token(
        self, auth_service: AuthService
    ) -> None:
        with pytest.raises(UnauthorizedError):
            await auth_service.complete_totp_challenge(
                challenge_token="not-a-real-jwt",
                code="123456",
            )
