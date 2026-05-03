"""Password hashing and JWT utilities for human user authentication.

Distinct from src.core.security, which handles machine-to-machine API
keys. This module backs the therapist (email + password + JWT) and
patient (magic link + JWT) auth flows.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from src.core.config import Settings, get_settings

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

TokenAudience = Literal["therapist", "patient"]


class AuthError(Exception):
    """Authentication failure (bad password, bad token, expired token)."""


@dataclass
class TokenClaims:
    """Decoded JWT claims."""

    user_id: uuid.UUID
    organization_id: uuid.UUID
    audience: TokenAudience
    expires_at: datetime


def hash_password(plain_password: str) -> str:
    """Return a bcrypt hash for a plaintext password."""
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Return True if the plaintext password matches the stored hash."""
    return _pwd_context.verify(plain_password, password_hash)


def create_access_token(
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    audience: TokenAudience,
    settings: Settings | None = None,
    ttl_seconds: int | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, datetime]:
    """Mint a signed JWT for a user.

    Returns (token, expires_at). The audience field separates therapist
    sessions from single-patient magic-link sessions so a patient token
    can't be swapped in for a therapist token.
    """
    settings = settings or get_settings()
    ttl = ttl_seconds
    if ttl is None:
        ttl = (
            settings.jwt_access_token_ttl_seconds
            if audience == "therapist"
            else settings.magic_link_ttl_seconds
        )
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=ttl)

    claims: dict[str, Any] = {
        "sub": str(user_id),
        "org": str(organization_id),
        "aud": audience,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": secrets.token_urlsafe(8),
    }
    if extra_claims:
        claims.update(extra_claims)

    token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_at


def decode_access_token(
    token: str,
    expected_audience: TokenAudience,
    settings: Settings | None = None,
) -> TokenClaims:
    """Decode and validate a JWT. Raises AuthError on any failure."""
    settings = settings or get_settings()
    try:
        raw = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=expected_audience,
        )
    except JWTError as exc:
        raise AuthError(f"Invalid or expired token: {exc}") from exc

    try:
        user_id = uuid.UUID(raw["sub"])
        organization_id = uuid.UUID(raw["org"])
        expires_at = datetime.fromtimestamp(int(raw["exp"]), tz=UTC)
    except (KeyError, ValueError, TypeError) as exc:
        raise AuthError("Malformed token claims") from exc

    return TokenClaims(
        user_id=user_id,
        organization_id=organization_id,
        audience=expected_audience,
        expires_at=expires_at,
    )
