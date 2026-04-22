"""Tests for TotpService enrollment, activation, verification, and disable flows."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pyotp
import pytest
from cryptography.fernet import Fernet

from src.core.crypto import decrypt_secret, encrypt_secret
from src.core.exceptions import ConflictError, UnauthorizedError
from src.models.db.user import User, UserRole
from src.services.totp_service import TotpService


@pytest.fixture
def test_settings() -> MagicMock:
    """Settings stub using a real Fernet key so encrypt/decrypt works."""
    s = MagicMock()
    s.totp_encryption_key = Fernet.generate_key().decode("utf-8")
    s.totp_issuer = "TherapyRAG-Test"
    return s


def _make_user(
    *,
    totp_enabled_at: datetime | None = None,
    totp_secret: str | None = None,
    totp_pending_secret: str | None = None,
) -> MagicMock:
    """Create a User mock with all fields TotpService touches."""
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.organization_id = uuid.uuid4()
    u.email = "doc@example.com"
    u.role = UserRole.THERAPIST
    u.full_name = "Dr. Test"
    u.password_hash = "hashed"
    u.email_verified_at = None
    u.failed_login_count = 0
    u.locked_until = None
    u.totp_secret = totp_secret
    u.totp_enabled_at = totp_enabled_at
    u.totp_pending_secret = totp_pending_secret
    u.created_at = datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)
    u.updated_at = datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)
    return u


@pytest.fixture
def db_session() -> AsyncMock:
    """AsyncSession stub — flush is awaited, nothing else is exercised."""
    session = AsyncMock()
    return session


@pytest.fixture
def service(db_session: AsyncMock, test_settings: MagicMock) -> TotpService:
    return TotpService(db_session, settings=test_settings)


class TestEnroll:
    @pytest.mark.asyncio
    async def test_enroll_sets_pending_secret_and_returns_uri(
        self,
        service: TotpService,
        db_session: AsyncMock,
        test_settings: MagicMock,
    ) -> None:
        user = _make_user()
        service._auth_service.get_user_by_id = AsyncMock(return_value=user)

        uri, raw_secret = await service.enroll(user.id)

        # Raw secret is plaintext Base32; URI embeds it (URL-encoded);
        # user's pending column holds the encrypted form.
        assert uri.startswith("otpauth://totp/")
        assert "TherapyRAG-Test" in uri
        # Email is URL-encoded inside the otpauth label (@ → %40).
        assert "doc%40example.com" in uri
        assert len(raw_secret) == 32  # pyotp default
        assert user.totp_pending_secret is not None
        assert user.totp_pending_secret != raw_secret
        assert decrypt_secret(
            user.totp_pending_secret, settings=test_settings
        ) == raw_secret
        db_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_enroll_conflict_if_already_enabled(
        self, service: TotpService
    ) -> None:
        user = _make_user(totp_enabled_at=datetime.now(UTC))
        service._auth_service.get_user_by_id = AsyncMock(return_value=user)

        with pytest.raises(ConflictError):
            await service.enroll(user.id)

    @pytest.mark.asyncio
    async def test_enroll_overwrites_stale_pending(
        self,
        service: TotpService,
        test_settings: MagicMock,
    ) -> None:
        old = encrypt_secret("OLDSECRET", settings=test_settings)
        user = _make_user(totp_pending_secret=old)
        service._auth_service.get_user_by_id = AsyncMock(return_value=user)

        _, raw_secret = await service.enroll(user.id)

        assert user.totp_pending_secret != old
        assert decrypt_secret(
            user.totp_pending_secret, settings=test_settings
        ) == raw_secret


class TestActivate:
    @pytest.mark.asyncio
    async def test_activate_promotes_pending_to_active(
        self,
        service: TotpService,
        db_session: AsyncMock,
        test_settings: MagicMock,
    ) -> None:
        raw = pyotp.random_base32()
        encrypted = encrypt_secret(raw, settings=test_settings)
        user = _make_user(totp_pending_secret=encrypted)
        service._auth_service.get_user_by_id = AsyncMock(return_value=user)

        current_code = pyotp.TOTP(raw).now()
        await service.activate(user.id, current_code)

        assert user.totp_secret == encrypted
        assert user.totp_pending_secret is None
        assert user.totp_enabled_at is not None
        db_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_activate_rejects_wrong_code(
        self,
        service: TotpService,
        test_settings: MagicMock,
    ) -> None:
        raw = pyotp.random_base32()
        encrypted = encrypt_secret(raw, settings=test_settings)
        user = _make_user(totp_pending_secret=encrypted)
        service._auth_service.get_user_by_id = AsyncMock(return_value=user)

        with pytest.raises(UnauthorizedError):
            await service.activate(user.id, "000000")

        # Pending secret remains — activation was a no-op on failure.
        assert user.totp_pending_secret == encrypted
        assert user.totp_secret is None
        assert user.totp_enabled_at is None

    @pytest.mark.asyncio
    async def test_activate_conflict_if_no_pending(
        self, service: TotpService
    ) -> None:
        user = _make_user()  # no pending secret
        service._auth_service.get_user_by_id = AsyncMock(return_value=user)

        with pytest.raises(ConflictError):
            await service.activate(user.id, "123456")

    @pytest.mark.asyncio
    async def test_activate_conflict_if_already_enabled(
        self,
        service: TotpService,
        test_settings: MagicMock,
    ) -> None:
        raw = pyotp.random_base32()
        user = _make_user(
            totp_enabled_at=datetime.now(UTC),
            totp_pending_secret=encrypt_secret(raw, settings=test_settings),
        )
        service._auth_service.get_user_by_id = AsyncMock(return_value=user)

        with pytest.raises(ConflictError):
            await service.activate(user.id, pyotp.TOTP(raw).now())


class TestVerifyCode:
    def test_verify_valid_code(
        self, service: TotpService, test_settings: MagicMock
    ) -> None:
        raw = pyotp.random_base32()
        encrypted = encrypt_secret(raw, settings=test_settings)
        current = pyotp.TOTP(raw).now()

        assert service.verify_code(encrypted, current) is True

    def test_verify_wrong_code(
        self, service: TotpService, test_settings: MagicMock
    ) -> None:
        raw = pyotp.random_base32()
        encrypted = encrypt_secret(raw, settings=test_settings)

        assert service.verify_code(encrypted, "000000") is False

    def test_verify_none_secret_returns_false(self, service: TotpService) -> None:
        assert service.verify_code(None, "123456") is False

    def test_verify_empty_secret_returns_false(self, service: TotpService) -> None:
        assert service.verify_code("", "123456") is False

    def test_verify_malformed_cipher_returns_false(
        self, service: TotpService
    ) -> None:
        """Tampered/wrong-key ciphertext should fail closed, not raise."""
        assert service.verify_code("not-a-valid-cipher-string", "123456") is False


class TestDisable:
    @pytest.mark.asyncio
    async def test_disable_clears_totp_fields(
        self,
        service: TotpService,
        db_session: AsyncMock,
        test_settings: MagicMock,
    ) -> None:
        raw = pyotp.random_base32()
        encrypted = encrypt_secret(raw, settings=test_settings)
        user = _make_user(
            totp_secret=encrypted,
            totp_enabled_at=datetime.now(UTC),
        )
        service._auth_service.get_user_by_id = AsyncMock(return_value=user)

        await service.disable(user.id, pyotp.TOTP(raw).now())

        assert user.totp_secret is None
        assert user.totp_enabled_at is None
        assert user.totp_pending_secret is None
        db_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disable_rejects_wrong_code(
        self,
        service: TotpService,
        test_settings: MagicMock,
    ) -> None:
        raw = pyotp.random_base32()
        encrypted = encrypt_secret(raw, settings=test_settings)
        user = _make_user(
            totp_secret=encrypted,
            totp_enabled_at=datetime.now(UTC),
        )
        service._auth_service.get_user_by_id = AsyncMock(return_value=user)

        with pytest.raises(UnauthorizedError):
            await service.disable(user.id, "000000")

        # Nothing cleared.
        assert user.totp_secret == encrypted
        assert user.totp_enabled_at is not None

    @pytest.mark.asyncio
    async def test_disable_conflict_when_not_enabled(
        self, service: TotpService
    ) -> None:
        user = _make_user()  # no TOTP
        service._auth_service.get_user_by_id = AsyncMock(return_value=user)

        with pytest.raises(ConflictError):
            await service.disable(user.id, "123456")
