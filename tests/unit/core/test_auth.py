"""Tests for password hashing and JWT utilities."""

import time
import uuid
from datetime import UTC, datetime

import pytest

from src.core.auth import (
    AuthError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from src.core.config import Settings


def _test_settings() -> Settings:
    return Settings(
        database_url="postgresql://user:pass@localhost/test",  # type: ignore[arg-type]
        redis_url="redis://localhost:6379",  # type: ignore[arg-type]
        jwt_secret="test-secret-for-auth-unit-tests",
        jwt_algorithm="HS256",
        jwt_access_token_ttl_seconds=3600,
        magic_link_ttl_seconds=600,
    )


def test_hash_and_verify_password_roundtrip() -> None:
    password = "correct horse battery staple"
    digest = hash_password(password)
    assert digest != password
    assert verify_password(password, digest) is True
    assert verify_password("wrong password", digest) is False


def test_hash_password_generates_different_salts() -> None:
    password = "same-password"
    assert hash_password(password) != hash_password(password)


def test_create_and_decode_therapist_token() -> None:
    settings = _test_settings()
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()

    token, expires_at = create_access_token(
        user_id=user_id,
        organization_id=org_id,
        audience="therapist",
        settings=settings,
    )
    assert isinstance(token, str)
    assert expires_at > datetime.now(UTC)

    claims = decode_access_token(token, expected_audience="therapist", settings=settings)
    assert claims.user_id == user_id
    assert claims.organization_id == org_id
    assert claims.audience == "therapist"


def test_decode_rejects_wrong_audience() -> None:
    settings = _test_settings()
    token, _ = create_access_token(
        user_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        audience="patient",
        settings=settings,
    )
    with pytest.raises(AuthError):
        decode_access_token(token, expected_audience="therapist", settings=settings)


def test_decode_rejects_expired_token() -> None:
    settings = _test_settings()
    token, _ = create_access_token(
        user_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        audience="therapist",
        settings=settings,
        ttl_seconds=1,
    )
    time.sleep(2)
    with pytest.raises(AuthError):
        decode_access_token(token, expected_audience="therapist", settings=settings)


def test_decode_rejects_tampered_token() -> None:
    settings = _test_settings()
    token, _ = create_access_token(
        user_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        audience="therapist",
        settings=settings,
    )
    tampered = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    with pytest.raises(AuthError):
        decode_access_token(tampered, expected_audience="therapist", settings=settings)
