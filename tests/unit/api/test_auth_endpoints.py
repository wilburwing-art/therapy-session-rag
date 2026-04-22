"""Unit tests for Auth API endpoints.

These tests mount the auth router into an isolated FastAPI app and use
dependency overrides to swap out the real service layer. The point is
to catch wiring bugs (response model mismatches, status codes, missing
dependencies) without needing Postgres, Redis, or outbound email.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.dependencies import (
    get_api_key_auth,
    get_current_patient,
    get_current_therapist,
)
from src.api.v1.endpoints.auth import (
    get_auth_rate_limiter,
    get_auth_service,
    get_email_service,
    get_magic_link_service,
    get_totp_service,
    router,
)
from src.core.config import Settings, get_settings
from src.core.database import get_db_session
from src.core.exceptions import ConflictError, UnauthorizedError, setup_exception_handlers
from src.models.db.user import User, UserRole
from src.services.email_service import EmailResult, EmailServiceError
from src.services.rate_limiter import RateLimitExceeded


def _make_user(
    user_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
    email: str = "doc@example.com",
    role: UserRole = UserRole.THERAPIST,
    full_name: str | None = "Dr. Test",
    email_verified_at: datetime | None = None,
    totp_enabled_at: datetime | None = None,
) -> MagicMock:
    """Create a mock User with every field Pydantic response models read."""
    user = MagicMock(spec=User)
    user.id = user_id or uuid.uuid4()
    user.organization_id = org_id or uuid.uuid4()
    user.email = email
    user.role = role
    user.full_name = full_name
    user.email_verified_at = email_verified_at
    user.password_hash = "hashed"
    user.failed_login_count = 0
    user.locked_until = None
    user.totp_secret = None
    user.totp_enabled_at = totp_enabled_at
    user.totp_pending_secret = None
    user.created_at = datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)
    user.updated_at = datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)
    return user


@pytest.fixture
def test_settings() -> Settings:
    """Settings with secure=False so TestClient accepts cookies over http."""
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/d",
        redis_url="redis://localhost:6379/0",
        jwt_cookie_secure=False,
    )


@pytest.fixture
def mock_auth_service() -> MagicMock:
    """Mock AuthService with common methods preset as AsyncMock."""
    svc = MagicMock()
    svc.authenticate_therapist = AsyncMock()
    svc.register_practice = AsyncMock()
    svc.request_password_reset = AsyncMock()
    svc.confirm_password_reset = AsyncMock()
    svc.request_email_verification = AsyncMock()
    svc.confirm_email_verification = AsyncMock()
    svc.get_user_by_id = AsyncMock()
    return svc


@pytest.fixture
def mock_magic_link_service() -> MagicMock:
    svc = MagicMock()
    svc.issue_link = AsyncMock()
    svc.consume_link = AsyncMock()
    return svc


@pytest.fixture
def mock_totp_service() -> MagicMock:
    svc = MagicMock()
    svc.enroll = AsyncMock()
    svc.activate = AsyncMock()
    svc.disable = AsyncMock()
    svc.verify_code = MagicMock(return_value=True)
    return svc


@pytest.fixture
def mock_auth_rate_limiter() -> MagicMock:
    """Rate limiter that allows every call unless a test overrides it."""
    limiter = MagicMock()
    limiter.check_login = AsyncMock(return_value=None)
    limiter.check_registration = AsyncMock(return_value=None)
    limiter.check_password_reset = AsyncMock(return_value=None)
    return limiter


@pytest.fixture
def mock_email_service() -> MagicMock:
    svc = MagicMock()
    svc.send_email_verification = MagicMock(
        return_value=EmailResult(delivered=True, provider_id="em_1")
    )
    svc.send_magic_link = MagicMock(
        return_value=EmailResult(delivered=True, provider_id="em_1")
    )
    svc.send_password_reset = MagicMock(
        return_value=EmailResult(delivered=True, provider_id="em_1")
    )
    return svc


@pytest.fixture
def mock_auth_context() -> MagicMock:
    ctx = MagicMock()
    ctx.api_key_id = uuid.uuid4()
    ctx.organization_id = uuid.uuid4()
    ctx.api_key_name = "test"
    return ctx


@pytest.fixture
def therapist_user() -> MagicMock:
    return _make_user(role=UserRole.THERAPIST)


@pytest.fixture
def patient_user() -> MagicMock:
    return _make_user(role=UserRole.PATIENT, email="pt@example.com", full_name="Pat")


@pytest.fixture
def app(
    mock_auth_service: MagicMock,
    mock_magic_link_service: MagicMock,
    mock_email_service: MagicMock,
    mock_auth_context: MagicMock,
    mock_totp_service: MagicMock,
    mock_auth_rate_limiter: MagicMock,
    therapist_user: MagicMock,
    patient_user: MagicMock,
    test_settings: Settings,
) -> FastAPI:
    test_app = FastAPI()
    setup_exception_handlers(test_app)
    test_app.include_router(router, prefix="/auth")

    test_app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    test_app.dependency_overrides[get_api_key_auth] = lambda: mock_auth_context
    test_app.dependency_overrides[get_auth_service] = lambda: mock_auth_service
    test_app.dependency_overrides[get_magic_link_service] = lambda: mock_magic_link_service
    test_app.dependency_overrides[get_email_service] = lambda: mock_email_service
    test_app.dependency_overrides[get_totp_service] = lambda: mock_totp_service
    test_app.dependency_overrides[get_auth_rate_limiter] = lambda: mock_auth_rate_limiter
    test_app.dependency_overrides[get_settings] = lambda: test_settings
    test_app.dependency_overrides[get_current_therapist] = lambda: therapist_user
    test_app.dependency_overrides[get_current_patient] = lambda: patient_user

    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


class TestLogin:
    def test_login_success_sets_session_cookie(
        self,
        client: TestClient,
        mock_auth_service: MagicMock,
        therapist_user: MagicMock,
    ) -> None:
        expires_at = datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC)
        mock_auth_service.authenticate_therapist.return_value = (
            therapist_user,
            "jwt.token.value",
            expires_at,
            False,  # requires_2fa
        )

        response = client.post(
            "/auth/login",
            json={"email": "doc@example.com", "password": "correct-horse"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["user_id"] == str(therapist_user.id)
        assert body["organization_id"] == str(therapist_user.organization_id)
        assert body["email"] == therapist_user.email
        assert body["full_name"] == therapist_user.full_name
        assert body["expires_at"].startswith("2026-04-21T12:00:00")
        assert "therapyrag_session" in response.cookies
        assert response.cookies["therapyrag_session"] == "jwt.token.value"
        # Paired CSRF cookie is set alongside the session.
        assert "therapyrag_csrf" in response.cookies

    def test_login_bad_password_returns_401(
        self,
        client: TestClient,
        mock_auth_service: MagicMock,
    ) -> None:
        mock_auth_service.authenticate_therapist.side_effect = UnauthorizedError(
            "Invalid email or password"
        )

        response = client.post(
            "/auth/login",
            json={"email": "doc@example.com", "password": "wrong"},
        )

        assert response.status_code == 401
        assert "therapyrag_session" not in response.cookies


class TestRegister:
    def test_register_success_returns_201_and_practice_name(
        self,
        client: TestClient,
        mock_auth_service: MagicMock,
        mock_email_service: MagicMock,
        therapist_user: MagicMock,
    ) -> None:
        expires_at = datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC)
        mock_auth_service.register_practice.return_value = (
            therapist_user,
            "new.jwt.token",
            expires_at,
        )
        mock_auth_service.request_email_verification.return_value = "verify-token-abc"

        response = client.post(
            "/auth/register",
            json={
                "email": "new@example.com",
                "password": "secure-pass-1",
                "full_name": "Dr. New",
                "practice_name": "New Practice",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["user_id"] == str(therapist_user.id)
        assert body["practice_name"] == "New Practice"
        assert body["email"] == therapist_user.email
        assert "therapyrag_session" in response.cookies
        assert response.cookies["therapyrag_session"] == "new.jwt.token"
        # Verification email must have been dispatched.
        mock_email_service.send_email_verification.assert_called_once()
        _, kwargs = mock_email_service.send_email_verification.call_args
        assert kwargs["to_email"] == therapist_user.email
        assert "verify-token-abc" in kwargs["verification_url"]

    def test_register_email_send_failure_does_not_fail_signup(
        self,
        client: TestClient,
        mock_auth_service: MagicMock,
        mock_email_service: MagicMock,
        therapist_user: MagicMock,
    ) -> None:
        mock_auth_service.register_practice.return_value = (
            therapist_user,
            "new.jwt.token",
            datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC),
        )
        mock_auth_service.request_email_verification.return_value = "tok"
        mock_email_service.send_email_verification.side_effect = EmailServiceError(
            "SMTP down"
        )

        response = client.post(
            "/auth/register",
            json={
                "email": "new@example.com",
                "password": "secure-pass-1",
                "full_name": "Dr. New",
                "practice_name": "New Practice",
            },
        )

        # Registration should still succeed even if the email send blew up.
        assert response.status_code == 201
        assert "therapyrag_session" in response.cookies


class TestLogout:
    def test_logout_clears_session_and_csrf_cookies(
        self, client: TestClient
    ) -> None:
        response = client.post("/auth/logout")
        assert response.status_code == 204
        set_cookie_headers = response.headers.get_list("set-cookie")
        # Two delete-cookie headers: session + csrf.
        cookie_names = " ".join(set_cookie_headers)
        assert "therapyrag_session=" in cookie_names
        assert "therapyrag_csrf=" in cookie_names
        # Empty value + Max-Age=0 is how Starlette deletes cookies.
        assert any('Max-Age=0' in h for h in set_cookie_headers)

    def test_patient_logout_clears_cookies(self, client: TestClient) -> None:
        response = client.post("/auth/patient/logout")
        assert response.status_code == 204
        set_cookie_headers = response.headers.get_list("set-cookie")
        cookie_names = " ".join(set_cookie_headers)
        assert "therapyrag_patient=" in cookie_names
        assert "therapyrag_csrf=" in cookie_names


class TestMe:
    def test_me_returns_therapist_identity(
        self,
        client: TestClient,
        therapist_user: MagicMock,
    ) -> None:
        response = client.get("/auth/me")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(therapist_user.id)
        assert body["organization_id"] == str(therapist_user.organization_id)
        assert body["email"] == therapist_user.email
        assert body["role"] == "therapist"
        assert body["full_name"] == therapist_user.full_name


class TestPasswordReset:
    def test_password_reset_request_always_202_for_unknown_user(
        self,
        client: TestClient,
        mock_auth_service: MagicMock,
        mock_email_service: MagicMock,
    ) -> None:
        # Service returns None for an unknown email.
        mock_auth_service.request_password_reset.return_value = None

        response = client.post(
            "/auth/password-reset-request",
            json={"email": "nobody@example.com"},
        )

        assert response.status_code == 202
        assert response.json() == {"sent": True}
        # No email dispatched when user doesn't exist.
        mock_email_service.send_password_reset.assert_not_called()

    def test_password_reset_request_also_202_when_user_exists(
        self,
        client: TestClient,
        mock_auth_service: MagicMock,
        mock_email_service: MagicMock,
    ) -> None:
        mock_auth_service.request_password_reset.return_value = "reset-token-xyz"

        response = client.post(
            "/auth/password-reset-request",
            json={"email": "doc@example.com"},
        )

        # Same response shape as the unknown-user case — must not leak
        # which emails are registered.
        assert response.status_code == 202
        assert response.json() == {"sent": True}
        mock_email_service.send_password_reset.assert_called_once()

    def test_password_reset_confirm_success_logs_user_in(
        self,
        client: TestClient,
        mock_auth_service: MagicMock,
        therapist_user: MagicMock,
    ) -> None:
        mock_auth_service.confirm_password_reset.return_value = therapist_user
        expires_at = datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC)
        mock_auth_service.authenticate_therapist.return_value = (
            therapist_user,
            "post.reset.jwt",
            expires_at,
            False,  # requires_2fa
        )

        response = client.post(
            "/auth/password-reset-confirm",
            json={"token": "reset-token-xyz", "new_password": "brand-new-pw-1"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["user_id"] == str(therapist_user.id)
        assert body["email"] == therapist_user.email
        assert "therapyrag_session" in response.cookies
        assert response.cookies["therapyrag_session"] == "post.reset.jwt"

    def test_password_reset_confirm_invalid_token_401(
        self,
        client: TestClient,
        mock_auth_service: MagicMock,
    ) -> None:
        mock_auth_service.confirm_password_reset.side_effect = UnauthorizedError(
            "Invalid or already-used reset link"
        )

        response = client.post(
            "/auth/password-reset-confirm",
            json={"token": "bad-token", "new_password": "brand-new-pw-1"},
        )

        assert response.status_code == 401


class TestEmailVerification:
    def test_verify_email_request_returns_202(
        self,
        client: TestClient,
        mock_auth_service: MagicMock,
        mock_email_service: MagicMock,
        therapist_user: MagicMock,
    ) -> None:
        mock_auth_service.request_email_verification.return_value = "tok-123"

        response = client.post("/auth/verify-email-request")

        assert response.status_code == 202
        assert response.json() == {"sent": True}
        mock_auth_service.request_email_verification.assert_awaited_once_with(
            therapist_user.id
        )
        mock_email_service.send_email_verification.assert_called_once()

    def test_verify_email_confirm_returns_current_user(
        self,
        client: TestClient,
        mock_auth_service: MagicMock,
    ) -> None:
        verified = _make_user(
            email="verified@example.com",
            email_verified_at=datetime(2026, 4, 21, 11, 0, 0, tzinfo=UTC),
        )
        mock_auth_service.confirm_email_verification.return_value = verified

        response = client.post(
            "/auth/verify-email-confirm",
            json={"token": "verify-token-abc"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(verified.id)
        assert body["email"] == "verified@example.com"
        assert body["role"] == "therapist"
        assert body["email_verified_at"] is not None


class TestMagicLink:
    def test_create_magic_link_returns_token_and_sends_email(
        self,
        client: TestClient,
        mock_magic_link_service: MagicMock,
        mock_auth_service: MagicMock,
        mock_email_service: MagicMock,
        patient_user: MagicMock,
    ) -> None:
        expires_at = datetime.now(UTC) + timedelta(minutes=15)
        mock_magic_link_service.issue_link.return_value = ("raw-magic-xyz", expires_at)
        mock_auth_service.get_user_by_id.return_value = patient_user

        response = client.post(
            "/auth/patient/magic-link",
            json={"patient_id": str(patient_user.id)},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["token"] == "raw-magic-xyz"
        assert "expires_at" in body
        mock_email_service.send_magic_link.assert_called_once()
        _, kwargs = mock_email_service.send_magic_link.call_args
        assert kwargs["to_email"] == patient_user.email
        assert "raw-magic-xyz" in kwargs["magic_link_url"]

    def test_redeem_magic_link_success_sets_patient_cookie(
        self,
        client: TestClient,
        mock_magic_link_service: MagicMock,
        patient_user: MagicMock,
    ) -> None:
        expires_at = datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC)
        mock_magic_link_service.consume_link.return_value = (
            patient_user,
            "patient.jwt.token",
            expires_at,
        )

        response = client.post(
            "/auth/patient/session",
            json={"token": "raw-magic-xyz"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["patient_id"] == str(patient_user.id)
        assert body["organization_id"] == str(patient_user.organization_id)
        assert "therapyrag_patient" in response.cookies
        assert response.cookies["therapyrag_patient"] == "patient.jwt.token"

    def test_redeem_magic_link_bad_token_returns_401(
        self,
        client: TestClient,
        mock_magic_link_service: MagicMock,
    ) -> None:
        mock_magic_link_service.consume_link.side_effect = UnauthorizedError(
            "Invalid or expired link"
        )

        response = client.post(
            "/auth/patient/session",
            json={"token": "bogus-token"},
        )

        assert response.status_code == 401
        assert "therapyrag_patient" not in response.cookies


class TestRegisterConflict:
    def test_register_duplicate_email_returns_409(
        self,
        client: TestClient,
        mock_auth_service: MagicMock,
    ) -> None:
        """Duplicate email raises ConflictError from the service — router must pass through."""
        mock_auth_service.register_practice.side_effect = ConflictError(
            detail="A user with this email already exists"
        )

        response = client.post(
            "/auth/register",
            json={
                "email": "dup@example.com",
                "password": "secure-pass-1",
                "full_name": "Dr. Dup",
                "practice_name": "Dup Practice",
            },
        )

        assert response.status_code == 409


class TestRateLimiting:
    def test_login_429_when_rate_limited(
        self,
        client: TestClient,
        mock_auth_rate_limiter: MagicMock,
    ) -> None:
        mock_auth_rate_limiter.check_login.side_effect = RateLimitExceeded(
            "too many", remaining=0, reset_time=42
        )

        response = client.post(
            "/auth/login",
            json={"email": "doc@example.com", "password": "whatever"},
        )

        assert response.status_code == 429

    def test_register_429_when_rate_limited(
        self,
        client: TestClient,
        mock_auth_rate_limiter: MagicMock,
    ) -> None:
        mock_auth_rate_limiter.check_registration.side_effect = RateLimitExceeded(
            "too many", remaining=0, reset_time=3000
        )

        response = client.post(
            "/auth/register",
            json={
                "email": "new@example.com",
                "password": "secure-pass-1",
                "full_name": "Dr. New",
                "practice_name": "New Practice",
            },
        )

        assert response.status_code == 429

    def test_password_reset_429_when_rate_limited(
        self,
        client: TestClient,
        mock_auth_rate_limiter: MagicMock,
        mock_email_service: MagicMock,
    ) -> None:
        mock_auth_rate_limiter.check_password_reset.side_effect = RateLimitExceeded(
            "too many", remaining=0, reset_time=1800
        )

        response = client.post(
            "/auth/password-reset-request",
            json={"email": "someone@example.com"},
        )

        assert response.status_code == 429
        mock_email_service.send_password_reset.assert_not_called()


class TestLoginWith2FA:
    def test_login_with_2fa_enabled_returns_challenge(
        self,
        client: TestClient,
        mock_auth_service: MagicMock,
        therapist_user: MagicMock,
    ) -> None:
        expires_at = datetime(2026, 4, 21, 12, 5, 0, tzinfo=UTC)
        mock_auth_service.authenticate_therapist.return_value = (
            therapist_user,
            "short.lived.challenge.jwt",
            expires_at,
            True,  # requires_2fa
        )

        response = client.post(
            "/auth/login",
            json={"email": "doc@example.com", "password": "correct-horse"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["requires_2fa"] is True
        assert body["challenge_token"] == "short.lived.challenge.jwt"
        # Critical: no session cookie on a 2FA challenge.
        assert "therapyrag_session" not in response.cookies

    def test_2fa_challenge_completes_and_sets_session_cookie(
        self,
        client: TestClient,
        mock_auth_service: MagicMock,
        therapist_user: MagicMock,
    ) -> None:
        expires_at = datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC)
        mock_auth_service.complete_totp_challenge = AsyncMock(
            return_value=(therapist_user, "final.session.jwt", expires_at)
        )

        response = client.post(
            "/auth/2fa/challenge",
            json={
                "challenge_token": "short.lived.challenge.jwt",
                "code": "123456",
            },
        )

        assert response.status_code == 200
        assert response.cookies["therapyrag_session"] == "final.session.jwt"
        assert "therapyrag_csrf" in response.cookies

    def test_2fa_challenge_invalid_code_returns_401(
        self,
        client: TestClient,
        mock_auth_service: MagicMock,
    ) -> None:
        mock_auth_service.complete_totp_challenge = AsyncMock(
            side_effect=UnauthorizedError("Invalid 2FA code")
        )

        response = client.post(
            "/auth/2fa/challenge",
            json={
                "challenge_token": "anything",
                "code": "000000",
            },
        )

        assert response.status_code == 401


class TestTwoFAEnrollmentEndpoints:
    def test_enroll_returns_provisioning_uri_and_secret(
        self,
        client: TestClient,
        mock_totp_service: MagicMock,
    ) -> None:
        mock_totp_service.enroll.return_value = (
            "otpauth://totp/TherapyRAG:doc@example.com?secret=ABC&issuer=TherapyRAG",
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567",
        )

        response = client.post("/auth/2fa/enroll")

        assert response.status_code == 200
        body = response.json()
        assert body["provisioning_uri"].startswith("otpauth://")
        assert body["secret"] == "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"

    def test_activate_200_on_success(
        self,
        client: TestClient,
        mock_totp_service: MagicMock,
    ) -> None:
        mock_totp_service.activate.return_value = None

        response = client.post("/auth/2fa/activate", json={"code": "123456"})

        assert response.status_code == 200
        assert response.json() == {"enabled": True}

    def test_activate_invalid_code_returns_401(
        self,
        client: TestClient,
        mock_totp_service: MagicMock,
    ) -> None:
        mock_totp_service.activate.side_effect = UnauthorizedError(
            "Invalid 2FA code"
        )

        response = client.post("/auth/2fa/activate", json={"code": "000000"})

        assert response.status_code == 401

    def test_disable_requires_correct_password(
        self,
        client: TestClient,
        mock_totp_service: MagicMock,
        therapist_user: MagicMock,
    ) -> None:
        """Wrong password: endpoint rejects with 401 before calling TotpService."""
        from src.core.auth import hash_password

        # Put a real argon2 hash on the user so verify_password runs
        # cleanly and returns False for the guessed password.
        therapist_user.password_hash = hash_password("actual-password")

        response = client.post(
            "/auth/2fa/disable",
            json={"code": "123456", "password": "guess"},
        )

        assert response.status_code == 401
        mock_totp_service.disable.assert_not_called()

    def test_disable_ok_with_correct_password(
        self,
        client: TestClient,
        mock_totp_service: MagicMock,
        therapist_user: MagicMock,
    ) -> None:
        from src.core.auth import hash_password

        therapist_user.password_hash = hash_password("actual-password")
        mock_totp_service.disable.return_value = None

        response = client.post(
            "/auth/2fa/disable",
            json={"code": "123456", "password": "actual-password"},
        )

        assert response.status_code == 200
        assert response.json() == {"enabled": False}
        mock_totp_service.disable.assert_awaited_once()
